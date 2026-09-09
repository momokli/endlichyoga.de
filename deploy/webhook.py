#!/usr/bin/env python3
"""Deploy webhook receiver for endlichyoga.de.

Mirrors the mariusklimke.de pattern (MacMasus/mariusklimke.de
deploy/webhook.py, which itself mirrors the openclaw-deploy pattern).
Listens on 127.0.0.1:18794 and, on a POST to /deploy with the correct bearer
token, triggers `endlichyoga-deploy.service` (which pulls the `built` branch
and rsyncs it into the docroot /opt/http/endlichyoga.de). This is the HTTPS
target used by the GitHub Actions workflow (.github/workflows/deploy.yml) so a
push to `main` deploys immediately.

The shared secret lives in /etc/endlichyoga/deploy.token (NOT in git); GitHub
holds the same value as the `DEPLOY_TOKEN` repository secret. Provisioning is
done with deploy/provision.sh on planet (no Ansible role in this repo).

Improvement over the openclaw receiver: binds 127.0.0.1 (Caddy reverse-proxies
the public subdomain), per the recommendation in
openclaw-deploy/docs/deployment-review.md.

Run as root (needs `systemctl start` without password).
"""

import hmac
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN_FILE = "/etc/endlichyoga/deploy.token"
PORT = 18794


def read_token():
    with open(TOKEN_FILE) as f:
        return f.read().strip()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/deploy":
            self.send_response(404)
            self.end_headers()
            return
        auth = self.headers.get("Authorization", "").strip()
        if not hmac.compare_digest(auth, "Bearer " + read_token()):
            self.send_response(401)
            self.end_headers()
            return
        subprocess.run(["systemctl", "start", "endlichyoga-deploy.service"])  # service runs as root
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"triggered"}')

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
