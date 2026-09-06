#!/usr/bin/env bash
# On-target install for the dashboard (DESIGN §5). Runs ON the deploy box, from
# the app directory; deploy/deploy.sh invokes it over SSH after syncing the code
# and secrets. Idempotent — re-run any time to pick up new code.
#
# It assumes the app directory already holds the code, config.toml and (at
# ~/.config/trmnl/token.json) the OAuth token — deploy.sh puts them there.
#
# No Docker: the box runs Python natively. Pillow comes from apt (prebuilt);
# everything else is pure-Python in a venv that reuses that system Pillow.
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE=trmnl-dashboard
cd "$APP_DIR"

echo "==> system packages (Pillow prebuilt + venv; nothing compiles)"
sudo apt-get update -qq
sudo apt-get install -y python3-venv python3-pil

echo "==> venv (reuses the system Pillow)"
[ -d .venv ] || python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --quiet --upgrade pip

echo "==> Python dependencies (pure-Python; Pillow stays from apt)"
.venv/bin/pip install --quiet -r deploy/requirements-pi.txt
.venv/bin/pip install --quiet -e . --no-deps

echo "==> sanity: imports resolve on this box"
.venv/bin/python - <<'PY'
import PIL, httpx, google.auth, requests, tomli
from trmnl.server import loop  # noqa: F401
print("imports OK; Pillow", PIL.__version__)
PY

echo "==> systemd service"
user="$(id -un)"
tmp="$(mktemp)"
sed "s#__USER__#${user}#g; s#__APP_DIR__#${APP_DIR}#g" deploy/${SERVICE}.service > "$tmp"
sudo install -m 644 "$tmp" /etc/systemd/system/${SERVICE}.service
rm -f "$tmp"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE}"
sudo systemctl restart "${SERVICE}"

echo "==> waiting for the first build cycle..."
sleep 6
if [ -f "${APP_DIR}/screen.bmp" ]; then
  echo "OK: screen.bmp written ($(stat -c%s "${APP_DIR}/screen.bmp") bytes)"
else
  echo "NOTE: screen.bmp not written yet — check: journalctl -u ${SERVICE} -n 30"
fi
sudo systemctl --no-pager status "${SERVICE}" | head -6 || true
echo "==> install done"
