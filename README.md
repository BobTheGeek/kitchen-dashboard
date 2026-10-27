# kitchen-dashboard

Family wall screen for the kitchen: this week's calendar, what's next, and a daily TODO list per person.
Runs on home-ai; shown full-screen on the kitchen kiosk and on phones over Tailscale. See `CLAUDE.md`.

    scripts/dev.sh            # fake data at http://localhost:8081
    pytest -q && ruff check .
    git push                  # deploys to home-ai within ~2 minutes
    scripts/deploy.sh         # or deploy right away after pushing (on main, pushed, over SSH)

First-time setup on home-ai: `sh ops/install-on-home-ai.sh key`, add the printed key on GitHub as a read-only
deploy key, then `sh ops/install-on-home-ai.sh install`.
