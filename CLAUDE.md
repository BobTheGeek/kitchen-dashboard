# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Kitchen Dashboard

Family wall display for the Gibilaro household (Bob, Belen, Ben). Part of the private **household-ai** system.
Rule one: **family data stays in the house.**

## Where things are
- Spec: `docs/superpowers/specs/2026-10-26-kitchen-dashboard-part1-design.md` · Design: `docs/design/README.md`
  (print a design card: `python3 -I scripts/design_card.py 2a`).
- Server: `app/` (FastAPI). `store` (SQLite + change counter), `todos` (rules), `settings` (colors, people),
  `calendar` (calendar-api client, cache, week builder), `labels` (pure formatting), `api` (routes),
  `house` (House writes, each logged with its inverse), `actions` (the `house_actions` log behind change cards and Undo),
  `clock` (the only place the app reads the time).
- Page: `app/static/` plain HTML/CSS/ES modules, no build step. `main.js` picks the layout, `kitchen.js` (3000×2000 stage), `phone.js` (≤ 900px), shared `api.js`, `ui.js`.

## How the code fits together
- `api.create_app()` builds everything and takes the collaborators as arguments (`db_path`, `source`, `whisper`, `house`,
  `house_token`, `photos_dir`). Tests pass fakes there; `DASHBOARD_FAKE=1` swaps in the fixture calendar, fake whisper and fake House.
- Time: call `clock.now()`, never `datetime.now()`. Tests pin it with the `freeze("2026-10-26T15:20")` fixture (`tests/conftest.py`).
- Live updates: a write bumps the `meta.changes` counter in the same transaction, the page sees it on its `/api/changes` poll and refetches.
- House writes go through `HouseOps`, so each one records how to reverse it. A new House action needs an `inverse` for Undo to work.
- Schema: `store.SCHEMA` is only `create table if not exists`, and there are no migrations. A new column on an existing table
  will not reach the live database by itself.
- After a deploy the page reloads itself when `/api/version` changes, so the kiosk needs no touch. The kiosk has no console:
  browser errors go to `/api/client-error` and land in the server log.

## How it runs
- home-ai (M1 Mac, OrbStack): container `kitchen-dashboard`, port 8081 → 8000, network `household-ai_default`,
  data `~/household-ai/data/dashboard/dashboard.db`.
- Kiosk: Surface Book, Fedora, full-screen browser at `http://home-ai:8081`. Never deploy to it.
- Calendar: `calendar-api` (household-ai repo), read-only here except `DELETE /events/{uid}` for House-made events.

## Commands
- Dev with fake data: `scripts/dev.sh` → http://localhost:8081 (narrow the window for the phone layout)
- Tests: `pytest -q && ruff check .` from the `.venv` that `scripts/dev.sh` creates (Python 3.13). One test: `pytest -q tests/test_todos.py -k overdue`.
- The Docker test stage (`docker build --target test .`) runs in CI and gates every deploy on home-ai. On the dev Mac Docker may not be running.
- Deploy: push to `main` → live within ~2 min (home-ai watcher polls every 2 min).
  Right away: `scripts/deploy.sh`. It refuses unless you are on `main` with HEAD equal to `origin/main`,
  then runs `ops/watch-deploy.sh` on home-ai over SSH, so manual deploys get the same rollback and alerts.
- Watcher (`ops/watch-deploy.sh`): takes a lock (`~/.kitchen-deploy.lock`), redeploys if the running version differs
  from HEAD, rolls back on a failed deploy, alerts via ntfy on a failed deploy or rollback, and alerts after 3 failed GitHub fetches.
- A failed commit is recorded in `~/.kitchen-deploy.failed` and skipped (one log line, no alert) until a new commit
  lands; self-heal redeploys have no rollback.
- Logs on home-ai: `~/household-ai/logs/kitchen-deploy.log`, `docker logs kitchen-dashboard`.

