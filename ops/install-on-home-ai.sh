#!/bin/sh
# One-time setup on home-ai.
#   sh install-on-home-ai.sh key      -> makes a deploy key and prints it; add it to GitHub as READ-ONLY
#   sh install-on-home-ai.sh install  -> clones, deploys, loads the 2-minute watcher
set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
KEY="$HOME/.ssh/kitchen_dashboard_deploy"
REPO="git@github-kitchen:BobTheGeek/kitchen-dashboard.git"
PLIST="$HOME/Library/LaunchAgents/com.household.kitchen-deploy.plist"
case "$1" in
  key)
    [ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N "" -C "home-ai kitchen-dashboard deploy (read-only)" -f "$KEY"
    if ! grep -q "Host github-kitchen" "$HOME/.ssh/config" 2>/dev/null; then
      printf '\nHost github-kitchen\n  HostName github.com\n  User git\n  IdentityFile %s\n  IdentitiesOnly yes\n' "$KEY" \
        >> "$HOME/.ssh/config"
    fi
    echo "Add this as a READ-ONLY deploy key at https://github.com/BobTheGeek/kitchen-dashboard/settings/keys"
    echo
    cat "$KEY.pub"
    ;;
  install)
    ssh -o StrictHostKeyChecking=accept-new -T git@github-kitchen 2>&1 | grep -q "successfully authenticated" \
      || { echo "Deploy key not working yet. Run '$0 key' and add the key on GitHub first."; exit 1; }
    [ -d "$HOME/kitchen-dashboard/.git" ] || git clone -q "$REPO" "$HOME/kitchen-dashboard"
    mkdir -p "$HOME/household-ai/logs"
    cd "$HOME/kitchen-dashboard"
    sh ops/deploy-here.sh
    cp ops/com.household.kitchen-deploy.plist "$PLIST"
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    echo "== watcher loaded: pushes to main deploy within about 2 minutes"
    ;;
  *) echo "usage: $0 key|install"; exit 1 ;;
esac
