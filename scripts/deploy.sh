#!/bin/sh
# Deploy origin/main to home-ai now, instead of waiting for the 2-minute watcher. Needs Tailscale + SSH key.
# Runs the same watcher launchd runs on home-ai, so manual deploys get the same fast-forward, rollback and alert handling.
set -e
HOST="${HOME_AI:-bobg@home-ai}"
if [ -n "$(git status --porcelain)" ]; then
  echo "Commit first: the working tree has uncommitted changes." >&2
  exit 1
fi
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
  echo "Switch to main first (currently on $BRANCH): only origin/main gets deployed." >&2
  exit 1
fi
git fetch -q origin main
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
  echo "Push first: HEAD must equal origin/main." >&2
  exit 1
fi
ssh "$HOST" 'sh ~/kitchen-dashboard/ops/watch-deploy.sh'
