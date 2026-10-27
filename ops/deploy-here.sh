#!/bin/sh
# Build, test and (re)start the dashboard from the current checkout. Runs ON home-ai.
set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$(dirname "$0")/.."
export APP_VERSION="$(git rev-parse --short HEAD)"
mkdir -p "$HOME/household-ai/data/dashboard"
echo "== testing $APP_VERSION"
docker build -q --target test -t kitchen-dashboard:test . >/dev/null
echo "== starting $APP_VERSION"
docker compose up -d --build --quiet-pull
i=0
while [ $i -lt 30 ]; do
  v=$(curl -fs --max-time 3 http://localhost:8081/api/version 2>/dev/null | sed -n 's/.*"version":"\([^"]*\)".*/\1/p')
  if [ "$v" = "$APP_VERSION" ]; then
    echo "== live: $APP_VERSION"
    docker image prune -f >/dev/null 2>&1 || true
    exit 0
  fi
  i=$((i + 1)); sleep 2
done
echo "== health check failed for $APP_VERSION" >&2
exit 1
