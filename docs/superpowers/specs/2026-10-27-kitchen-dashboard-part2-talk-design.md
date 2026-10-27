# Kitchen Dashboard, Part 2: Talk to the house

Date: 2026-10-27 · Owner: Bob · Status: approved design, awaiting spec review · Beads: kd-gzm

## 1. Context

Part 1 (core dashboard) is live on home-ai and auto-deploys from `main`. Part 2 turns on the large "Talk to the house" button: a voice/chat panel on the kitchen screen and on phones that talks to **the House**, the household's local AI in Open WebUI. Part 3 (photo slideshow) is separate.

Design screens (from `docs/design/README.md`): kitchen 2b, 5a, 5b, 5c, 5d, 8g, 8e; the "Change by voice" button in 3a; phone 4d and "Ask the house to change it" in 8h.

Main rule unchanged: **family data stays in the house.** Speech, text and model calls never leave home-ai.

### What exists today (checked 2026-10-27)

- Open WebUI v0.12.3 (`open-webui` container, port 3000) with a custom model **House** (`id: house`, base `qwen3.5:9b` via Ollama on the host) and one tool, `household_dates`. Two admin accounts. `ENABLE_OPENAI_API=false`.
- Ollama on the host: `qwen3.5:9b`, `qwen3.5:4b`, `nomic-embed-text`. home-ai is an M1 Pro with 16 GB RAM.
- calendar-api: `GET /calendars` (Family = default, "most events"; Benny Time = "events specific to our son, Ben"; both writable and shown in the kitchen), `GET /events`, `POST /events` (`title, date, start_time?, end_time?, duration_minutes?, calendar?, location?`), `PATCH`/`DELETE /events/{uid}` for House-made events only.
- No speech-to-text is set up anywhere.

## 2. Decisions (Bob, 2026-10-27)

| Topic | Decision |
|---|---|
| Brain | The existing **House** model in Open WebUI, called through Open WebUI's API with a new **Kitchen** account. |
| Speech-to-text | **whisper.cpp** running natively on home-ai (Metal), as a launchd service. Never the browser's Web Speech API. |
| Answers | **Text only** on screen. No text-to-speech. |
| Acting | The House **acts immediately**; the panel shows what changed with **Undo**. |
| History | Kept **only while the panel is open**. Nothing saved in Open WebUI. Writes are still logged. |
| Powers | Calendar add + read (change/delete only House-made events); TODOs add, read, check off, delete; general questions. |
| Which calendar | The model chooses using calendar-api's calendar purposes (Family default, Benny Time for Ben). |
| HTTPS | `tailscale serve` on **port 8082** (already allowed for family devices). Kiosk URL becomes `https://home-ai.<tailnet>.ts.net:8082`. |
| Microphone | On only after a tap on Talk. Auto-stop after ~1.5 s of silence or on Stop. |
| Live transcript | **Not in Part 2.** Sound bars while listening; words appear at "Thinking". (Deviation from 2b, approved.) |
| household-ai changes | Approved: 2 new tool files, Kitchen account, whisper launchd job, `tailscale serve`. |

## 3. Architecture

```
Kiosk / phone (HTTPS :8082 via tailscale serve, mic)
   │  WAV audio / text
   ▼
kitchen-dashboard (FastAPI)
   ├─ /api/talk/listen ──► whisper.cpp server on the Mac (127.0.0.1:8178)  → text
   ├─ /api/talk/message ─► Open WebUI /api/chat/completions (Kitchen key, model "house")
   │                          └─ House tools (Open WebUI, server-side)
   │                               ├─ household_dates (exists)
   │                               ├─ household_calendar (new) ─┐
   │                               └─ household_todos (new) ────┤
   └─ /api/house/*  ◄───────────────────────────────────────────┘  (token-protected)
          ├─ events → calendar-api
          ├─ todos  → SQLite (existing todos module)
          └─ every write → house_actions log (for change cards + Undo)
```

### 3.1 New dashboard units

| Unit | Job |
|---|---|
| `talk` | Talk sessions in memory: `id`, message history, last-used time. Ends on panel close or after 10 min idle. Builds the Open WebUI request, returns reply + changes. |
| `stt` | Sends 16 kHz mono WAV to whisper.cpp, returns text. Fake implementation for dev/CI. |
| `house_client` | Calls Open WebUI `/api/chat/completions`. Fake implementation for dev/CI. |
| `actions` | The `house_actions` table: record a change with its inverse; list a session's changes; undo one. |
| `house_api` | The `/api/house/*` routes used by the House tools. Token check. Proxies event writes to calendar-api, TODO writes to `todos`, and records every write in `actions`. |

### 3.2 Configuration (env, compose)

- `OPENWEBUI_URL=http://open-webui:8080` (same Docker network).
- `OPENWEBUI_KEY_FILE=/run/secrets/kitchen_openwebui_key` — mounted read-only from `~/household-ai/secrets/kitchen_openwebui_key`.
- `HOUSE_TOKEN_FILE=/run/secrets/house_tools_token` — mounted read-only from `~/household-ai/secrets/house_tools_token`.
- `WHISPER_URL=http://host.docker.internal:8178`. The build must confirm the container reaches the host's loopback service through OrbStack; if not, whisper listens on the Docker bridge address instead.
- Secrets are never committed, never logged, never sent to the browser.

