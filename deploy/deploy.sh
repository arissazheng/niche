#!/usr/bin/env bash
# Sends your local backend/.env and deploy/ config to the Vultr server, then redeploys origin/main now.
# The server also redeploys by itself whenever main changes (niche-autodeploy.timer).
# Usage (from the repo root): deploy/deploy.sh
set -euo pipefail
HOST=${NICHE_HOST:-root@149.28.78.19}
cd "$(dirname "$0")/.."
scp -q backend/.env "$HOST":/opt/niche/backend/.env
scp -qr deploy/. "$HOST":/opt/niche/deploy/
ssh "$HOST" 'chmod 600 /opt/niche/backend/.env && chmod +x /opt/niche/deploy/*.sh \
  && cp /opt/niche/deploy/niche-autodeploy.* /etc/systemd/system/ && systemctl daemon-reload \
  && systemctl enable -q --now niche-autodeploy.timer && /opt/niche/deploy/autodeploy.sh --force'
