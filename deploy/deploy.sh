#!/usr/bin/env bash
# Push-deploy the dashboard to the always-on box from a dev machine (DESIGN §5).
#
#   deploy/deploy.sh <user@host> [ssh-key]
#   e.g.  deploy/deploy.sh pi@192.168.0.185
#
# It rsyncs the code, copies the two secrets (config.toml and the OAuth token,
# both git-ignored — they never enter the repo), then runs deploy/install.sh on
# the box over SSH. Re-run any time to update; it's idempotent.
#
# Prerequisites, both in the repo root and git-ignored:
#   - config.toml   the box's real config. Paths use ~ (e.g. token_path =
#                   "~/.config/trmnl/token.json") so they resolve on the target.
#   - token.json    the OAuth refresh token minted by the one-time consent.
set -euo pipefail

TARGET="${1:?usage: deploy/deploy.sh <user@host> [ssh-key]}"
KEY="${2:-$HOME/.ssh/id_ed25519}"
APP_DIR="trmnl-dashboard"    # under the remote user's home
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSH_OPTS=(-i "$KEY" -o BatchMode=yes)
cd "$REPO_ROOT"

[ -f config.toml ] || { echo "error: config.toml missing in repo root (copy config.example.toml, fill it in, use ~ paths)"; exit 1; }
[ -f token.json ]  || { echo "error: token.json missing in repo root (the OAuth refresh token)"; exit 1; }
command -v rsync >/dev/null || { echo "error: rsync not found on this machine"; exit 1; }

echo "==> preparing directories on ${TARGET}"
ssh "${SSH_OPTS[@]}" "$TARGET" "mkdir -p ~/${APP_DIR} ~/.config/trmnl"

echo "==> syncing code"
rsync -az --delete \
  --exclude '.git' --exclude '.venv' --exclude '.local' --exclude '__pycache__' \
  --exclude '*.pyc' --exclude '.pytest_cache' --exclude '*.egg-info' \
  --exclude 'config.toml' --exclude 'config.local.toml' --exclude 'token.json' \
  -e "ssh ${SSH_OPTS[*]}" \
  trmnl tests pyproject.toml README.md config.example.toml deploy \
  "${TARGET}:~/${APP_DIR}/"

echo "==> copying secrets (git-ignored; over the same key)"
scp "${SSH_OPTS[@]}" config.toml "${TARGET}:~/${APP_DIR}/config.toml"
scp "${SSH_OPTS[@]}" token.json  "${TARGET}:~/.config/trmnl/token.json"
ssh "${SSH_OPTS[@]}" "$TARGET" "chmod 600 ~/${APP_DIR}/config.toml ~/.config/trmnl/token.json"

echo "==> running install on ${TARGET}"
ssh "${SSH_OPTS[@]}" "$TARGET" "cd ~/${APP_DIR} && bash deploy/install.sh"

echo "==> deployed. The device's captive portal should point at http://<box-ip>:8080"
