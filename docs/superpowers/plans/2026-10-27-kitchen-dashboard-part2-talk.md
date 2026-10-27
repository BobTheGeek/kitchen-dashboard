# Kitchen Dashboard Part 2 (Talk to the house) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn on "Talk to the house": a voice/text panel on the kitchen screen and phones that sends what people say to the local House (Open WebUI), lets the House change the calendar and TODOs through new tools, and shows each change with Undo.

**Architecture:** The dashboard gains five server units: `actions` (change log with inverses), `house` (`HouseOps`: every House write, logged), `talk` (whisper client, Open WebUI client, fakes, sessions, `TalkService`), plus `/api/house/*` (token-protected, used by two new Open WebUI tools) and `/api/talk/*` (used by the page). The page gains `talk.js` (mic → 16 kHz WAV, silence detection, API), `talk-wall.js` (kitchen panel) and `talk-phone.js` (phone thread). whisper.cpp runs natively on home-ai under launchd; Open WebUI is reached on the Docker network.

**Tech Stack:** Python 3.13, FastAPI 0.120.0, stdlib `urllib` for all outbound HTTP (no new dependencies), SQLite, plain ES modules (Web Audio API), whisper.cpp (`whisper-server`, Metal), Open WebUI v0.12.3 tools (Python, pydantic Valves), `tailscale serve`.

**Spec:** `docs/superpowers/specs/2026-10-27-kitchen-dashboard-part2-talk-design.md`
**Design:** `docs/design/README.md` section "Talk to the house"; print a card with `.venv/bin/python -I scripts/design_card.py 2b` (also `5a`, `5b`, `5c`, `5d`, `8g`, `8e`, `4d`, `3a`, `8h`).

## Global Constraints

- Family data stays in the house: audio, text and model calls never leave home-ai. No CDNs, web fonts, analytics or third-party APIs. System fonts only.
- Never use the browser Web Speech API. Speech-to-text is whisper.cpp at `WHISPER_URL` only.
- Secrets (`openwebui_key`, `house_token`) live only in `~/household-ai/secrets/kitchen/` on home-ai, mounted read-only at `/run/kitchen-secrets/`. Never commit, log, return in an API response, or send them to the browser.
- `/api/house/*` requires `Authorization: Bearer <house_token>` (constant-time compare). Missing token config → 503 `House tools are not set up on the dashboard`.
- All dates and times America/Chicago, computed in code. Never slice calendar ISO strings for timed events.
- Kitchen: touch only, tap targets ≥ 100px, nothing below 30px. Phone: ≥ 48px targets.
- Escape all model, calendar and TODO text with `esc()` before inserting into the DOM.
- The family is fixed at Bob, Belen, Ben (no adding or removing people).
- calendar-api write contract (verified 2026-10-27): `POST /events` body `{title, date, start_time?, end_time?, duration_minutes?, calendar?, location?, notes?}` → 200 `{"saved": true, "event": {...uid...}}`; `PATCH /events/{uid}` body `{title?, date?, start_time?, end_time?, location?, notes?}` → 200 `{"saved": true, "event": {...}}`; `DELETE /events/{uid}` → 200 `{"deleted": true, "title", "when"}`; errors 400/403/404/502 with `{"detail": "..."}`. House may change or delete only events it created.
- Open WebUI (verified): `POST /api/chat/completions` with `Authorization: Bearer <key>`; body fields `model`, `messages`, `tool_ids`, `session_id`, `stream`; tools receive `__metadata__["session_id"]`. Tools are created with `POST /api/v1/tools/create` `{id, name, content, meta: {description}}` and updated with `POST /api/v1/tools/id/{id}/update`; Valves via `POST /api/v1/tools/id/{id}/valves/update`.
- Tailscale name: `home-ai.tailfa3a6f.ts.net`. HTTPS for the mic is served on port 8082 by `tailscale serve`.
- Design talk values (README): sheet 2200×1480 at left 400 top 260, radius 80, padding 80×96, shadow `0 60px 160px rgba(0,0,0,.35)`; typing sheet 2400×1700 at left 300 top 160; dashboard behind: opacity .35, blur 6px, overlay `rgba(28,27,31,.45)`; header mono 600/36 letter-spacing .12em; waveform 16 bars 44 wide gap 28 max 400 tall accent; transcript 500/72; buttons 200 high (Stop, Say it again), outline 6px `#e6e3ee`; answer reply 500/72; change card bg `#f4f2f7` radius 48 padding 32×40, `ADDED` pill green mono 600/32; keyboard keys 120 high radius 24 bg `#f4f2f7` 600/48, modifiers `#e6e3ee` mono 36, bottom row 140; night sheet bg `#1a1920`, 3px `#2a2832` border, header `#9d87e6`, Stop pill `#e8e2d6` text `#0f0e12`; toast ink pill padding 36×48, 56px green check, 500/44, `UNDO` mono outline; new chip glow 8px `#2fb36a` outline offset 6 for 3 s; panel auto-closes 20 s after Answer with no touch.
- Work on a branch; `main` deploys to the kitchen. Commit trailer: `Co-Authored-By: Claude <model> <noreply@anthropic.com>` naming the model that wrote the commit.

## File Structure

```
app/store.py               + house_actions table
app/labels.py              + chip_detail()
app/actions.py             NEW: change log with inverses
app/calendar.py            + HttpSource._send/create/update/find, FixtureSource create/update/find,
                             CalendarService create/update/find, local(), fields_from_event()
app/house.py               NEW: HouseOps (logged House writes + undo)
app/talk.py                NEW: TalkError, WhisperClient, FakeWhisper, OpenWebUIClient, FakeHouse, Sessions, TalkService
app/api.py                 + /api/house/*, /api/talk/*, wiring (env, secrets, fakes)
app/static/js/talk.js      NEW: Recorder (mic → 16 kHz WAV, silence), talkApi
app/static/js/talk-wall.js NEW: kitchen panel (2b, 5a–5d, 8g, 8e) + undo toast + glow
app/static/js/talk-phone.js NEW: phone thread (4d)
app/static/js/kitchen.js   + Talk button, Change by voice (3a)
app/static/js/phone.js     + talk screen, Ask the house (8h)
app/static/css/kitchen.css + talk panel styles
app/static/css/phone.css   + thread styles
house_tools/household_calendar.py  NEW Open WebUI tool
house_tools/household_todos.py     NEW Open WebUI tool
ops/install-whisper.sh, ops/install-house-tools.sh  NEW
docker-compose.yml, ops/deploy-here.sh  + secrets mount, env
tests/test_actions.py, test_house_api.py, test_talk.py, test_house_tools.py  NEW; tests/fakes.py extended
CLAUDE.md, README.md
```

---

### Task 1: Action log and chip detail label

**Files:**
- Modify: `app/store.py` (SCHEMA), `app/labels.py`
- Create: `app/actions.py`, `tests/test_actions.py`
- Modify: `tests/test_labels.py`

**Interfaces:**
- Produces: table `house_actions`; `labels.chip_detail(d: date, at: datetime | time | None) -> str` (`"THU 29 · 4:00 PM"` or `"THU 29"`); `actions.record(con, now, *, session_id, kind, verb, title, detail, ref=None, calendar=None, person=None, inverse=None) -> dict`, `actions.get(con, id) -> dict | None`, `actions.last_id(con) -> int`, `actions.claim_unattributed(con, session_id, after_id) -> int`, `actions.for_session(con, session_id, after_id=0) -> list[dict]`, `actions.mark_undone(con, id, now) -> None`. Row dicts have keys `id, session_id, kind, verb, title, detail, ref, calendar, person, inverse (dict|None), created_at, undone_at`.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_labels.py`:
```python
def test_chip_detail():
    thu = date(2026, 10, 29)
    assert labels.chip_detail(thu, at(16, 0, thu)) == "THU 29 · 4:00 PM"
    assert labels.chip_detail(thu, None) == "THU 29"
```

`tests/test_actions.py`:
```python
from app import actions


def rec(con, now, sid="s1", **kw):
    base = dict(session_id=sid, kind="todo", verb="ADDED", title="Feed Milo", detail="TUE 27", ref="5",
                person="Ben", inverse={"op": "delete_todo", "id": 5})
    return actions.record(con, now, **(base | kw))


def test_record_and_get(con, freeze):
    now = freeze("2026-10-27T09:00")
    a = rec(con, now)
    got = actions.get(con, a["id"])
    assert got["inverse"] == {"op": "delete_todo", "id": 5} and got["undone_at"] is None
    assert got["created_at"].startswith("2026-10-27T09:00") and got["ref"] == "5"


def test_for_session_and_after(con, freeze):
    now = freeze("2026-10-27T09:00")
    a1 = rec(con, now)
    rec(con, now, sid="other")
    a3 = rec(con, now, title="Second")
    assert [a["title"] for a in actions.for_session(con, "s1")] == ["Feed Milo", "Second"]
    assert [a["id"] for a in actions.for_session(con, "s1", after_id=a1["id"])] == [a3["id"]]


def test_claim_unattributed(con, freeze):
    now = freeze("2026-10-27T09:00")
    before = actions.last_id(con)
    rec(con, now, sid=None)
    assert actions.claim_unattributed(con, "s2", before) == 1
    assert [a["session_id"] for a in actions.for_session(con, "s2")] == ["s2"]


def test_mark_undone_and_no_inverse(con, freeze):
    now = freeze("2026-10-27T09:00")
    a = rec(con, now, inverse=None)
    assert actions.get(con, a["id"])["inverse"] is None
    actions.mark_undone(con, a["id"], now)
    assert actions.get(con, a["id"])["undone_at"] is not None
    assert actions.get(con, 999) is None
```

Run: `.venv/bin/pytest -q tests/test_actions.py tests/test_labels.py` → FAIL (`ImportError: cannot import name 'actions'`, `AttributeError: chip_detail`).

- [ ] **Step 2: Implement**

Append to `SCHEMA` in `app/store.py` (inside the string, after `meta`):
```sql
create table if not exists house_actions (
    id integer primary key,
    session_id text,
    kind text not null,
    verb text not null,
    title text not null,
    detail text not null,
    ref text,
    calendar text,
    person text,
    inverse text,
    created_at text not null,
    undone_at text
);
```

Append to `app/labels.py`:
```python
def chip_detail(d: date, at: datetime | time | None) -> str:
    """Change-card line: 'THU 29 · 4:00 PM', or 'THU 29' with no time."""
    head = f"{d.strftime('%a').upper()} {d.day}"
    return head if at is None else f"{head} · {clock_time(at)}"
```

`app/actions.py`:
```python
"""House action log: every change the House makes, with how to reverse it (change cards and Undo)."""
import json
import sqlite3
from datetime import datetime

COLUMNS = "id, session_id, kind, verb, title, detail, ref, calendar, person, inverse, created_at, undone_at"


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["inverse"] = json.loads(d["inverse"]) if d["inverse"] else None
    return d


def record(con: sqlite3.Connection, now: datetime, *, session_id: str | None, kind: str, verb: str, title: str,
           detail: str, ref: str | None = None, calendar: str | None = None, person: str | None = None,
           inverse: dict | None = None) -> dict:
    with con:
        cur = con.execute(
            "insert into house_actions (session_id, kind, verb, title, detail, ref, calendar, person, inverse, created_at)"
            " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, kind, verb, title, detail, ref, calendar, person,
             json.dumps(inverse) if inverse is not None else None, now.isoformat(timespec="seconds")))
    return get(con, cur.lastrowid)


def get(con: sqlite3.Connection, action_id: int) -> dict | None:
    r = con.execute(f"select {COLUMNS} from house_actions where id = ?", (action_id,)).fetchone()
    return _row(r) if r else None


def last_id(con: sqlite3.Connection) -> int:
    return con.execute("select coalesce(max(id), 0) from house_actions").fetchone()[0]


def claim_unattributed(con: sqlite3.Connection, session_id: str, after_id: int) -> int:
    """Fallback when a tool call carried no session id: give this session the unowned rows made during its call."""
    with con:
        cur = con.execute("update house_actions set session_id = ? where session_id is null and id > ?",
                          (session_id, after_id))
    return cur.rowcount


def for_session(con: sqlite3.Connection, session_id: str, after_id: int = 0) -> list[dict]:
    rows = con.execute(f"select {COLUMNS} from house_actions where session_id = ? and id > ? order by id",
                       (session_id, after_id))
    return [_row(r) for r in rows]


def mark_undone(con: sqlite3.Connection, action_id: int, now: datetime) -> None:
    with con:
        con.execute("update house_actions set undone_at = ? where id = ?",
                    (now.isoformat(timespec="seconds"), action_id))
```

- [ ] **Step 3: Verify and commit**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check .` → all pass.
```bash
git add app/store.py app/labels.py app/actions.py tests/test_actions.py tests/test_labels.py
git commit -m "Add House action log and change-card detail label"
```

---

### Task 2: Calendar writes (create, update, find)

**Files:**
- Modify: `app/calendar.py`, `tests/fakes.py`, `tests/test_calendar.py`

**Interfaces:**
- Produces: `calendar.local(value: str | None) -> datetime | None` (rename of `_local`; keep `_local = local` alias for existing callers); `calendar.fields_from_event(ev: dict) -> dict` (calendar-api NewEvent fields: `title, date, start_time?, end_time?, calendar, location`); `HttpSource.create(fields) -> (int, dict)`, `.update(uid, fields) -> (int, dict)`, `.find(uid, start: date, days: int) -> dict | None` (raises `CalendarError`); same three on `FixtureSource`; `CalendarService.create/update(...)` (invalidate cache on success) and `.find(uid) -> dict | None` (cache first, then source over 60 days).
- `FakeSource` in `tests/fakes.py` gains `create`, `update`, `find` with recorded calls and settable results.

- [ ] **Step 1: Write failing tests** — append to `tests/test_calendar.py`:
```python
def test_fields_from_event_timed_and_all_day():
    timed = ev("Family", "Dentist", "2026-10-29T21:00:00Z", "2026-10-29T21:45:00Z", location="Dr. Osei")
    assert cal.fields_from_event(timed) == {"title": "Dentist", "calendar": "Family", "location": "Dr. Osei",
                                            "date": "2026-10-29", "start_time": "16:00", "end_time": "16:45"}
    allday = ev("Family", "Halloween", "2026-10-31", "2026-11-01", all_day=True)
    assert cal.fields_from_event(allday) == {"title": "Halloween", "calendar": "Family", "location": None,
                                             "date": "2026-10-31"}


def test_fixture_create_update_find_delete(tmp_path, freeze):
    p = tmp_path / "f.json"
    p.write_text('{"events": []}')
    freeze("2026-10-27T08:00")
    src = cal.FixtureSource(p)
    status, body = src.create({"title": "Dentist", "date": "2026-10-29", "start_time": "16:00", "duration_minutes": 45})
    uid = body["event"]["uid"]
    assert status == 200 and body["saved"] and body["event"]["added_by_house"]
    assert src.find(uid, None, 0)["title"] == "Dentist"
    status, body = src.update(uid, {"title": "Dentist · Ben", "start_time": "15:00"})
    assert status == 200 and cal.local(body["event"]["start"]).hour == 15 and body["event"]["title"] == "Dentist · Ben"
    assert src.delete(uid)[0] in (200, 204)
    assert src.find(uid, None, 0) is None


def test_service_create_invalidates(store, freeze):
    src = FakeSource([])
    svc = cal.CalendarService(src, store)
    freeze("2026-10-27T09:00")
    svc.events()
    src.create_result = (200, {"saved": True, "event": ev("Family", "New", "2026-10-28T10:00:00-05:00", uid="n1",
                                                           house=True)})
    assert svc.create({"title": "New", "date": "2026-10-28"})[0] == 200
    svc.events()
    assert src.calls == 2


def test_service_find_uses_cache_then_source(store, freeze):
    src = FakeSource([ev("Family", "a", "2026-10-27T10:00:00-05:00", uid="u1")])
    svc = cal.CalendarService(src, store)
    freeze("2026-10-27T09:00")
    svc.events()
    assert svc.find("u1")["title"] == "a"
    src.found = ev("Family", "far", "2026-12-01T10:00:00-06:00", uid="u9")
    assert svc.find("u9")["title"] == "far"
```

