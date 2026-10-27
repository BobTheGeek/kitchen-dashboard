# Kitchen Dashboard, Part 1: Core dashboard

Date: 2026-10-26 · Owner: Bob · Status: approved design, awaiting spec review

## 1. Context

A Skylight-style family wall display for the Gibilaro household (Bob, Belen, Ben). It is one part of **household-ai**, a private home system whose main rule is **family data stays in the house**.

This is a fresh build. The Claude Cowork handoff (`HANDOFF.md`) is used as requirements only; none of its code is reused. The UI comes from Claude Design: `docs/design/README.md` (tokens, per-screen specs) and `docs/design/Kitchen Dashboard.dc.html` (visual reference; it loads React from a CDN for its own preview, which is never copied into the app).

The full project is three parts, built in order, each with its own spec:

1. **Core dashboard** (this spec)
2. **Talk to the house**: voice/chat panel, local speech-to-text, House AI adding events and TODOs, HTTPS on the kiosk
3. **Photo slideshow**: shared Apple Photos album synced on home-ai, idle slideshow

## 2. Goals

- A live, useful screen in the kitchen: clock, what's next, this week's calendar, and a daily TODO list per person that can be checked off by touch.
- Phones can see the same data, add and edit TODOs, and change settings.
- Deploys are safe: a failing test means nothing ships.

**Non-goals for Part 1:** the Talk panel (the button is shown but inert), editing events, "Change by voice", person photos (initials instead), slideshow, bills, login.

## 3. Environment

| Piece | Where |
|---|---|
| This app | container `kitchen-dashboard` on **home-ai** (M1 Mac, macOS, OrbStack). Host port `8081` → app port `8000`. |
| Calendar data | container `calendar-api` on the same Docker network (`household-ai_default`), `http://calendar-api:8000`. Internal only. |
| App data | SQLite at `/data/dashboard.db` → host `~/household-ai/data/dashboard/` (backed up nightly by household-ai). |
| Kitchen screen | Surface Book, Fedora, kiosk browser at `http://home-ai:8081`. 3000×2000, devicePixelRatio 1, touch only. Never deploy to it. |
| Phones | same URL over Tailscale. |

Network is Tailscale only. Family devices may reach home-ai ports 3000, 8081, 8082, 5006. SSH: `bobg@home-ai`.

**calendar-api endpoints** (verified 2026-10-26 from its OpenAPI): `GET /calendars`, `GET /events`, `POST /events`, `PATCH /events/{uid}` and `DELETE /events/{uid}` (both only for events House created), `GET /free-weekends`. Event fields: `calendar, title, when, start, end, all_day, location, uid, added_by_house`.

**Known issue:** on 2026-10-26 every calendar-api call returns `502 Couldn't reach iCloud calendars: AuthorizationError`. The fix belongs in the household-ai repo (Bob). Part 1 is developed against fake data and works with stale/empty data until it is fixed.

## 4. Hard constraints

1. No external network calls from the page or the server. No CDNs, web fonts, analytics or third-party APIs.
2. Kitchen screen: 3000×2000 at DPR 1, read from across a room. Never fix sizing with browser zoom or `--force-device-scale-factor`. Nothing on the wall below 30px.
3. Touch only on the kiosk: no hover, no keyboard. Kitchen tap targets ≥ 100px; phone ≥ 48px. Text entry is phone only in Part 1.
4. Escape all calendar and TODO text before inserting it into the DOM.
5. All dates and times are **America/Chicago**, computed in code, on the server and (for the clock) with an explicit `timeZone` on the page.
6. This app never talks to iCloud. Calendar writes go only through calendar-api.
7. No secrets in the repo.
8. Dependencies few and pinned. Plain HTML/CSS/JS, no frameworks or bundlers.

## 5. Architecture

```
Kiosk / phone browser ──HTTP──▶ kitchen-dashboard (FastAPI) ──HTTP──▶ calendar-api ──▶ iCloud
                                     │
                                     └── SQLite /data/dashboard.db
```

**Server (Python 3.13 + FastAPI)**, four units with one job each:

| Unit | Job | Depends on |
|---|---|---|
| `calendar` | Fetch events/calendars from calendar-api; 60 s in-memory cache; last good response also saved to SQLite so a restart still has data; bucket events into Chicago days; build Next up; format labels. | calendar-api, `store` |
| `todos` | People and TODO rules: today's list, carry-over, overdue, all-done. | `store` |
| `settings` | Calendar colors and family members. | `store` |
| `store` | SQLite connection, schema creation and migrations, change counter. | SQLite |

Plus `api` (routes only, thin) and `format` (pure functions: relative labels, chip text color). The server does the formatting so it can be tested with pytest; the page stays thin.

**Page (`app/static/`)**: one `index.html`, CSS, and plain JS. One shared data module (fetch, poll, escape); separate layout CSS for kitchen and phone (`@media (max-width: 900px)`). No build step.

