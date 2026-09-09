#!/bin/bash
# deploy.sh — server-side deploy for endlichyoga.de.
#
# Triggered by the webhook receiver (endlichyoga-webhook.service) via the
# systemd oneshot unit endlichyoga-deploy.service (runs as user `deploy`).
#
# The GitHub Actions workflow (.github/workflows/deploy.yml) publishes the
# site 1:1 (static site, no build step) to the `built` branch of this repo.
# This script downloads that branch as a tarball (public repo, no
# credentials) and rsyncs it into the Caddy docroot — the same pattern as the
# mariusklimke.de deploy (MacMasus/mariusklimke.de deploy/deploy.sh):
# /opt/http/endlichyoga.de.
#
# Requires: curl, tar, rsync (all present on planet).

set -euo pipefail

REPO="${REPO:-momokli/endlichyoga.de}"   # canonical repo (after merge)
BRANCH="${BRANCH:-built}"                 # set via deploy-repo.conf drop-in
DEST="/opt/http/endlichyoga.de"
URL="https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "Downloading ${BRANCH} branch of ${REPO} ..."
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

curl -fsSL "$URL" | tar -xz --strip-components=1 -C "$TMP"

if [ ! -f "$TMP/index.html" ]; then
    log "ERROR: built branch has no index.html — aborting"
    exit 1
fi

log "Syncing into $DEST ..."
rsync -a --delete "$TMP/" "$DEST/"

log "Deploy complete: $(find "$DEST" -maxdepth 1 -type f | wc -l) files in docroot"