In `tests/fakes.py`, extend `FakeSource.__init__` and add methods:
```python
        self.create_result = (200, {"saved": True, "event": {}})
        self.update_result = (200, {"saved": True, "event": {}})
        self.created = []
        self.updated = []
        self.found = None

    def create(self, fields):
        self.created.append(fields)
        return self.create_result

    def update(self, uid, fields):
        self.updated.append((uid, fields))
        return self.update_result

    def find(self, uid, start, days):
        if self.fail:
            raise CalendarError("calendar-api unavailable")
        if self.found and self.found["uid"] == uid:
            return self.found
        return next((e for e in self.items if e["uid"] == uid), None)
```
(Place the new attributes inside `__init__` after `self.deleted = []`; the methods after `delete`.)

Run the four tests → FAIL (`AttributeError: fields_from_event`).

- [ ] **Step 2: Implement in `app/calendar.py`**

Rename `_local` to `local` (keep `_local = local` right after it). Add after `local`:
```python
def fields_from_event(ev: dict) -> dict:
    """calendar-api event → NewEvent fields (used to re-create or restore an event on Undo)."""
    out = {"title": ev["title"], "calendar": ev.get("calendar"), "location": ev.get("location")}
    if ev.get("all_day"):
        out["date"] = date.fromisoformat(ev["start"][:10]).isoformat()  # all-day start is a plain date
        return out
    start, end = local(ev["start"]), local(ev.get("end"))
    out |= {"date": start.date().isoformat(), "start_time": start.strftime("%H:%M")}
    if end is not None:
        out["end_time"] = end.strftime("%H:%M")
    return out
```

Replace `HttpSource.delete` with a shared sender and add the new methods:
```python
    def _send(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.base_url}{path}", data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, {"detail": raw.decode(errors="replace") or e.reason}
        except Exception as e:
            return 502, {"detail": f"calendar-api unavailable: {type(e).__name__}"}

    def delete(self, uid: str) -> tuple[int, dict]:
        return self._send("DELETE", f"/events/{urllib.parse.quote(uid, safe='')}")

    def create(self, fields: dict) -> tuple[int, dict]:
        return self._send("POST", "/events", fields)

    def update(self, uid: str, fields: dict) -> tuple[int, dict]:
        return self._send("PATCH", f"/events/{urllib.parse.quote(uid, safe='')}", fields)

    def find(self, uid: str, start: date, days: int) -> dict | None:
        status, body = self._send("GET", "/events?" + urllib.parse.urlencode({"start": start.isoformat(), "days": days}))
        if status >= 300:
            raise CalendarError(body.get("detail", "calendar-api error"))
        return next((e for e in body.get("events", []) if e["uid"] == uid), None)
```

In `FixtureSource`: add `self.extra: list[dict] = []` and `self._n = 0` in `__init__`; in `_materialize` return `[e for e in out if e["uid"] not in self.deleted] + list(self.extra)`; then add:
```python
    def _event(self, fields: dict, uid: str) -> dict:
        d = date.fromisoformat(fields["date"])
        if fields.get("start_time"):
            hh, mm = map(int, fields["start_time"].split(":"))
            s = datetime(d.year, d.month, d.day, hh, mm, tzinfo=clock.TZ)
            if fields.get("end_time"):
                eh, em = map(int, fields["end_time"].split(":"))
                e = s.replace(hour=eh, minute=em)
            else:
                e = s + timedelta(minutes=int(fields.get("duration_minutes") or 60))
            start, end, all_day = s.isoformat(), e.isoformat(), False
        else:
            start, end, all_day = d.isoformat(), (d + timedelta(days=1)).isoformat(), True
        return {"calendar": fields.get("calendar") or "Family", "title": fields["title"], "when": "", "start": start,
                "end": end, "all_day": all_day, "location": fields.get("location"), "uid": uid, "added_by_house": True}

    def create(self, fields: dict) -> tuple[int, dict]:
        self._n += 1
        ev = self._event(fields, f"fake-new-{self._n}")
        self.extra.append(ev)
        return 200, {"saved": True, "event": ev}

    def find(self, uid: str, start, days) -> dict | None:
        return next((e for e in self._materialize() if e["uid"] == uid), None)

    def update(self, uid: str, fields: dict) -> tuple[int, dict]:
        cur = self.find(uid, None, 0)
        if cur is None:
            return 404, {"detail": f"No House-created event with uid {uid}."}
        if not cur["added_by_house"]:
            return 403, {"detail": "House can only change or delete events it created."}
        new = self._event(fields_from_event(cur) | {k: v for k, v in fields.items() if v is not None}, uid)
        self.extra = [e for e in self.extra if e["uid"] != uid]
        self.deleted.add(uid)  # hides the base copy if it was a fixture event
        self.extra.append(new)
        return 200, {"saved": True, "event": new}
```
and make `delete` remove from `self.extra` first:
```python
    def delete(self, uid: str) -> tuple[int, dict]:
        if any(e["uid"] == uid for e in self.extra):
            self.extra = [e for e in self.extra if e["uid"] != uid]
            return 204, {}
        ...existing body...
```

Add to `CalendarService`:
```python
    def create(self, fields: dict) -> tuple[int, dict]:
        status, body = self.source.create(fields)
        if status < 300:
            self.invalidate()
        return status, body

    def update(self, uid: str, fields: dict) -> tuple[int, dict]:
        status, body = self.source.update(uid, fields)
        if status < 300:
            self.invalidate()
        return status, body

    def find(self, uid: str) -> dict | None:
        for e in (self._mem[2] if self._mem else []):
            if e["uid"] == uid:
                return e
        return self.source.find(uid, clock.now().date(), 60)
```

