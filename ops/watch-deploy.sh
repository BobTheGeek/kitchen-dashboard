#!/bin/sh
# Pull-based deploy. launchd runs this every 2 minutes on home-ai; scripts/deploy.sh runs it over ssh for manual deploys.
# New commit on origin/main -> test, start, health check. Any failure -> roll back and send an ntfy alert.
# HEAD already at origin/main but the running version differs (interrupted deploy) -> redeploy HEAD.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$HOME/kitchen-dashboard" || exit 1
LOCK="$HOME/.kitchen-deploy.lock"
FAILS="$HOME/.kitchen-deploy.fetchfails"
log() { echo "$(date '+%F %T') $*"; }
notify() {
  curl -fs --max-time 5 -H "Title: kitchen-dashboard" -H "Tags: warning" -d "$1" \
    http://localhost:8090/home-ai-alerts >/dev/null 2>&1 || true
}
running_version() {
  curl -fs --max-time 3 http://localhost:8081/api/version 2>/dev/null | sed -n 's/.*"version":"\([^"]*\)".*/\1/p'
}

# One run at a time, so a manual deploy over ssh and the launchd run never overlap.
# A lock older than 15 minutes is left behind by a killed run, so it is taken over.
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +15 2>/dev/null)" ]; then
    log "removing stale lock $LOCK"
    rmdir "$LOCK" 2>/dev/null
  fi
  mkdir "$LOCK" 2>/dev/null || { log "another deploy is running; skipping"; exit 0; }
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
trap 'exit 1' INT TERM HUP

if FETCH_ERR=$(git fetch -q origin main 2>&1); then
  rm -f "$FAILS"
else
  n=$(cat "$FAILS" 2>/dev/null); n=$(( ${n:-0} + 1 ))
  echo "$n" > "$FAILS"
  log "fetch from origin failed ($n in a row): $FETCH_ERR"
  [ "$n" -eq 3 ] && notify "Can't fetch from GitHub for ~6 minutes (deploy key or network?). Deploys are paused."
  exit 0   # offline or no key: try again next run
fi

PREV=$(git rev-parse HEAD)
if [ "$PREV" != "$(git rev-parse origin/main)" ]; then
  NEW=$(git rev-parse --short origin/main)
  log "deploying $NEW"
  if ! git merge -q --ff-only origin/main; then
    notify "Can't fast-forward to $NEW (local changes or a force-push?). Not deployed."
    exit 1
  fi
  CAN_ROLL_BACK=1
else
  HEADSHA=$(git rev-parse --short HEAD)
  RUNNING=$(running_version)
  [ "$RUNNING" = "$HEADSHA" ] && exit 0
  NEW=$HEADSHA
  log "running version '${RUNNING:-none}' is not $HEADSHA; redeploying $HEADSHA"
  CAN_ROLL_BACK=0
fi

if sh ops/deploy-here.sh; then
  log "live $NEW"
  exit 0
fi

if [ "$CAN_ROLL_BACK" -eq 0 ]; then
  log "FAILED redeploy of $NEW, no earlier commit to roll back to"
  notify "Redeploy of $NEW failed (tests, build or health). Not rolled back: no earlier commit to return to. See ~/household-ai/logs/kitchen-deploy.log"
  exit 1
fi

BACK=$(git rev-parse --short "$PREV")
log "deploy of $NEW failed; rolling back to $BACK"
if git reset -q --hard "$PREV" && sh ops/deploy-here.sh; then
  log "FAILED $NEW, rolled back to $BACK"
  notify "Deploy of $NEW failed (tests, build or health). Rolled back to $BACK. See ~/household-ai/logs/kitchen-deploy.log"
else
  log "FAILED $NEW, rollback to $BACK FAILED"
  notify "Deploy of $NEW failed AND rollback to $BACK failed. Service may be down. See ~/household-ai/logs/kitchen-deploy.log"
fi
exit 1