## Rules
- The family is fixed at three: Bob, Belen, Ben (Bob's decision, 2026-10-27). People can be renamed, never added or removed; the wall always shows exactly three TODO cards.
- No external network calls, CDNs, web fonts or analytics. System fonts only.
- All dates/times America/Chicago, computed on the server. Never slice calendar ISO strings for dates.
- Kitchen: touch only, ≥ 120px targets (the 13.5-inch 267 PPI screen makes 1px = 0.095 mm, and 1 cm is the minimum), content ≥ 44px and labels ≥ 36px; never use browser zoom to fix sizing. The layout's three reading distances are at the top of `kitchen.css`.
- Check new CSS class names in `kitchen.css` for collisions: it is one global file, and `.dots` and `.band` have both clashed before.
- Escape all calendar/TODO text (`esc()` in `ui.js`).
- Polling: `/api/changes` every 10 s, week + today every 60 s. Writes to todos/people/colors must call `store.bump`.
- Ask Bob before touching household-ai, Tailscale rules, kiosk config, or what family data the screen shows.
- `main` is production. Branch + PR for anything bigger than a small tweak.

## Talk to the house (Part 2)
- Spec: `docs/superpowers/specs/2026-10-27-kitchen-dashboard-part2-talk-design.md`.
- Code: `app/talk.py` (clients, sessions, `TalkService`), `app/api.py` (`/api/talk/*`). Page: `app/static/js/talk.js` (recorder, shared API), `talk-wall.js` (kitchen panel), `talk-phone.js` (phone thread).
- Flow: page records 16 kHz WAV → `/api/talk/listen` → whisper.cpp (`WHISPER_URL`, launchd `com.household.whisper` on home-ai)
  → `/api/talk/message` → Open WebUI House (`OPENWEBUI_URL`, Kitchen account key) → House tools (`house_tools/`)
  → `/api/house/*` (token) → calendar-api / TODOs, each write logged in `house_actions` for change cards + Undo.
- whisper.cpp is pinned to the tag in `ops/install-whisper.sh` (`TAG`, currently v1.9.5).
- Secrets: `~/household-ai/secrets/kitchen/{openwebui_key,house_token}` → `/run/kitchen-secrets` (read-only). Never log or return them.
- Never use the browser Web Speech API. Mic needs HTTPS: `https://home-ai.tailfa3a6f.ts.net:8082` (`tailscale serve`); it works once `tailscale serve` is set up on home-ai.
- Accepted risk: calendar titles from outside invites reach the House (bounded by Undo and House-only event edits).
- `/api/talk/*` is reachable by anyone who can reach port 8081 (tailnet/LAN): same trust model as Part 1.
- Open WebUI setup the House needs: the Kitchen account must have read access to the House model **and** to its
  base model `qwen3.5:9b` (an unregistered base model is admin-only: log says `base_model_unregistered`).
- We call Open WebUI with `stream: false` and `params.function_calling: "legacy"`. In native mode a non-streaming
  caller gets the tool calls back unrun, and the House replies with nothing. Legacy mode runs one tool pass per turn.
- Restart the container after creating or changing the kitchen secrets (they are read once at startup).
- Fake mode (`DASHBOARD_FAKE=1`) has a fake whisper and a fake House ("add a todo for Ben to feed Milo").
- Install scripts on home-ai: `sh ops/install-whisper.sh` (builds and runs whisper.cpp); `OWUI_ADMIN_KEY=… sh ops/install-house-tools.sh` (updates House tools).

## Open work
- Tracked in Beads (`kd-` ids, committed in `.beads/`): `bd ready`, `bd show <id>`, `bd update <id> --status in_progress`, `bd close <id>`.

## Photo slideshow (Part 3)
- Spec: `docs/superpowers/specs/2026-10-27-kitchen-dashboard-part3-slideshow-design.md`.
- Source: shared album "Kitchen Tablet Slideshow" (name in `ops/photo-sync.sh`). home-ai is signed in to Bob's Apple ID
  with only Photos → Shared Albums on. Never turn on iCloud Photos, Keychain or Messages there.
- Sync: launchd `com.household.kitchen-photo-sync` runs `ops/photo-sync.sh` hourly (osxphotos lists the album UUIDs; the files come from `Photos Library.photoslibrary/scopes/collectionshare/originals/`, because osxphotos 0.77 cannot export shared-album photos; `sips` → JPEG, max 3000 px)
  into `~/household-ai/data/photos/kitchen/`, mounted read-only at `/photos`. Log: `~/household-ai/logs/kitchen-photo-sync.log`.
  Install/update: `sh ops/install-photo-sync.sh` on home-ai.
- Server: `app/photos.py` (name rule, hours 7 AM–9 PM), routes `/api/photos` and `/photos/{name}`. Page: `slideshow.js` (kitchen only).
- Test the page fast with `?idle=5` (idle seconds).
- Emptying the album does not clear the wall (the sync keeps old photos when an export comes back empty). To clear it, delete the files in `~/household-ai/data/photos/kitchen/` on home-ai.