**Updates (smart polling):**
- Every 10 s the page calls `GET /api/changes` → `{"n": <int>}` (about 20 bytes).
- When `n` changes, it fetches `/api/today` (and `/api/settings` if needed).
- Calendar data (`/api/week`) refreshes every 60 s regardless, and at midnight.
- The server does not write access-log lines for `/api/changes` or `/api/version`.
- Phones poll only while the page is visible (`visibilitychange`).
- A tap on the kiosk updates its own screen at once (optimistic); other devices see it within ~10 s.

## 6. Data model (SQLite)

```sql
people(id INTEGER PK, name TEXT NOT NULL, sort INTEGER NOT NULL)
todos(id INTEGER PK, person_id INTEGER NOT NULL REFERENCES people(id),
      text TEXT NOT NULL, date TEXT NOT NULL,          -- YYYY-MM-DD, Chicago
      time TEXT,                                        -- HH:MM, Chicago, optional
      done_at TEXT,                                     -- ISO timestamp with offset, or NULL
      created_by TEXT NOT NULL DEFAULT 'phone',         -- 'phone' | 'house'
      created_at TEXT NOT NULL)
calendar_colors(calendar TEXT PK, color TEXT NOT NULL)  -- '#rrggbb'
calendar_cache(key TEXT PK, fetched_at TEXT NOT NULL, body TEXT NOT NULL)
meta(key TEXT PK, value TEXT NOT NULL)                  -- 'changes' counter, 'schema_version'
```

- First run seeds people: Bob, Belen, Ben (in that order).
- Every write to `todos`, `people` or `calendar_colors` bumps `meta.changes` in the same transaction.
- Deleting a person who has TODOs is refused (move or delete the TODOs first).

## 7. Rules

### TODOs
For person P on Chicago date D (today), the list contains:
1. open items with `date = D`;
2. open items with `date < D` (**carried over**);
3. items done on D (by `done_at` in Chicago time), whatever their `date`.

Items with `date > D` are hidden until their day.

An item is **overdue** when it is open and either `date < D`, or `date = D` and `time` is set and earlier than now.

Order: overdue first (oldest first), then open items by time (timed before untimed, then by creation), then done items.

Header count: `N left`, or `M overdue · N left` when any are overdue (`N` counts all open items, overdue included). **All done** when the list has ≥ 1 item and none are open (count reads `X of X`). **Empty** when the list has no items.

Tapping toggles done/undone. Un-doing an item restores it to open with its original `date`.

### Events
- The dashboard shows the calendars calendar-api returns for `kitchen_only=true`. Settings lists those same calendars. Which calendars are "kitchen" calendars is set in calendar-api (household-ai), not here. "Who an event is for" is its calendar; per-person calendars (e.g. "Bob") are added there if needed.
- Each event's day is its start converted to America/Chicago (all-day events use their date as-is). Never slice raw ISO strings.
- Week strip: 7 rolling days starting today. Per day: all-day events first, then timed events by start. Show at most 3 chips; if more, a `+N more` pill opens the day sheet (8d).
- Next up: up to 4 events, in order, that are today's all-day events or timed events whose start is ≥ now.
- Relative label: `Today, 5:30 PM` · `Tomorrow, 9:00 AM` · else `Wed, 4:00 PM`. All-day: `Today` / `Tomorrow` / `Wed` with `all day` as the chip time.
- Chip text color: `#1c1b1f` when the color's relative luminance > 0.55, else `#fff` (design rule 1e). Computed on the server and returned with each calendar.
- Calendars with no stored color get the next unused preset from the design's 8 presets (yellow, orange, red, pink, violet, blue, teal, green), then stored.
- Delete is offered only when `added_by_house` is true. Otherwise the event sheet shows "Change it in your Calendar app".

### Night mode (6a)
From 22:00 to 06:00 Chicago time the kiosk shows the night screen. Any tap shows the full dashboard for 2 minutes, then it returns to night. The switch is a 1 s crossfade. "Tomorrow" shows the first event of the next day; "Still open today" shows people with open items and their counts. The phone layout has no night mode.

### Status line
- Green `up to date` when calendar data is < 5 min old.
- Amber `last updated X min ago` when calendar data is ≥ 5 min old (server is reachable, calendar-api is not).
- Amber `last updated — offline` when the page has had no server response for 30 s.
- Amber `connecting to the home server…` on first load until the first response.

## 8. API