### 3.3 whisper.cpp service (home-ai)

- Built from source with Metal; model `ggml-small.en` (~470 MB). If `small.en` is too slow alongside the House model, fall back to `base.en`.
- Runs `whisper-server --host 127.0.0.1 --port 8178 -m <model>` under launchd (`com.household.whisper`), restart on failure, log to `~/household-ai/logs/whisper.log`.
- Install script lives in this repo (`ops/install-whisper.sh`); it records the exact whisper.cpp git tag it built.

### 3.4 House tools (Open WebUI)

Source lives in this repo (`house_tools/household_calendar.py`, `house_tools/household_todos.py`) with tests. `ops/install-house-tools.sh` installs or updates them in Open WebUI through its admin API and copies them to `~/household-ai/tools/`. Each tool has Valves (admin settings in Open WebUI) for `dashboard_url` and `token`.

Every tool call sends `Authorization: Bearer <token>` and `X-Talk-Session: <__metadata__.chat_id>` when present.

**household_calendar**
- `list_calendars()` — names and purposes.
- `list_events(start_date, days)` — events with times in Chicago.
- `add_event(title, date, start_time?, end_time?, duration_minutes?, calendar?, location?)`
- `update_event(uid, …fields)` — House-made events only (calendar-api enforces).
- `delete_event(uid)` — House-made events only.

**household_todos**
- `list_todos(person, date?)` — today's list by default.
- `add_todo(person, text, date?, time?)` — date defaults to today; person by name (Bob, Belen, Ben).
- `complete_todo(todo_id)` / `reopen_todo(todo_id)`
- `delete_todo(todo_id)`

Tool return strings are short, factual sentences the model can repeat ("Added 'Dentist · Ben' to Family on Thu 29 Oct at 4:00 PM").

### 3.5 House endpoints (`/api/house/*`, token required)

| Method | Path | Does | Logged inverse |
|---|---|---|---|
| GET | `/api/house/calendars` | calendar-api `/calendars` | – |
| GET | `/api/house/events?start&days` | calendar-api `/events` | – |
| POST | `/api/house/events` | calendar-api `POST /events` | delete the new uid |
| PATCH | `/api/house/events/{uid}` | reads the event first, then `PATCH` | PATCH back to the old fields |
| DELETE | `/api/house/events/{uid}` | reads the event first, then `DELETE` | re-create it (new uid) |
| GET | `/api/house/todos?person&date` | `todos.today_view` for that person | – |
| POST | `/api/house/todos` | `todos.create(created_by="house")` | delete it |
| POST | `/api/house/todos/{id}/done` and `/reopen` | `todos.update(done=…)` | the opposite |
| DELETE | `/api/house/todos/{id}` | reads it first, then deletes | re-create it |

calendar-api refusals are returned as-is with their message. After any event write the calendar cache is invalidated.

`house_actions(id, session_id NULL, kind, label, detail, calendar, color, payload JSON, inverse JSON, created_at, undone_at NULL)`. Rows from Open WebUI chats outside the kitchen have `session_id` NULL; they are logged but not shown.

### 3.6 Talk endpoints (no token; tailnet only, like the rest of the page)

| Method | Path | Body → result |
|---|---|---|
| POST | `/api/talk/sessions` | `{context?: {event_uid}}` → `{id}` |
| GET | `/api/talk/sessions/{id}` | → `{busy, changes: [Change]}` (used after Cancel to pick up late changes) |
| DELETE | `/api/talk/sessions/{id}` | ends it (after any in-flight call finishes) |
| POST | `/api/talk/listen` | `audio/wav` (≤ 30 s, ≤ 2 MB) → `{text}`; empty text means "didn't catch that" |
| POST | `/api/talk/message` | `{session_id, text}` → `{reply, changes: [Change]}` |
| POST | `/api/talk/actions/{id}/undo` | → `{ok}` or 409 with a message |

`Change = {id, verb: "ADDED"|"CHANGED"|"REMOVED"|"DONE"|"REOPENED", title, detail, calendar?, person?, color, ink, undone}` — `detail` is the chip line, e.g. `THU 29 · 4:00 PM`.

`/api/talk/message`:
1. Appends the user text to the session.
2. Calls Open WebUI with `model: "house"`, the session's messages, `tool_ids: ["household_dates", "household_calendar", "household_todos"]`, `chat_id: <session id>`, non-streaming, timeout 60 s. A short system message adds: today's date and time in Chicago, the family (Bob, Belen, Ben), "act directly, then say what you did in one or two sentences", and, when the session has a context event, that event's details.
3. Collects `house_actions` rows for this session created during the call. **Fallback** if `chat_id` does not reach the tools: rows from requests carrying no session header, created during this call, are attributed to it (the build confirms which path works).
4. Returns `reply` and the changes.

The open session and history live only in dashboard memory; Open WebUI is not asked to save the chat.

