#!/bin/sh
# Run on home-ai from the repo: sh ops/install-photo-sync.sh. Safe to run again.
set -eu
cd "$(dirname "$0")/.."
command -v "$HOME/.local/bin/osxphotos" >/dev/null || { echo "Install first: uv tool install --python 3.12 osxphotos"; exit 1; }
mkdir -p "$HOME/household-ai/data/photos/kitchen" "$HOME/household-ai/logs"
PLIST="$HOME/Library/LaunchAgents/com.household.kitchen-photo-sync.plist"
cp ops/com.household.kitchen-photo-sync.plist "$PLIST"
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"   # RunAtLoad: the first sync starts now
echo "Installed. Watch: tail -f ~/household-ai/logs/kitchen-photo-sync.log"
