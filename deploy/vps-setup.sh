#!/usr/bin/env bash
# Run on VPS as root or with sudo after cloning to /opt/bookfinder
set -euo pipefail

APP_DIR=/opt/bookfinder
PORT=8010

cd "$APP_DIR"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Optional: rsync FB2 from dev machine:
# rsync -avz user@dev:Bookfinder/data/books/fb2/ data/books/fb2/

cp deploy/bookfinder.service /etc/systemd/system/
sed -i "s|/opt/bookfinder|$APP_DIR|g" /etc/systemd/system/bookfinder.service

systemctl daemon-reload
systemctl enable bookfinder
systemctl restart bookfinder

echo "Bookfinder on http://127.0.0.1:$PORT — configure nginx (deploy/nginx-bookfinder.conf)"