- [ ] **Step 3: Verify and commit**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check .` → all pass (the existing fixture delete test still returns `(204, {})`).
```bash
git add app/calendar.py tests/fakes.py tests/test_calendar.py
git commit -m "Add calendar create, update and find for House writes"
```

---

### Task 3: HouseOps and the /api/house endpoints

**Files:**
- Create: `app/house.py`, `tests/test_house_api.py`
- Modify: `app/api.py`

**Interfaces:**
- Consumes: Tasks 1–2; `todos.create/update/get/delete/today_view`; `settings.people`.
- Produces: `HouseOps(cal)` with `add_event(con, now, sid, fields) -> (int, dict)`, `update_event(con, now, sid, uid, fields) -> (int, dict)`, `delete_event(con, now, sid, uid) -> (int, dict)`, `add_todo(con, now, sid, *, person, text, date, time=None) -> dict` (raises `LookupError(message)`), `set_todo_done(con, now, sid, todo_id, done) -> dict` (raises `KeyError`), `delete_todo(con, now, sid, todo_id) -> dict` (raises `KeyError`), `undo(con, now, action_id) -> (bool, str)`, `person_name(con, person_id) -> str`.
- `create_app(db_path=None, source=None, version=None, whisper=None, house=None, house_token=None)` — `house_token` used by `/api/house/*`. (`whisper`/`house` are wired in Task 4; accept and ignore them here.)
- HTTP: as spec §3.5. `GET /api/house/todos?person=` → `{"person", "date", "todos": [today-view items]}` (today only).

- [ ] **Step 1: Write failing tests** — `tests/test_house_api.py`:
```python
import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from tests.fakes import FakeSource, ev

TOKEN = "t0ken"
AUTH = {"Authorization": f"Bearer {TOKEN}", "X-Talk-Session": "s1"}


@pytest.fixture
def src():
    return FakeSource([ev("Family", "Soccer", "2026-10-27T17:30:00-05:00", uid="u1"),
                       ev("Family", "House thing", "2026-10-28T10:00:00-05:00", "2026-10-28T11:00:00-05:00",
                          uid="h1", house=True)])


@pytest.fixture
def client(tmp_path, src, freeze):
    freeze("2026-10-27T09:00")
    return TestClient(create_app(db_path=str(tmp_path / "h.db"), source=src, version="t", house_token=TOKEN))


def test_token_required(client):
    assert client.get("/api/house/calendars").status_code == 401
    assert client.get("/api/house/calendars", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_not_configured(tmp_path, src, freeze):
    freeze("2026-10-27T09:00")
    c = TestClient(create_app(db_path=str(tmp_path / "n.db"), source=src, version="t", house_token=""))
    r = c.get("/api/house/calendars", headers=AUTH)
    assert r.status_code == 503 and "not set up" in r.json()["detail"]


def test_add_todo_logs_and_undo(client):
    r = client.post("/api/house/todos", headers=AUTH, json={"person": "ben", "text": "Feed Milo"})
    assert r.status_code == 201
    todo = r.json()
    assert todo["person"] == "Ben" and todo["created_by"] == "house" and todo["date"] == "2026-10-27"
    changes = client.get("/api/talk/sessions/s1").json()["changes"]
    assert [(c["verb"], c["title"], c["person"]) for c in changes] == [("ADDED", "Feed Milo", "Ben")]
    assert client.post(f"/api/talk/actions/{changes[0]['id']}/undo").json() == {"ok": True}
    ben = next(p for p in client.get("/api/today").json()["people"] if p["name"] == "Ben")
    assert ben["todos"] == []


def test_unknown_person(client):
    r = client.post("/api/house/todos", headers=AUTH, json={"person": "Ana", "text": "x"})
    assert r.status_code == 404 and "Bob, Belen and Ben" in r.json()["detail"]


def test_done_reopen_delete_and_undo(client):
    tid = client.post("/api/house/todos", headers=AUTH, json={"person": "Bob", "text": "Call"}).json()["id"]
    assert client.post(f"/api/house/todos/{tid}/done", headers=AUTH).json()["done"] is True
    assert client.post(f"/api/house/todos/{tid}/reopen", headers=AUTH).json()["done"] is False
    assert client.delete(f"/api/house/todos/{tid}", headers=AUTH).status_code == 200
    removed = client.get("/api/talk/sessions/s1").json()["changes"][-1]
    assert removed["verb"] == "REMOVED"
    client.post(f"/api/talk/actions/{removed['id']}/undo")
    bob = next(p for p in client.get("/api/today").json()["people"] if p["name"] == "Bob")
    assert [t["text"] for t in bob["todos"]] == ["Call"]
    assert client.post("/api/house/todos/999/done", headers=AUTH).status_code == 404


def test_list_todos(client):
    client.post("/api/house/todos", headers=AUTH, json={"person": "Ben", "text": "Homework", "time": "16:00"})
    body = client.get("/api/house/todos", headers=AUTH, params={"person": "Ben"}).json()
    assert body["person"] == "Ben" and body["todos"][0]["time_label"] == "4:00 PM"


def test_add_event_logs_inverse(client, src):
    src.create_result = (200, {"saved": True, "event": ev("Benny Time", "Dentist", "2026-10-29T16:00:00-05:00",
                                                           uid="n1", house=True)})
    r = client.post("/api/house/events", headers=AUTH, json={"title": "Dentist", "date": "2026-10-29",
                                                             "start_time": "16:00", "calendar": "Benny Time"})
    assert r.status_code == 200 and src.created[0]["calendar"] == "Benny Time"
    c = client.get("/api/talk/sessions/s1").json()["changes"][0]
    assert (c["verb"], c["detail"], c["calendar"], c["ref"]) == ("ADDED", "THU 29 · 4:00 PM", "Benny Time", "n1")
    client.post(f"/api/talk/actions/{c['id']}/undo")
    assert src.deleted == ["n1"]


def test_update_and_delete_event_inverse(client, src):
    src.update_result = (200, {"saved": True, "event": ev("Family", "House thing", "2026-10-28T12:00:00-05:00",
                                                          uid="h1", house=True)})
    client.patch("/api/house/events/h1", headers=AUTH, json={"start_time": "12:00"})
    changed = client.get("/api/talk/sessions/s1").json()["changes"][0]
    client.post(f"/api/talk/actions/{changed['id']}/undo")
    assert src.updated[-1] == ("h1", {"title": "House thing", "location": None, "date": "2026-10-28",
                                      "start_time": "10:00", "end_time": "11:00"})
    src.delete_result = (200, {"deleted": True, "title": "House thing", "when": "Wed"})
    assert client.delete("/api/house/events/h1", headers=AUTH).status_code == 200
    removed = client.get("/api/talk/sessions/s1").json()["changes"][-1]
    client.post(f"/api/talk/actions/{removed['id']}/undo")
    assert src.created[-1]["title"] == "House thing" and src.created[-1]["start_time"] == "10:00"


def test_calendar_refusal_passes_through_and_is_not_logged(client, src):
    src.update_result = (403, {"detail": "House can only change or delete events it created."})
    r = client.patch("/api/house/events/u1", headers=AUTH, json={"title": "x"})
    assert r.status_code == 403 and "House can only" in r.json()["detail"]
    assert client.get("/api/talk/sessions/s1").json()["changes"] == []


def test_undo_twice_and_unknown(client):
    tid = client.post("/api/house/todos", headers=AUTH, json={"person": "Bob", "text": "x"}).json()["id"]
    assert tid
    aid = client.get("/api/talk/sessions/s1").json()["changes"][0]["id"]
    assert client.post(f"/api/talk/actions/{aid}/undo").json() == {"ok": True}
    assert client.post(f"/api/talk/actions/{aid}/undo").json() == {"ok": True}
    assert client.post("/api/talk/actions/999/undo").status_code == 409
```

Run: `.venv/bin/pytest -q tests/test_house_api.py` → FAIL (`TypeError: create_app() got an unexpected keyword argument 'house_token'`).

Note: `GET /api/talk/sessions/{id}` and the undo route are created in this task in a minimal form (changes only) so the House tests can observe the log; Task 4 extends the session route with `busy`.

- [ ] **Step 2: Implement `app/house.py`**
```python
"""What the House may do through the dashboard: calendar and TODO writes, each logged with its inverse for Undo."""
import sqlite3
from datetime import date, datetime, time

from app import actions, labels, settings, todos
from app.calendar import CalendarError, CalendarService, fields_from_event, local


def event_detail(ev: dict) -> str:
    if ev.get("all_day"):
        return labels.chip_detail(date.fromisoformat(ev["start"][:10]), None) + " · ALL DAY"
    start = local(ev["start"])
    return labels.chip_detail(start.date(), start)


def todo_detail(item: dict) -> str:
    at = time.fromisoformat(item["time"]) if item.get("time") else None
    return labels.chip_detail(date.fromisoformat(item["date"]), at)


class HouseOps:
    def __init__(self, cal: CalendarService):
        self.cal = cal

    def person_name(self, con: sqlite3.Connection, person_id: int) -> str:
        return next((p["name"] for p in settings.people(con) if p["id"] == person_id), "?")

    def _find(self, uid: str) -> dict | None:
        try:
            return self.cal.find(uid)
        except CalendarError:
            return None

    def add_event(self, con, now: datetime, sid: str | None, fields: dict) -> tuple[int, dict]:
        status, body = self.cal.create(fields)
        if status < 300:
            ev = body.get("event") or {}
            actions.record(con, now, session_id=sid, kind="event", verb="ADDED", title=ev.get("title", fields["title"]),
                           detail=event_detail(ev) if ev.get("start") else "", ref=ev.get("uid"),
                           calendar=ev.get("calendar"),
                           inverse={"op": "delete_event", "uid": ev["uid"]} if ev.get("uid") else None)
        return status, body

    def update_event(self, con, now: datetime, sid: str | None, uid: str, fields: dict) -> tuple[int, dict]:
        before = self._find(uid)
        status, body = self.cal.update(uid, fields)
        if status < 300:
            ev = body.get("event") or before or {}
            inverse = None
            if before:
                restore = fields_from_event(before)
                restore.pop("calendar", None)  # PATCH cannot move calendars
                inverse = {"op": "update_event", "uid": uid, "fields": restore}
            actions.record(con, now, session_id=sid, kind="event", verb="CHANGED", title=ev.get("title", "event"),
                           detail=event_detail(ev) if ev.get("start") else "", ref=uid, calendar=ev.get("calendar"),
                           inverse=inverse)
        return status, body

    def delete_event(self, con, now: datetime, sid: str | None, uid: str) -> tuple[int, dict]:
        before = self._find(uid)
        status, body = self.cal.delete(uid)
        if status < 300:
            actions.record(con, now, session_id=sid, kind="event", verb="REMOVED",
                           title=(before or {}).get("title") or body.get("title", "event"),
                           detail=event_detail(before) if before else body.get("when", ""), ref=uid,
                           calendar=(before or {}).get("calendar"),
                           inverse={"op": "create_event", "fields": fields_from_event(before)} if before else None)
        return status, body

    def add_todo(self, con, now: datetime, sid: str | None, *, person: str, text: str, date: str,
                 time: str | None = None) -> dict:
        p = next((p for p in settings.people(con) if p["name"].lower() == person.strip().lower()), None)
        if p is None:
            raise LookupError(f"No one called {person}. The family is Bob, Belen and Ben.")
        item = todos.create(con, now, person_id=p["id"], text=text, date=date, time=time, created_by="house")
        actions.record(con, now, session_id=sid, kind="todo", verb="ADDED", title=item["text"],
                       detail=todo_detail(item), ref=str(item["id"]), person=p["name"],
                       inverse={"op": "delete_todo", "id": item["id"]})
        return item | {"person": p["name"]}

    def set_todo_done(self, con, now: datetime, sid: str | None, todo_id: int, done: bool) -> dict:
        before = todos.get(con, todo_id)
        if before is None:
            raise KeyError(todo_id)
        item = todos.update(con, now, todo_id, {"done": done})
        name = self.person_name(con, item["person_id"])
        actions.record(con, now, session_id=sid, kind="todo", verb="DONE" if done else "REOPENED",
                       title=item["text"], detail=todo_detail(item), ref=str(todo_id), person=name,
                       inverse={"op": "set_todo_done", "id": todo_id, "done": before["done"]})
        return item | {"person": name}

    def delete_todo(self, con, now: datetime, sid: str | None, todo_id: int) -> dict:
        before = todos.get(con, todo_id)
        if before is None:
            raise KeyError(todo_id)
        todos.delete(con, todo_id)
        name = self.person_name(con, before["person_id"])
        actions.record(con, now, session_id=sid, kind="todo", verb="REMOVED", title=before["text"],
                       detail=todo_detail(before), ref=str(todo_id), person=name,
                       inverse={"op": "create_todo", "person_id": before["person_id"], "text": before["text"],
                                "date": before["date"], "time": before["time"], "done": before["done"]})
        return before | {"person": name}

    def undo(self, con, now: datetime, action_id: int) -> tuple[bool, str]:
        a = actions.get(con, action_id)
        if a is None:
            return False, "No such change"
        if a["undone_at"]:
            return True, "Already undone"
        inv = a["inverse"]
        if inv is None:
            return False, "This change can't be undone here"
        status, body = 200, {}
        op = inv["op"]
        if op == "delete_event":
            status, body = self.cal.delete(inv["uid"])
        elif op == "update_event":
            status, body = self.cal.update(inv["uid"], inv["fields"])
        elif op == "create_event":
            status, body = self.cal.create(inv["fields"])
        elif op == "delete_todo":
            if not todos.delete(con, inv["id"]):
                status, body = 404, {"detail": "That TODO is already gone"}
        elif op == "set_todo_done":
            try:
                todos.update(con, now, inv["id"], {"done": inv["done"]})
            except KeyError:
                status, body = 404, {"detail": "That TODO is gone"}
        elif op == "create_todo":
            item = todos.create(con, now, person_id=inv["person_id"], text=inv["text"], date=inv["date"],
                                time=inv["time"], created_by="house")
            if inv["done"]:
                todos.update(con, now, item["id"], {"done": True})
        else:
            return False, "Unknown change"
        if status >= 300:
            return False, body.get("detail", "Couldn't undo")
        actions.mark_undone(con, action_id, now)
        return True, "Undone"
```

- [ ] **Step 3: Wire routes in `app/api.py`**

Add imports: `import hmac`, `from fastapi import Header`, `from app import actions`, `from app.house import HouseOps`. Add models after `PersonPatch`:
```python
Place = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class HouseEventIn(BaseModel):
    title: Text
    date: dt.date
    start_time: HHMM | None = None
    end_time: HHMM | None = None
    duration_minutes: int | None = Field(None, ge=5, le=1440)
    calendar: Name | None = None
    location: Place | None = None


class HouseEventPatch(BaseModel):
    title: Text | None = None
    date: dt.date | None = None
    start_time: HHMM | None = None
    end_time: HHMM | None = None
    location: Place | None = None


class HouseTodoIn(BaseModel):
    person: Name
    text: Text
    date: dt.date | None = None
    time: HHMM | None = None


def _fields(model: BaseModel) -> dict:
    out = model.model_dump(exclude_none=True)
    if "date" in out:
        out["date"] = out["date"].isoformat()
    return out
```

Change the signature to `def create_app(db_path=None, source=None, version=None, whisper=None, house=None, house_token=None)` and, after `cal = CalendarService(...)`, add `ops = HouseOps(cal)` and `token = house_token if house_token is not None else _read_secret("HOUSE_TOKEN_FILE")`, with this module-level helper:
```python
def _read_secret(env_name: str) -> str:
    path = os.environ.get(env_name)
    if path and Path(path).is_file():
        return Path(path).read_text().strip()
    return ""
```

Add inside `create_app` (before the `/` route):
```python
    def house_auth(authorization: Annotated[str | None, Header()] = None):
        if not token:
            raise HTTPException(503, "House tools are not set up on the dashboard")
        if not authorization or not hmac.compare_digest(authorization, f"Bearer {token}"):
            raise HTTPException(401, "Bad house token")

    House = Annotated[None, Depends(house_auth)]
    Sid = Annotated[str | None, Header(alias="X-Talk-Session")]

    def passthrough(status: int, body: dict):
        return JSONResponse(body, status_code=status) if status != 204 else Response(status_code=204)

    @app.get("/api/house/calendars")
    def house_calendars(_: House):
        if isinstance(cal.source, HttpSource):
            return passthrough(*cal.source._send("GET", "/calendars"))
        return {"default": "Family", "calendars": [
            {"name": "Family", "purpose": "Our primary shared family calendar for most events", "writable": True},
            {"name": "Benny Time", "purpose": "Events specific to our son, Ben", "writable": True}]}

    @app.get("/api/house/events")
    def house_events(_: House, start: dt.date | None = None, days: int = 7):
        try:
            evs = cal.source.events(start or clock.now().date(), max(1, min(days, 60)))
        except Exception:
            raise HTTPException(502, "Couldn't read the calendar") from None
        return {"events": evs}

    @app.post("/api/house/events")
    def house_add_event(body: HouseEventIn, _: House, con: Con, sid: Sid = None):
        return passthrough(*ops.add_event(con, clock.now(), sid, _fields(body)))

    @app.patch("/api/house/events/{uid}")
    def house_update_event(uid: str, body: HouseEventPatch, _: House, con: Con, sid: Sid = None):
        return passthrough(*ops.update_event(con, clock.now(), sid, uid, _fields(body)))

    @app.delete("/api/house/events/{uid}")
    def house_delete_event(uid: str, _: House, con: Con, sid: Sid = None):
        return passthrough(*ops.delete_event(con, clock.now(), sid, uid))

    @app.get("/api/house/todos")
    def house_list_todos(person: str, _: House, con: Con):
        view = todos.today_view(con, clock.now())
        p = next((p for p in view["people"] if p["name"].lower() == person.strip().lower()), None)
        if p is None:
            raise HTTPException(404, f"No one called {person}. The family is Bob, Belen and Ben.")
        return {"person": p["name"], "date": view["date"], "todos": p["todos"]}

    @app.post("/api/house/todos", status_code=201)
    def house_add_todo(body: HouseTodoIn, _: House, con: Con, sid: Sid = None):
        now = clock.now()
        try:
            return ops.add_todo(con, now, sid, person=body.person, text=body.text,
                                date=(body.date or now.date()).isoformat(), time=body.time)
        except LookupError as e:
            raise HTTPException(404, str(e)) from None

    def _todo_op(fn, *args):
        try:
            return fn(*args)
        except KeyError:
            raise HTTPException(404, "No such TODO") from None

    @app.post("/api/house/todos/{todo_id}/done")
    def house_done(todo_id: int, _: House, con: Con, sid: Sid = None):
        return _todo_op(ops.set_todo_done, con, clock.now(), sid, todo_id, True)

    @app.post("/api/house/todos/{todo_id}/reopen")
    def house_reopen(todo_id: int, _: House, con: Con, sid: Sid = None):
        return _todo_op(ops.set_todo_done, con, clock.now(), sid, todo_id, False)

    @app.delete("/api/house/todos/{todo_id}")
    def house_delete_todo(todo_id: int, _: House, con: Con, sid: Sid = None):
        return _todo_op(ops.delete_todo, con, clock.now(), sid, todo_id)

    def change_cards(con, session_id: str, after_id: int = 0) -> list[dict]:
        colors = {c["name"]: (c["color"], c["ink"]) for c in settings.calendars(con)}
        out = []
        for a in actions.for_session(con, session_id, after_id):
            color, ink = colors.get(a["calendar"], ("#6b45d9", "#fff"))
            out.append({"id": a["id"], "kind": a["kind"], "verb": a["verb"], "title": a["title"],
                        "detail": a["detail"], "ref": a["ref"], "calendar": a["calendar"], "person": a["person"],
                        "color": color, "ink": ink, "undone": a["undone_at"] is not None,
                        "undoable": a["inverse"] is not None})
        return out

    @app.get("/api/talk/sessions/{session_id}")
    def talk_session(session_id: str, con: Con):
        return {"busy": False, "changes": change_cards(con, session_id)}

    @app.post("/api/talk/actions/{action_id}/undo")
    def talk_undo(action_id: int, con: Con):
        ok, message = ops.undo(con, clock.now(), action_id)
        if not ok:
            raise HTTPException(409, message)
        cal.invalidate()
        return {"ok": True}
```
Note for the implementer: `FakeSource` must also gain `delete_result` (default `(204, {})`) — it already returns `self.delete_result`; keep `self.deleted.append(uid)`.

- [ ] **Step 4: Verify and commit**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check .` → all pass.
```bash
git add app/house.py app/api.py tests/test_house_api.py tests/fakes.py
git commit -m "Add House operations with undo and token-protected /api/house endpoints"
```

---

### Task 4: Talk service (whisper, Open WebUI, sessions) and /api/talk

**Files:**
- Create: `app/talk.py`, `tests/test_talk.py`
- Modify: `app/api.py`

**Interfaces:**
- Produces in `app/talk.py`: `TalkError(message, status=503)`; `clean_transcript(text) -> str`; `clean_reply(text) -> str`; `WhisperClient(url, timeout=20).transcribe(wav: bytes) -> str`; `FakeWhisper(text="add a todo for Ben to feed Milo").transcribe(wav) -> str` (returns `""` for `len(wav) < 1000`); `OpenWebUIClient(url, key, model="house", timeout=60).chat(messages, session_id) -> str`; `FakeHouse(do_add_todo=None).chat(messages, session_id) -> str`; `Sessions(ttl=600, clock=time.monotonic)` with `create(context=None) -> dict`, `get(id) -> dict | None`, `end(id) -> None`; `TalkService(store, house, whisper, sessions=None)` with `listen(wav) -> str`, `message(session_id, text, change_cards) -> dict`.
- HTTP (spec §3.6): `POST /api/talk/sessions` `{context?: {event: {uid, title, when_label, calendar}}}` → `{id}`; `GET /api/talk/sessions/{id}` → `{busy, changes}`; `DELETE /api/talk/sessions/{id}` → 204; `POST /api/talk/listen` (body `audio/wav`, ≤ 2 MB) → `{text}`; `POST /api/talk/message` `{session_id, text (1–500)}` → `{reply, changes}`; errors carry `TalkError.status` and `{"detail": message}`.

- [ ] **Step 1: Write failing tests** — `tests/test_talk.py`:
```python
import io
import json
import urllib.request

import pytest
from fastapi.testclient import TestClient

from app import talk
from app.api import create_app
from tests.fakes import FakeSource

TOKEN = "t0ken"


def test_clean_transcript_and_reply():
    assert talk.clean_transcript(" [BLANK_AUDIO] ") == ""
    assert talk.clean_transcript("(music) Add a todo  for Ben.") == "Add a todo for Ben."
    assert talk.clean_reply("<think>hmm</think>\nDone, added it.") == "Done, added it."


def test_sessions_expire():
    now = [0.0]
    s = talk.Sessions(ttl=600, clock=lambda: now[0])
    a = s.create()
    now[0] = 599
    assert s.get(a["id"]) is not None
    now[0] = 1300
    assert s.get(a["id"]) is None


def test_whisper_client_sends_multipart(monkeypatch):
    seen = {}

    class Resp(io.BytesIO):
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_open(req, timeout):
        seen["url"], seen["ctype"], seen["body"] = req.full_url, req.headers["Content-type"], req.data
        return Resp(json.dumps({"text": " Feed Milo. "}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    assert talk.WhisperClient("http://w:8178").transcribe(b"RIFFxxxx") == "Feed Milo."
    assert seen["url"] == "http://w:8178/inference" and "multipart/form-data" in seen["ctype"]
    assert b'name="file"; filename="speech.wav"' in seen["body"] and b"RIFFxxxx" in seen["body"]


def test_whisper_down(monkeypatch):
    def boom(req, timeout):
        raise OSError("refused")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(talk.TalkError, match="Voice isn't working"):
        talk.WhisperClient("http://w:8178").transcribe(b"x")


def test_openwebui_client_request(monkeypatch):
    seen = {}

    class Resp(io.BytesIO):
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_open(req, timeout):
        seen["body"], seen["auth"] = json.loads(req.data), req.headers["Authorization"]
        return Resp(json.dumps({"choices": [{"message": {"content": "<think>x</think>Hi"}}]}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    reply = talk.OpenWebUIClient("http://owui:8080", "k3y").chat([{"role": "user", "content": "hi"}], "s9")
    assert reply == "Hi" and seen["auth"] == "Bearer k3y"
    assert seen["body"]["model"] == "house" and seen["body"]["session_id"] == "s9" and seen["body"]["stream"] is False
    assert seen["body"]["tool_ids"] == ["household_dates", "household_calendar", "household_todos"]


class ToolCallingHouse:
    """Acts like the House: calls /api/house with the session id, then replies."""

    def __init__(self):
        self.client = None
        self.seen = []

    def chat(self, messages, session_id):
        self.seen.append(messages)
        self.client.post("/api/house/todos", json={"person": "Ben", "text": "Feed Milo"},
                         headers={"Authorization": f"Bearer {TOKEN}", "X-Talk-Session": session_id})
        return "Done. Feed Milo is on Ben's list."


@pytest.fixture
def setup(tmp_path, freeze):
    freeze("2026-10-27T09:00")
    house = ToolCallingHouse()
    app = create_app(db_path=str(tmp_path / "t.db"), source=FakeSource(), version="t",
                     whisper=talk.FakeWhisper("add a todo for Ben"), house=house, house_token=TOKEN)
    client = TestClient(app)
    house.client = client
    return client, house


def test_full_message_flow(setup):
    client, house = setup
    sid = client.post("/api/talk/sessions", json={}).json()["id"]
    assert client.post("/api/talk/listen", content=b"R" * 2000, headers={"Content-Type": "audio/wav"}).json() == \
        {"text": "add a todo for Ben"}
    r = client.post("/api/talk/message", json={"session_id": sid, "text": "add a todo for Ben"}).json()
    assert r["reply"].startswith("Done") and [(c["verb"], c["title"]) for c in r["changes"]] == [("ADDED", "Feed Milo")]
    system = house.seen[0][0]
    assert system["role"] == "system" and "Bob, Belen" in system["content"] and "America/Chicago" in system["content"]
    r2 = client.post("/api/talk/message", json={"session_id": sid, "text": "thanks"}).json()
    assert len(house.seen[1]) == 4  # system + user + assistant + user: history kept within the session
    assert [c["title"] for c in r2["changes"]] == ["Feed Milo"]  # only this call's changes
    assert client.delete(f"/api/talk/sessions/{sid}").status_code == 204
    assert client.post("/api/talk/message", json={"session_id": sid, "text": "x"}).status_code == 404


def test_context_event_in_prompt(setup):
    client, house = setup
    sid = client.post("/api/talk/sessions", json={"context": {"event": {
        "uid": "h1", "title": "Dentist", "when_label": "Thursday 29 Oct, 4:00 PM", "calendar": "Family"}}}).json()["id"]
    client.post("/api/talk/message", json={"session_id": sid, "text": "move it to 5"})
    assert "Dentist" in house.seen[0][0]["content"] and "h1" in house.seen[0][0]["content"]


def test_fallback_attribution(tmp_path, freeze):
    freeze("2026-10-27T09:00")

    class NoHeaderHouse(ToolCallingHouse):
        def chat(self, messages, session_id):
            self.client.post("/api/house/todos", json={"person": "Bob", "text": "Call"},
                             headers={"Authorization": f"Bearer {TOKEN}"})
            return "ok"

    house = NoHeaderHouse()
    client = TestClient(create_app(db_path=str(tmp_path / "f.db"), source=FakeSource(), version="t",
                                   whisper=talk.FakeWhisper(), house=house, house_token=TOKEN))
    house.client = client
    sid = client.post("/api/talk/sessions", json={}).json()["id"]
    assert [c["title"] for c in client.post("/api/talk/message", json={"session_id": sid, "text": "x"}).json()
            ["changes"]] == ["Call"]


def test_errors(tmp_path, freeze):
    freeze("2026-10-27T09:00")

    class DownHouse:
        def chat(self, messages, session_id):
            raise talk.TalkError("The house isn't answering", 502)

    client = TestClient(create_app(db_path=str(tmp_path / "e.db"), source=FakeSource(), version="t",
                                   whisper=None, house=DownHouse(), house_token=TOKEN))
    sid = client.post("/api/talk/sessions", json={}).json()["id"]
    r = client.post("/api/talk/message", json={"session_id": sid, "text": "hi"})
    assert r.status_code == 502 and r.json()["detail"] == "The house isn't answering"
    r = client.post("/api/talk/listen", content=b"x" * 2000, headers={"Content-Type": "audio/wav"})
    assert r.status_code == 503 and "Voice" in r.json()["detail"]
    big = client.post("/api/talk/listen", content=b"x" * (2 * 1024 * 1024 + 1), headers={"Content-Type": "audio/wav"})
    assert big.status_code == 413
    assert client.post("/api/talk/message", json={"session_id": sid, "text": ""}).status_code == 422


def test_fake_mode_end_to_end(tmp_path, freeze, monkeypatch):
    freeze("2026-10-27T09:00")
    monkeypatch.setenv("DASHBOARD_FAKE", "1")
    client = TestClient(create_app(db_path=str(tmp_path / "fm.db"), version="t"))
    sid = client.post("/api/talk/sessions", json={}).json()["id"]
    text = client.post("/api/talk/listen", content=b"R" * 2000, headers={"Content-Type": "audio/wav"}).json()["text"]
    r = client.post("/api/talk/message", json={"session_id": sid, "text": text}).json()
    assert r["changes"] and r["changes"][0]["person"] == "Ben"
```

Run → FAIL (`ImportError: cannot import name 'talk'`).

- [ ] **Step 2: Implement `app/talk.py`**
```python
"""Talk to the house: speech-to-text, the House (Open WebUI) and short-lived panel sessions."""
import json
import re
import secrets
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid

from app import actions, clock

TOOL_IDS = ["household_dates", "household_calendar", "household_todos"]


class TalkError(Exception):
    def __init__(self, message: str, status: int = 503):
        super().__init__(message)
        self.status = status


def clean_transcript(text: str) -> str:
    """Drop whisper's non-speech tags such as [BLANK_AUDIO] or (music)."""
    return " ".join(re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", text or "").split())


def clean_reply(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def _multipart(boundary: str, fields: list[tuple[str, str | None, bytes]]) -> bytes:
    out = []
    for name, filename, data in fields:
        disp = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename else "")
        head = f"--{boundary}\r\nContent-Disposition: {disp}\r\n"
        head += "Content-Type: audio/wav\r\n\r\n" if filename else "\r\n"
        out += [head.encode(), data, b"\r\n"]
    out.append(f"--{boundary}--\r\n".encode())
    return b"".join(out)


class WhisperClient:
    def __init__(self, url: str, timeout: float = 20):
        self.url = url.rstrip("/")
        self.timeout = timeout

    def transcribe(self, wav: bytes) -> str:
        boundary = "kd" + secrets.token_hex(8)
        body = _multipart(boundary, [("file", "speech.wav", wav), ("response_format", None, b"json"),
                                     ("temperature", None, b"0.0")])
        req = urllib.request.Request(f"{self.url}/inference", data=body, method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return clean_transcript(json.load(r).get("text", ""))
        except Exception as e:
            raise TalkError("Voice isn't working right now") from e


class FakeWhisper:
    def __init__(self, text: str = "add a todo for Ben to feed Milo"):
        self.text = text

    def transcribe(self, wav: bytes) -> str:
        return "" if len(wav) < 1000 else self.text


class OpenWebUIClient:
    def __init__(self, url: str, key: str, model: str = "house", timeout: float = 60):
        self.url, self.key, self.model, self.timeout = url.rstrip("/"), key, model, timeout

    def chat(self, messages: list[dict], session_id: str) -> str:
        body = {"model": self.model, "messages": messages, "tool_ids": TOOL_IDS, "session_id": session_id,
                "stream": False}
        req = urllib.request.Request(f"{self.url}/api/chat/completions", data=json.dumps(body).encode(),
                                     method="POST", headers={"Content-Type": "application/json",
                                                             "Authorization": f"Bearer {self.key}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.load(r)
        except (TimeoutError, socket.timeout) as e:
            raise TalkError("The house took too long to answer", 504) from e
        except Exception as e:
            raise TalkError("The house isn't answering", 502) from e
        try:
            return clean_reply(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as e:
            raise TalkError("The house isn't answering", 502) from e


class FakeHouse:
    """Stand-in for the House in fake mode. Understands 'add a todo for <name> to <text>'."""

    def __init__(self, do_add_todo=None):
        self.do_add_todo = do_add_todo

    def chat(self, messages: list[dict], session_id: str) -> str:
        text = messages[-1]["content"]
        m = re.search(r"todo for (\w+) to (.+)", text, re.I)
        if m and self.do_add_todo:
            what = m.group(2).strip().rstrip(".!?")
            self.do_add_todo(session_id, m.group(1), what)
            return f"Done. “{what}” is on {m.group(1).capitalize()}'s list for today."
        return f"(fake house) You said: {text}"


class Sessions:
    def __init__(self, ttl: float = 600, clock=time.monotonic):
        self.ttl, self.clock = ttl, clock
        self._s: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _expire(self):
        now = self.clock()
        for k in [k for k, s in self._s.items() if not s["busy"] and now - s["used"] > self.ttl]:
            del self._s[k]

    def create(self, context: dict | None = None) -> dict:
        s = {"id": uuid.uuid4().hex, "messages": [], "context": context or {}, "busy": False, "used": self.clock()}
        with self._lock:
            self._expire()
            self._s[s["id"]] = s
        return s

    def get(self, session_id: str) -> dict | None:
        with self._lock:
            self._expire()
            s = self._s.get(session_id)
            if s:
                s["used"] = self.clock()
            return s

    def end(self, session_id: str) -> None:
        with self._lock:
            self._s.pop(session_id, None)


class TalkService:
    def __init__(self, store, house, whisper, sessions: Sessions | None = None):
        self.store, self.house, self.whisper = store, house, whisper
        self.sessions = sessions or Sessions()

    def listen(self, wav: bytes) -> str:
        if self.whisper is None:
            raise TalkError("Voice isn't working right now")
        return self.whisper.transcribe(wav)

    def system_prompt(self, session: dict) -> str:
        now = clock.now()
        lines = [
            f"You are the House, answering on the family's kitchen screen. Now: {now:%A %-d %B %Y, %-I:%M %p} "
            "(America/Chicago).",
            "The family is Bob, Belen and their son Ben. TODO lists exist only for these three.",
            "When asked to add, change, check off or remove something, do it with your tools right away, then say "
            "what you did in one or two short sentences.",
            "Keep every answer short: it is read on a wall screen.",
        ]
        ev = (session.get("context") or {}).get("event")
        if ev:
            lines.append(f"The person is looking at this event: “{ev.get('title')}”, {ev.get('when_label')}, "
                         f"{ev.get('calendar')} calendar, uid {ev.get('uid')}.")
        return "\n".join(lines)

    def message(self, session_id: str, text: str, change_cards) -> dict:
        s = self.sessions.get(session_id)
        if s is None:
            raise TalkError("That conversation has ended", 404)
        if self.house is None:
            raise TalkError("The house isn't answering", 502)
        con = self.store.connect()
        try:
            since = actions.last_id(con)
            s["messages"].append({"role": "user", "content": text})
            s["busy"] = True
            try:
                reply = self.house.chat([{"role": "system", "content": self.system_prompt(s)}] + s["messages"],
                                        session_id)
            except TalkError:
                s["messages"].pop()
                raise
            finally:
                s["busy"] = False
            s["messages"].append({"role": "assistant", "content": reply})
            actions.claim_unattributed(con, session_id, since)
            return {"reply": reply, "changes": change_cards(con, session_id, since)}
        finally:
            con.close()
```

- [ ] **Step 3: Wire into `app/api.py`**

Imports: `from fastapi.concurrency import run_in_threadpool`, `from app.talk import FakeHouse, FakeWhisper, OpenWebUIClient, TalkError, TalkService, WhisperClient`.

After `ops = HouseOps(cal)`:
```python
    fake = os.environ.get("DASHBOARD_FAKE") == "1"
    if house_token is None:
        token = "dev-token" if fake else _read_secret("HOUSE_TOKEN_FILE")
    else:
        token = house_token
    if whisper is None and fake:
        whisper = FakeWhisper()
    elif whisper is None and os.environ.get("WHISPER_URL"):
        whisper = WhisperClient(os.environ["WHISPER_URL"])
    if house is None and fake:
        house = FakeHouse()
    elif house is None:
        key = _read_secret("OPENWEBUI_KEY_FILE")
        house = OpenWebUIClient(os.environ.get("OPENWEBUI_URL", "http://open-webui:8080"), key) if key else None

    def _fake_add(session_id: str, person: str, text: str) -> None:
        with closing(store.connect()) as con:
            now = clock.now()
            ops.add_todo(con, now, session_id, person=person, text=text, date=now.date().isoformat())

    if isinstance(house, FakeHouse) and house.do_add_todo is None:
        house.do_add_todo = _fake_add
    talk = TalkService(store, house, whisper)
```
(Remove the earlier `token = ...` line from Task 3; this block replaces it.)

Add models:
```python
class TalkContext(BaseModel):
    event: dict[str, str] | None = None


class SessionIn(BaseModel):
    context: TalkContext | None = None


class MessageIn(BaseModel):
    session_id: str
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
```

Add an exception handler and routes (replace Task 3's `talk_session`):
```python
    @app.exception_handler(TalkError)
    async def talk_error(request: Request, exc: TalkError):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.post("/api/talk/sessions")
    def talk_start(body: SessionIn):
        context = body.context.model_dump(exclude_none=True) if body.context else {}
        return {"id": talk.sessions.create(context)["id"]}

    @app.get("/api/talk/sessions/{session_id}")
    def talk_session(session_id: str, con: Con):
        s = talk.sessions.get(session_id)
        return {"busy": bool(s and s["busy"]), "changes": change_cards(con, session_id)}

    @app.delete("/api/talk/sessions/{session_id}", status_code=204)
    def talk_end(session_id: str):
        talk.sessions.end(session_id)

    @app.post("/api/talk/listen")
    async def talk_listen(request: Request):
        wav = await request.body()
        if len(wav) > 2 * 1024 * 1024:
            raise HTTPException(413, "That recording is too long")
        return {"text": await run_in_threadpool(talk.listen, wav)}

    @app.post("/api/talk/message")
    def talk_message(body: MessageIn):
        return talk.message(body.session_id, body.text, change_cards)
```
Note `talk_end` must wait for an in-flight call (spec): `Sessions.end` only drops the dict entry; the running `message` call keeps its own reference and still logs its changes under the session id, which `GET` keeps returning. That satisfies "ends it after any in-flight call finishes" for the client.

- [ ] **Step 4: Verify and commit**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check .` → all pass.
```bash
git add app/talk.py app/api.py tests/test_talk.py
git commit -m "Add talk service: whisper and Open WebUI clients, sessions, /api/talk routes, fake mode"
```

---

### Task 5: House tools for Open WebUI

**Files:**
- Create: `house_tools/household_calendar.py`, `house_tools/household_todos.py`, `tests/test_house_tools.py`

**Interfaces:**
- Each file is a single Open WebUI tool module: a module docstring frontmatter (`title`, `author`, `description`, `version`), a `Tools` class with nested `Valves(BaseModel)` (`dashboard_url` default `http://kitchen-dashboard:8000`, `token` default `""`), and module-level `_open = urllib.request.urlopen` so tests can route calls.
- Methods (all return short strings; all accept `__metadata__: dict = None` and send `X-Talk-Session` from `__metadata__["session_id"]`):
  - calendar: `list_calendars()`, `list_events(start_date: str = "", days: int = 7)`, `add_event(title, date, start_time="", end_time="", duration_minutes=60, calendar="", location="")`, `update_event(uid, title="", date="", start_time="", end_time="", location="")`, `delete_event(uid)`.
  - todos: `list_todos(person)`, `add_todo(person, text, date="", time="")`, `complete_todo(todo_id: int)`, `reopen_todo(todo_id: int)`, `delete_todo(todo_id: int)`.

- [ ] **Step 1: Write failing tests** — `tests/test_house_tools.py` (routes the tools' HTTP calls into the real app through TestClient):
```python
import importlib.util
import io
import json
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from tests.fakes import FakeSource, ev

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "t0ken"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "house_tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Resp(io.BytesIO):
    def __init__(self, status, data):
        super().__init__(data)
        self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): return False


@pytest.fixture
def wired(tmp_path, freeze):
    freeze("2026-10-27T09:00")
    src = FakeSource([ev("Family", "House thing", "2026-10-28T10:00:00-05:00", uid="h1", house=True)])
    client = TestClient(create_app(db_path=str(tmp_path / "x.db"), source=src, version="t", house_token=TOKEN))

    def route(req, timeout):
        path = req.full_url.replace("http://kitchen-dashboard:8000", "")
        r = client.request(req.get_method(), path, content=req.data, headers=dict(req.header_items()))
        if r.status_code >= 400:
            raise urllib.error.HTTPError(req.full_url, r.status_code, "err", {}, io.BytesIO(r.content))
        return Resp(r.status_code, r.content)

    tools = {}
    for name in ("household_todos", "household_calendar"):
        mod = load(name)
        mod._open = route
        t = mod.Tools()
        t.valves.token = TOKEN
        tools[name] = t
    return client, src, tools


META = {"session_id": "s1"}


def test_todo_tool_roundtrip(wired):
    client, _, tools = wired
    t = tools["household_todos"]
    out = t.add_todo("ben", "Feed Milo", __metadata__=META)
    assert out.startswith("Added TODO #") and "Ben" in out and "Feed Milo" in out
    assert "Feed Milo" in t.list_todos("Ben", __metadata__=META)
    tid = int(out.split("#")[1].split()[0])
    assert "Done" in t.complete_todo(tid, __metadata__=META)
    assert "[x]" in t.list_todos("Ben")
    assert "Removed" in t.delete_todo(tid, __metadata__=META)
    verbs = [c["verb"] for c in client.get("/api/talk/sessions/s1").json()["changes"]]
    assert verbs == ["ADDED", "DONE", "REMOVED"]


def test_todo_tool_errors(wired):
    _, _, tools = wired
    t = tools["household_todos"]
    assert "Bob, Belen and Ben" in t.add_todo("Ana", "x")
    t.valves.token = "wrong"
    assert "can't reach the kitchen dashboard" in t.list_todos("Ben")


def test_calendar_tool(wired):
    _, src, tools = wired
    c = tools["household_calendar"]
    src.create_result = (200, {"saved": True, "event": ev("Benny Time", "Dentist", "2026-10-29T16:00:00-05:00",
                                                           uid="n1", house=True) | {"when": "Thu 29 Oct, 4:00 PM"}})
    out = c.add_event("Dentist", "2026-10-29", start_time="16:00", calendar="Benny Time", __metadata__=META)
    assert "Added" in out and "Dentist" in out and "n1" in out
    assert src.created[0] == {"title": "Dentist", "date": "2026-10-29", "start_time": "16:00",
                              "duration_minutes": 60, "calendar": "Benny Time"}
    assert "House thing" in c.list_events("2026-10-27", 7)
    src.update_result = (403, {"detail": "House can only change or delete events it created."})
    assert "House can only" in c.update_event("zzz", title="x")
    assert "Family" in c.list_calendars()
```

Run → FAIL (`FileNotFoundError: house_tools/household_todos.py`).

- [ ] **Step 2: Implement `house_tools/household_todos.py`**
```python
"""
title: Household TODOs
author: household-ai
description: Read and change the family's daily TODO lists (Bob, Belen, Ben) shown on the kitchen screen.
version: 0.1.0
"""
import json
import urllib.error
import urllib.parse
import urllib.request

from pydantic import BaseModel, Field

_open = urllib.request.urlopen


class Tools:
    class Valves(BaseModel):
        dashboard_url: str = Field("http://kitchen-dashboard:8000", description="Kitchen dashboard base URL")
        token: str = Field("", description="House tools token (~/household-ai/secrets/kitchen/house_token)")

    def __init__(self):
        self.valves = self.Valves()

    def _call(self, method: str, path: str, body: dict | None = None, metadata: dict | None = None):
        headers = {"Authorization": f"Bearer {self.valves.token}"}
        sid = (metadata or {}).get("session_id")
        if sid:
            headers["X-Talk-Session"] = str(sid)
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.valves.dashboard_url.rstrip("/") + path, data=data, method=method,
                                     headers=headers)
        try:
            with _open(req, timeout=20) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            except ValueError:
                return e.code, {"detail": str(e.reason)}
        except Exception:
            return 0, {}

    @staticmethod
    def _err(status: int, body: dict) -> str:
        if status in (0, 401, 503):
            return "I can't reach the kitchen dashboard right now, so I couldn't do that."
        detail = body.get("detail")
        if isinstance(detail, list):
            detail = "; ".join(str(x.get("msg", "")) for x in detail)
        return f"That didn't work: {detail or 'unknown error'}"

    def list_todos(self, person: str, __metadata__: dict = None) -> str:
        """
        List today's TODOs for one person, including open items carried over from earlier days.
        :param person: Bob, Belen or Ben.
        """
        status, body = self._call("GET", "/api/house/todos?" + urllib.parse.urlencode({"person": person}),
                                  metadata=__metadata__)
        if status != 200:
            return self._err(status, body)
        if not body["todos"]:
            return f"{body['person']} has nothing on the list today."
        lines = []
        for t in body["todos"]:
            line = f"- [{'x' if t['done'] else ' '}] #{t['id']} {t['text']}"
            if t.get("time_label"):
                line += f" at {t['time_label']}"
            if t.get("overdue"):
                line += " (overdue)"
            lines.append(line)
        return f"{body['person']}'s TODOs today:\n" + "\n".join(lines)

    def add_todo(self, person: str, text: str, date: str = "", time: str = "", __metadata__: dict = None) -> str:
        """
        Add a TODO to one person's list.
        :param person: Bob, Belen or Ben.
        :param text: What to do, short (e.g. "Feed Milo").
        :param date: Day as YYYY-MM-DD; leave empty for today.
        :param time: Optional 24-hour time HH:MM.
        """
        body = {"person": person, "text": text}
        if date:
            body["date"] = date
        if time:
            body["time"] = time
        status, res = self._call("POST", "/api/house/todos", body, __metadata__)
        if status not in (200, 201):
            return self._err(status, res)
        when = res["date"] + (f" at {res['time']}" if res.get("time") else "")
        return f"Added TODO #{res['id']} for {res['person']}: “{res['text']}” on {when}."

    def _set(self, todo_id: int, action: str, metadata: dict | None) -> str:
        status, res = self._call("POST", f"/api/house/todos/{int(todo_id)}/{action}", metadata=metadata)
        if status != 200:
            return self._err(status, res)
        return f"{'Done' if action == 'done' else 'Reopened'}: #{res['id']} “{res['text']}” for {res['person']}."

    def complete_todo(self, todo_id: int, __metadata__: dict = None) -> str:
        """
        Check off a TODO. Use list_todos first to find its number.
        :param todo_id: The TODO number, e.g. 12.
        """
        return self._set(todo_id, "done", __metadata__)

    def reopen_todo(self, todo_id: int, __metadata__: dict = None) -> str:
        """
        Mark a checked-off TODO as not done again.
        :param todo_id: The TODO number.
        """
        return self._set(todo_id, "reopen", __metadata__)

    def delete_todo(self, todo_id: int, __metadata__: dict = None) -> str:
        """
        Remove a TODO from a list.
        :param todo_id: The TODO number.
        """
        status, res = self._call("DELETE", f"/api/house/todos/{int(todo_id)}", metadata=__metadata__)
        if status != 200:
            return self._err(status, res)
        return f"Removed #{res['id']} “{res['text']}” from {res['person']}'s list."
```

- [ ] **Step 3: Implement `house_tools/household_calendar.py`**

The file repeats the TODO tool's helpers on purpose: Open WebUI loads each tool file on its own, so they cannot share code.
```python
"""
title: Household Calendar
author: household-ai
description: Read the family calendars and add or change events (House may change or delete only events it created).
version: 0.1.0
"""
import json
import urllib.error
import urllib.parse
import urllib.request

from pydantic import BaseModel, Field

_open = urllib.request.urlopen


class Tools:
    class Valves(BaseModel):
        dashboard_url: str = Field("http://kitchen-dashboard:8000", description="Kitchen dashboard base URL")
        token: str = Field("", description="House tools token (~/household-ai/secrets/kitchen/house_token)")

    def __init__(self):
        self.valves = self.Valves()

    def _call(self, method: str, path: str, body: dict | None = None, metadata: dict | None = None):
        headers = {"Authorization": f"Bearer {self.valves.token}"}
        sid = (metadata or {}).get("session_id")
        if sid:
            headers["X-Talk-Session"] = str(sid)
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.valves.dashboard_url.rstrip("/") + path, data=data, method=method,
                                     headers=headers)
        try:
            with _open(req, timeout=20) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            except ValueError:
                return e.code, {"detail": str(e.reason)}
        except Exception:
            return 0, {}

    @staticmethod
    def _err(status: int, body: dict) -> str:
        if status in (0, 401, 503):
            return "I can't reach the kitchen dashboard right now, so I couldn't do that."
        detail = body.get("detail")
        if isinstance(detail, list):
            detail = "; ".join(str(x.get("msg", "")) for x in detail)
        return f"That didn't work: {detail or 'unknown error'}"

    def list_calendars(self, __metadata__: dict = None) -> str:
        """
        List the family calendars and what each one is for. Use it to pick the right calendar.
        """
        status, body = self._call("GET", "/api/house/calendars", metadata=__metadata__)
        if status != 200:
            return self._err(status, body)
        lines = [f"- {c['name']}: {c.get('purpose', '')}" for c in body.get("calendars", [])]
        return f"Default calendar: {body.get('default', 'Family')}\n" + "\n".join(lines)

    def list_events(self, start_date: str = "", days: int = 7, __metadata__: dict = None) -> str:
        """
        List events from a start day.
        :param start_date: First day as YYYY-MM-DD; empty for today.
        :param days: How many days to include (1-60).
        """
        query = {"days": days} | ({"start": start_date} if start_date else {})
        status, body = self._call("GET", "/api/house/events?" + urllib.parse.urlencode(query), metadata=__metadata__)
        if status != 200:
            return self._err(status, body)
        events = body.get("events", [])
        if not events:
            return "Nothing on the calendar in that range."
        return "\n".join(f"- {e.get('when') or e['start']} | {e['title']} | {e['calendar']} | uid {e['uid']}"
                         + (" | made by House" if e.get("added_by_house") else "") for e in events)

    def add_event(self, title: str, date: str, start_time: str = "", end_time: str = "", duration_minutes: int = 60,
                  calendar: str = "", location: str = "", __metadata__: dict = None) -> str:
        """
        Add an event to a family calendar.
        :param title: Short title, e.g. "Dentist · Ben".
        :param date: Day as YYYY-MM-DD.
        :param start_time: 24-hour HH:MM; leave empty for an all-day event.
        :param end_time: 24-hour HH:MM; leave empty to use duration_minutes.
        :param duration_minutes: Length when end_time is empty (default 60).
        :param calendar: Calendar name from list_calendars; empty for the default (Family).
        :param location: Optional place.
        """
        body = {"title": title, "date": date}
        if start_time:
            body["start_time"] = start_time
            if end_time:
                body["end_time"] = end_time
            else:
                body["duration_minutes"] = int(duration_minutes or 60)
        if calendar:
            body["calendar"] = calendar
        if location:
            body["location"] = location
        status, res = self._call("POST", "/api/house/events", body, __metadata__)
        if status != 200:
            return self._err(status, res)
        e = res.get("event", {})
        return f"Added “{e.get('title', title)}” to {e.get('calendar', calendar or 'Family')} ({e.get('when', date)}), uid {e.get('uid')}."

    def update_event(self, uid: str, title: str = "", date: str = "", start_time: str = "", end_time: str = "",
                     location: str = "", __metadata__: dict = None) -> str:
        """
        Change an event the House created. Leave a field empty to keep it.
        :param uid: The event uid from list_events.
        """
        body = {k: v for k, v in {"title": title, "date": date, "start_time": start_time, "end_time": end_time,
                                  "location": location}.items() if v}
        status, res = self._call("PATCH", f"/api/house/events/{urllib.parse.quote(uid, safe='')}", body, __metadata__)
        if status != 200:
            return self._err(status, res)
        e = res.get("event", {})
        return f"Changed “{e.get('title', '')}” ({e.get('when', '')})."

    def delete_event(self, uid: str, __metadata__: dict = None) -> str:
        """
        Delete an event the House created.
        :param uid: The event uid from list_events.
        """
        status, res = self._call("DELETE", f"/api/house/events/{urllib.parse.quote(uid, safe='')}",
                                 metadata=__metadata__)
        if status not in (200, 204):
            return self._err(status, res)
        return f"Removed “{res.get('title', 'the event')}”."
```
(In the file, the docstring frontmatter must be the first statement, then the imports and the full `Tools` class including the shared helpers — write it out in full.)

- [ ] **Step 4: Verify and commit**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check .` → all pass.
```bash
git add house_tools tests/test_house_tools.py
git commit -m "Add Open WebUI House tools for the calendar and TODOs"
```

---

### Task 6: home-ai setup scripts, compose and deploy wiring

**Files:**
- Create: `ops/install-whisper.sh`, `ops/install-house-tools.sh`
- Modify: `docker-compose.yml`, `ops/deploy-here.sh`

- [ ] **Step 1: `ops/install-whisper.sh`**
```sh
#!/bin/sh
# Builds whisper.cpp with Metal on home-ai and runs whisper-server on 127.0.0.1:8178 under launchd.
# Usage on home-ai: sh ops/install-whisper.sh   (needs Xcode command line tools and cmake: brew install cmake)
set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
TAG="${WHISPER_TAG:-v1.7.5}"
MODEL="${WHISPER_MODEL:-small.en}"
DIR="$HOME/household-ai/whisper"
PLIST="$HOME/Library/LaunchAgents/com.household.whisper.plist"
mkdir -p "$HOME/household-ai/logs"
if [ ! -d "$DIR/.git" ]; then
  git clone -q https://github.com/ggml-org/whisper.cpp "$DIR"
fi
cd "$DIR"
git fetch -q --tags
git checkout -q "$TAG"
cmake -B build -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build build -j --config Release --target whisper-server
[ -f "models/ggml-$MODEL.bin" ] || sh models/download-ggml-model.sh "$MODEL"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.household.whisper</string>
  <key>ProgramArguments</key><array>
    <string>$DIR/build/bin/whisper-server</string>
    <string>-m</string><string>$DIR/models/ggml-$MODEL.bin</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>8178</string>
    <string>-t</string><string>4</string>
  </array>
  <key>KeepAlive</key><true/>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$HOME/household-ai/logs/whisper.log</string>
  <key>StandardErrorPath</key><string>$HOME/household-ai/logs/whisper.log</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
sleep 1
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "== whisper.cpp $TAG ($MODEL) on 127.0.0.1:8178"
```
The implementer confirms on GitHub that tag `v1.7.5` exists (`git ls-remote --tags https://github.com/ggml-org/whisper.cpp | grep v1.7.5`) and that the server binary target is named `whisper-server` at that tag; if the newest stable tag differs, use it and record it in the report.

- [ ] **Step 2: `ops/install-house-tools.sh`**
```sh
#!/bin/sh
# Installs or updates the House tools in Open WebUI and sets their Valves. Run on home-ai:
#   OWUI_ADMIN_KEY=<an admin API key> sh ops/install-house-tools.sh
# The admin key is used for this call only and never stored. The House token is read from the secrets file.
set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$(dirname "$0")/.."
: "${OWUI_ADMIN_KEY:?set OWUI_ADMIN_KEY to an Open WebUI admin API key}"
OWUI="${OWUI_URL:-http://localhost:3000}"
TOKEN_FILE="$HOME/household-ai/secrets/kitchen/house_token"
[ -s "$TOKEN_FILE" ] || { echo "missing $TOKEN_FILE"; exit 1; }
for id in household_calendar household_todos; do
  python3 - "$OWUI" "$id" "house_tools/$id.py" "$TOKEN_FILE" <<'PY'
import json, os, re, sys, urllib.error, urllib.request
owui, tid, path, token_file = sys.argv[1:5]
key = os.environ["OWUI_ADMIN_KEY"]
src = open(path).read()
name = re.search(r"^title:\s*(.+)$", src, re.M).group(1).strip()
desc = re.search(r"^description:\s*(.+)$", src, re.M).group(1).strip()
def call(method, url, body=None):
    req = urllib.request.Request(owui + url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)
form = {"id": tid, "name": name, "content": src, "meta": {"description": desc}}
try:
    call("GET", f"/api/v1/tools/id/{tid}")
    call("POST", f"/api/v1/tools/id/{tid}/update", form)
    print("updated", tid)
except urllib.error.HTTPError:
    call("POST", "/api/v1/tools/create", form)
    print("created", tid)
call("POST", f"/api/v1/tools/id/{tid}/valves/update",
     {"dashboard_url": "http://kitchen-dashboard:8000", "token": open(token_file).read().strip()})
print("valves set", tid)
PY
  cp "house_tools/$id.py" "$HOME/household-ai/tools/$id.py"
done
echo "== Now share both tools with the Kitchen account: Open WebUI > Workspace > Tools > (tool) > Access."
```

- [ ] **Step 3: Compose and deploy**

`docker-compose.yml`, in the `kitchen-dashboard` service add to `environment`:
```yaml
      OPENWEBUI_URL: http://open-webui:8080
      OPENWEBUI_KEY_FILE: /run/kitchen-secrets/openwebui_key
      HOUSE_TOKEN_FILE: /run/kitchen-secrets/house_token
      WHISPER_URL: http://host.docker.internal:8178
```
add to `volumes`:
```yaml
      - ${HOME}/household-ai/secrets/kitchen:/run/kitchen-secrets:ro   # only the kitchen's two secrets
```
and add:
```yaml
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

`ops/deploy-here.sh`, after the `mkdir -p "$HOME/household-ai/data/dashboard"` line add:
```sh
mkdir -p "$HOME/household-ai/secrets/kitchen" && chmod 700 "$HOME/household-ai/secrets/kitchen"
```
(With no secret files yet, the app still starts; Talk shows "isn't answering"/"Voice isn't working" until setup is done.)

- [ ] **Step 4: Verify and commit**

Run: `sh -n ops/install-whisper.sh ops/install-house-tools.sh ops/deploy-here.sh && .venv/bin/pytest -q && .venv/bin/ruff check .`
```bash
chmod +x ops/install-whisper.sh ops/install-house-tools.sh
git add ops docker-compose.yml
git commit -m "Add whisper and House tool installers; mount kitchen secrets"
```

---

### Task 7: Shared talk client (mic → WAV, silence, API)

**Files:**
- Create: `app/static/js/talk.js`

**Interfaces:**
- Produces: `micAvailable() -> boolean`; `class Recorder({onLevel(v 0..1), onSilence(), silenceMs=1500, maxMs=15000})` with `start()`, `stop() -> Promise<{wav: Blob, heard: boolean}>`, `cancel()`; `talkApi.start(context) -> {id}`, `.status(id) -> {busy, changes}`, `.end(id)`, `.message(id, text) -> {reply, changes}`, `.undo(actionId)`, `.listen(wavBlob) -> text`.

- [ ] **Step 1: Write `app/static/js/talk.js`**
```js
// Talk to the house: microphone capture as 16 kHz WAV, silence detection, and the talk API.
// Speech never goes to the browser's own speech service: the WAV goes to the home server (whisper.cpp).
import { request } from "./api.js";

export const micAvailable = () => window.isSecureContext && !!navigator.mediaDevices?.getUserMedia;

export class Recorder {
  constructor({ onLevel, onSilence, silenceMs = 1500, maxMs = 15000 } = {}) {
    Object.assign(this, { onLevel, onSilence, silenceMs, maxMs });
  }

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    this.ctx = new AudioContext();
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = this.ctx.createScriptProcessor(4096, 1, 1);
    this.chunks = [];
    this.heard = false;
    this.started = this.quietSince = performance.now();
    this.node.onaudioprocess = (e) => {
      const data = new Float32Array(e.inputBuffer.getChannelData(0));
      this.chunks.push(data);
      let sum = 0;
      for (const v of data) sum += v * v;
      const rms = Math.sqrt(sum / data.length);
      this.onLevel?.(Math.min(1, rms * 8));
      const now = performance.now();
      if (rms > 0.02) { this.heard = true; this.quietSince = now; }
      if ((this.heard && now - this.quietSince > this.silenceMs) || now - this.started > this.maxMs) this.onSilence?.();
    };
    src.connect(this.node);
    this.node.connect(this.ctx.destination);
  }

  async stop() {
    this.node.disconnect();
    this.stream.getTracks().forEach((t) => t.stop());
    const rate = this.ctx.sampleRate;
    await this.ctx.close();
    const n = this.chunks.reduce((a, c) => a + c.length, 0);
    const all = new Float32Array(n);
    let o = 0;
    for (const c of this.chunks) { all.set(c, o); o += c.length; }
    return { wav: await toWav16k(all, rate), heard: this.heard };
  }

  cancel() {
    try { this.node?.disconnect(); this.stream?.getTracks().forEach((t) => t.stop()); this.ctx?.close(); } catch { /* already closed */ }
  }
}

