#!/bin/bash
# provision.sh — installer for the endlichyoga.de deploy webhook on planet.
# Run as root on planet (the deploy target):
#
#     sudo bash deploy/provision.sh            # apply
#     sudo bash deploy/provision.sh --dry-run  # show what would happen
#
# NOTE: unlike mariusklimke.de (Ansible role), this repo ships the complete
# server half in deploy/ — provision.sh IS the provisioning path
# (dependency-free, idempotent).
#
# Idempotent: existing token is preserved, existing Caddy block is skipped.
# Purely additive — nothing existing is modified or removed.
#
# After this: set the printed token as GitHub repo secret `DEPLOY_TOKEN`
# and (Cutover, see deploy/README.md) point DNS at planet:
#   A deploy.endlichyoga.de -> 65.21.27.234
#   A endlichyoga.de, www.endlichyoga.de -> 65.21.27.234

set -euo pipefail

APP_DIR=/opt/endlichyoga-deploy
TOKEN_FILE=/etc/endlichyoga/deploy.token
DOCROOT=/opt/http/endlichyoga.de
CADDYFILE=/home/momo/Caddyfile
SNIPPET="$(cd "$(dirname "$0")" && pwd)/Caddyfile.endlichyoga.conf"
PORT=18794
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

run() {
  if [ "$DRY" = 1 ]; then echo "  [dry-run] $*"; else "$@"; fi
}

echo "== endlichyoga.de deploy webhook provisioning (planet) =="

# 1. App dir, receiver, deploy script (deploy.sh runs as user `deploy`)
run mkdir -p "$APP_DIR" /etc/endlichyoga
run install -m 0755 "$(dirname "$0")/webhook.py" "$APP_DIR/webhook.py"
run install -m 0755 "$(dirname "$0")/deploy.sh" "$APP_DIR/deploy.sh"
run chown deploy:deploy "$APP_DIR/deploy.sh"

# 2. Docroot, owned by user `deploy`
run mkdir -p "$DOCROOT"
run chown deploy:deploy "$DOCROOT"

# 3. Shared secret — preserve if already present
if [ -f "$TOKEN_FILE" ]; then
  echo "  token exists ($TOKEN_FILE) — preserved"
else
  TOKEN="$(openssl rand -hex 32)"
  run sh -c "umask 077; printf '%s' '$TOKEN' > '$TOKEN_FILE'"
  echo "  !! NEW TOKEN: $TOKEN"
  echo "  !! -> GitHub secret DEPLOY_TOKEN = $TOKEN"
fi

# 4. systemd units (+ drop-in with REPO/BRANCH for the deploy service)
run install -m 0644 "$(dirname "$0")/endlichyoga-webhook.service" /etc/systemd/system/
run install -m 0644 "$(dirname "$0")/endlichyoga-deploy.service" /etc/systemd/system/
run mkdir -p /etc/systemd/system/endlichyoga-deploy.service.d
run install -m 0644 "$(dirname "$0")/deploy-repo.conf" /etc/systemd/system/endlichyoga-deploy.service.d/
run systemctl daemon-reload
run systemctl enable --now endlichyoga-webhook.service

# 5. Caddy block (marker-based, idempotent)
if grep -q "deploy.endlichyoga.de" "$CADDYFILE"; then
  echo "  Caddy block already present"
else
  echo "  appending endlichyoga.de blocks to $CADDYFILE"
  # Remove a possible unmanaged endlichyoga.de site block first (it gets
  # replaced by the managed block below; duplicate site blocks would fail
  # validation).
  if grep -q '^endlichyoga\.de, www\.endlichyoga\.de {' "$CADDYFILE"; then
    echo "  removing unmanaged endlichyoga.de block (replaced by managed block)"
    run sed -i '/^endlichyoga\.de, www\.endlichyoga\.de {$/,/^}$/d' "$CADDYFILE"
  fi
  run python3 - "$CADDYFILE" "$SNIPPET" <<'PYEOF'
import sys
caddyfile, snippet = sys.argv[1], sys.argv[2]
with open(snippet, encoding="utf-8") as f:
    block = f.read()
if not block.startswith("\n"):
    block = "\n" + block
with open(caddyfile, "a", encoding="utf-8") as f:
    f.write(block)
PYEOF
  # Caddy runs as docker container `mellon-caddy` (host network) — validate
  # first, only reload on success. 127.0.0.1 reaches the host receiver.
  echo "  validating Caddy config (container)"
  run docker exec mellon-caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
  echo "  reloading Caddy"
  run docker exec mellon-caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
fi

echo "== done =="
echo "  DNS (manual, Cutover — see deploy/README.md):"
echo "    A deploy.endlichyoga.de            -> 65.21.27.234 (planet)"
echo "    A endlichyoga.de, www.endlichyoga.de -> 65.21.27.234 (planet, after cutover)"
echo "  GitHub:       secret DEPLOY_TOKEN (see above / token file)"
echo "  Test:         curl -X POST -H 'Authorization: Bearer <token>' http://127.0.0.1:$PORT/deploy"
