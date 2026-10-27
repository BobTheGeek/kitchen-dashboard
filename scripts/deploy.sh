#!/bin/sh
# Deploy origin/main to home-ai now, instead of waiting for the 2-minute watcher. Needs Tailscale + SSH key.
set -e
HOST="${HOME_AI:-bobg@home-ai}"
if [ -n "$(git status --porcelain)" ] || [ "$(git rev-parse HEAD)" != "$(git rev-parse '@{u}' 2>/dev/null)" ]; then
  echo "Commit and push first: only what is on origin/main gets deployed." >&2
  exit 1
fi
ssh "$HOST" 'cd ~/kitchen-dashboard && git fetch -q origin main && git merge -q --ff-only origin/main && sh ops/deploy-here.sh'