async function toWav16k(samples, rate) {
  const len = Math.max(1, Math.round((samples.length * 16000) / rate));
  const off = new OfflineAudioContext(1, len, 16000);
  const buf = off.createBuffer(1, Math.max(1, samples.length), rate);
  buf.copyToChannel(samples, 0);
  const s = off.createBufferSource();
  s.buffer = buf;
  s.connect(off.destination);
  s.start();
  const out = (await off.startRendering()).getChannelData(0);
  const view = new DataView(new ArrayBuffer(44 + out.length * 2));
  const str = (p, t) => [...t].forEach((c, i) => view.setUint8(p + i, c.charCodeAt(0)));
  str(0, "RIFF"); view.setUint32(4, 36 + out.length * 2, true); str(8, "WAVE"); str(12, "fmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true); view.setUint32(28, 32000, true); view.setUint16(32, 2, true);
  view.setUint16(34, 16, true); str(36, "data"); view.setUint32(40, out.length * 2, true);
  out.forEach((v, i) => view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, v)) * 0x7fff, true));
  return new Blob([view], { type: "audio/wav" });
}

export const talkApi = {
  start: (context) => request("POST", "/api/talk/sessions", context ? { context } : {}),
  status: (id) => request("GET", `/api/talk/sessions/${id}`),
  end: (id) => request("DELETE", `/api/talk/sessions/${id}`).catch(() => {}),
  message: (id, text) => request("POST", "/api/talk/message", { session_id: id, text }),
  undo: (actionId) => request("POST", `/api/talk/actions/${actionId}/undo`),
  async listen(wav) {
    const r = await fetch("/api/talk/listen", { method: "POST", headers: { "Content-Type": "audio/wav" }, body: wav });
    const data = await r.json().catch(() => null);
    if (!r.ok) {
      const e = new Error(`HTTP ${r.status}`);
      e.status = r.status;
      e.data = data;
      throw e;
    }
    return data.text;
  },
};
```

- [ ] **Step 2: Check and commit**

Run: `cp app/static/js/talk.js /tmp/talk.mjs && node --check /tmp/talk.mjs` (use the scratchpad dir instead of /tmp if required) and `.venv/bin/pytest -q`.
```bash
git add app/static/js/talk.js
git commit -m "Add shared talk client: mic capture as 16 kHz WAV, silence detection, talk API"
```

---

### Task 8: Kitchen talk panel (2b, 5a–5d, 8g, 8e), undo toast, glow, Change by voice

**Files:**
- Create: `app/static/js/talk-wall.js`
- Modify: `app/static/js/kitchen.js`, `app/static/css/kitchen.css`

**Interfaces:**
- Consumes: `talk.js`, `api.js` (`loadWeek`, `loadToday`), `ui.js` (`esc`, `icons`, `toast`, `errorText`).
- Produces: `initTalkWall(stageEl, dashEl)`; `openTalk({context = null, night = false, typing = false})`; `talkOpen() -> boolean`. Panel element `#talk-sheet` inside the stage. States: `starting`, `listening`, `thinking`, `answer`, `miss`, `error`, `nomic`, `typing`.

