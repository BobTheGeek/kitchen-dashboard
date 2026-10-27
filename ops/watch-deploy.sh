#!/bin/sh
# Pull-based deploy. launchd runs this every 2 minutes on home-ai.
# New commit on origin/main -> test, start, health check. Any failure -> roll back and send an ntfy alert.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$HOME/kitchen-dashboard" || exit 1
notify() {
  curl -fs --max-time 5 -H "Title: kitchen-dashboard" -H "Tags: warning" -d "$1" \
    http://localhost:8090/home-ai-alerts >/dev/null 2>&1 || true
}
git fetch -q origin main 2>/dev/null || exit 0   # offline: try again next run
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] && exit 0
PREV=$(git rev-parse HEAD)
NEW=$(git rev-parse --short origin/main)
echo "$(date '+%F %T') deploying $NEW"
if ! git merge -q --ff-only origin/main; then
  notify "Can't fast-forward to $NEW (local changes or a force-push?). Not deployed."
  exit 1
fi
if sh ops/deploy-here.sh; then
  echo "$(date '+%F %T') live $NEW"
else
  git reset -q --hard "$PREV"
  sh ops/deploy-here.sh >/dev/null 2>&1
  notify "Deploy of $NEW failed (tests, build or health). Rolled back to $(git rev-parse --short HEAD). See ~/household-ai/logs/kitchen-deploy.log"
  echo "$(date '+%F %T') FAILED $NEW, rolled back"
fi