## 4. Screens

All sizes, colors and copy follow `docs/design/README.md` ("Talk to the house"), with these behaviors:

- **2b Listening:** opens from the Talk button in 250 ms; asks for the mic; sound bars driven by the mic level; `● LISTENING`; **Stop** (ends and closes) and **Type instead**. Auto-stop after ~1.5 s of silence once speech has started, or after 15 s.
- **5a Thinking:** transcript shown muted; bouncing dots; **Cancel** closes the panel and stops waiting. The server lets the Open WebUI call finish; if it made changes, the wall shows the 5c toast with **UNDO** for them (the page asks `/api/talk/sessions/{id}` for late changes before ending the session).
- **5b Answer:** reply text; one change card per change (filled chip in the calendar's color, or person name for TODOs; verb pill); **Undo** (per card when several), **Ask more** (listens again in the same session), **Done**. Auto-closes 20 s after the answer with no touch.
- **5c Close:** new or changed chips glow with the 8 px success outline for 3 s; toast with **UNDO** for 6 s (undoes all changes from that answer).
- **5d Didn't catch that:** shown when listen returns empty text. **Say it again** and **Never mind**.
- **8g Type instead:** on-screen QWERTY keyboard (kiosk); suggestion pills; **Send** → Thinking.
- **8e Night:** the dark variant while night mode is on.
- **3a Change by voice** (kitchen) and **8h Ask the house to change it** (phone): open Talk with that event as the session context.
- **Phone 4d:** chat thread with the same API; mic button (tap to start/stop) and a text field (system keyboard); change cards with Undo.
- The Talk button on the wall and on phones becomes active; it shows a disabled state when the page is not on HTTPS (no mic) and offers Type instead.

## 5. Errors

| Failure | Behavior |
|---|---|
| Mic permission denied or not HTTPS | Message "The microphone is off for this screen" + **Type instead**. |
| whisper.cpp unreachable / error | "Voice isn't working right now" + **Type instead**. |
| Open WebUI slow | Thinking up to 60 s, Cancel available. |
| Open WebUI down / 5xx / timeout | "The house isn't answering" + **Try again** (re-sends the same text). |
| Tool failure / calendar-api refusal | The House's reply says so; no change card for it. |
| Undo fails (e.g. event already gone) | Toast "Couldn't undo"; card stays, marked unchanged. |
| Bad or missing House token | 401 to the tool; the tool returns "I can't reach the kitchen dashboard". |

## 6. Testing

- **pytest (server):** session create/end/expiry; listen with a fake whisper (WAV in, text out, empty → empty); message flow with a fake House that triggers `/api/house/*` writes and returns a reply; change collection per session and the fallback attribution; every House endpoint's write + inverse + undo (event add/update/delete, TODO add/done/reopen/delete); token required (401 without); calendar-api refusal pass-through; cache invalidation after event writes; size/length limits on listen.
- **House tools:** unit tests with a fake dashboard (requests, headers, Valves, error strings). Tests run in this repo's CI.
- **Fake mode:** `DASHBOARD_FAKE=1` uses the fake whisper and fake House so the whole panel works on a laptop.
- **Browser checks** (ego-browser) for each screen against the design cards.
- **Live:** a real end-to-end test on the kiosk and on a phone; confirm OrbStack host access to whisper and that `chat_id` reaches the tools.

## 7. Rollout

1. **home-ai setup (Bob + Claude):** build and load whisper.cpp; `tailscale serve --https=8082 http://localhost:8081` (enable HTTPS certificates in the Tailscale admin if needed); Kitchen account in Open WebUI (role user, House model only, API key); create the two secret files.
2. **Server parts**, tested in fake mode; compose mounts the secrets.
3. **Screens.**
4. **Install the House tools** with the script; set their Valves.
5. **Kiosk:** Bob changes `KIOSK_URL` to `https://home-ai.<tailnet>.ts.net:8082` and allows the mic for that origin only (Chromium policy `AudioCaptureAllowedUrls`), then restarts the kiosk. Phones bookmark the HTTPS address.
6. Live test; adjust from Bob's feedback.

Work happens on a branch with a PR; `main` deploys to the kitchen.

## 8. Out of scope

Live transcript while speaking; spoken answers; wake word / always-listening; per-person voice recognition; saving kitchen conversations; bills; the photo slideshow (Part 3).

## 9. Done when

- Tapping Talk on the kiosk, saying "add a TODO for Ben to feed Milo", shows an ADDED card, and Ben's card on the wall shows the item within ~10 s; Undo removes it.
- "Add a dentist appointment for Ben on Thursday at 4" adds a Benny Time (or Family) event, the chip glows on the wall, and Undo removes it.
- "What's on Saturday?" answers from the calendar without changing anything.
- The same works from a phone (4d), and Type instead works on the kiosk.
- whisper, Open WebUI or mic failures show the right message and never leave the panel stuck.
- No audio, text or key leaves home-ai; secrets are not in the repo, logs or browser.
- All tests pass in CI; `CLAUDE.md` describes the new parts and setup.