Reference: `.venv/bin/python -I scripts/design_card.py 2b` (and `5a`, `5b`, `5c`, `5d`, `8g`, `8e`, `3a`).

- [ ] **Step 1: Write `app/static/js/talk-wall.js`**
```js
// Kitchen "Talk to the house" panel (design 2b, 5a-5d, 8g, 8e). One panel at a time, over the dimmed dashboard.
import { loadToday, loadWeek } from "./api.js";
import { Recorder, micAvailable, talkApi } from "./talk.js";
import { errorText, esc, icons, toast } from "./ui.js";

const AUTO_CLOSE_MS = 20_000;
const KEYS = ["1234567890", "qwertyuiop", "asdfghjkl'", "zxcvbnm,.?"];
const SUGGEST = ["Add a todo for…", "Add an event…", "What's on this weekend?"];
let el, dash, t = null, pendingUndo = [];

export const talkOpen = () => t !== null;

export function initTalkWall(stageEl, dashEl) {
  dash = dashEl;
  el = document.createElement("div");
  el.id = "talk-sheet";
  el.hidden = true;
  stageEl.append(el);
  el.addEventListener("click", onClick);
  document.getElementById("toast").addEventListener("click", async (e) => {
    if (!e.target.closest("[data-undo-all]")) return;
    const ids = pendingUndo;
    pendingUndo = [];
    document.getElementById("toast").hidden = true;
    await undoMany(ids);
  });
}

export async function openTalk({ context = null, night = false, typing = false } = {}) {
  if (t) return;
  t = { mode: "starting", text: "", typed: "", shift: false, reply: "", changes: [], night, err: "", errKind: "",
        bars: new Array(16).fill(0.25), id: null, rec: null, closeTimer: null };
  dash.classList.add("dimmed");
  el.hidden = false;
  draw();
  try {
    t.id = (await talkApi.start(context)).id;
  } catch (err) {
    return fail(errorText(err), "start");
  }
  if (typing) return setMode("typing");
  if (!micAvailable()) return setMode("nomic");
  listen();
}

function setMode(mode) { if (t) { t.mode = mode; draw(); } }

async function listen() {
  clearTimeout(t.closeTimer);
  t.text = "";
  setMode("listening");
  const rec = new Recorder({ onLevel: level, onSilence: () => finishListening() });
  t.rec = rec;
  try {
    await rec.start();
  } catch {
    t.rec = null;
    setMode("nomic");
  }
}

async function finishListening() {
  const cur = t;
  const rec = cur?.rec;
  if (!rec) return;
  cur.rec = null;
  const { wav, heard } = await rec.stop();
  if (!heard) return setMode("miss");
  cur.text = "…";
  setMode("thinking");
  try {
    cur.text = await talkApi.listen(wav);
  } catch (err) {
    if (t === cur) fail(errorText(err), "voice");
    return;
  }
  if (t !== cur) return;
  if (!cur.text) return setMode("miss");
  send(cur.text);
}

async function send(text) {
  const cur = t;
  cur.text = text;
  setMode("thinking");
  try {
    const res = await talkApi.message(cur.id, text);
    if (t !== cur) return;
    cur.reply = res.reply;
    cur.changes = res.changes;
    setMode("answer");
    if (res.changes.length) Promise.all([loadWeek(), loadToday()]).catch(() => {});
    cur.closeTimer = setTimeout(() => close(), AUTO_CLOSE_MS);
  } catch (err) {
    if (t === cur) fail(errorText(err), "house");
  }
}

function fail(message, kind) {
  if (!t) return;
  t.err = message;
  t.errKind = kind;
  setMode("error");
}

function level(v) {
  if (!t) return;
  t.bars.shift();
  t.bars.push(Math.max(0.25, v));
  el.querySelectorAll(".wave i").forEach((b, i) => { b.style.transform = `scaleY(${t.bars[i]})`; });
}

async function close({ cancelled = false } = {}) {
  if (!t) return;
  const cur = t;
  t = null;
  clearTimeout(cur.closeTimer);
  cur.rec?.cancel();
  el.hidden = true;
  el.innerHTML = "";
  dash.classList.remove("dimmed");
  let changes = cur.changes;
  if (cancelled && cur.id) {
    for (let i = 0; i < 30; i++) {
      try {
        const s = await talkApi.status(cur.id);
        changes = s.changes;
        if (!s.busy) break;
      } catch { break; }
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
  if (cur.id) talkApi.end(cur.id);
  const live = changes.filter((c) => !c.undone);
  if (live.length) {
    await Promise.all([loadWeek(), loadToday()]).catch(() => {});
    glow(live);
    undoToast(live);
  }
}

function glow(changes) {
  for (const c of changes) {
    if (!c.ref || c.verb === "REMOVED") continue;
    const sel = c.kind === "event" ? `[data-uid="${CSS.escape(c.ref)}"]` : `[data-todo="${CSS.escape(c.ref)}"]`;
    document.querySelectorAll(sel).forEach((n) => {
      n.classList.add("new");
      setTimeout(() => n.classList.remove("new"), 3000);
    });
  }
}

const verbWord = { ADDED: "Added", CHANGED: "Changed", REMOVED: "Removed", DONE: "Checked off", REOPENED: "Reopened" };

function undoToast(changes) {
  const undoable = changes.filter((c) => c.undoable);
  pendingUndo = undoable.map((c) => c.id);
  const first = changes[0];
  const who = first.person ? ` for ${esc(first.person)}` : "";
  const text = changes.length === 1
    ? `${verbWord[first.verb]} ${esc(first.title)}${who}, ${esc(first.detail)}`
    : `${changes.length} changes made`;
  toast(text + (undoable.length ? ` <button class="toast-undo" data-undo-all>UNDO</button>` : ""), { ok: true });
}

async function undoMany(ids) {
  let failed = false;
  for (const id of ids) {
    try { await talkApi.undo(id); } catch { failed = true; }
  }
  Promise.all([loadWeek(), loadToday()]).catch(() => {});
  if (failed) toast("Couldn't undo");
}

async function undoCard(id) {
  try {
    await talkApi.undo(id);
    const c = t?.changes.find((x) => x.id === id);
    if (c) c.undone = true;
    draw();
    Promise.all([loadWeek(), loadToday()]).catch(() => {});
  } catch {
    toast("Couldn't undo");
  }
}

function typeKey(k) {
  if (k === "shift") t.shift = !t.shift;
  else if (k === "back") t.typed = t.typed.slice(0, -1);
  else if (k === "space") t.typed += " ";
  else { t.typed += t.shift ? k.toUpperCase() : k; t.shift = false; }
  draw();
}

async function onClick(e) {
  const b = e.target.closest("[data-t]");
  if (!b || !t) return;
  clearTimeout(t.closeTimer);
  const a = b.dataset.t;
  if (a === "stop" || a === "close" || a === "never") return close();
  if (a === "cancel") return close({ cancelled: true });
  if (a === "type") { t.rec?.cancel(); t.rec = null; return setMode("typing"); }
  if (a === "voice") return micAvailable() ? listen() : setMode("nomic");
  if (a === "again" || a === "more") return listen();
  if (a === "retry") return t.errKind === "house" && t.text ? send(t.text) : listen();
  if (a === "undo-all") { for (const c of t.changes.filter((x) => x.undoable && !x.undone)) await undoCard(c.id); return; }
  if (a === "undo") return undoCard(Number(b.dataset.id));
  if (a === "key") return typeKey(b.dataset.k);
  if (a === "suggest") { t.typed = b.dataset.s.replace("…", " "); return draw(); }
  if (a === "send") { const text = t.typed.trim(); if (text) { t.typed = ""; send(text); } }
}

function card(c) {
  const chip = c.kind === "event"
    ? `<span class="tchip" style="background:${esc(c.color)};color:${esc(c.ink)}"><b>${esc(c.detail)}</b>${esc(c.title)}</span>`
    : `<span class="tchip todo"><b>${esc(c.person || "")} · ${esc(c.detail)}</b>${esc(c.title)}</span>`;
  const meta = c.kind === "event" ? `${esc(c.calendar || "")} calendar` : `${esc(c.person || "")}'s TODOs`;
  return `<div class="tcard ${c.undone ? "undone" : ""}">${chip}<div class="tmeta">${meta}</div>` +
    `<span class="tverb">${c.undone ? "UNDONE" : esc(c.verb)}</span>` +
    (t.changes.length > 1 && c.undoable && !c.undone ? `<button class="tsmall" data-t="undo" data-id="${c.id}">Undo</button>` : "") +
    `</div>`;
}

