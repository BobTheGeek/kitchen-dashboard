# kitchen-dashboard

Family wall screen for the kitchen: this week's calendar, what's next, and a daily TODO list per person.
Runs on home-ai; shown full-screen on the kitchen kiosk and on phones over Tailscale. See `CLAUDE.md`.

    scripts/dev.sh            # fake data at http://localhost:8081
    pytest -q && ruff check .
    git push                  # deploys to home-ai within ~2 minutes
    scripts/deploy.sh         # or deploy right away after pushing (on main, pushed, over SSH)

Talk to the house (voice panel) is served over HTTPS at `https://home-ai.tailfa3a6f.ts.net:8082` (mic needs HTTPS).
On home-ai, `sh ops/install-whisper.sh` builds and runs the speech-to-text server, and
`OWUI_ADMIN_KEY=… sh ops/install-house-tools.sh` installs or updates the House tools. See `CLAUDE.md`.

First-time setup on home-ai: `sh ops/install-on-home-ai.sh key`, add the printed key on GitHub as a read-only
deploy key, then `sh ops/install-on-home-ai.sh install`.
