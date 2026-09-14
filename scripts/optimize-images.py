#!/usr/bin/env python3
"""optimize-images.py — Asset-Optimierung für endlichyoga.de (Issue #14, perf-assets).

Optimiert die von index.html geladenen Bild-Assets verlustarm auf ~2x der
Anzeigegröße (Retina), damit das Ladegewicht der Seite von ~15,5 MB auf
unter 3 MB fällt. Dateinamen und -formate bleiben unverändert (HTML bleibt
gültig, sichtbar identisch).

Voraussetzungen: Python 3 + Pillow (getestet mit Pillow 12.3.0).

Verwendung:
    python3 scripts/optimize-images.py            # alle Dateien optimieren
    python3 scripts/optimize-images.py --dry-run  # nur anzeigen, was zu tun wäre

Idempotent: Jede Datei wird in-memory neu erzeugt und nur ersetzt, wenn sich
die Bytes tatsächlich ändern. Ein zweiter Lauf ist damit garantiert eine
Null-Operation (deterministische Encode-Ergebnisse).

Exit-Codes: 0 = Erfolg, 1 = Fehler (fehlende Datei, fehlende Pillow-Installation,
nicht lesbares Bild o. Ä.). Fehlerhafte Dateien werden übersprungen und am
Ende gemeldet.

--------------------------------------------------------------------------
Datei-Liste und Zielparameter (Scope perf-assets, Issue #14)
--------------------------------------------------------------------------
ANZEIGEGRÖSSEN (Quelle: index.html / css/style.css):
  contact_photo.png     w-96 = 384 px Anzeigebreite
  fuer_wen_ist_yoga.png w-4/6 in 1/2-Spalte, ~250-420 px je Viewport
  ueber_mich.png        w-4/6 in 1/2-Spalte, ~250-420 px je Viewport
  gallery/v2/*.jpg      ~90 % der Grid-Zelle (2-3 Spalten), ~250-380 px
  gallery_blob.png      28rem (w-1/2 sm:w-72) = max. 448 px Anzeige
  ueberzeug_dich.png    klein (698x740) — nur skalieren falls > 1200 px
  video_blob.png        20rem = 320 px Anzeige, Datei nur 11,7 KB

ZIELGRÖSSEN (dieses Script):
  * PNG-Fotos/-Blobs mit langer Kante > 1200 px werden auf ~800 px lange
    Kante skaliert (Retina-2x der Anzeige, s. o.), dann auf 256 Farben
    quantisiert.
  * JPEG-Galerie (1920x1080) wird auf 800 px Breite skaliert und mit
    Qualität ~80 progressiv+optimiert gespeichert.
  * PNGs unter 1200 px (ueberzeug_dich 698x740, video_blob 645x653) werden
    NICHT skaliert, sondern nur verlustfrei re-encodiert (optimize=True),
    falls das kleiner wird. video_blob.png ist mit 11,7 KB bereits minimal —
    es bleibt faktisch unverändert, wenn der verlustfreie Encode nicht
    kleiner ist.

QUANTISIERUNG & ALPHA (wichtige Design-Entscheidung):
  Alle betroffenen PNGs sind RGBA mit echter Transparenz (freigestellte
  Fotos / Blob-Formen mit weichen Kanten). Pillow 12 verbietet
  Image.Quantize.MEDIANCUT für RGBA-Bilder ("Fast Octree ... and
  libimagequant ... are the only valid methods for quantizing RGBA images").
  Ein Flatten auf RGB (weißer Grund) würde die weichen Kanten/Transparenz
  zerstören — nicht sichtbar identisch. Daher wird für Bilder MIT Alpha
  method=Image.Quantize.FASTOCTREE (256 Farben, FLOYDSTEINBERG-Dither)
  verwendet: Pillow schreibt dann ein P-Modus-PNG mit voller 256-Eintrag-
  tRNS-Tabelle, d. h. der Alpha-Kanal bleibt pro Pixel erhalten
  (gemessene mittlere Abweichung ~3/255 pro Kanal). Nur reine RGB-Bilder
  (kein Alpha) nutzen MEDIANCUT wie im Issue beschrieben.

NICHT angefasst (Marken/Sonderfälle, fremde Pakete):
  img/logo.png, img/facebook.png, img/instagram.png, img/mail.png,
  favicon.png (Marken-Icons), vid/banner.m4v (Paket perf-video #15).
--------------------------------------------------------------------------
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Dateien und Zielgröße (lange Kante bei PNG, Breite bei JPEG).
TARGET_MAX_EDGE = {
    # PNG-Fotos/-Blobs: auf ~800 px lange Kante skalieren (Retina-2x).
    "img/contact_photo.png": 800,      # 6580x6080, Anzeige 384 px (w-96)
    "img/fuer_wen_ist_yoga.png": 800,  # 8360x7111, Anzeige ~250-420 px
    "img/ueber_mich.png": 800,         # 7930x7181, Anzeige ~250-420 px
    "img/gallery_blob.png": 800,       # 6295x5560, Anzeige max. 448 px
    # JPEG-Galerie (1920x1080): Breite 800 px, Qualität ~80, progressiv.
    "img/gallery/v2/1.jpg": 800,
    "img/gallery/v2/2.jpg": 800,
    "img/gallery/v2/3.jpg": 800,
    "img/gallery/v2/4.jpg": 800,
    "img/gallery/v2/5.jpg": 800,
    "img/gallery/v2/6.jpg": 800,
    "img/gallery/v2/7.jpg": 800,
    "img/gallery/v2/8.jpg": 800,
    "img/gallery/v2/9.jpg": 800,
    # Kleine PNGs (<= 1200 px): nur verlustfrei optimieren, nicht skalieren.
    "img/ueberzeug_dich.png": 1200,    # 698x740 -> nur verlustfrei
    "img/video_blob.png": 1200,        # 645x653 -> nur verlustfrei
}

# Dateien, die NIE verändert werden (Marken-Icons & Favicon, fremde Pakete).
PROTECTED = {
    "img/logo.png",
    "img/facebook.png",
    "img/instagram.png",
    "img/mail.png",
    "favicon.png",
}

PNG_COLORS = 256          # 8-Bit-Palette
PNG_DITHER = None         # FLOYDSTEINBERG-Dither wird je Fall gesetzt
JPEG_QUALITY = 80         # ~80 laut Issue #14


def log(msg):
    print(msg)


def err(msg):
    print(f"ERROR: {msg}", file=sys.stderr)


def _has_alpha(im):
    """True, wenn das Bild einen echten (ggf. teils transparenten) Alpha-
    Kanal hat."""
    if im.mode in ("RGBA", "LA"):
        alpha = im.getchannel("A")
        return alpha.getextrema()[0] < 255
    if im.mode == "P":
        return "transparency" in im.info
    return False


def encode_png(im):
    """Quantisiert `im` (bereits skaliert) auf 256 Farben + optimize=True.
    Liefert PNG-Bytes. Erhält Alpha, wo vorhanden (s. Modul-Doku)."""
    from PIL import Image

    if im.mode in ("RGBA", "LA", "P") and _has_alpha(im):
        rgba = im.convert("RGBA") if im.mode != "RGBA" else im
        # FASTOCTREE ist die einzige Pillow-12-Methode für RGBA, die Alpha
        # erhält (MEDIANCUT wirft bei RGBA). Schreibt P-PNG mit tRNS[256].
        pal = rgba.quantize(
            colors=PNG_COLORS,
            method=Image.Quantize.FASTOCTREE,
            dither=Image.Dither.FLOYDSTEINBERG,
        )
    else:
        rgb = im.convert("RGB")
        pal = rgb.quantize(
            colors=PNG_COLORS,
            method=Image.Quantize.MEDIANCUT,
            dither=Image.Dither.FLOYDSTEINBERG,
        )
    import io
    buf = io.BytesIO()
    pal.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def optimize_png(rel, path, target_edge):
    """Skaliert (falls lange Kante > target_edge) und quantisiert. Fallback:
    verlustfreier Re-Encode, wenn das Bild bereits <= target_edge ist."""
    from PIL import Image

    im = Image.open(path)
    width, height = im.size
    longest = max(width, height)

    # Idempotenz: bereits quantisiertes (P-Modus) PNG im Zielbereich.
    if longest <= target_edge and im.mode == "P":
        return None, "unverändert (bereits optimiert)"

    if longest > target_edge:
        scale = target_edge / float(longest)
        new_size = (max(1, round(width * scale)),
                    max(1, round(height * scale)))
        im = im.resize(new_size, Image.LANCZOS)
        data = encode_png(im)
        action = "skaliert+quantisiert"
    else:
        # Bereits klein genug: verlustfreier Re-Encode (optimize=True);
        # übernehmen nur, wenn die Datei tatsächlich kleiner wird.
        import io
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        data = buf.getvalue()
        if len(data) >= os.path.getsize(path):
            return None, "unverändert (verlustfreier Encode ohne Gewinn)"
        action = "verlustfrei optimiert"

    if data == open(path, "rb").read():
        return None, "unverändert (bereits optimiert)"
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)
    return data, action


def optimize_jpeg(rel, path, target_width):
    """Skaliert auf target_width Breite, speichert progressiv + optimize."""
    from PIL import Image

    im = Image.open(path)
    width, height = im.size

    # Idempotenz: bereits progressiv gespeichertes JPEG im Zielbereich
    # (unser Encode setzt info['progressive']=True; Baseline-JPEGs nicht).
    if width <= target_width and im.info.get("progressive"):
        return None, "unverändert (bereits optimiert)"

    if im.mode != "RGB":
        im = im.convert("RGB")
    if width > target_width:
        new_height = max(1, round(height * (target_width / float(width))))
        im = im.resize((target_width, new_height), Image.LANCZOS)

    import io
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=JPEG_QUALITY,
            progressive=True, optimize=True)
    data = buf.getvalue()
    if data == open(path, "rb").read():
        return None, "unverändert (bereits optimiert)"
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)
    return data, "skaliert+JPEG-komprimiert"


def main():
    dry_run = "--dry-run" in sys.argv

    try:
        from PIL import Image  # noqa: F401 — Verfügbarkeit prüfen
    except ImportError:
        err("Pillow ist nicht installiert "
            "(benötigt: pip install Pillow; getestet mit 12.3.0).")
        return 1

    changed = 0
    errors = 0
    for rel, target in sorted(TARGET_MAX_EDGE.items()):
        path = os.path.join(REPO_ROOT, rel)
        if not os.path.exists(path):
            err(f"Datei fehlt: {rel}")
            errors += 1
            continue
        if rel in PROTECTED:
            err(f"{rel} ist geschützt (PROTECTED) — übersprungen.")
            errors += 1
            continue
        try:
            if rel.lower().endswith(".jpg"):
                if dry_run:
                    log(f"[dry-run] {rel} -> Breite {target} px, "
                        f"JPEG-Qualität {JPEG_QUALITY}")
                    continue
                _, action = optimize_jpeg(rel, path, target)
                log(f"{rel}: {action}")
            elif rel.lower().endswith(".png"):
                if dry_run:
                    log(f"[dry-run] {rel} -> max. {target} px Kante")
                    continue
                _, action = optimize_png(rel, path, target)
                log(f"{rel}: {action}")
            else:
                err(f"Unbekanntes Format: {rel}")
                errors += 1
                continue
            if _ is not None:
                changed += 1
        except Exception as e:  # noqa: BLE001 — sauberer Exit-Code gewollt
            err(f"{rel}: {e}")
            errors += 1

    log(f"\n{changed} Datei(en) geändert.")
    if errors:
        err(f"{errors} Fehler aufgetreten — Exit-Code 1.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