function draw() {
  if (!t) return;
  const night = t.night ? " night" : "";
  const mic = icons.mic(40, "currentColor");
  let body;
  switch (t.mode) {
    case "starting":
    case "listening":
      body = `<div class="th accent">● LISTENING</div>` +
        `<div class="wave">${t.bars.map((v) => `<i style="transform:scaleY(${v})"></i>`).join("")}</div>` +
        `<div class="said muted">Listening…</div>` +
        `<div class="tb"><button class="tbtn stop flex" data-t="stop"><span class="sq"></span>Stop</button>` +
        `<button class="tbtn outline w560" data-t="type">Type instead</button></div>`;
      break;
    case "thinking":
      body = `<div class="th muted">THINKING</div><div class="said muted center">“${esc(t.text)}”</div>` +
        `<div class="dots"><i></i><i></i><i></i></div>` +
        `<div class="tb"><button class="tbtn outline ink flex" data-t="cancel">Cancel</button></div>`;
      break;
    case "answer": {
      const undoable = t.changes.some((c) => c.undoable && !c.undone);
      body = `<div class="th row"><span class="muted">ANSWER</span><span class="utter">“${esc(t.text)}”</span></div>` +
        `<div class="reply">${esc(t.reply)}</div><div class="tcards">${t.changes.map(card).join("")}</div>` +
        `<div class="tb">` + (undoable ? `<button class="tbtn outline w520" data-t="undo-all">Undo</button>` : "") +
        `<button class="tbtn soft flex" data-t="more">${mic}Ask more</button>` +
        `<button class="tbtn ink-fill flex" data-t="close">Done</button></div>`;
      break;
    }
    case "miss":
      body = `<div class="th muted">DIDN'T CATCH THAT</div><div class="reply">Sorry, I didn't catch that.</div>` +
        `<div class="explain">Try again a little closer to the screen.</div>` +
        `<div class="tb"><button class="tbtn accent flex" data-t="again">${mic}Say it again</button>` +
        `<button class="tbtn outline w560" data-t="never">Never mind</button></div>`;
      break;
    case "nomic":
      body = `<div class="th muted">MICROPHONE OFF</div><div class="reply">The microphone is off for this screen.</div>` +
        `<div class="tb"><button class="tbtn accent flex" data-t="type">Type instead</button>` +
        `<button class="tbtn outline w560" data-t="close">Close</button></div>`;
      break;
    case "error":
      body = `<div class="th muted">SOMETHING WENT WRONG</div><div class="reply">${esc(t.err)}</div>` +
        `<div class="tb"><button class="tbtn accent flex" data-t="retry">Try again</button>` +
        `<button class="tbtn outline w560" data-t="type">Type instead</button>` +
        `<button class="tbtn outline w520" data-t="close">Close</button></div>`;
      break;
    case "typing": {
      const rows = KEYS.map((r) => `<div class="krow">${[...r].map((k) => `<button class="key" data-t="key" data-k="${esc(k)}">` +
        `${esc(t.shift ? k.toUpperCase() : k)}</button>`).join("")}</div>`).join("");
      body = `<div class="th row"><span class="accent">TYPE TO THE HOUSE</span>` +
        (micAvailable() ? `<button class="link" data-t="voice">Use voice instead</button>` : "") + `</div>` +
        `<div class="tinput">${esc(t.typed)}<span class="caret"></span></div>` +
        `<div class="pills">${SUGGEST.map((s) => `<button class="pill" data-t="suggest" data-s="${esc(s)}">${esc(s)}</button>`).join("")}</div>` +
        `<div class="kbd">${rows}<div class="krow last"><button class="key mod" data-t="key" data-k="shift">⇧</button>` +
        `<button class="key space" data-t="key" data-k="space">space</button>` +
        `<button class="key mod" data-t="key" data-k="back">⌫</button>` +
        `<button class="key send" data-t="send">Send</button></div></div>` +
        `<button class="tclose" data-t="close">${icons.x(52, 8, "#1c1b1f")}</button>`;
      break;
    }
  }
  el.innerHTML = `<div class="tscrim"></div><div class="tsheet ${t.mode === "typing" ? "typing" : ""}${night}">${body}</div>`;
}
```

- [ ] **Step 2: Wire into `app/static/js/kitchen.js`**

1. Import: `import { initTalkWall, openTalk } from "./talk-wall.js";`
2. In `buildShell()`, change the Talk button markup to `<button class="talk" id="talk" data-talk>` (drop `aria-disabled`).
3. In `eventSheet(ev)` (view mode), when `ev.can_delete` is true, put a **Change by voice** button before Delete:
```js
  const actions = ev.can_delete
    ? `<button class="btn soft flex" data-voice="${esc(ev.uid)}">${icons.mic(40, "currentColor")}Change by voice</button>` +
      `<button class="btn outline w460" data-delete="${esc(ev.uid)}">Delete</button>`
    : `<div class="note">Change it in your Calendar app</div>`;
