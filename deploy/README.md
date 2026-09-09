# Deploy — server side (endlichyoga.de)

Everything in this directory is the **server-side half** of the deploy
pipeline. It mirrors the established webhook pattern from
[`MacMasus/mariusklimke.de`](https://github.com/MacMasus/mariusklimke.de)
(`deploy/` there, which itself mirrors `momokli/openclaw-deploy`) — no SSH
keys are involved anywhere.

```
push to main (momokli/endlichyoga.de)
  └─ GitHub Actions (ubuntu-latest)
       ├─ sanity check (index.html, impressum.html, datenschutz.html, css/style.css)
       ├─ publish 1:1 copy → `built` branch   (static site — no build step)
       └─ POST https://deploy.endlichyoga.de/deploy  (Bearer DEPLOY_TOKEN)

planet (systemd)
  └─ endlichyoga-webhook.service (webhook.py, 127.0.0.1:18794)
       └─ systemctl start endlichyoga-deploy.service
            └─ deploy.sh  (user: deploy)
                 ├─ download `built` branch tarball (codeload.github.com)
                 └─ rsync --delete → /opt/http/endlichyoga.de/
```

## Files

| File | Purpose |
| --- | --- |
| `webhook.py` | HTTP receiver: validates `Authorization: Bearer <token>` on `POST /deploy`, then starts the deploy unit. Binds `127.0.0.1:18794`. |
| `endlichyoga-webhook.service` | systemd unit running `webhook.py` (root, so `systemctl start` works without a password). |
| `endlichyoga-deploy.service` | systemd **oneshot** unit running `deploy.sh` as user `deploy` (owns the docroot). |
| `deploy-repo.conf` | Drop-in for `endlichyoga-deploy.service`: sets `REPO`/`BRANCH` for `deploy.sh`. Installs to `/etc/systemd/system/endlichyoga-deploy.service.d/`. |
| `deploy.sh` | Pulls the `built` branch tarball and rsyncs it into `/opt/http/endlichyoga.de/`. |
| `provision.sh` | **Installer** (idempotent, run as root on planet). There is no Ansible role for endlichyoga.de — `provision.sh` *is* the provisioning path. |
| `Caddyfile.endlichyoga.conf` | Caddy site blocks (webhook reverse proxy + static site with cache headers), appended to `/home/momo/Caddyfile` by `provision.sh`. |

## Provisioning on planet

On planet, from a checkout of this repo:

```sh
sudo bash deploy/provision.sh            # apply
sudo bash deploy/provision.sh --dry-run  # preview
```

What it does (idempotent, purely additive):

1. Installs `/opt/endlichyoga-deploy/webhook.py` + `/opt/endlichyoga-deploy/deploy.sh`
   (`deploy.sh` owned by user `deploy`).
2. Creates the docroot `/opt/http/endlichyoga.de` (owned by user `deploy`).
3. Creates `/etc/endlichyoga/deploy.token` (mode 0600) — **preserved** if it
   already exists. Prints a fresh token otherwise.
4. Installs the systemd units + drop-in, runs `daemon-reload` and
   `systemctl enable --now endlichyoga-webhook.service`
   (`endlichyoga-deploy.service` is a oneshot started by the webhook on each
   `/deploy` POST — it is not enabled, matching the mariusklimke pattern).
5. Appends the `deploy.endlichyoga.de` + `endlichyoga.de` blocks from
   `Caddyfile.endlichyoga.conf` to `/home/momo/Caddyfile` (skipped if already
   present), then validates and reloads Caddy (`docker exec mellon-caddy`).

Manual equivalent (if you prefer not to run `provision.sh`):

```sh
sudo mkdir -p /opt/endlichyoga-deploy /etc/endlichyoga /opt/http/endlichyoga.de
sudo install -m 0755 deploy/webhook.py /opt/endlichyoga-deploy/
sudo install -m 0755 deploy/deploy.sh /opt/endlichyoga-deploy/
sudo chown deploy:deploy /opt/endlichyoga-deploy/deploy.sh /opt/http/endlichyoga.de
sudo sh -c 'umask 077; openssl rand -hex 32 > /etc/endlichyoga/deploy.token'
sudo install -m 0644 deploy/endlichyoga-webhook.service deploy/endlichyoga-deploy.service /etc/systemd/system/
sudo install -m 0644 -D deploy/deploy-repo.conf /etc/systemd/system/endlichyoga-deploy.service.d/deploy-repo.conf
sudo systemctl daemon-reload
sudo systemctl enable --now endlichyoga-webhook.service
# Caddy: append deploy/Caddyfile.endlichyoga.conf to /home/momo/Caddyfile,
# then: docker exec mellon-caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
#       docker exec mellon-caddy caddy reload   --config /etc/caddy/Caddyfile --adapter caddyfile
```

## GitHub secrets (momokli/endlichyoga.de, repo settings)

| Secret | Value |
| --- | --- |
| `DEPLOY_TOKEN` | Content of `/etc/endlichyoga/deploy.token` on planet |

The workflow `.github/workflows/deploy.yml` reads only `DEPLOY_TOKEN` (the
webhook URL is fixed in the workflow).

## DNS & Cutover

Current state: `endlichyoga.de` + `www.endlichyoga.de` point at the **old**
server `65.21.181.48`. Target: **planet** `65.21.27.234` (same infrastructure
that already serves mariusklimke.de).

Records needed (Cloudflare):

| Name | Type | Value |
| --- | --- | --- |
| `deploy.endlichyoga.de` | A | `65.21.27.234` (planet) |
| `endlichyoga.de` | A | `65.21.27.234` (planet, after cutover) |
| `www.endlichyoga.de` | A | `65.21.27.234` (planet, after cutover) |

### Cutover checklist (manual, NOT executed by any automation here)

- [ ] Merge the server-setup PR (`deploy/`, this directory) and the
      deploy-workflow PR (`.github/workflows/deploy.yml`).
- [ ] `sudo bash deploy/provision.sh` on planet.
- [ ] Create GitHub secret `DEPLOY_TOKEN` = content of
      `/etc/endlichyoga/deploy.token`.
- [ ] Smoke test locally on planet:
      `curl -X POST -H 'Authorization: Bearer <token>' http://127.0.0.1:18794/deploy`
      → expect `{"status":"triggered"}`; then
      `journalctl -u endlichyoga-deploy.service -n 20` shows a successful rsync.
- [ ] Trigger the workflow once (`workflow_dispatch`) and confirm the webhook
      fires end-to-end (`endlichyoga-webhook.service` log).
- [ ] Add `deploy.endlichyoga.de` A record; verify
      `https://deploy.endlichyoga.de/deploy` returns 401 without and 200 with
      the token.
- [ ] **Switch** `endlichyoga.de` + `www.endlichyoga.de` A records to
      `65.21.27.234`.
- [ ] Verify: `curl -fsSI https://endlichyoga.de` → 200, `server: Caddy`,
      content matches the repo (index.html).
- [ ] Rollback if needed: point the A records back to `65.21.181.48` (old
      server keeps serving until then — nothing is deleted there).

## Test

```sh
curl -X POST -H "Authorization: Bearer <token>" http://127.0.0.1:18794/deploy
```
