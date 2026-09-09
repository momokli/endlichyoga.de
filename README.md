# endlichyoga.de

**endlichYoga – Yoga in Günzburg** · statische Website

Repo für die Website [endlichyoga.de](https://endlichyoga.de) — eine rein
statische Yoga-Website (HTML/CSS/JS, keine CMS, kein Build-Schritt). Das
Repository ist zugleich die **Single Source of Truth für die
Deploy-Infrastruktur** (CI/CD + Server-Setup), angelehnt an das bewährte
Muster aus [`MacMasus/mariusklimke.de`](https://github.com/MacMasus/mariusklimke.de).

## Architektur

```
Repo main (momokli/endlichyoga.de)
  │  push
  ▼
GitHub Actions  .github/workflows/deploy.yml
  ├─ Sanity-Check (index.html, impressum.html, datenschutz.html, css/style.css)
  ├─ publish 1:1-Kopie → `built`-Branch  (statische Seite — kein Build)
  └─ POST https://deploy.endlichyoga.de/deploy  (Bearer DEPLOY_TOKEN)
        │
        ▼
planet (Hetzner, systemd)
  ├─ endlichyoga-webhook.service  (webhook.py, 127.0.0.1:18794)
  │    └─ startet endlichyoga-deploy.service
  │         └─ deploy.sh (User `deploy`) lädt `built`-Tarball
  │              └─ rsync --delete → /opt/http/endlichyoga.de/
  ▼
Caddy (mellon-caddy) — endlichyoga.de, www.endlichyoga.de → Docroot
```

Der `built`-Branch ist eine automatisch erzeugte, force-gepushte 1:1-Kopie
von `main` — nie direkt bearbeiten.

## Verzeichnisstruktur

```
├── index.html            Startseite
├── impressum.html        Impressum
├── datenschutz.html      Datenschutz
├── css/style.css         Styles
├── fonts/                Webfonts (woff/woff2/ttf/eot/svg)
├── img/                  Bilder (inkl. gallery/v1, gallery/v2)
├── vid/banner.m4v        Video-Banner
├── favicon.png
├── .github/workflows/
│   ├── deploy.yml        CI/CD: `built`-Branch + Deploy-Webhook
│   └── healthcheck.yml   Stündlicher Erreichbarkeits-Check (Issue bei Downtime)
└── deploy/               Server-Setup für planet (systemd, webhook.py,
                          deploy.sh, provision.sh, Caddyfile-Snippet)
```

## Deploy-Ablauf

1. Push auf `main` → Workflow `.github/workflows/deploy.yml` läuft
   (auch manuell per `workflow_dispatch`).
2. Der Workflow publiziert den Stand 1:1 als `built`-Branch und ruft
   `https://deploy.endlichyoga.de/deploy` mit dem Secret `DEPLOY_TOKEN` auf.
3. Auf planet nimmt `webhook.py` (Port 18794) den Request entgegen und stößt
   `endlichyoga-deploy.service` an; `deploy.sh` lädt den `built`-Tarball und
   rsynct ihn in den Caddy-Docroot `/opt/http/endlichyoga.de`.

Details & Server-Einrichtung (planet, Tokens, systemd, Caddy, DNS-Cutover):
**[deploy/README.md](deploy/README.md)**.

Nützliche Workflows:
- [Deploy-Workflow](.github/workflows/deploy.yml)
- [Health-Check-Workflow](.github/workflows/healthcheck.yml)

## Lokale Entwicklung

Statische Seite: einfach die HTML-Dateien öffnen bzw. das Repo-Verzeichnis mit
einem beliebigen Static-Server ausliefern, z. B. `python3 -m http.server`.

> Hinweis: Dieses Repo enthält ausschließlich Infrastruktur- und
> Website-Dateien. Für Beiträge gilt: keine inhaltlichen Änderungen an der
> Website ohne separates Issue.