```
4. In `startKitchen`, after `nightEl = ...`, call `initTalkWall(stage, dash);`.
5. In the stage click handler, extend the selector with `[data-talk],[data-voice]` and handle first:
```js
    if (d.talk !== undefined) return openTalk({ night: nightEl.classList.contains("on") });
    if (d.voice) {
      const ev = findEvent(d.voice);
      closeSheet();
      return openTalk({ context: ev ? { event: { uid: ev.uid, title: ev.title, when_label: ev.when_label,
                                                 calendar: ev.calendar } } : null });
    }
```
6. Night mode must not close the talk panel: in `updateNight`, only call `closeSheet()` (talk lives in `#talk-sheet`, not `#sheet`). Keep the panel above `#night` (CSS z-index below). On the night screen the Talk button is not visible, so the panel opens in night style only when started from the woken dashboard while `isNight(new Date())`; pass `night: isNight(new Date())` instead of the class check.

- [ ] **Step 3: Styles — append to `app/static/css/kitchen.css`**
```css
/* Talk to the house panel (2b, 5a-5d, 8g, 8e) */
#talk-sheet { position: absolute; inset: 0; z-index: 5; }
.tscrim { position: absolute; inset: 0; background: rgba(28,27,31,.45); animation: fade-in .25s; }
.tsheet { position: absolute; left: 400px; top: 260px; width: 2200px; height: 1480px; background: var(--surface);
  border-radius: 80px; padding: 80px 96px; box-shadow: 0 60px 160px rgba(0,0,0,.35); display: flex; flex-direction: column;
  gap: 48px; animation: sheet-in .25s ease-out; }
.tsheet.typing { left: 300px; top: 160px; width: 2400px; height: 1700px; gap: 36px; }
.th { font: 600 36px var(--mono); letter-spacing: .12em; text-align: center; }
.th.row { display: flex; justify-content: space-between; align-items: baseline; text-align: left; }
.th .utter { font: 40px var(--sans); letter-spacing: 0; color: var(--muted); max-width: 60%; text-align: right; }
.accent { color: var(--accent); } .muted { color: var(--muted); } .center { text-align: center; }
.wave { flex: 1; display: flex; align-items: center; justify-content: center; gap: 28px; }
.wave i { width: 44px; height: 400px; border-radius: 22px; background: var(--accent); transform-origin: center;
  transition: transform .08s linear; }
.said { font: 500 72px/1.2 var(--sans); text-align: center; }
.dots { flex: 1; display: flex; justify-content: center; align-items: center; gap: 40px; }
.dots i { width: 64px; height: 64px; border-radius: 50%; background: var(--accent); animation: bounce 1.4s infinite ease-in-out; }
.dots i:nth-child(2) { animation-delay: .2s; } .dots i:nth-child(3) { animation-delay: .4s; }
@keyframes bounce { 0%, 80%, 100% { transform: scale(.6); opacity: .5; } 40% { transform: scale(1); opacity: 1; } }
.reply { font: 500 72px/1.2 var(--sans); }
.explain { font: 44px/1.3 var(--sans); color: var(--muted); }
.tcards { display: flex; flex-direction: column; gap: 24px; flex: 1; overflow-y: auto; min-height: 0; }
.tcard { background: var(--surface-2); border-radius: 48px; padding: 32px 40px; display: flex; align-items: center; gap: 32px; }
.tcard.undone { opacity: .5; }
.tchip { border-radius: 28px; padding: 18px 28px; font: 600 40px/1.15 var(--sans); display: flex; flex-direction: column; }
.tchip b { font: 600 32px var(--mono); opacity: .85; }
.tchip.todo { background: var(--surface); color: var(--ink); }
.tmeta { font: 36px var(--mono); color: var(--muted); flex: 1; }
.tverb { background: var(--success); color: #fff; border-radius: 999px; padding: 10px 24px; font: 600 32px var(--mono); }
.tcard.undone .tverb { background: var(--ring); }
.tsmall { height: 100px; padding: 0 36px; border-radius: 999px; border: 5px solid var(--divider-2); font: 600 40px var(--sans);
  color: var(--muted); }
.tb { display: flex; gap: 32px; margin-top: auto; }
.tbtn { height: 200px; border-radius: 999px; display: flex; align-items: center; justify-content: center; gap: 28px;
  font: 600 56px var(--sans); }
.tbtn.flex { flex: 1; } .tbtn.w560 { width: 560px; } .tbtn.w520 { width: 520px; }
.tbtn.stop, .tbtn.ink-fill { background: var(--ink); color: #fff; }
.tbtn.stop .sq { width: 44px; height: 44px; border-radius: 8px; background: #fff; }
.tbtn.outline { border: 6px solid var(--divider-2); color: var(--muted); font-size: 48px; }
.tbtn.outline.ink { border-color: var(--ink); color: var(--ink); }
.tbtn.soft { background: var(--accent-soft); color: var(--accent); }
.tbtn.accent { background: var(--accent); color: #fff; }
.tinput { border: 6px solid var(--accent); border-radius: 40px; padding: 32px 40px; font: 56px var(--sans); min-height: 140px; }
.tinput .caret { display: inline-block; width: 5px; height: 64px; background: var(--accent); vertical-align: -10px;
  animation: blink 1s steps(1) infinite; }
@keyframes blink { 50% { opacity: 0; } }
.pills { display: flex; gap: 24px; }
.pill { height: 120px; padding: 0 44px; border-radius: 999px; background: var(--surface-2); font: 600 44px var(--sans); }
.link { font: 600 40px var(--sans); color: var(--accent); letter-spacing: 0; min-height: 100px; }
.kbd { display: flex; flex-direction: column; gap: 16px; margin-top: auto; }
.krow { display: flex; gap: 16px; }
.key { flex: 1; height: 120px; border-radius: 24px; background: var(--surface-2); font: 600 48px var(--sans); }
.key.mod { background: var(--divider-2); font: 36px var(--mono); flex: 0 0 220px; }
.krow.last .key { height: 140px; } .key.space { flex: 4; } .key.send { flex: 0 0 360px; background: var(--ink); color: #fff;
  border-radius: 999px; }
.tclose { position: absolute; right: 64px; top: 56px; width: 120px; height: 120px; border-radius: 50%;
  background: var(--surface-2); display: flex; align-items: center; justify-content: center; }
.tsheet.typing .th.row { padding-right: 160px; }
/* Night (8e) */
.tsheet.night { background: #1a1920; border: 3px solid #2a2832; color: #e8e2d6; }
.tsheet.night .th.accent { color: #9d87e6; }
.tsheet.night .wave, .tsheet.night .said, .tsheet.night .reply { opacity: .8; }
.tsheet.night .wave i, .tsheet.night .dots i { background: #9d87e6; }
.tsheet.night .tbtn.stop { background: #e8e2d6; color: #0f0e12; }
.tsheet.night .tbtn.stop .sq { background: #0f0e12; }
.tsheet.night .tbtn.outline { border-color: #3a3744; color: #8a8494; }
/* Change by voice on the event sheet, toast undo, new-chip glow on TODO rows */
.btn.soft { background: var(--accent-soft); color: var(--accent); gap: 24px; }
.toast-undo { margin-left: 24px; padding: 12px 28px; border: 3px solid rgba(255,255,255,.5); border-radius: 999px;
  font: 600 36px var(--mono); color: #fff; min-height: 80px; }
.todo.new { outline: 8px solid var(--success); outline-offset: 6px; border-radius: 24px; }
```
Note: the kiosk toast's `UNDO` button is 80px tall inside a scaled toast; it is reachable but under the 100px target. Make `.toast-undo` `min-height: 100px` if the toast row allows it after checking against card 5c.

- [ ] **Step 4: Browser check and commit**