All JSON. Times are Chicago with offset.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/version` | `{version}`; page reloads when it changes after a deploy |
| GET | `/api/changes` | `{n}`; the cheap poll |
| GET | `/api/week` | `{generated_at, stale_since?, days:[{date, dow, day, is_today, events:[…], more}], next:[…], calendars:[{name, color, ink}]}`. Each event: `uid, calendar, title, start, end, all_day, location, time_label, relative_label, can_delete` |
| GET | `/api/today` | `{date, people:[{id, name, initial, todos:[{id, text, date, time, done, overdue, carried}], left, overdue, state: "open"\|"all_done"\|"empty"}]}` |
| POST | `/api/todos` | `{person_id, text (1–120 chars), date, time?}` → created todo |
| PATCH | `/api/todos/{id}` | any of `text, person_id, date, time, done` |
| DELETE | `/api/todos/{id}` | remove |
| GET | `/api/settings` | `{calendars:[{name, color, ink}], people:[{id, name, sort}]}` |
| PUT | `/api/settings/calendars/{name}` | `{color}` |
| POST / PATCH / DELETE | `/api/settings/people[/{id}]` | add, rename/reorder, remove a person |
| DELETE | `/api/events/{uid}` | passes through to calendar-api `DELETE /events/{uid}`; calendar-api's refusal is returned as-is with its message |
| GET | `/` | the page |

Part 2's House AI will use the same TODO endpoints with `created_by: "house"`.

## 9. Screens in Part 1

From `docs/design/README.md`; match its sizes, spacing, colors and copy.

**Kitchen:** 2a dashboard (with an inert Talk button), 8c busy day, 8d day sheet, 3a event detail (the "Change by voice" button is hidden until Part 2), 3c delete confirm, 8a overdue, 8b empty states, 8f loading, 6a night mode. Person photo slots show the person's initial.

**Phone:** 4a home (Talk button inert), 4b add TODO, 4c settings (calendar colors with presets and custom color input; family rename only (the family is fixed at Bob, Belen, Ben; changed 2026-10-27); the greyed "Later" block), 8h event detail (read-only rows; Delete only for House events), 8i TODO edit.

**Not in Part 1:** 2b, 5a–5d, 8e, 8g, 4d (Part 2); 7a, 7c and photo upload (Part 3).

## 10. Errors

| Failure | Behavior |
|---|---|
| calendar-api down or 502 | Serve last good data from memory or `calendar_cache`; `stale_since` set; status amber. If there was never any data: empty week with `free` days and the status line explains. |
| Server unreachable | Page keeps last data on screen; after 30 s the status shows offline; polling continues. |
| TODO toggle/save fails | Revert the optimistic change; show a short toast ("Couldn't save, try again"). |
| Invalid input | 422 with a field message; the phone form shows it next to the field. |
| calendar-api refuses delete | Sheet shows calendar-api's message; nothing removed locally. |
| Unknown calendar color | Next preset assigned and stored. |

## 11. Testing

- **pytest** against the API with a temp SQLite file and a fake calendar-api (injected fixture data, including events sent in UTC):
  - carry-over, overdue (past date and past time), done-today from an old date, future items hidden, ordering, counts, all-done and empty states;
  - Chicago day bucketing, including an evening event whose UTC date is the next day, and across a DST change;
  - Next up selection, `+N more`, relative labels, chip ink color for light and dark colors;
  - settings: preset assignment, color change, person rename (add/remove removed 2026-10-27);
  - change counter bumps on every write and not on reads;
  - delete pass-through: success, and calendar-api refusal returned with its message;
  - stale cache served when calendar-api fails, including after a restart.
- **ruff** for lint.
- **Visual check:** run in fake mode; screenshot at 3000×2000 and 430 px wide with ego-browser; compare with the design cards. Then Bob sends a photo of the real screen.
- A fake mode (`DASHBOARD_FAKE=1`) serves fixture events with day offsets from today, for dev and CI.

## 12. Deploy

- **Dockerfile**: base → `test` stage (installs dev deps, runs ruff + pytest) → runtime stage. `docker build --target test` gates every deploy.
- **docker-compose.yml**: service `kitchen-dashboard`, port `8081:8000`, network `household-ai_default` (external), volume `~/household-ai/data/dashboard:/data`, `TZ=America/Chicago`, `restart: unless-stopped`.
- **home-ai watcher (launchd, every 2 min)**: fetch `origin/main`; if new, fast-forward, build the test stage, start the new version, and wait until `/api/version` reports the new commit. On any failure: roll back to the previous commit, redeploy it, and send an ntfy alert to `http://localhost:8090/home-ai-alerts`. Log to `~/household-ai/logs/kitchen-deploy.log`.
- **One-time setup on home-ai**: a script generates a read-only deploy key and prints it; Bob adds it at `https://github.com/BobTheGeek/kitchen-dashboard/settings/keys`; the script then clones, deploys and loads the watcher.
- **`scripts/deploy.sh`**: deploy `origin/main` now over SSH; refuses if there is uncommitted or unpushed work.
- **GitHub Actions**: ruff, pytest and `docker build --target test` on every push and PR.
- `main` is production. Use branches and PRs for anything bigger than a small tweak.

## 13. Done when

- All tests pass in CI and in the Docker test stage.
- The app runs on home-ai at `http://home-ai:8081` and deploys itself from `main`.
- The kiosk shows the dashboard; Bob confirms legibility from a photo of the real screen.
- A TODO added on a phone appears on the kiosk within ~10 s, and a kiosk tap shows on phones within ~10 s.
- With calendar-api failing, the screen still shows (stale or empty) data and an amber status.
- `CLAUDE.md` describes the architecture, commands and constraints.