Run fake mode (`DASHBOARD_FAKE=1 DASHBOARD_DB=<scratch>/t8.db .venv/bin/uvicorn app.main:app --port 8097`). `localhost` counts as a secure context, so the mic API exists; the ego-browser cannot grant a real mic — exercise the flow with **Type instead**:
1. 3000×2000. Tap **Talk to the house**: the panel shows LISTENING (or MICROPHONE OFF if mic is denied). Screenshot vs card 2b.
2. **Type instead** → keyboard sheet (8g); type `add a todo for Ben to feed Milo` with the keys; **Send** → THINKING (5a) → ANSWER (5b) with an `ADDED` card for Ben. Screenshot each.
3. **Done** → panel closes, Ben's new row glows green (≈3 s), toast "Added feed Milo for Ben, …" with **UNDO**. Tap **UNDO** → the row disappears.
4. Open the House fixture event (Dentist · Ben) → **Change by voice** shows → opens the panel.
5. With the API blocked via CDP (`/api/talk/message`), Send → error state with **Try again**.
Stop the server; `.venv/bin/pytest -q && .venv/bin/ruff check .`.
```bash
git add app/static/js/talk-wall.js app/static/js/kitchen.js app/static/css/kitchen.css
git commit -m "Add kitchen talk panel with undo, glow and Change by voice"
```

---

### Task 9: Phone talk thread (4d) and Ask the house (8h)

**Files:**
- Create: `app/static/js/talk-phone.js`
- Modify: `app/static/js/phone.js`, `app/static/css/phone.css`

**Interfaces:**
- Produces: `initTalkPhone(rerender)`; `startTalkPhone(context = null)`; `endTalkPhone()`; `renderTalkPhone() -> string`; `onTalkClick(dataset) -> boolean` (true if handled); `onTalkSubmit(event) -> boolean`.
- Phone `view.screen` gains `"talk"`.

Reference: `.venv/bin/python -I scripts/design_card.py 4d` and `8h`.

- [ ] **Step 1: Write `app/static/js/talk-phone.js`**
```js
// Phone "Talk to the house" thread (design 4d). Same API as the wall; mic is tap-to-start / tap-to-stop.
import { loadToday, loadWeek } from "./api.js";
import { Recorder, micAvailable, talkApi } from "./talk.js";
import { errorText, esc, icons, toast } from "./ui.js";

let rerender = () => {};
let s = null;  // { id, items: [{role, text, changes}], busy, rec }

export function initTalkPhone(fn) { rerender = fn; }

export async function startTalkPhone(context = null) {
  s = { id: null, items: [], busy: false, rec: null };
  rerender();
  try { s.id = (await talkApi.start(context)).id; } catch (err) { s.items.push({ role: "house", text: errorText(err), changes: [] }); }
  rerender();
}

export function endTalkPhone() {
  if (!s) return;
  s.rec?.cancel();
  if (s.id) talkApi.end(s.id);
  s = null;
}

async function send(text) {
  if (!s?.id || !text) return;
  s.items.push({ role: "you", text, changes: [] });
  s.busy = true;
  rerender();
  try {
    const res = await talkApi.message(s.id, text);
    s.items.push({ role: "house", text: res.reply, changes: res.changes });
    if (res.changes.length) Promise.all([loadWeek(), loadToday()]).catch(() => {});
  } catch (err) {
    s.items.push({ role: "house", text: errorText(err), changes: [] });
  }
  s.busy = false;
  rerender();
  window.scrollTo(0, document.body.scrollHeight);
}

async function toggleMic() {
  if (!micAvailable()) return toast("The microphone needs the secure (https) address");
  if (s.rec) {
    const rec = s.rec;
    s.rec = null;
    rerender();
    const { wav, heard } = await rec.stop();
    if (!heard) return toast("Didn't catch that");
    try {
      const text = await talkApi.listen(wav);
      if (text) send(text); else toast("Didn't catch that");
    } catch (err) { toast(esc(errorText(err))); }
    return;
  }
  s.rec = new Recorder({ onSilence: () => { if (s?.rec) toggleMic(); } });
  try { await s.rec.start(); } catch { s.rec = null; toast("The microphone is off"); }
  rerender();
}

const verbClass = (c) => (c.undone ? "undone" : "");

function changeCard(c) {
  return `<div class="p-tcard ${verbClass(c)}"><i class="bar" style="background:${esc(c.color)}"></i>` +
    `<div class="b"><div class="t">${esc(c.title)}</div><div class="m">${esc(c.detail)} · ${esc(c.calendar || c.person || "")}</div></div>` +
    `<span class="p-tverb">${c.undone ? "UNDONE" : esc(c.verb)}</span>` +
    (c.undoable && !c.undone ? `<button class="p-chipbtn" data-tundo="${c.id}">Undo</button>` : "") + `</div>`;
}

export function renderTalkPhone() {
  if (!s) return "";
  const thread = s.items.map((m) => m.role === "you"
    ? `<div class="p-msg you">${esc(m.text)}</div>`
    : `<div class="p-msg house">${esc(m.text)}</div>${m.changes.map(changeCard).join("")}`).join("") +
    (s.busy ? `<div class="p-msg house typing"><i></i><i></i><i></i></div>` : "");
  return `<div class="phone p-talk-view"><div class="p-title-row"><div class="p-title"><span class="dot">●</span> The house</div>` +
    `<button class="p-link" data-tclose>Close</button></div><div class="p-thread">${thread || `<div class="p-empty">Ask the house anything.</div>`}</div></div>` +
    `<form class="p-tbar" id="talk-form" autocomplete="off"><input name="msg" placeholder="Ask the house…" maxlength="500">` +
    `<button type="button" class="p-mic ${s.rec ? "on" : ""}" data-tmic aria-label="Talk">${icons.mic(20)}</button></form>`;
}

export function onTalkClick(d) {
  if (!s) return false;
  if (d.tclose !== undefined) { endTalkPhone(); return "close"; }
  if (d.tmic !== undefined) { toggleMic(); return true; }
  if (d.tundo) {
    const id = Number(d.tundo);
    talkApi.undo(id).then(() => {
      s?.items.forEach((m) => m.changes.forEach((c) => { if (c.id === id) c.undone = true; }));
      Promise.all([loadWeek(), loadToday()]).catch(() => {});
      rerender();
    }).catch(() => toast("Couldn't undo"));
    return true;
  }
  return false;
}

export function onTalkSubmit(e) {
  if (e.target.id !== "talk-form") return false;
  e.preventDefault();
  const text = e.target.msg.value.trim();
  e.target.msg.value = "";
  send(text);
  return true;
}
```

- [ ] **Step 2: Wire into `app/static/js/phone.js`**

1. Import: `import { endTalkPhone, initTalkPhone, onTalkClick, onTalkSubmit, renderTalkPhone, startTalkPhone } from "./talk-phone.js";`
2. In `home()`, change the Talk button to `<button class="p-talk" data-go-talk>${icons.mic(20)}Talk to the house</button>` (drop `aria-disabled`).
3. In `eventSheet()`, when `ev.can_delete` and not confirming, add before Delete: `<button class="p-btn soft flex" data-ask="${esc(ev.uid)}">Ask the house to change it</button>`.
4. In `render()`: `const screen = view.screen === "talk" ? renderTalkPhone() : view.screen === "add" ? renderAdd() : ...`.
5. At the top of `onClick` (after `const d = t.dataset;`):
```js
  const handled = onTalkClick(d);
  if (handled === "close") { go("home"); return; }
  if (handled) return;
  if (d.goTalk !== undefined) { go("talk"); startTalkPhone(); return; }
  if (d.ask) {
    const ev = findEvent(d.ask);
    view.sheet = null;
    go("talk");
    startTalkPhone(ev ? { event: { uid: ev.uid, title: ev.title, when_label: ev.when_label, calendar: ev.calendar } } : null);
    return;
  }
```
6. At the top of `onSubmit`: `if (onTalkSubmit(e)) return;`.
7. In `startPhone`, call `initTalkPhone(render)`; in `go()`, when leaving `"talk"` for another screen call `endTalkPhone()` (`if (view.screen === "talk" && screen !== "talk") endTalkPhone();` before changing `view.screen`).
8. The `onClick` early selector `e.target.closest("button,[data-close]")` already covers the new buttons.

- [ ] **Step 3: Styles — append to `app/static/css/phone.css`**
```css
/* Phone talk thread (4d) */
.p-talk-view { padding-bottom: 120px; }
.p-title .dot { color: var(--accent); font-size: 20px; vertical-align: 3px; }
.p-thread { display: flex; flex-direction: column; gap: 10px; }
.p-msg { max-width: 82%; padding: 12px 16px; font: 17px/1.35 var(--sans); }
.p-msg.you { align-self: flex-end; background: var(--ink); color: #fff; border-radius: 22px 22px 6px 22px; }
.p-msg.house { align-self: flex-start; background: var(--surface); border-radius: 22px 22px 22px 6px; }
.p-msg.typing { display: flex; gap: 6px; }
.p-msg.typing i { width: 8px; height: 8px; border-radius: 50%; background: var(--faint); animation: bounce 1.4s infinite; }
.p-msg.typing i:nth-child(2) { animation-delay: .2s; } .p-msg.typing i:nth-child(3) { animation-delay: .4s; }
@keyframes bounce { 0%, 80%, 100% { opacity: .3; } 40% { opacity: 1; } }
.p-tcard { align-self: flex-start; width: 82%; background: var(--surface); border-radius: 16px; padding: 12px 14px;
  display: flex; align-items: center; gap: 10px; }
.p-tcard.undone { opacity: .5; }
.p-tcard .bar { width: 8px; align-self: stretch; border-radius: 4px; }
.p-tcard .b { flex: 1; } .p-tcard .t { font: 600 16px var(--sans); } .p-tcard .m { font: 12px var(--mono); color: var(--muted); }
.p-tverb { background: var(--success); color: #fff; border-radius: 999px; padding: 4px 10px; font: 600 11px var(--mono); }
.p-chipbtn { min-height: 48px; padding: 0 14px; border-radius: 999px; border: 2px solid var(--divider-2); font: 600 14px var(--sans); }
.p-tbar { position: fixed; left: 0; right: 0; bottom: 0; padding: 12px 20px 30px; display: flex; gap: 10px; max-width: 900px;
  margin: 0 auto; background: linear-gradient(rgba(250,249,247,0), var(--bg) 35%); }
.p-tbar input { flex: 1; height: 56px; border-radius: 999px; border: 2px solid var(--divider-2); padding: 0 20px;
  font: 17px var(--sans); background: var(--surface); color: var(--ink); }
.p-mic { width: 56px; height: 56px; border-radius: 50%; background: var(--accent); display: flex; align-items: center;
  justify-content: center; }
.p-mic.on { background: var(--danger); animation: pulse 1s infinite; }
@keyframes pulse { 50% { transform: scale(1.08); } }
.p-btn.soft { background: var(--accent-soft); color: var(--accent); }
```

- [ ] **Step 4: Browser check and commit**

Fake mode at 430×932: tap **Talk to the house** → thread view; type `add a todo for Ben to feed Milo` → House bubble + change card with **Undo** → Undo greys it. Event sheet for the House fixture event → **Ask the house to change it** opens the thread. **Close** returns home. Compare with cards 4d and 8h. Then `.venv/bin/pytest -q && .venv/bin/ruff check .`.
```bash
git add app/static/js/talk-phone.js app/static/js/phone.js app/static/css/phone.css
git commit -m "Add phone talk thread and Ask the house"
```

---

### Task 10: Docs

**Files:**
- Modify: `CLAUDE.md`, `README.md`

- [ ] **Step 1: `CLAUDE.md`** — add a "Talk to the house (Part 2)" section:
```markdown
## Talk to the house (Part 2)
- Spec: `docs/superpowers/specs/2026-10-27-kitchen-dashboard-part2-talk-design.md`.
- Flow: page records 16 kHz WAV → `/api/talk/listen` → whisper.cpp (`WHISPER_URL`, launchd `com.household.whisper` on home-ai)
  → `/api/talk/message` → Open WebUI House (`OPENWEBUI_URL`, Kitchen account key) → House tools (`house_tools/`)
  → `/api/house/*` (token) → calendar-api / TODOs, each write logged in `house_actions` for change cards + Undo.
- Secrets: `~/household-ai/secrets/kitchen/{openwebui_key,house_token}` → `/run/kitchen-secrets` (read-only). Never log or return them.
- Never use the browser Web Speech API. Mic needs HTTPS: `https://home-ai.tailfa3a6f.ts.net:8082` (`tailscale serve`).
- Fake mode has a fake whisper and a fake House ("add a todo for Ben to feed Milo").
- Update House tools: `OWUI_ADMIN_KEY=… sh ops/install-house-tools.sh` on home-ai.
```
- [ ] **Step 2: `README.md`** — add the HTTPS address and the two install scripts in one short paragraph.
- [ ] **Step 3: Commit**
```bash
git add CLAUDE.md README.md
git commit -m "Document Talk to the house"
```

---

### Task 11: Rollout on home-ai, kiosk and phones (Bob + controller)

Not a subagent task: the controller does this with Bob after the branch is merged. Several steps are blocked for Claude by the permission classifier and are run by Bob with `!`.

- [ ] **Step 1 (Bob, Tailscale admin):** enable **HTTPS Certificates** in the Tailscale admin console (DNS page) for tailnet `tailfa3a6f.ts.net`.
- [ ] **Step 2 (Bob on home-ai):** `tailscale serve --bg --https=8082 http://127.0.0.1:8081` (on macOS the CLI is `/Applications/Tailscale.app/Contents/MacOS/Tailscale`). Check `https://home-ai.tailfa3a6f.ts.net:8082` loads from a phone.
- [ ] **Step 3 (Bob in Open WebUI):** create user **Kitchen** (role user); give it access to the **House** model only; Settings → Account → create an API key; enable API keys for users if Open WebUI asks (Admin → Settings → General).
- [ ] **Step 4 (Bob on home-ai):** create the secrets:
```sh
mkdir -p ~/household-ai/secrets/kitchen && chmod 700 ~/household-ai/secrets/kitchen
printf '%s' '<Kitchen API key>' > ~/household-ai/secrets/kitchen/openwebui_key
openssl rand -hex 32 > ~/household-ai/secrets/kitchen/house_token
chmod 600 ~/household-ai/secrets/kitchen/*
```
  If the container (uid 10001) cannot read 600 files on the OrbStack bind mount, use 644 inside the 700 directory.
- [ ] **Step 5 (controller over SSH):** `sh ~/kitchen-dashboard/ops/install-whisper.sh`; check `curl -s 127.0.0.1:8178` answers and `docker exec kitchen-dashboard python -c "import urllib.request;print(urllib.request.urlopen('http://host.docker.internal:8178').status)"` returns 200.
- [ ] **Step 6 (Bob on home-ai):** `OWUI_ADMIN_KEY=<admin key> sh ~/kitchen-dashboard/ops/install-house-tools.sh`; then share both tools with the Kitchen account in Open WebUI (Workspace → Tools → Access).
- [ ] **Step 7 (controller):** live test from a laptop browser on `https://…:8082`: typed and spoken "add a TODO for Ben to feed Milo"; confirm the change card appears (proves `session_id` reaches the tools; if not, the fallback attribution still shows it — note which in the report). Undo it.
- [ ] **Step 8 (Bob on the Surface):** set `KIOSK_URL=https://home-ai.tailfa3a6f.ts.net:8082` in `/etc/kiosk.conf`; allow the mic for that origin only with a Chromium policy file `/etc/chromium/policies/managed/kiosk-mic.json` (path depends on the browser package; for Google Chrome use `/etc/opt/chrome/policies/managed/`):
```json
{ "AudioCaptureAllowedUrls": ["https://home-ai.tailfa3a6f.ts.net:8082"] }
```
  then `sudo systemctl restart kiosk`.
- [ ] **Step 9:** Bob tests on the kiosk and a phone; adjust from his feedback. Close beads issue `kd-gzm`.
