# Kitchen Dashboard Part 1 (Core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and ship the core kitchen dashboard (calendar week, Next up, per-person daily TODOs, night mode, phone screens) to home-ai, deploying itself from `main`.

**Architecture:** A FastAPI server with four small units (`store`, `todos`, `settings`, `calendar`) plus pure label helpers (`labels`) and a thin `api` module. The server does all date logic and formatting in America/Chicago and serves a plain HTML/CSS/JS page. The page polls a tiny change counter every 10 s and the calendar every 60 s. The kitchen layout is authored at the design's exact 3000×2000 px and scaled to fit smaller windows (scale is 1 on the kiosk).

**Tech Stack:** Python 3.13, FastAPI 0.120.0, uvicorn 0.38.0, SQLite (stdlib), pytest 8.4.2, httpx 0.28.1, ruff 0.14.1, plain ES-module JavaScript, Docker + compose, launchd on macOS.

**Spec:** `docs/superpowers/specs/2026-10-26-kitchen-dashboard-part1-design.md`
**Design:** `docs/design/README.md` and `docs/design/Kitchen Dashboard.dc.html` (card ids such as `2a`; print one card's markup with `python3 -I scripts/design_card.py 2a`, added in Task 7).

## Global Constraints

- No external network calls from the page or the server. No CDNs, web fonts, analytics or third-party APIs. System fonts only: sans `system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif`; mono `ui-monospace, Menlo, Consolas, "Liberation Mono", monospace`.
- All dates and times are America/Chicago, computed in code. Never slice raw calendar ISO strings to get a date.
- Kitchen: 3000×2000 at DPR 1; touch only; no hover styles; tap targets ≥ 100px; nothing below 30px. Never use browser zoom or `--force-device-scale-factor`.
- Phone: `max-width: 900px`; tap targets ≥ 48px; the only place with text entry.
- Escape all calendar and TODO text before inserting it into the DOM (`esc()` in `app/static/js/ui.js`).
- This app never talks to iCloud. Calendar writes go only through calendar-api.
- No secrets in the repo.
- Dependencies pinned in `requirements.txt` / `requirements-dev.txt`. No JS frameworks, bundlers or JS test tools.
- calendar-api: `http://calendar-api:8000`, `GET /events?start=YYYY-MM-DD&days=N&kitchen_only=true` → `{events:[{calendar, title, when, start, end, all_day, location, uid, added_by_house}]}`; `DELETE /events/{uid}` only for House events.
- Ports: host `8081` → app `8000`. Docker network `household-ai_default` (external). Data volume `~/household-ai/data/dashboard:/data`.
- Design colors (from `docs/design/README.md`): bg `#faf9f7`, surface `#fff`, surface-2 `#f4f2f7`, divider `#f0eef4`/`#e6e3ee`, dashed `#d9d5e3`, ink `#1c1b1f`, muted `#6b6875`, faint `#9995a3`, ring `#c9c4d6`, accent `#6b45d9`, accent-soft `#efe9fb`, success `#2fb36a`, warning `#e9a23b` (text `#b5742a`), danger `#d2382f` (tint `#fdf1f0`). Night: bg `#0f0e12`, line `#2a2832`, text `#e8e2d6`/`#d9d3c7`, muted `#8a8494`/`#6f6a7a`, dim `#4a4752`, success `#3a7d55`.
- Calendar presets, in order: `#f2c230` yellow, `#e0702a` orange, `#d2382f` red, `#e0457b` pink, `#6b45d9` violet, `#2b5fd9` blue, `#14a08a` teal, `#2fb36a` green.
- Chip ink: `#1c1b1f` when relative luminance > 0.55, else `#fff`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

## File Structure

```
app/__init__.py            empty
app/clock.py               TZ and now(); tests monkeypatch clock.now
app/store.py               Store: SQLite connect, schema, seed, change counter
app/labels.py              pure formatting: times, relative labels, when label, ink color, presets
app/todos.py               TODO rules: today_view, create, update, delete
app/settings.py            calendar colors and people
app/calendar.py            HttpSource, FixtureSource, CalendarService (cache + stale), build_week
app/api.py                 create_app(): routes, validation, quiet access log, static files
app/main.py                `app = create_app()` for uvicorn
app/static/index.html
app/static/css/base.css    tokens, reset, shared pieces (chips, icons, toast)
app/static/css/kitchen.css 3000×2000 stage, dashboard, sheets, night
app/static/css/phone.css   phone layout and sheets
app/static/js/ui.js        esc, Chicago time formatting, icons, toast
app/static/js/api.js       request(), shared state, polling, status line
app/static/js/kitchen.js   kitchen dashboard, sheets, night mode
app/static/js/phone.js     phone home, add TODO, settings, sheets
app/static/js/main.js      picks layout, version reload
fixtures/events.json       fake events (day offsets) for dev and CI
tests/__init__.py, tests/conftest.py, tests/fakes.py
tests/test_store.py, test_labels.py, test_todos.py, test_settings.py, test_calendar.py, test_api.py
scripts/dev.sh, scripts/deploy.sh, scripts/design_card.py
ops/deploy-here.sh, ops/watch-deploy.sh, ops/install-on-home-ai.sh, ops/com.household.kitchen-deploy.plist
Dockerfile, .dockerignore, docker-compose.yml, .github/workflows/ci.yml
requirements.txt, requirements-dev.txt, pyproject.toml, CLAUDE.md, README.md
```

---

### Task 1: Project skeleton and store

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `app/__init__.py`, `app/clock.py`, `app/store.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_store.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `app.clock.TZ: ZoneInfo`, `app.clock.now() -> datetime` (aware, Chicago). `app.store.Store(path: str)` with `.connect() -> sqlite3.Connection` (row_factory `sqlite3.Row`, foreign keys on, `check_same_thread=False`, schema ensured on construction). Module functions `store.bump(con) -> None`, `store.changes(con) -> int`, constant `store.SEED_PEOPLE = ("Bob", "Belen", "Ben")`. Test fixtures `store`, `con`, `freeze`.

- [ ] **Step 1: Create tooling files**

`requirements.txt`:
```
fastapi==0.120.0
uvicorn==0.38.0
```

`requirements-dev.txt`:
```
-r requirements.txt
pytest==8.4.2
httpx==0.28.1
ruff==0.14.1
```

`pyproject.toml`:
```toml
[project]
name = "kitchen-dashboard"
version = "0.1.0"
requires-python = ">=3.13"

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]

[tool.ruff]
line-length = 120
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

Append to `.gitignore`:
```
.dev.db
```

Create empty `app/__init__.py` and `tests/__init__.py`.

Run: `python3.13 -m venv .venv && . .venv/bin/activate && pip install -q -r requirements-dev.txt`
Expected: installs without errors.

- [ ] **Step 2: Write `app/clock.py`**

```python
"""The one place the app reads the time. Tests replace `now` with monkeypatch."""
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Chicago")


def now() -> datetime:
    return datetime.now(TZ)
```

- [ ] **Step 3: Write test fixtures `tests/conftest.py`**

```python
from datetime import datetime

import pytest

from app import clock
from app.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / "test.db"))


@pytest.fixture
def con(store):
    c = store.connect()
    yield c
    c.close()


@pytest.fixture
def freeze(monkeypatch):
    """freeze("2026-10-26T15:20") pins clock.now() to that Chicago wall time."""
    def _freeze(local_iso: str) -> datetime:
        dt = datetime.fromisoformat(local_iso).replace(tzinfo=clock.TZ)
        monkeypatch.setattr(clock, "now", lambda: dt)
        return dt
    return _freeze
```

- [ ] **Step 4: Write the failing tests `tests/test_store.py`**

```python
from app import store as st


def test_seeds_people_once(store):
    with store.connect() as c:
        names = [r["name"] for r in c.execute("select name from people order by sort")]
    assert names == ["Bob", "Belen", "Ben"]
    st.Store(store.path)  # opening again must not seed twice
    with store.connect() as c:
        assert c.execute("select count(*) from people").fetchone()[0] == 3


def test_change_counter(con):
    assert st.changes(con) == 0
    with con:
        st.bump(con)
        st.bump(con)
    assert st.changes(con) == 2


def test_foreign_keys_on(con):
    import sqlite3

    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        with con:
            con.execute("insert into todos (person_id, text, date, created_at) values (999, 'x', '2026-10-26', 'now')")
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `pytest tests/test_store.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.store'`

- [ ] **Step 6: Write `app/store.py`**

```python
"""SQLite access: schema, first-run seed and the change counter the page polls."""
import sqlite3
from pathlib import Path

SEED_PEOPLE = ("Bob", "Belen", "Ben")

SCHEMA = """
create table if not exists people (
    id integer primary key,
    name text not null,
    sort integer not null
);
create table if not exists todos (
    id integer primary key,
    person_id integer not null references people(id),
    text text not null,
    date text not null,
    time text,
    done_at text,
    created_by text not null default 'phone',
    created_at text not null
);
create table if not exists calendar_colors (
    calendar text primary key,
    color text not null
);
create table if not exists calendar_cache (
    key text primary key,
    fetched_at text not null,
    body text not null
);
create table if not exists meta (
    key text primary key,
    value text not null
);
"""


class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        con = self.connect()
        try:
            con.executescript(SCHEMA)
            with con:
                con.execute("insert or ignore into meta (key, value) values ('changes', '0')")
                con.execute("insert or ignore into meta (key, value) values ('schema_version', '1')")
                if con.execute("select count(*) from people").fetchone()[0] == 0:
                    con.executemany("insert into people (name, sort) values (?, ?)",
                                    [(n, i) for i, n in enumerate(SEED_PEOPLE)])
        finally:
            con.close()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("pragma foreign_keys = on")
        return con


def bump(con: sqlite3.Connection) -> None:
    """Call inside the same transaction as any write the page must notice."""
    con.execute("update meta set value = cast(value as integer) + 1 where key = 'changes'")


def changes(con: sqlite3.Connection) -> int:
    return int(con.execute("select value from meta where key = 'changes'").fetchone()[0])
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_store.py -q && ruff check .`
Expected: `3 passed`, ruff `All checks passed!`

- [ ] **Step 8: Commit**

```bash
git add requirements.txt requirements-dev.txt pyproject.toml .gitignore app tests
git commit -m "Add project skeleton, clock and SQLite store

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Label helpers

**Files:**
- Create: `app/labels.py`, `tests/test_labels.py`

**Interfaces:**
- Produces (all pure):
  - `PRESETS: list[str]` (the 8 preset hex colors, in order)
  - `DARK_INK = "#1c1b1f"`, `LIGHT_INK = "#fff"`
  - `clock_time(dt: datetime) -> str` → `"5:30 PM"`
  - `day_word(d: date, today: date) -> str` → `"Today" | "Tomorrow" | "Wed"`
  - `relative_label(d: date, start: datetime | None, today: date) -> str` → `"Today, 5:30 PM"`, or `"Today"` for all-day
  - `time_label(start: datetime | None) -> str` → `"5:30 PM"` or `"all day"`
  - `when_label(d: date, start: datetime | None, end: datetime | None) -> str` → `"Thursday 29 Oct, 4:00 – 4:45 PM"`
  - `todo_time_label(hhmm: str | None) -> str | None` → `"2:00 PM"`
  - `ink_for(color: str) -> str`

- [ ] **Step 1: Write the failing tests `tests/test_labels.py`**

```python
from datetime import date, datetime

from app import labels
from app.clock import TZ

TODAY = date(2026, 10, 26)  # a Monday


def at(h, m, d=TODAY):
    return datetime(d.year, d.month, d.day, h, m, tzinfo=TZ)


def test_clock_time_has_no_leading_zero():
    assert labels.clock_time(at(9, 0)) == "9:00 AM"
    assert labels.clock_time(at(17, 30)) == "5:30 PM"
    assert labels.clock_time(at(0, 5)) == "12:05 AM"


def test_relative_label():
    assert labels.relative_label(TODAY, at(17, 30), TODAY) == "Today, 5:30 PM"
    tue = date(2026, 10, 27)
    assert labels.relative_label(tue, at(9, 0, tue), TODAY) == "Tomorrow, 9:00 AM"
    wed = date(2026, 10, 28)
    assert labels.relative_label(wed, at(16, 0, wed), TODAY) == "Wed, 4:00 PM"
    assert labels.relative_label(TODAY, None, TODAY) == "Today"


def test_time_label():
    assert labels.time_label(None) == "all day"
    assert labels.time_label(at(6, 30)) == "6:30 AM"


def test_when_label():
    thu = date(2026, 10, 29)
    assert labels.when_label(thu, at(16, 0, thu), at(16, 45, thu)) == "Thursday 29 Oct, 4:00 – 4:45 PM"
    assert labels.when_label(thu, at(11, 0, thu), at(13, 0, thu)) == "Thursday 29 Oct, 11:00 AM – 1:00 PM"
    assert labels.when_label(thu, at(16, 0, thu), None) == "Thursday 29 Oct, 4:00 PM"
    assert labels.when_label(thu, None, None) == "Thursday 29 Oct, all day"


def test_todo_time_label():
    assert labels.todo_time_label("14:00") == "2:00 PM"
    assert labels.todo_time_label(None) is None


def test_ink_for_light_and_dark():
    assert labels.ink_for("#f2c230") == labels.DARK_INK   # yellow
    assert labels.ink_for("#2b5fd9") == labels.LIGHT_INK  # blue
    assert labels.ink_for("#e0457b") == labels.LIGHT_INK  # pink
    assert labels.ink_for("#FFFFFF") == labels.DARK_INK


def test_presets():
    assert labels.PRESETS == ["#f2c230", "#e0702a", "#d2382f", "#e0457b",
                              "#6b45d9", "#2b5fd9", "#14a08a", "#2fb36a"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_labels.py -q`
Expected: FAIL with `ImportError: cannot import name 'labels'`

- [ ] **Step 3: Write `app/labels.py`**

```python
"""Text the page shows, built on the server so pytest can check it. Pure functions only."""
from datetime import date, datetime, time

PRESETS = ["#f2c230", "#e0702a", "#d2382f", "#e0457b", "#6b45d9", "#2b5fd9", "#14a08a", "#2fb36a"]
DARK_INK = "#1c1b1f"
LIGHT_INK = "#fff"


def clock_time(dt: datetime | time) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def day_word(d: date, today: date) -> str:
    delta = (d - today).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    return d.strftime("%a")


def relative_label(d: date, start: datetime | None, today: date) -> str:
    word = day_word(d, today)
    return word if start is None else f"{word}, {clock_time(start)}"


def time_label(start: datetime | None) -> str:
    return "all day" if start is None else clock_time(start)


def when_label(d: date, start: datetime | None, end: datetime | None) -> str:
    head = f"{d.strftime('%A')} {d.day} {d.strftime('%b')}"
    if start is None:
        return f"{head}, all day"
    if end is None:
        return f"{head}, {clock_time(start)}"
    s, e = clock_time(start), clock_time(end)
    if s[-2:] == e[-2:]:
        s = s[:-3]
    return f"{head}, {s} – {e}"


def todo_time_label(hhmm: str | None) -> str | None:
    if not hhmm:
        return None
    h, m = map(int, hhmm.split(":"))
    return clock_time(time(h, m))


def _channel(c: int) -> float:
    v = c / 255
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def ink_for(color: str) -> str:
    """Design rule 1e: dark text on light fills, white text on dark fills."""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    lum = 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)
    return DARK_INK if lum > 0.55 else LIGHT_INK
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_labels.py -q && ruff check .`
Expected: `7 passed`, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add app/labels.py tests/test_labels.py
git commit -m "Add label helpers for times, relative days and chip ink

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: TODO rules

**Files:**
- Create: `app/todos.py`, `tests/test_todos.py`

**Interfaces:**
- Consumes: `store.bump`, `labels.todo_time_label`, fixtures `con`, `freeze`.
- Produces:
  - `today_view(con, now: datetime) -> dict` → `{"date": "YYYY-MM-DD", "people": [Person]}` where Person = `{"id", "name", "initial", "todos": [Item], "left": int, "overdue": int, "state": "open"|"all_done"|"empty"}` and Item = `{"id", "person_id", "text", "date", "time", "time_label", "done", "overdue", "carried", "created_by"}`.
  - `create(con, now, *, person_id: int, text: str, date: str, time: str | None, created_by: str = "phone") -> dict` (an Item without `overdue`/`carried`; raises `LookupError("unknown person")`).
  - `update(con, now, todo_id: int, fields: dict) -> dict` (keys any of `text, person_id, date, time, done`; raises `KeyError` if no such todo, `LookupError` for unknown person).
  - `delete(con, todo_id: int) -> bool`.
  - `get(con, todo_id: int) -> dict | None`.

- [ ] **Step 1: Write the failing tests `tests/test_todos.py`**

```python
import pytest

from app import store as st
from app import todos


def ids(con):
    return {r["name"]: r["id"] for r in con.execute("select id, name from people")}


def add(con, now, who, text, date, time=None):
    return todos.create(con, now, person_id=ids(con)[who], text=text, date=date, time=time)


def person(view, name):
    return next(p for p in view["people"] if p["name"] == name)


def test_empty_state(con, freeze):
    now = freeze("2026-10-26T09:00")
    view = todos.today_view(con, now)
    assert view["date"] == "2026-10-26"
    assert [p["name"] for p in view["people"]] == ["Bob", "Belen", "Ben"]
    ben = person(view, "Ben")
    assert ben["state"] == "empty" and ben["todos"] == [] and ben["initial"] == "B"


def test_today_carry_over_and_future(con, freeze):
    now = freeze("2026-10-26T09:00")
    add(con, now, "Bob", "old open", "2026-10-24")
    add(con, now, "Bob", "today", "2026-10-26")
    add(con, now, "Bob", "tomorrow", "2026-10-27")
    bob = person(todos.today_view(con, now), "Bob")
    texts = [t["text"] for t in bob["todos"]]
    assert texts == ["old open", "today"]
    assert bob["todos"][0]["carried"] and bob["todos"][0]["overdue"]
    assert bob["left"] == 2 and bob["overdue"] == 1 and bob["state"] == "open"


def test_timed_item_becomes_overdue(con, freeze):
    now = freeze("2026-10-26T14:30")
    add(con, now, "Bob", "plumber", "2026-10-26", "14:00")
    add(con, now, "Bob", "pick up", "2026-10-26", "17:00")
    bob = person(todos.today_view(con, now), "Bob")
    by = {t["text"]: t for t in bob["todos"]}
    assert by["plumber"]["overdue"] and not by["pick up"]["overdue"]
    assert by["plumber"]["time_label"] == "2:00 PM"


def test_order_overdue_then_timed_then_untimed_then_done(con, freeze):
    now = freeze("2026-10-26T15:00")
    a = add(con, now, "Ben", "untimed", "2026-10-26")
    add(con, now, "Ben", "late", "2026-10-26", "18:00")
    add(con, now, "Ben", "early", "2026-10-26", "16:00")
    add(con, now, "Ben", "overdue", "2026-10-26", "09:00")
    add(con, now, "Ben", "carried", "2026-10-25")
    todos.update(con, now, a["id"], {"done": True})
    ben = person(todos.today_view(con, now), "Ben")
    assert [t["text"] for t in ben["todos"]] == ["carried", "overdue", "early", "late", "untimed"]
    assert ben["todos"][-1]["done"]


def test_done_today_from_old_date_still_shows(con, freeze):
    now = freeze("2026-10-26T10:00")
    t = add(con, now, "Belen", "old", "2026-10-20")
    todos.update(con, now, t["id"], {"done": True})
    belen = person(todos.today_view(con, now), "Belen")
    assert [x["text"] for x in belen["todos"]] == ["old"]
    assert belen["state"] == "all_done" and belen["left"] == 0


def test_done_yesterday_is_hidden(con, freeze):
    yesterday = freeze("2026-10-25T20:00")
    t = add(con, yesterday, "Belen", "done yesterday", "2026-10-25")
    todos.update(con, yesterday, t["id"], {"done": True})
    now = freeze("2026-10-26T08:00")
    assert person(todos.today_view(con, now), "Belen")["state"] == "empty"


def test_undo_restores_open(con, freeze):
    now = freeze("2026-10-26T10:00")
    t = add(con, now, "Bob", "x", "2026-10-26")
    todos.update(con, now, t["id"], {"done": True})
    again = todos.update(con, now, t["id"], {"done": False})
    assert again["done"] is False and again["date"] == "2026-10-26"


def test_writes_bump_changes(con, freeze):
    now = freeze("2026-10-26T10:00")
    t = add(con, now, "Bob", "x", "2026-10-26")
    todos.update(con, now, t["id"], {"text": "y"})
    todos.delete(con, t["id"])
    assert st.changes(con) == 3


def test_errors(con, freeze):
    now = freeze("2026-10-26T10:00")
    with pytest.raises(LookupError):
        todos.create(con, now, person_id=999, text="x", date="2026-10-26", time=None)
    with pytest.raises(KeyError):
        todos.update(con, now, 999, {"text": "x"})
    assert todos.delete(con, 999) is False


def test_move_to_other_person(con, freeze):
    now = freeze("2026-10-26T10:00")
    t = add(con, now, "Bob", "x", "2026-10-26")
    moved = todos.update(con, now, t["id"], {"person_id": ids(con)["Ben"], "time": "15:30"})
    assert moved["person_id"] == ids(con)["Ben"] and moved["time"] == "15:30"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_todos.py -q`
Expected: FAIL with `ImportError: cannot import name 'todos'`

- [ ] **Step 3: Write `app/todos.py`**

```python
"""Daily TODOs per person: what today's list holds, its order, and its counts."""
import sqlite3
from datetime import datetime

from app import labels
from app import store as st

FIELDS = ("text", "person_id", "date", "time", "done")


def _item(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "person_id": row["person_id"], "text": row["text"],
        "date": row["date"], "time": row["time"], "time_label": labels.todo_time_label(row["time"]),
        "done": row["done_at"] is not None, "created_by": row["created_by"],
    }


def get(con: sqlite3.Connection, todo_id: int) -> dict | None:
    row = con.execute("select * from todos where id = ?", (todo_id,)).fetchone()
    return _item(row) if row else None


def today_view(con: sqlite3.Connection, now: datetime) -> dict:
    today, hhmm = now.date().isoformat(), now.strftime("%H:%M")
    rows = con.execute(
        """select * from todos
           where (done_at is null and date <= ?) or (done_at is not null and substr(done_at, 1, 10) = ?)""",
        (today, today)).fetchall()
    by_person: dict[int, list[dict]] = {}
    for row in rows:
        item = _item(row)
        open_ = not item["done"]
        item["carried"] = open_ and item["date"] < today
        item["overdue"] = open_ and (item["carried"] or (item["date"] == today and bool(item["time"])
                                                          and item["time"] < hhmm))
        item["_done_at"] = row["done_at"]
        by_person.setdefault(item["person_id"], []).append(item)

    def order(t: dict) -> tuple:
        if t["done"]:
            return (3, t["_done_at"], "", t["id"])
        if t["overdue"]:
            return (0, t["date"], t["time"] or "", t["id"])
        if t["time"]:
            return (1, t["time"], "", t["id"])
        return (2, "", "", t["id"])

    people = []
    for p in con.execute("select id, name from people order by sort, id"):
        items = sorted(by_person.get(p["id"], []), key=order)
        for t in items:
            del t["_done_at"]
        left = sum(not t["done"] for t in items)
        state = "empty" if not items else "all_done" if left == 0 else "open"
        people.append({"id": p["id"], "name": p["name"], "initial": p["name"][:1].upper(), "todos": items,
                       "left": left, "overdue": sum(t["overdue"] for t in items), "state": state})
    return {"date": today, "people": people}


def _check_person(con: sqlite3.Connection, person_id: int) -> None:
    if not con.execute("select 1 from people where id = ?", (person_id,)).fetchone():
        raise LookupError("unknown person")


def create(con: sqlite3.Connection, now: datetime, *, person_id: int, text: str, date: str,
           time: str | None, created_by: str = "phone") -> dict:
    _check_person(con, person_id)
    with con:
        cur = con.execute(
            "insert into todos (person_id, text, date, time, created_by, created_at) values (?, ?, ?, ?, ?, ?)",
            (person_id, text, date, time, created_by, now.isoformat(timespec="seconds")))
        st.bump(con)
    return get(con, cur.lastrowid)


def update(con: sqlite3.Connection, now: datetime, todo_id: int, fields: dict) -> dict:
    if get(con, todo_id) is None:
        raise KeyError(todo_id)
    if "person_id" in fields:
        _check_person(con, fields["person_id"])
    sets, values = [], []
    for key in FIELDS:
        if key not in fields:
            continue
        if key == "done":
            sets.append("done_at = ?")
            values.append(now.isoformat(timespec="seconds") if fields["done"] else None)
        else:
            sets.append(f"{key} = ?")
            values.append(fields[key])
    if sets:
        with con:
            con.execute(f"update todos set {', '.join(sets)} where id = ?", (*values, todo_id))
            st.bump(con)
    return get(con, todo_id)


def delete(con: sqlite3.Connection, todo_id: int) -> bool:
    with con:
        cur = con.execute("delete from todos where id = ?", (todo_id,))
        if cur.rowcount:
            st.bump(con)
    return cur.rowcount > 0
```

`done_at` is written with `now.isoformat()` where `now` is Chicago time, so its first 10 characters are the Chicago date. That is the only date the app slices, and the app wrote it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_todos.py -q && ruff check .`
Expected: `10 passed`, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add app/todos.py tests/test_todos.py
git commit -m "Add TODO rules: carry-over, overdue, order and counts

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Settings (calendar colors and people)

**Files:**
- Create: `app/settings.py`, `tests/test_settings.py`

**Interfaces:**
- Consumes: `store.bump`, `labels.PRESETS`, `labels.ink_for`.
- Produces:
  - `ensure_colors(con, names: list[str]) -> dict[str, str]` (assigns presets to unseen names; returns all stored colors)
  - `calendars(con) -> list[dict]` → `[{"name", "color", "ink"}]` in first-seen order
  - `set_color(con, name: str, color: str) -> dict` → `{"name", "color", "ink"}` (color lower-cased)
  - `people(con) -> list[dict]` → `[{"id", "name", "sort"}]`
  - `add_person(con, name: str) -> dict`
  - `update_person(con, person_id: int, *, name: str | None = None, sort: int | None = None) -> dict` (raises `KeyError`)
  - `delete_person(con, person_id: int) -> None` (raises `KeyError` if missing, `ValueError("has todos")` if the person has TODOs)

- [ ] **Step 1: Write the failing tests `tests/test_settings.py`**

```python
import pytest

from app import labels, settings
from app import store as st


def test_presets_assigned_in_order_and_kept(con):
    colors = settings.ensure_colors(con, ["Family", "School"])
    assert colors == {"Family": labels.PRESETS[0], "School": labels.PRESETS[1]}
    colors = settings.ensure_colors(con, ["School", "Belen"])
    assert colors["School"] == labels.PRESETS[1] and colors["Belen"] == labels.PRESETS[2]


def test_preset_skips_colors_in_use(con):
    settings.set_color(con, "Family", labels.PRESETS[0])
    settings.set_color(con, "Work", labels.PRESETS[1])
    assert settings.ensure_colors(con, ["New"])["New"] == labels.PRESETS[2]


def test_wraps_when_all_presets_used(con):
    names = [f"C{i}" for i in range(9)]
    colors = settings.ensure_colors(con, names)
    assert colors["C8"] == labels.PRESETS[0]


def test_set_color_and_calendar_list(con):
    settings.ensure_colors(con, ["Family"])
    out = settings.set_color(con, "Family", "#2B5FD9")
    assert out == {"name": "Family", "color": "#2b5fd9", "ink": "#fff"}
    assert settings.calendars(con) == [out]


def test_no_bump_when_nothing_new(con):
    settings.ensure_colors(con, ["Family"])
    n = st.changes(con)
    settings.ensure_colors(con, ["Family"])
    assert st.changes(con) == n


def test_people_crud(con):
    ana = settings.add_person(con, "Ana")
    assert ana["sort"] == 3 and [p["name"] for p in settings.people(con)][-1] == "Ana"
    assert settings.update_person(con, ana["id"], name="Anna")["name"] == "Anna"
    settings.delete_person(con, ana["id"])
    assert "Anna" not in [p["name"] for p in settings.people(con)]
    with pytest.raises(KeyError):
        settings.delete_person(con, 999)


def test_cannot_delete_person_with_todos(con):
    ben = next(p for p in settings.people(con) if p["name"] == "Ben")
    with con:
        con.execute("insert into todos (person_id, text, date, created_at) values (?, 'x', '2026-10-26', 'n')",
                    (ben["id"],))
    with pytest.raises(ValueError):
        settings.delete_person(con, ben["id"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_settings.py -q`
Expected: FAIL with `ImportError: cannot import name 'settings'`

- [ ] **Step 3: Write `app/settings.py`**

```python
"""Calendar colors and the family list, both edited from the phone."""
import sqlite3

from app import labels
from app import store as st


def ensure_colors(con: sqlite3.Connection, names: list[str]) -> dict[str, str]:
    colors = {r["calendar"]: r["color"] for r in con.execute("select calendar, color from calendar_colors")}
    new = [n for n in dict.fromkeys(names) if n not in colors]
    if new:
        with con:
            for name in new:
                used = set(colors.values())
                free = [c for c in labels.PRESETS if c not in used]
                color = free[0] if free else labels.PRESETS[len(colors) % len(labels.PRESETS)]
                con.execute("insert into calendar_colors (calendar, color) values (?, ?)", (name, color))
                colors[name] = color
            st.bump(con)
    return colors


def calendars(con: sqlite3.Connection) -> list[dict]:
    rows = con.execute("select calendar, color from calendar_colors order by rowid")
    return [{"name": r["calendar"], "color": r["color"], "ink": labels.ink_for(r["color"])} for r in rows]


def set_color(con: sqlite3.Connection, name: str, color: str) -> dict:
    color = color.lower()
    with con:
        con.execute("insert into calendar_colors (calendar, color) values (?, ?) "
                    "on conflict(calendar) do update set color = excluded.color", (name, color))
        st.bump(con)
    return {"name": name, "color": color, "ink": labels.ink_for(color)}


def people(con: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in con.execute("select id, name, sort from people order by sort, id")]


def _person(con: sqlite3.Connection, person_id: int) -> dict:
    row = con.execute("select id, name, sort from people where id = ?", (person_id,)).fetchone()
    if not row:
        raise KeyError(person_id)
    return dict(row)


def add_person(con: sqlite3.Connection, name: str) -> dict:
    with con:
        sort = con.execute("select coalesce(max(sort), -1) + 1 from people").fetchone()[0]
        cur = con.execute("insert into people (name, sort) values (?, ?)", (name, sort))
        st.bump(con)
    return _person(con, cur.lastrowid)


def update_person(con: sqlite3.Connection, person_id: int, *, name: str | None = None,
                  sort: int | None = None) -> dict:
    _person(con, person_id)
    with con:
        if name is not None:
            con.execute("update people set name = ? where id = ?", (name, person_id))
        if sort is not None:
            con.execute("update people set sort = ? where id = ?", (sort, person_id))
        st.bump(con)
    return _person(con, person_id)


def delete_person(con: sqlite3.Connection, person_id: int) -> None:
    _person(con, person_id)
    if con.execute("select 1 from todos where person_id = ? limit 1", (person_id,)).fetchone():
        raise ValueError("has todos")
    with con:
        con.execute("delete from people where id = ?", (person_id,))
        st.bump(con)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_settings.py -q && ruff check .`
Expected: `7 passed`, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add app/settings.py tests/test_settings.py
git commit -m "Add settings: calendar colors with presets, family list

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Calendar service and week builder

**Files:**
- Create: `app/calendar.py`, `fixtures/events.json`, `tests/fakes.py`, `tests/test_calendar.py`

**Interfaces:**
- Consumes: `clock.now`, `clock.TZ`, `labels.*`, `Store`.
- Produces:
  - `class CalendarError(Exception)`
  - `HttpSource(base_url: str, timeout: float = 15)` with `.events(start: date, days: int) -> list[dict]` (raises `CalendarError`) and `.delete(uid: str) -> tuple[int, dict]`
  - `FixtureSource(path: Path)` with the same two methods
  - `CalendarService(source, store: Store, ttl: int = 60)` with `.events(days: int = 7) -> dict` → `{"events": list[dict], "fetched_at": datetime | None, "ok": bool}`, `.delete(uid) -> tuple[int, dict]`, `.invalidate()`
  - `build_week(events: list[dict], now: datetime, colors: dict[str, str], days: int = 7) -> dict` → `{"days": [Day], "next": [Event]}`. Day = `{"date", "dow", "dow_long", "day", "month", "is_today", "events": [Event], "more": int}` (`events` holds every event of the day, sorted; the page shows the first 3; `more = max(0, len - 3)`). Event = `{"uid", "calendar", "title", "start", "end", "all_day", "location", "time_label", "relative_label", "when_label", "color", "ink", "can_delete"}`.
  - `tests.fakes.FakeSource`, `tests.fakes.ev(...)`.

- [ ] **Step 1: Write `tests/fakes.py`**

```python
from app.calendar import CalendarError


def ev(calendar, title, start, end=None, all_day=False, uid=None, house=False, location=None):
    return {"calendar": calendar, "title": title, "start": start, "end": end, "all_day": all_day,
            "location": location, "uid": uid or f"{calendar}-{title}-{start}", "added_by_house": house,
            "when": ""}


class FakeSource:
    def __init__(self, events=None):
        self.items = list(events or [])
        self.fail = False
        self.calls = 0
        self.delete_result = (204, {})
        self.deleted = []

    def events(self, start, days):
        self.calls += 1
        if self.fail:
            raise CalendarError("calendar-api unavailable")
        return list(self.items)

    def delete(self, uid):
        self.deleted.append(uid)
        return self.delete_result
```

- [ ] **Step 2: Write the failing tests `tests/test_calendar.py`**

```python
from datetime import datetime, timedelta

from app import calendar as cal
from app.clock import TZ
from tests.fakes import FakeSource, ev

COLORS = {"Family": "#f2c230", "School": "#e0457b"}


def week(events, now):
    return cal.build_week(events, now, COLORS)


def test_evening_utc_event_lands_on_chicago_day(freeze):
    now = freeze("2026-10-26T09:00")
    # 8:30 PM Chicago on Mon 26 Oct is 01:30 UTC on Tue 27 Oct.
    w = week([ev("Family", "Late dinner", "2026-10-27T01:30:00Z", "2026-10-27T02:30:00Z")], now)
    assert [e["title"] for e in w["days"][0]["events"]] == ["Late dinner"]
    assert w["days"][0]["events"][0]["time_label"] == "8:30 PM"
    assert w["days"][1]["events"] == []


def test_dst_change_keeps_local_times(freeze):
    now = freeze("2026-10-31T09:00")
    # DST ends Sun 1 Nov 2026 at 2 AM. 9 AM CST that Sunday = 15:00 UTC.
    w = week([ev("Family", "Brunch", "2026-11-01T15:00:00+00:00")], now)
    sunday = w["days"][1]
    assert sunday["date"] == "2026-11-01" and sunday["events"][0]["time_label"] == "9:00 AM"


def test_day_fields_and_sorting(freeze):
    now = freeze("2026-10-26T09:00")
    events = [
        ev("School", "Piano", "2026-10-26T16:00:00-05:00"),
        ev("Family", "Grandma visits", "2026-10-26", "2026-10-27", all_day=True),
        ev("Family", "Standup", "2026-10-26T09:30:00-05:00"),
    ]
    day = week(events, now)["days"][0]
    assert (day["dow"], day["dow_long"], day["day"], day["month"], day["is_today"]) == \
        ("MON", "MONDAY", 26, "OCT", True)
    assert [e["title"] for e in day["events"]] == ["Grandma visits", "Standup", "Piano"]
    first = day["events"][0]
    assert first["time_label"] == "all day" and first["color"] == "#f2c230" and first["ink"] == "#1c1b1f"


def test_more_count(freeze):
    now = freeze("2026-10-26T09:00")
    events = [ev("Family", f"E{h}", f"2026-10-31T{h:02d}:00:00-05:00") for h in range(10, 15)]
    sat = week(events, now)["days"][5]
    assert len(sat["events"]) == 5 and sat["more"] == 2


def test_next_up(freeze):
    now = freeze("2026-10-26T15:00")
    events = [
        ev("Family", "Earlier today", "2026-10-26T09:00:00-05:00"),
        ev("Family", "All day today", "2026-10-26", all_day=True),
        ev("School", "Soccer", "2026-10-26T17:30:00-05:00"),
        ev("Family", "Standup", "2026-10-27T09:00:00-05:00"),
        ev("School", "Piano", "2026-10-28T16:00:00-05:00"),
        ev("Family", "Later", "2026-10-29T16:00:00-05:00"),
    ]
    nxt = week(events, now)["next"]
    assert [e["title"] for e in nxt] == ["All day today", "Soccer", "Standup", "Piano"]
    assert [e["relative_label"] for e in nxt] == ["Today", "Today, 5:30 PM", "Tomorrow, 9:00 AM", "Wed, 4:00 PM"]


def test_out_of_range_dropped_and_can_delete(freeze):
    now = freeze("2026-10-26T09:00")
    events = [ev("Family", "Old", "2026-10-25T10:00:00-05:00"),
              ev("Family", "House made", "2026-10-27T10:00:00-05:00", house=True),
              ev("Family", "Far", "2026-11-05T10:00:00-06:00")]
    w = week(events, now)
    titles = [e["title"] for d in w["days"] for e in d["events"]]
    assert titles == ["House made"] and w["days"][1]["events"][0]["can_delete"] is True


def test_unknown_calendar_gets_default_color(freeze):
    now = freeze("2026-10-26T09:00")
    e = week([ev("Mystery", "x", "2026-10-26T10:00:00-05:00")], now)["days"][0]["events"][0]
    assert e["color"] == "#6b6875"


def test_service_caches_for_ttl(store, freeze):
    src = FakeSource([ev("Family", "a", "2026-10-26T10:00:00-05:00")])
    svc = cal.CalendarService(src, store, ttl=60)
    freeze("2026-10-26T09:00:00")
    svc.events()
    freeze("2026-10-26T09:00:30")
    svc.events()
    assert src.calls == 1
    freeze("2026-10-26T09:01:30")
    svc.events()
    assert src.calls == 2


def test_service_serves_stale_when_down_and_after_restart(store, freeze):
    src = FakeSource([ev("Family", "a", "2026-10-26T10:00:00-05:00")])
    t0 = freeze("2026-10-26T09:00")
    cal.CalendarService(src, store).events()
    src.fail = True
    freeze("2026-10-26T09:10")
    fresh_service = cal.CalendarService(src, store)  # simulates a restart: empty memory
    res = fresh_service.events()
    assert res["ok"] is False and res["fetched_at"] == t0 and res["events"][0]["title"] == "a"


def test_service_with_no_data_ever(store, freeze):
    src = FakeSource()
    src.fail = True
    freeze("2026-10-26T09:00")
    res = cal.CalendarService(src, store).events()
    assert res == {"events": [], "fetched_at": None, "ok": False}


def test_delete_invalidates_cache(store, freeze):
    src = FakeSource([ev("Family", "a", "2026-10-26T10:00:00-05:00", house=True)])
    svc = cal.CalendarService(src, store)
    freeze("2026-10-26T09:00")
    svc.events()
    assert svc.delete("u1") == (204, {})
    svc.events()
    assert src.calls == 2 and src.deleted == ["u1"]


def test_fixture_source_materializes_offsets(tmp_path, freeze):
    p = tmp_path / "f.json"
    p.write_text('{"events": [{"calendar": "Family", "title": "T", "offset": 1, "time": "09:00", "minutes": 30},'
                 '{"calendar": "Family", "title": "A", "offset": 0, "all_day": true, "house": true}]}')
    freeze("2026-10-26T08:00")
    src = cal.FixtureSource(p)
    items = src.events(datetime(2026, 10, 26, tzinfo=TZ).date(), 7)
    timed = next(e for e in items if e["title"] == "T")
    assert datetime.fromisoformat(timed["start"]) == datetime(2026, 10, 27, 9, 0, tzinfo=TZ)
    assert datetime.fromisoformat(timed["end"]) - datetime.fromisoformat(timed["start"]) == timedelta(minutes=30)
    house = next(e for e in items if e["title"] == "A")
    assert src.delete(timed["uid"])[0] == 403
    assert src.delete(house["uid"]) == (204, {})
    assert [e["title"] for e in src.events(datetime(2026, 10, 26, tzinfo=TZ).date(), 7)] == ["T"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_calendar.py -q`
Expected: FAIL with `ImportError` on `app.calendar`

- [ ] **Step 4: Write `app/calendar.py`**

```python
"""Calendar data: read from calendar-api (or fixtures), cache it, and shape the week the page shows."""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from app import clock, labels
from app.store import Store

MAX_CHIPS = 3
NEXT_UP = 4
UNKNOWN_COLOR = "#6b6875"
CACHE_KEY = "events"


class CalendarError(Exception):
    pass


class HttpSource:
    def __init__(self, base_url: str, timeout: float = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def events(self, start: date, days: int) -> list[dict]:
        query = urllib.parse.urlencode({"start": start.isoformat(), "days": days, "kitchen_only": "true"})
        try:
            with urllib.request.urlopen(f"{self.base_url}/events?{query}", timeout=self.timeout) as r:
                return json.load(r)["events"]
        except Exception as e:
            raise CalendarError(f"calendar-api unavailable: {type(e).__name__}") from e

    def delete(self, uid: str) -> tuple[int, dict]:
        url = f"{self.base_url}/events/{urllib.parse.quote(uid, safe='')}"
        req = urllib.request.Request(url, method="DELETE")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = r.read()
                return r.status, (json.loads(body) if body else {})
        except urllib.error.HTTPError as e:
            body = e.read()
            try:
                return e.code, json.loads(body)
            except ValueError:
                return e.code, {"detail": body.decode(errors="replace") or e.reason}
        except Exception as e:
            return 502, {"detail": f"calendar-api unavailable: {type(e).__name__}"}


class FixtureSource:
    """Fake calendar-api for dev and CI. Fixture dates are day offsets from today."""

    def __init__(self, path: Path):
        self.items = json.loads(Path(path).read_text())["events"]
        self.deleted: set[str] = set()

    def _materialize(self) -> list[dict]:
        today = clock.now().date()
        out = []
        for i, f in enumerate(self.items):
            d = today + timedelta(days=f["offset"])
            if f.get("all_day"):
                start, end = d.isoformat(), (d + timedelta(days=1)).isoformat()
            else:
                hh, mm = map(int, f["time"].split(":"))
                s = datetime(d.year, d.month, d.day, hh, mm, tzinfo=clock.TZ)
                start, end = s.isoformat(), (s + timedelta(minutes=f.get("minutes", 60))).isoformat()
            out.append({"calendar": f["calendar"], "title": f["title"], "when": "", "start": start, "end": end,
                        "all_day": bool(f.get("all_day")), "location": f.get("location"), "uid": f"fake-{i}",
                        "added_by_house": bool(f.get("house"))})
        return [e for e in out if e["uid"] not in self.deleted]

    def events(self, start: date, days: int) -> list[dict]:
        return self._materialize()

    def delete(self, uid: str) -> tuple[int, dict]:
        match = next((e for e in self._materialize() if e["uid"] == uid), None)
        if match is None:
            return 404, {"detail": "No such event"}
        if not match["added_by_house"]:
            return 403, {"detail": "House can only delete events it created"}
        self.deleted.add(uid)
        return 204, {}


class CalendarService:
    """60 s cache in memory; last good data also kept in SQLite so a restart never blanks the screen."""

    def __init__(self, source, store: Store, ttl: int = 60):
        self.source = source
        self.store = store
        self.ttl = ttl
        self._mem: tuple[str, datetime, list[dict]] | None = None  # (request key, fetched_at, events)

    def invalidate(self) -> None:
        self._mem = None

    def events(self, days: int = 7) -> dict:
        now = clock.now()
        key = f"{now.date().isoformat()}:{days}"
        if self._mem and self._mem[0] == key and (now - self._mem[1]).total_seconds() < self.ttl:
            return {"events": self._mem[2], "fetched_at": self._mem[1], "ok": True}
        try:
            events = self.source.events(now.date(), days)
        except CalendarError:
            return self._stale()
        self._mem = (key, now, events)
        con = self.store.connect()
        try:
            with con:
                con.execute("insert into calendar_cache (key, fetched_at, body) values (?, ?, ?) "
                            "on conflict(key) do update set fetched_at = excluded.fetched_at, body = excluded.body",
                            (CACHE_KEY, now.isoformat(), json.dumps(events)))
        finally:
            con.close()
        return {"events": events, "fetched_at": now, "ok": True}

    def _stale(self) -> dict:
        if self._mem:
            return {"events": self._mem[2], "fetched_at": self._mem[1], "ok": False}
        con = self.store.connect()
        try:
            row = con.execute("select fetched_at, body from calendar_cache where key = ?", (CACHE_KEY,)).fetchone()
        finally:
            con.close()
        if not row:
            return {"events": [], "fetched_at": None, "ok": False}
        return {"events": json.loads(row["body"]), "fetched_at": datetime.fromisoformat(row["fetched_at"]),
                "ok": False}

    def delete(self, uid: str) -> tuple[int, dict]:
        status, body = self.source.delete(uid)
        if status < 300:
            self.invalidate()
        return status, body


def _local(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(clock.TZ)


def build_week(events: list[dict], now: datetime, colors: dict[str, str], days: int = 7) -> dict:
    today = now.date()
    by_day: dict[date, list[tuple]] = {today + timedelta(days=i): [] for i in range(days)}
    upcoming = []
    for raw in events:
        all_day = bool(raw.get("all_day"))
        start = None if all_day else _local(raw["start"])
        end = None if all_day else _local(raw.get("end"))
        d = date.fromisoformat(raw["start"][:10]) if all_day else start.date()
        if d not in by_day:
            continue
        color = colors.get(raw["calendar"], UNKNOWN_COLOR)
        item = {
            "uid": raw["uid"], "calendar": raw["calendar"], "title": raw["title"],
            "start": start.isoformat() if start else d.isoformat(),
            "end": end.isoformat() if end else None, "all_day": all_day, "location": raw.get("location"),
            "time_label": labels.time_label(start), "relative_label": labels.relative_label(d, start, today),
            "when_label": labels.when_label(d, start, end), "color": color, "ink": labels.ink_for(color),
            "can_delete": bool(raw.get("added_by_house")),
        }
        sort_key = (d, 0 if all_day else 1, start or now, raw["title"])
        by_day[d].append((sort_key, item))
        if (all_day and d == today) or (start is not None and start >= now):
            upcoming.append((sort_key, item))
    day_list = []
    for d, items in by_day.items():
        ordered = [item for _, item in sorted(items, key=lambda x: x[0])]
        day_list.append({"date": d.isoformat(), "dow": d.strftime("%a").upper(), "dow_long": d.strftime("%A").upper(),
                         "day": d.day, "month": d.strftime("%b").upper(), "is_today": d == today,
                         "events": ordered, "more": max(0, len(ordered) - MAX_CHIPS)})
    nxt = [item for _, item in sorted(upcoming, key=lambda x: x[0])[:NEXT_UP]]
    return {"days": day_list, "next": nxt}
```

- [ ] **Step 5: Write `fixtures/events.json`**

```json
{
  "_note": "Fake calendar-api data for DASHBOARD_FAKE=1. offset = days from today. house = made by House (deletable).",
  "events": [
    {"calendar": "School", "title": "Soccer practice", "offset": 0, "time": "17:30", "minutes": 90},
    {"calendar": "Family", "title": "Dinner with the Garcias", "offset": 0, "time": "19:00", "minutes": 120,
     "location": "Garcia house"},
    {"calendar": "Bob work", "title": "Standup", "offset": 1, "time": "09:00", "minutes": 15},
    {"calendar": "School", "title": "Piano", "offset": 2, "time": "16:00", "minutes": 45},
    {"calendar": "Family", "title": "Dentist · Ben", "offset": 3, "time": "16:00", "minutes": 45,
     "location": "Dr. Osei, 14 Mill Lane", "house": true},
    {"calendar": "Belen", "title": "Yoga", "offset": 4, "time": "18:30", "minutes": 60},
    {"calendar": "Family", "title": "Pizza night", "offset": 4, "all_day": true},
    {"calendar": "School", "title": "Soccer match", "offset": 5, "time": "10:00", "minutes": 90},
    {"calendar": "Bob work", "title": "Lunch with Sam", "offset": 5, "time": "13:00", "minutes": 60},
    {"calendar": "Belen", "title": "Market", "offset": 5, "time": "15:00", "minutes": 60},
    {"calendar": "Family", "title": "Carve pumpkins", "offset": 5, "time": "17:00", "minutes": 60},
    {"calendar": "Family", "title": "Trick or treat", "offset": 5, "time": "18:00", "minutes": 120},
    {"calendar": "Family", "title": "Grandma visits", "offset": 6, "all_day": true}
  ]
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_calendar.py -q && ruff check .`
Expected: `12 passed`, ruff clean.

- [ ] **Step 7: Commit**

```bash
git add app/calendar.py fixtures tests/fakes.py tests/test_calendar.py
git commit -m "Add calendar service with stale cache and Chicago week builder

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: API

**Files:**
- Create: `app/api.py`, `app/main.py`, `app/static/index.html` (placeholder replaced in Task 7), `tests/test_api.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `create_app(db_path: str | None = None, source=None, version: str | None = None) -> FastAPI`; `app.main.app`; `QuietPolls` logging filter; HTTP API exactly as in spec section 8. The `/api/week` body = `build_week(...)` plus `"fetched_at": str | None`, `"calendar_ok": bool`, `"calendars": [...]`. (`fetched_at` + `calendar_ok` replace the spec's `stale_since`: the page computes the age from `fetched_at`.) `/api/settings` = `{"calendars": [...], "people": [...]}`.

- [ ] **Step 1: Write a temporary page so `/` works**

`app/static/index.html`:
```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Kitchen</title></head><body></body></html>
```

- [ ] **Step 2: Write the failing tests `tests/test_api.py`**

```python
import logging

import pytest
from fastapi.testclient import TestClient

from app.api import QuietPolls, create_app
from tests.fakes import FakeSource, ev


@pytest.fixture
def src():
    return FakeSource([ev("Family", "Soccer", "2026-10-26T17:30:00-05:00", uid="u1"),
                       ev("Family", "House thing", "2026-10-27T10:00:00-05:00", uid="h1", house=True)])


@pytest.fixture
def client(tmp_path, src, freeze):
    freeze("2026-10-26T15:00")
    return TestClient(create_app(db_path=str(tmp_path / "api.db"), source=src, version="abc123"))


def people(client):
    return {p["name"]: p["id"] for p in client.get("/api/settings").json()["people"]}


def test_page_and_version(client):
    r = client.get("/")
    assert r.status_code == 200 and "<title>Kitchen</title>" in r.text
    assert r.headers["cache-control"] == "no-cache"
    assert client.get("/api/version").json() == {"version": "abc123"}


def test_week(client):
    w = client.get("/api/week").json()
    assert len(w["days"]) == 7 and w["calendar_ok"] is True and w["fetched_at"].startswith("2026-10-26T15:00")
    assert w["days"][0]["events"][0]["title"] == "Soccer"
    assert w["next"][0]["relative_label"] == "Today, 5:30 PM"
    assert w["calendars"] == [{"name": "Family", "color": "#f2c230", "ink": "#1c1b1f"}]


def test_week_when_calendar_down(client, src):
    src.fail = True
    w = client.get("/api/week").json()
    assert w["calendar_ok"] is False and w["fetched_at"] is None and len(w["days"]) == 7


def test_todo_roundtrip_and_changes(client):
    n0 = client.get("/api/changes").json()["n"]
    bob = people(client)["Bob"]
    r = client.post("/api/todos", json={"person_id": bob, "text": "  Call the plumber ", "date": "2026-10-26",
                                        "time": "14:00"})
    assert r.status_code == 201
    todo = r.json()
    assert todo["text"] == "Call the plumber" and todo["created_by"] == "phone"
    assert client.get("/api/changes").json()["n"] == n0 + 1
    today = client.get("/api/today").json()
    bob_card = next(p for p in today["people"] if p["name"] == "Bob")
    assert bob_card["todos"][0]["overdue"] is True and bob_card["overdue"] == 1
    assert client.patch(f"/api/todos/{todo['id']}", json={"done": True}).json()["done"] is True
    assert client.patch(f"/api/todos/{todo['id']}", json={"time": None}).json()["time"] is None
    assert client.delete(f"/api/todos/{todo['id']}").status_code == 204
    assert client.delete(f"/api/todos/{todo['id']}").status_code == 404


def test_todo_validation(client):
    bob = people(client)["Bob"]
    assert client.post("/api/todos", json={"person_id": bob, "text": "   ", "date": "2026-10-26"}).status_code == 422
    assert client.post("/api/todos", json={"person_id": bob, "text": "x", "date": "2026-10-26",
                                           "time": "25:00"}).status_code == 422
    assert client.post("/api/todos", json={"person_id": 999, "text": "x", "date": "2026-10-26"}).status_code == 422
    assert client.post("/api/todos", json={"person_id": bob, "text": "x" * 121, "date": "2026-10-26"}).status_code \
        == 422
    assert client.patch("/api/todos/999", json={"text": "x"}).status_code == 404


def test_house_can_create(client):
    ben = people(client)["Ben"]
    r = client.post("/api/todos", json={"person_id": ben, "text": "Feed Milo", "date": "2026-10-26",
                                        "created_by": "house"})
    assert r.json()["created_by"] == "house"


def test_settings(client):
    client.get("/api/week")  # registers Family
    r = client.put("/api/settings/calendars/Family", json={"color": "#2B5FD9"})
    assert r.json() == {"name": "Family", "color": "#2b5fd9", "ink": "#fff"}
    assert client.put("/api/settings/calendars/Family", json={"color": "blue"}).status_code == 422
    ana = client.post("/api/settings/people", json={"name": "Ana"}).json()
    assert client.patch(f"/api/settings/people/{ana['id']}", json={"name": "Anna"}).json()["name"] == "Anna"
    assert client.delete(f"/api/settings/people/{ana['id']}").status_code == 204
    assert client.delete("/api/settings/people/999").status_code == 404


def test_cannot_remove_person_with_todos(client):
    ben = people(client)["Ben"]
    client.post("/api/todos", json={"person_id": ben, "text": "x", "date": "2026-10-26"})
    r = client.delete(f"/api/settings/people/{ben}")
    assert r.status_code == 409 and "TODO" in r.json()["detail"]


def test_delete_event_passthrough(client, src):
    assert client.delete("/api/events/h1").status_code == 204
    src.delete_result = (403, {"detail": "House can only delete events it created"})
    r = client.delete("/api/events/u1")
    assert r.status_code == 403 and r.json()["detail"] == "House can only delete events it created"


def test_quiet_polls_filter():
    f = QuietPolls()

    def rec(path):
        return logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                                 ("127.0.0.1:1", "GET", path, "1.1", 200), None)
    assert f.filter(rec("/api/changes")) is False
    assert f.filter(rec("/api/version?x=1")) is False
    assert f.filter(rec("/api/week")) is True
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_api.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.api'`

- [ ] **Step 4: Write `app/api.py`**

```python
"""HTTP routes. Thin: validation and status codes here, rules in todos/settings/calendar."""
import datetime as dt
import logging
import os
from contextlib import closing
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints

from app import clock, settings, todos
from app import store as st
from app.calendar import CalendarService, FixtureSource, HttpSource, build_week

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
QUIET_PATHS = {"/api/changes", "/api/version"}

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
HHMM = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Color = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]


class TodoIn(BaseModel):
    person_id: int
    text: Text
    date: dt.date
    time: HHMM | None = None
    created_by: Literal["phone", "house"] = "phone"


class TodoPatch(BaseModel):
    person_id: int | None = None
    text: Text | None = None
    date: dt.date | None = None
    time: HHMM | None = None
    done: bool | None = None


class ColorIn(BaseModel):
    color: Color


class PersonIn(BaseModel):
    name: Name


class PersonPatch(BaseModel):
    name: Name | None = None
    sort: int | None = Field(None, ge=0)


class QuietPolls(logging.Filter):
    """Keep the 10-second polls out of the access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3:
            return str(args[2]).split("?")[0] not in QUIET_PATHS
        return True


def create_app(db_path: str | None = None, source=None, version: str | None = None) -> FastAPI:
    db_path = db_path or os.environ.get("DASHBOARD_DB", "/data/dashboard.db")
    version = version or os.environ.get("APP_VERSION", "dev")
    if source is None:
        if os.environ.get("DASHBOARD_FAKE") == "1":
            source = FixtureSource(ROOT / "fixtures" / "events.json")
        else:
            source = HttpSource(os.environ.get("CALENDAR_API", "http://calendar-api:8000"))
    store = st.Store(db_path)
    cal = CalendarService(source, store)
    logging.getLogger("uvicorn.access").addFilter(QuietPolls())

    app = FastAPI(title="Kitchen Dashboard", version=version)

    def db():
        with closing(store.connect()) as con:
            yield con

    Con = Annotated[object, Depends(db)]

    @app.middleware("http")
    async def no_cache_static(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/api/version")
    def get_version():
        return {"version": version}

    @app.get("/api/changes")
    def get_changes(con: Con):
        return {"n": st.changes(con)}

    @app.get("/api/week")
    def get_week(con: Con):
        res = cal.events(days=7)
        colors = settings.ensure_colors(con, [e["calendar"] for e in res["events"]])
        body = build_week(res["events"], clock.now(), colors)
        body["fetched_at"] = res["fetched_at"].isoformat(timespec="seconds") if res["fetched_at"] else None
        body["calendar_ok"] = res["ok"]
        body["calendars"] = settings.calendars(con)
        return body

    @app.get("/api/today")
    def get_today(con: Con):
        return todos.today_view(con, clock.now())

    @app.post("/api/todos", status_code=201)
    def post_todo(body: TodoIn, con: Con):
        try:
            return todos.create(con, clock.now(), person_id=body.person_id, text=body.text,
                                date=body.date.isoformat(), time=body.time, created_by=body.created_by)
        except LookupError:
            raise HTTPException(422, "Unknown person") from None

    @app.patch("/api/todos/{todo_id}")
    def patch_todo(todo_id: int, body: TodoPatch, con: Con):
        fields = body.model_dump(exclude_unset=True)
        if "date" in fields and fields["date"] is not None:
            fields["date"] = fields["date"].isoformat()
        for key in ("text", "person_id", "date", "done"):
            if key in fields and fields[key] is None:
                raise HTTPException(422, f"{key} can't be empty")
        try:
            return todos.update(con, clock.now(), todo_id, fields)
        except KeyError:
            raise HTTPException(404, "No such TODO") from None
        except LookupError:
            raise HTTPException(422, "Unknown person") from None

    @app.delete("/api/todos/{todo_id}", status_code=204)
    def delete_todo(todo_id: int, con: Con):
        if not todos.delete(con, todo_id):
            raise HTTPException(404, "No such TODO")

    @app.get("/api/settings")
    def get_settings(con: Con):
        return {"calendars": settings.calendars(con), "people": settings.people(con)}

    @app.put("/api/settings/calendars/{name}")
    def put_color(name: str, body: ColorIn, con: Con):
        return settings.set_color(con, name, body.color)

    @app.post("/api/settings/people", status_code=201)
    def post_person(body: PersonIn, con: Con):
        return settings.add_person(con, body.name)

    @app.patch("/api/settings/people/{person_id}")
    def patch_person(person_id: int, body: PersonPatch, con: Con):
        try:
            return settings.update_person(con, person_id, name=body.name, sort=body.sort)
        except KeyError:
            raise HTTPException(404, "No such person") from None

    @app.delete("/api/settings/people/{person_id}", status_code=204)
    def delete_person(person_id: int, con: Con):
        try:
            settings.delete_person(con, person_id)
        except KeyError:
            raise HTTPException(404, "No such person") from None
        except ValueError:
            raise HTTPException(409, "Move or delete this person's TODOs first") from None

    @app.delete("/api/events/{uid}")
    def delete_event(uid: str):
        status, body = cal.delete(uid)
        if status == 204:
            return Response(status_code=204)
        return JSONResponse(body, status_code=status)

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
```

`app/main.py`:
```python
from app.api import create_app

app = create_app()
```

- [ ] **Step 5: Run all tests**

Run: `pytest -q && ruff check .`
Expected: all tests pass (`49 passed` or more), ruff clean.

- [ ] **Step 6: Smoke-run in fake mode**

Run: `DASHBOARD_FAKE=1 DASHBOARD_DB=.dev.db uvicorn app.main:app --port 8081` in one shell, then `curl -s localhost:8081/api/week | python3 -m json.tool | head -30` and `curl -s localhost:8081/api/today`.
Expected: 7 days with fixture events; three people with empty TODO lists. Stop the server.

- [ ] **Step 7: Commit**

```bash
git add app/api.py app/main.py app/static/index.html tests/test_api.py
git commit -m "Add JSON API: week, today, todos, settings, event delete

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Page shell, shared JS and dev script

**Files:**
- Create: `app/static/css/base.css`, `app/static/js/ui.js`, `app/static/js/api.js`, `app/static/js/main.js`, `scripts/dev.sh`, `scripts/design_card.py`
- Modify: `app/static/index.html`

**Interfaces:**
- Produces (JS modules):
  - `ui.js`: `esc(s)`, `TZ`, `clockText(date) -> "4:12"`, `dateText(date) -> "MON 26 OCT"`, `chicagoParts(date) -> {iso: "YYYY-MM-DD", hour: 0-23}`, `chipStyle(ev) -> 'style="background:…;color:…"'`, `icons.mic(size)`, `icons.check(size)`, `icons.x(size, color)`, `toast(html, {ok})`, `errorText(err) -> string`.
  - `api.js`: `state` (`{week, today, settings, lastOk, startedAt, changes}`), `onChange(fn)`, `emit()`, `request(method, url, body?)`, `loadWeek()`, `loadToday()`, `loadSettings()`, `startPolling({alwaysOn: bool})`, `status(now?) -> {tone: "green"|"amber", text}`.
  - `main.js`: chooses `kitchen` (min-width 901px) or `phone` and calls `startKitchen(root)` / `startPhone(root)`; checks `/api/version` every 60 s and reloads on change.
  - Kitchen module must export `startKitchen(root: HTMLElement)`; phone module must export `startPhone(root: HTMLElement)`. Tasks 8 and 11 create them; this task adds stubs.

- [ ] **Step 1: Write `scripts/design_card.py`** (prints one design card's markup, for reference while styling)

```python
"""Print the markup of one Claude Design card. Usage: python3 -I scripts/design_card.py 2a"""
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "docs" / "design" / "Kitchen Dashboard.dc.html"
html = SRC.read_text()
card = sys.argv[1]
m = re.search(rf'<div class="dv-opt" id="{re.escape(card)}">', html)
if not m:
    sys.exit(f"no card {card}")
end = html.find('<div class="dv-opt"', m.end())
print(re.sub(r"\s+", " ", html[m.start(): end if end > 0 else len(html)]))
```

- [ ] **Step 2: Write `scripts/dev.sh`**

```sh
#!/bin/sh
# Local dev with fake calendar data: http://localhost:8081 (narrow the window below 900px for the phone layout)
set -e
cd "$(dirname "$0")/.."
[ -d .venv ] || python3.13 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements-dev.txt
DASHBOARD_FAKE=1 DASHBOARD_DB=.dev.db exec uvicorn app.main:app --reload --port 8081
```

Run: `chmod +x scripts/dev.sh`

- [ ] **Step 3: Write `app/static/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <title>Kitchen</title>
  <link rel="stylesheet" href="/static/css/base.css">
  <link rel="stylesheet" href="/static/css/kitchen.css">
  <link rel="stylesheet" href="/static/css/phone.css">
</head>
<body>
  <div id="root"></div>
  <div id="toast" class="toast" hidden></div>
  <script type="module" src="/static/js/main.js"></script>
</body>
</html>
```

- [ ] **Step 4: Write `app/static/css/base.css`**

```css
/* Tokens and shared pieces. Values come from docs/design/README.md. System fonts only. */
:root {
  --bg: #faf9f7; --surface: #fff; --surface-2: #f4f2f7; --divider: #f0eef4; --divider-2: #e6e3ee;
  --dashed: #d9d5e3; --ink: #1c1b1f; --muted: #6b6875; --faint: #9995a3; --ring: #c9c4d6;
  --accent: #6b45d9; --accent-soft: #efe9fb; --success: #2fb36a; --warning: #e9a23b; --warning-text: #b5742a;
  --danger: #d2382f; --danger-tint: #fdf1f0;
  --sans: system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  --mono: ui-monospace, Menlo, Consolas, "Liberation Mono", monospace;
  --photo: repeating-linear-gradient(45deg, #e9e6f3 0 12px, #f5f3fa 12px 24px);
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; background: var(--bg); color: var(--ink); font-family: var(--sans); }
body { -webkit-tap-highlight-color: transparent; }
button { font: inherit; color: inherit; background: none; border: 0; padding: 0; cursor: pointer; }
[hidden] { display: none !important; }

/* CSS icons (no icon fonts). Sizes are set inline by ui.js. */
.i-mic { position: relative; display: inline-block; }
.i-mic b { position: absolute; display: block; }
.i-check { display: inline-block; border-left: solid currentColor; border-bottom: solid currentColor;
  transform: rotate(-45deg) translate(10%, -25%); }
.i-x { position: relative; display: inline-block; }
.i-x::before, .i-x::after { content: ""; position: absolute; left: 0; top: 50%; width: 100%; height: var(--t);
  margin-top: calc(var(--t) / -2); background: var(--c); border-radius: 4px; }
.i-x::before { transform: rotate(45deg); }
.i-x::after { transform: rotate(-45deg); }

.toast { position: fixed; left: 50%; transform: translateX(-50%); z-index: 50; background: var(--ink); color: #fff;
  border-radius: 999px; display: flex; align-items: center; box-shadow: 0 30px 80px rgba(0,0,0,.3);
  animation: toast-in .2s ease-out; }
@keyframes toast-in { from { opacity: 0; transform: translate(-50%, 20px); } }
```

- [ ] **Step 5: Write `app/static/js/ui.js`**

```js
// Small shared helpers: escaping, Chicago time, icons, toast. No framework.
export const TZ = "America/Chicago";

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const timeFmt = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit", hour12: true });
const dateFmt = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "short", day: "numeric", month: "short" });
const partsFmt = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", hourCycle: "h23" });

export const clockText = (d) => timeFmt.format(d).replace(/\s?[AP]M$/, "");

export function dateText(d) {
  const p = Object.fromEntries(dateFmt.formatToParts(d).map((x) => [x.type, x.value]));
  return `${p.weekday} ${p.day} ${p.month}`.toUpperCase();
}

export function chicagoParts(d) {
  const p = Object.fromEntries(partsFmt.formatToParts(d).map((x) => [x.type, x.value]));
  return { iso: `${p.year}-${p.month}-${p.day}`, hour: Number(p.hour) };
}

export const chipStyle = (ev) => `style="background:${esc(ev.color)};color:${esc(ev.ink)}"`;

export const icons = {
  // Mic: capsule + U cradle + stem + base, drawn with boxes like the design.
  mic(w, color = "#fff") {
    const u = w / 50;
    return `<span class="i-mic" style="width:${w}px;height:${62 * u}px">` +
      `<b style="left:${14 * u}px;top:0;width:${22 * u}px;height:${38 * u}px;border-radius:999px;background:${color}"></b>` +
      `<b style="left:0;top:${20 * u}px;width:${50 * u}px;height:${30 * u}px;border:${6 * u}px solid ${color};` +
      `border-top:none;border-radius:0 0 999px 999px"></b>` +
      `<b style="left:${22 * u}px;top:${50 * u}px;width:${6 * u}px;height:${8 * u}px;background:${color}"></b>` +
      `<b style="left:${10 * u}px;top:${57 * u}px;width:${30 * u}px;height:${6 * u}px;border-radius:999px;` +
      `background:${color}"></b></span>`;
  },
  check(w, thick, color = "#fff") {
    return `<span class="i-check" style="width:${w}px;height:${w / 2}px;border-width:0 0 ${thick}px ${thick}px;` +
      `color:${color}"></span>`;
  },
  x(w, thick, color) {
    return `<span class="i-x" style="width:${w}px;height:${w}px;--t:${thick}px;--c:${color}"></span>`;
  },
};

let toastTimer;
export function toast(html, { ok = false, ms = 6000, cls = "" } = {}) {
  const el = document.getElementById("toast");
  el.className = `toast ${cls}`;
  el.innerHTML = (ok ? `<span class="toast-ok">${icons.check(24, 6, "var(--success)")}</span>` : "") +
    `<span>${html}</span>`;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, ms);
}

export function errorText(err) {
  const d = err?.data?.detail;
  if (Array.isArray(d)) return d.map((x) => x.msg).join(", ");
  return d || err?.message || "Something went wrong";
}
```

- [ ] **Step 6: Write `app/static/js/api.js`**

```js
// Shared data + smart polling. The page asks for a tiny change number every 10 s and refetches only on change.
export const state = { week: null, today: null, settings: null, lastOk: null, startedAt: Date.now(), changes: null };
const listeners = new Set();

export const onChange = (fn) => listeners.add(fn);
export const emit = () => listeners.forEach((fn) => fn(state));

export async function request(method, url, body) {
  const r = await fetch(url, {
    method, cache: "no-store",
    headers: body !== undefined ? { "Content-Type": "application/json" } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = r.status === 204 ? null : await r.json().catch(() => null);
  state.lastOk = Date.now();  // any answer means the server is reachable
  if (!r.ok) {
    const err = new Error(`HTTP ${r.status}`);
    err.status = r.status;
    err.data = data;
    throw err;
  }
  return data;
}

export async function loadWeek() { state.week = await request("GET", "/api/week"); emit(); }
export async function loadToday() { state.today = await request("GET", "/api/today"); emit(); }
export async function loadSettings() { state.settings = await request("GET", "/api/settings"); emit(); }

async function pollChanges() {
  const { n } = await request("GET", "/api/changes");
  if (n !== state.changes) {
    state.changes = n;
    await Promise.all([loadToday(), loadSettings()]);
  } else {
    emit();  // keeps the status line fresh
  }
}

export function startPolling({ alwaysOn }) {
  const safe = (fn) => () => fn().catch((e) => { console.warn(e); emit(); });
  const fast = safe(pollChanges);
  // The 60 s tick also refreshes today, so timed TODOs turn overdue without a write.
  const slow = safe(() => Promise.all([loadWeek(), loadToday()]));
  let timers = [];
  const start = () => {
    if (timers.length) return;
    fast(); slow();
    timers = [setInterval(fast, 10_000), setInterval(slow, 60_000)];
  };
  const stop = () => { timers.forEach(clearInterval); timers = []; };
  start();
  if (!alwaysOn) document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
}

export function status(now = Date.now()) {
  const quiet = now - (state.lastOk ?? state.startedAt);
  if (quiet >= 30_000) return { tone: "amber", text: "last updated — offline" };
  if (!state.lastOk || !state.week) return { tone: "amber", text: "connecting to the home server…" };
  if (!state.week.fetched_at) return { tone: "amber", text: "no calendar data yet" };
  const mins = Math.floor((now - Date.parse(state.week.fetched_at)) / 60_000);
  if (mins >= 5) return { tone: "amber", text: `last updated ${mins} min ago` };
  return { tone: "green", text: "up to date" };
}
```

- [ ] **Step 7: Write `app/static/js/main.js` and module stubs**

`app/static/js/main.js`:
```js
// Picks the kitchen or phone layout and reloads the page after a deploy.
import { startKitchen } from "./kitchen.js";
import { startPhone } from "./phone.js";

const root = document.getElementById("root");
const isPhone = window.matchMedia("(max-width: 900px)").matches;
document.body.classList.add(isPhone ? "is-phone" : "is-kitchen");
(isPhone ? startPhone : startKitchen)(root);

let version = null;
async function checkVersion() {
  try {
    const r = await fetch("/api/version", { cache: "no-store" });
    const { version: v } = await r.json();
    if (version && v !== version) location.reload();
    version = v;
  } catch { /* offline; try again next minute */ }
}
checkVersion();
setInterval(checkVersion, 60_000);
```

`app/static/js/kitchen.js` (stub, replaced in Task 8):
```js
export function startKitchen(root) { root.textContent = "kitchen"; }
```

`app/static/js/phone.js` (stub, replaced in Task 11):
```js
export function startPhone(root) { root.textContent = "phone"; }
```

Create empty `app/static/css/kitchen.css` and `app/static/css/phone.css`.

- [ ] **Step 8: Check it loads**

Run: `scripts/dev.sh`, then open `http://localhost:8081` with ego-browser at 1500×1000 and at 430×932.
Expected: the word `kitchen` at 1500 wide; `phone` at 430 wide; no console errors; no requests to any host but localhost.

- [ ] **Step 9: Run tests and commit**

Run: `pytest -q && ruff check .`
Expected: all pass.

```bash
git add app/static scripts
git commit -m "Add page shell, shared JS helpers, polling and dev script

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Kitchen dashboard (2a, 8a, 8b, 8c, 8f)

**Files:**
- Modify: `app/static/js/kitchen.js`, `app/static/css/kitchen.css`

**Interfaces:**
- Consumes: `state`, `onChange`, `request`, `loadToday`, `loadWeek`, `startPolling`, `status` from `api.js`; `esc`, `clockText`, `dateText`, `chicagoParts`, `chipStyle`, `icons`, `toast`, `errorText` from `ui.js`.
- Produces: `startKitchen(root)`. The stage element `#stage` (3000×2000) holds `#dash`, `#sheet` (Task 9) and `#night` (Task 10). Exported for Tasks 9–10: `openEvent(uid)` and `openDay(dateIso)` are called from click handlers; Task 9 defines them in `kitchen.js`. This task wires clicks to `openEvent`/`openDay` and defines both as no-ops for now.

Reference markup: `python3 -I scripts/design_card.py 2a` (also `8a`, `8b`, `8c`, `8f`).

- [ ] **Step 1: Write `app/static/css/kitchen.css`**

```css
/* Kitchen layout, authored at the design's 3000x2000 px. JS scales the stage to fit smaller windows;
   on the kiosk the scale is exactly 1. */
body.is-kitchen { overflow: hidden; }
.stage { position: absolute; left: 0; top: 0; width: 3000px; height: 2000px; transform-origin: 0 0;
  transform: scale(var(--scale, 1)); overflow: hidden; background: var(--bg); user-select: none; }

.dash { position: absolute; inset: 0; padding: 72px 80px; display: grid; grid-template-columns: 820px 1fr; gap: 72px;
  transition: opacity .25s, filter .25s; }
.dash.dimmed { opacity: .35; filter: blur(6px); }

/* Left rail */
.rail { display: flex; flex-direction: column; gap: 48px; min-height: 0; }
.clock { font: 600 260px/1 var(--sans); letter-spacing: -.04em; font-variant-numeric: tabular-nums; }
.date { font: 40px var(--mono); color: var(--muted); letter-spacing: .06em; margin-top: 12px; }
.next { display: flex; flex-direction: column; gap: 18px; flex: 1; min-height: 0; }
.label { font: 600 32px var(--mono); letter-spacing: .1em; color: var(--muted); }
.next-card { background: var(--surface); border-radius: 40px; padding: 28px 36px; display: flex; flex-direction: column;
  gap: 14px; min-height: 120px; text-align: left; }
.next-card .title { font: 600 44px/1.1 var(--sans); }
.next-card .chip { align-self: flex-start; border-radius: 999px; padding: 10px 24px; font: 600 32px var(--mono); }
.next-empty { font: 600 44px/1.1 var(--sans); color: var(--faint); padding: 28px 0; }
.talk { background: var(--accent); color: #fff; border-radius: 999px; height: 220px; display: flex; align-items: center;
  justify-content: center; gap: 36px; box-shadow: 0 20px 60px rgba(107,69,217,.3); font: 600 56px/1 var(--sans); }
.talk .mic { width: 100px; height: 100px; border-radius: 50%; background: rgba(255,255,255,.2); display: flex;
  align-items: center; justify-content: center; }
.status { display: flex; align-items: center; gap: 16px; font: 32px var(--mono); color: var(--muted); }
.status .dot { width: 18px; height: 18px; border-radius: 50%; background: var(--success); }
.status.amber { color: var(--warning-text); }
.status.amber .dot { background: var(--warning); }

/* Week strip */
.right { display: grid; grid-template-rows: 760px 1fr; gap: 64px; min-height: 0; }
.week { display: grid; grid-template-columns: repeat(7, 1fr); gap: 20px; min-height: 0; }
.day { display: flex; flex-direction: column; gap: 14px; min-width: 0; min-height: 0; }
.day-head { text-align: center; padding: 18px 0; border-radius: 999px; }
.day-head .dow { font: 600 30px var(--mono); letter-spacing: .08em; color: var(--muted); }
.day-head .num { font: 600 64px/1 var(--sans); }
.day.today .day-head { background: var(--accent); color: #fff; }
.day.today .day-head .dow { color: #fff; }
.ev { border-radius: 28px; padding: 22px 26px; font: 600 34px/1.15 var(--sans); text-align: left; overflow-wrap: anywhere; }
.ev .t { font: 30px var(--mono); opacity: .85; }
.ev.light .t { opacity: .7; }
.more { height: 100px; border-radius: 999px; border: 5px solid var(--ink); display: flex; align-items: center;
  justify-content: center; gap: 16px; font: 600 34px var(--sans); }
.more .dots { display: flex; gap: 6px; }
.more .dots i { width: 14px; height: 14px; border-radius: 50%; display: inline-block; }
.free { flex: 1; border-radius: 28px; border: 4px dashed var(--divider-2); display: flex; align-items: center;
  justify-content: center; font: 30px var(--mono); color: var(--ring); }
.ev.new { outline: 8px solid var(--success); outline-offset: 6px; }

/* TODO cards */
.people { display: grid; grid-template-columns: repeat(3, 1fr) 120px; gap: 28px; min-height: 0; }
.person { background: var(--surface); border-radius: 48px; padding: 32px; display: flex; flex-direction: column; gap: 14px;
  min-height: 0; overflow: hidden; position: relative; }
.person-head { display: flex; align-items: center; gap: 20px; margin-bottom: 8px; }
.avatar { width: 100px; height: 100px; border-radius: 50%; background: var(--photo); display: flex; align-items: center;
  justify-content: center; font: 600 40px var(--mono); color: var(--muted); flex: none; }
.person-head .name { font: 600 52px/1 var(--sans); flex: 1; }
.person-head .count { font: 30px var(--mono); color: var(--muted); }
.person-head .count.overdue { color: var(--danger); }
.todo { display: flex; align-items: center; gap: 20px; min-height: 100px; text-align: left; width: 100%; }
.ring { width: 60px; height: 60px; border-radius: 50%; border: 5px solid var(--ring); flex: none; display: flex;
  align-items: center; justify-content: center; transition: background .15s, border-color .15s; }
.ring .i-check { transform: rotate(-45deg) translate(3px, -4px) scale(0); transition: transform .15s; }
.todo .text { font: 38px/1.15 var(--sans); flex: 1; transition: color .15s; }
.todo .when { font: 30px var(--mono); color: var(--muted); }
.todo.done .ring { background: var(--accent); border-color: var(--accent); }
.todo.done .ring .i-check { transform: rotate(-45deg) translate(3px, -4px) scale(1); }
.todo.done .text { color: var(--faint); text-decoration: line-through; }
.todo.done .when { color: var(--ring); }
.todo.overdue { background: var(--danger-tint); border-radius: 24px; padding: 0 20px; margin: 0 -20px; width: auto; }
.todo.overdue .ring { border-color: var(--danger); }
.todo.overdue .when { color: var(--danger); font-weight: 600; }
.person-empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px;
  text-align: center; }
.person-empty .big { font: 600 44px/1.1 var(--sans); color: var(--faint); }
.person-empty .hint { font: 30px/1.4 var(--mono); color: var(--ring); }
.person.all-done { background: var(--success); color: #fff; animation: fade-in .3s; }
.person.all-done .avatar { background: rgba(255,255,255,.3); color: #fff; }
.person.all-done .count { color: #fff; opacity: .9; }
.all-done-body { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; }
.all-done-body .badge { width: 150px; height: 150px; border-radius: 50%; background: #fff; display: flex;
  align-items: center; justify-content: center; }
.all-done-body .word { font: 600 56px/1.1 var(--sans); }
.confetti { position: absolute; width: 20px; height: 36px; border-radius: 6px; animation: fade-in .3s; }
.slot { border: 5px dashed var(--dashed); border-radius: 48px; display: flex; align-items: center; justify-content: center;
  font: 600 56px var(--sans); color: var(--ring); }
@keyframes fade-in { from { opacity: 0; } }

/* Loading skeleton (8f) */
.skel { background: var(--divider); border-radius: 40px; }
.skel.talk { background: var(--divider-2); box-shadow: none; }
.dash.loading .label { color: var(--ring); }

/* Toast on the wall */
.is-kitchen .toast { bottom: calc(80px * var(--scale, 1)); padding: 36px 48px; gap: 28px; font: 500 44px var(--sans);
  transform: translateX(-50%) scale(var(--scale, 1)); transform-origin: bottom center; }
.is-kitchen .toast-ok { width: 56px; height: 56px; border-radius: 50%; background: #fff; display: flex;
  align-items: center; justify-content: center; }
```

- [ ] **Step 2: Write `app/static/js/kitchen.js`**

```js
// Kitchen wall screen (design 2a and its states). Authored at 3000x2000; scaled to fit in dev windows.
import { loadToday, loadWeek, onChange, request, startPolling, state, status } from "./api.js";
import { chicagoParts, chipStyle, clockText, dateText, errorText, esc, icons, toast } from "./ui.js";

let stage, dash;

function fitStage() {
  const s = Math.min(window.innerWidth / 3000, window.innerHeight / 2000);
  document.documentElement.style.setProperty("--scale", String(s));
}

const light = (ev) => ev.ink === "#1c1b1f";

function chip(ev) {
  return `<button class="ev ${light(ev) ? "light" : ""}" data-uid="${esc(ev.uid)}" ${chipStyle(ev)}>` +
    `<div class="t">${esc(ev.time_label)}</div>${esc(ev.title)}</button>`;
}

function dayColumn(d) {
  const shown = d.events.slice(0, 3);
  const extra = d.events.slice(3);
  const more = d.more ? `<button class="more" data-day="${esc(d.date)}"><span class="dots">${extra.slice(0, 3)
    .map((e) => `<i style="background:${esc(e.color)}"></i>`).join("")}</span>+${d.more} more</button>` : "";
  const body = d.events.length ? shown.map(chip).join("") + more : `<div class="free">free</div>`;
  return `<div class="day ${d.is_today ? "today" : ""}"><div class="day-head"><div class="dow">${esc(d.dow)}</div>` +
    `<div class="num">${d.day}</div></div>${body}</div>`;
}

function nextCards(next) {
  if (!next.length) return `<div class="next-empty">Nothing coming up</div>`;
  return next.map((ev) => `<button class="next-card" data-uid="${esc(ev.uid)}"><div class="title">${esc(ev.title)}</div>` +
    `<div class="chip" ${chipStyle(ev)}>${esc(ev.relative_label)}</div></button>`).join("");
}

const CONFETTI = [[80, 180, "#f2c230", 20], [320, 160, "#fff", -35], [520, 220, "#e0457b", 60], [200, 300, "#fff", -10],
  [460, 340, "#f2c230", 45]];

function personCard(p) {
  if (p.state === "all_done") {
    return `<div class="person all-done">` +
      CONFETTI.map(([l, t, c, r]) => `<i class="confetti" style="left:${l}px;top:${t}px;background:${c};` +
        `transform:rotate(${r}deg)"></i>`).join("") +
      `<div class="person-head"><div class="avatar">${esc(p.initial)}</div><div class="name">${esc(p.name)}</div>` +
      `<div class="count">${p.todos.length} of ${p.todos.length}</div></div>` +
      `<div class="all-done-body"><div class="badge">${icons.check(66, 13, "var(--success)")}</div>` +
      `<div class="word">All done!</div></div></div>`;
  }
  const count = p.overdue ? `<div class="count overdue">${p.overdue} overdue · ${p.left} left</div>`
    : p.state === "open" ? `<div class="count">${p.left} left</div>` : "";
  const body = p.state === "empty"
    ? `<div class="person-empty"><div class="big">Nothing today</div>` +
      `<div class="hint">say “add a todo for ${esc(p.name)}”<br>or use your phone</div></div>`
    : p.todos.map((t) => `<button class="todo ${t.done ? "done" : ""} ${t.overdue ? "overdue" : ""}" data-todo="${t.id}">` +
        `<span class="ring">${icons.check(28, 6)}</span><span class="text">${esc(t.text)}</span>` +
        (t.time_label ? `<span class="when">${esc(t.time_label)}</span>` : "") + `</button>`).join("");
  return `<div class="person"><div class="person-head"><div class="avatar">${esc(p.initial)}</div>` +
    `<div class="name">${esc(p.name)}</div>${count}</div>${body}</div>`;
}

function skeleton() {
  const days = Array.from({ length: 7 }, (_, i) => `<div class="day ${i === 0 ? "today" : ""}"><div class="day-head">` +
    `<div class="dow">&nbsp;</div><div class="num">&nbsp;</div></div><div class="skel" style="height:130px"></div></div>`);
  return {
    next: [1, 2, 3].map(() => `<div class="skel" style="height:150px"></div>`).join(""),
    week: days.join(""),
    people: [1, 2, 3].map(() => `<div class="skel" style="border-radius:48px"></div>`).join(""),
  };
}

function render() {
  const loading = !state.week || !state.today;
  const sk = loading ? skeleton() : null;
  const now = new Date();
  const st = status();
  dash.className = `dash ${loading ? "loading" : ""} ${dash.classList.contains("dimmed") ? "dimmed" : ""}`;
  dash.innerHTML =
    `<div class="rail"><div><div class="clock" id="clock">${clockText(now)}</div>` +
    `<div class="date" id="date">${dateText(now)}</div></div>` +
    `<div class="next"><div class="label">NEXT UP</div>${loading ? sk.next : nextCards(state.week.next)}</div>` +
    `<button class="talk ${loading ? "skel" : ""}" aria-disabled="true">` +
    (loading ? "" : `<span class="mic">${icons.mic(50)}</span>Talk to the house`) + `</button>` +
    `<div class="status ${st.tone === "amber" ? "amber" : ""}" id="status"><span class="dot"></span>${esc(st.text)}</div></div>` +
    `<div class="right"><div class="week">${loading ? sk.week : state.week.days.map(dayColumn).join("")}</div>` +
    `<div class="people">${loading ? sk.people : state.today.people.slice(0, 3).map(personCard).join("")}` +
    `<div class="slot">+</div></div></div>`;
}

function tickClock() {
  const now = new Date();
  const c = document.getElementById("clock");
  if (c) {
    c.textContent = clockText(now);
    document.getElementById("date").textContent = dateText(now);
    const st = status();
    const s = document.getElementById("status");
    s.className = `status ${st.tone === "amber" ? "amber" : ""}`;
    s.innerHTML = `<span class="dot"></span>${esc(st.text)}`;
  }
  return now;
}

async function toggleTodo(btn) {
  const id = Number(btn.dataset.todo);
  const done = !btn.classList.contains("done");
  btn.classList.toggle("done", done);
  try {
    await request("PATCH", `/api/todos/${id}`, { done });
    await loadToday();
  } catch (err) {
    btn.classList.toggle("done", !done);
    toast(`Couldn't save, try again`);
    console.warn(errorText(err));
  }
}

// Replaced in Task 9.
export function openEvent(uid) { void uid; }
export function openDay(dateIso) { void dateIso; }

export function startKitchen(root) {
  root.innerHTML = `<div class="stage" id="stage"><div class="dash" id="dash"></div></div>`;
  stage = document.getElementById("stage");
  dash = document.getElementById("dash");
  fitStage();
  window.addEventListener("resize", fitStage);
  stage.addEventListener("click", (e) => {
    const t = e.target.closest("[data-todo],[data-uid],[data-day]");
    if (!t) return;
    if (t.dataset.todo) toggleTodo(t);
    else if (t.dataset.uid) openEvent(t.dataset.uid);
    else if (t.dataset.day) openDay(t.dataset.day);
  });
  onChange(render);
  render();
  startPolling({ alwaysOn: true });
  let day = chicagoParts(new Date()).iso;
  setInterval(() => {
    const now = tickClock();
    const today = chicagoParts(now).iso;
    if (today !== day) { day = today; Promise.all([loadWeek(), loadToday()]).catch(() => {}); }  // midnight
  }, 1000);
}
```

- [ ] **Step 3: Check it against the design**

Run: `scripts/dev.sh`. With ego-browser, open `http://localhost:8081` at a 3000×2000 viewport and take a screenshot. Then add TODOs with curl so each state shows:
```sh
B=$(curl -s localhost:8081/api/settings | python3 -c "import sys,json;print({p['name']:p['id'] for p in json.load(sys.stdin)['people']})")
echo $B   # note the ids
curl -s -XPOST localhost:8081/api/todos -H 'content-type: application/json' -d '{"person_id":1,"text":"Call the plumber","date":"'$(date +%F)'","time":"00:01"}'
curl -s -XPOST localhost:8081/api/todos -H 'content-type: application/json' -d '{"person_id":1,"text":"Book flights to Lisbon","date":"'$(date +%F)'"}'
curl -s -XPOST localhost:8081/api/todos -H 'content-type: application/json' -d '{"person_id":2,"text":"Return library books","date":"'$(date +%F)'"}'
```
Tap Belen's only item in the browser.
Expected: matches card 2a: clock, NEXT UP cards with filled chips, purple Talk pill, week strip with today's purple header, Saturday-offset column shows 3 chips then `+2 more`. Bob's card shows `1 overdue · 2 left` with a red-tinted first row (8a). Belen's card turns green with `All done!` (2a). Ben shows `Nothing today` (8b). Days with no events show dashed `free` (8b). Stop the server, reload the page: skeleton with amber `connecting to the home server…`, then after 30 s `last updated — offline` (8f).

- [ ] **Step 4: Run tests and commit**

Run: `pytest -q && ruff check .`

```bash
git add app/static
git commit -m "Add kitchen dashboard: next up, week strip, TODO cards and states

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Kitchen sheets (8d, 3a, 3c) and toast

**Files:**
- Modify: `app/static/js/kitchen.js`, `app/static/css/kitchen.css`

**Interfaces:**
- Consumes: `state.week` (events carry `when_label`, `location`, `can_delete`, `color`, `ink`, `calendar`), `state.today.people` (names for WHO), `request`, `loadWeek`.
- Produces: real `openEvent(uid)`, `openDay(dateIso)`, `closeSheet()` in `kitchen.js`.

Reference markup: `python3 -I scripts/design_card.py 3a` (also `3c`, `8d`).

- [ ] **Step 1: Add sheet styles to `app/static/css/kitchen.css`**

```css
/* Sheets over the dimmed dashboard */
.scrim { position: absolute; inset: 0; background: rgba(28,27,31,.45); animation: fade-in .25s; }
.sheet { position: absolute; background: var(--surface); border-radius: 80px; box-shadow: 0 60px 160px rgba(0,0,0,.35);
  overflow: hidden; display: flex; flex-direction: column; animation: sheet-in .25s ease-out; }
@keyframes sheet-in { from { opacity: 0; transform: scale(.96); } }
.sheet.event { left: 650px; top: 380px; width: 1700px; height: 1240px; }
.sheet.day-sheet { left: 650px; top: 260px; width: 1700px; height: 1480px; padding: 80px 96px; gap: 32px; }
.close { width: 120px; height: 120px; border-radius: 50%; background: rgba(0,0,0,.12); display: flex; align-items: center;
  justify-content: center; flex: none; }
.day-sheet .close { background: var(--surface-2); }
.band { padding: 72px 96px 64px; display: flex; justify-content: space-between; align-items: flex-start; gap: 48px;
  transition: opacity .2s; }
.band .cal { font: 600 32px var(--mono); letter-spacing: .12em; opacity: .7; }
.band .title { font: 600 96px/1.05 var(--sans); margin-top: 16px; }
.facts { padding: 64px 96px; display: grid; grid-template-columns: 260px 1fr; row-gap: 36px; column-gap: 40px;
  align-items: baseline; font: 44px/1.2 var(--sans); }
.facts .k { font: 600 30px var(--mono); letter-spacing: .12em; color: var(--muted); }
.who-pill { display: inline-flex; align-items: center; gap: 14px; background: var(--surface-2); border-radius: 999px;
  padding: 10px 28px 10px 12px; }
.who-pill .avatar { width: 56px; height: 56px; font-size: 26px; }
.actions { margin-top: auto; padding: 0 96px 72px; display: flex; gap: 28px; align-items: center; }
.btn { height: 180px; border-radius: 999px; display: flex; align-items: center; justify-content: center;
  font: 600 48px var(--sans); }
.btn.outline { border: 6px solid var(--divider-2); color: var(--muted); }
.btn.danger { background: var(--danger); color: #fff; }
.btn.flex { flex: 1; }
.btn.w460 { width: 460px; margin-left: auto; }
.note { font: 40px/1.3 var(--sans); color: var(--muted); flex: 1; }
.confirm { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 24px;
  text-align: center; padding: 0 96px; }
.confirm .q { font: 600 72px/1.15 var(--sans); }
.confirm .sub { font: 40px/1.3 var(--sans); color: var(--muted); }
.confirm .sub.err { color: var(--danger); }
.day-sheet .head { display: flex; justify-content: space-between; align-items: center; }
.day-sheet .dow { font: 600 36px var(--mono); letter-spacing: .12em; color: var(--muted); }
.day-sheet .big { font: 600 96px/1 var(--sans); margin-top: 12px; }
.day-sheet .rows { overflow-y: auto; min-height: 0; }
.day-row { display: flex; align-items: center; gap: 32px; min-height: 140px; border-top: 3px solid var(--divider);
  width: 100%; text-align: left; }
.day-row .t { width: 220px; font: 600 36px var(--mono); color: var(--muted); flex: none; }
.day-row .pill { flex: 1; border-radius: 999px; padding: 20px 36px; font: 600 44px var(--sans); }
```

- [ ] **Step 2: Replace the `openEvent`/`openDay` stubs in `app/static/js/kitchen.js`**

Remove the two stub functions and add (keep `loadWeek` imported from `api.js`):

```js
let sheetEl;

function findEvent(uid) {
  for (const d of state.week?.days ?? []) {
    const ev = d.events.find((e) => e.uid === uid);
    if (ev) return ev;
  }
  return null;
}

function showSheet(html) {
  dash.classList.add("dimmed");
  sheetEl.innerHTML = `<div class="scrim" data-close></div>${html}`;
  sheetEl.hidden = false;
}

export function closeSheet() {
  sheetEl.hidden = true;
  sheetEl.innerHTML = "";
  dash.classList.remove("dimmed");
}

function eventSheet(ev, mode = "view", error = "") {
  const who = (state.today?.people ?? []).filter((p) => p.name === ev.calendar);
  const band = `<div class="band" style="background:${esc(ev.color)};color:${esc(ev.ink)};${mode === "view" ? "" : "opacity:.5"}">` +
    `<div><div class="cal">${esc(ev.calendar.toUpperCase())}</div><div class="title">${esc(ev.title)}</div></div>` +
    (mode === "view" ? `<button class="close" data-close>${icons.x(52, 8, ev.ink)}</button>` : "") + `</div>`;
  if (mode === "confirm") {
    return `<div class="sheet event">${band}<div class="confirm">` +
      `<div class="q">Remove this from the ${esc(ev.calendar)} calendar?</div>` +
      `<div class="sub ${error ? "err" : ""}">${esc(error || "Everyone's phone will update too.")}</div></div>` +
      `<div class="actions">` + (error
        ? `<button class="btn outline flex" data-close>Close</button>`
        : `<button class="btn outline flex" data-keep="${esc(ev.uid)}">Keep it</button>` +
          `<button class="btn danger flex" data-remove="${esc(ev.uid)}">Yes, remove</button>`) + `</div></div>`;
  }
  const facts = `<div class="k">WHEN</div><div>${esc(ev.when_label)}</div>` +
    (ev.location ? `<div class="k">WHERE</div><div>${esc(ev.location)}</div>` : "") +
    (who.length ? `<div class="k">WHO</div><div>${who.map((p) => `<span class="who-pill"><span class="avatar">` +
      `${esc(p.initial)}</span>${esc(p.name)}</span>`).join(" ")}</div>` : "");
  const actions = ev.can_delete
    ? `<button class="btn outline w460" data-delete="${esc(ev.uid)}">Delete</button>`
    : `<div class="note">Change it in your Calendar app</div>`;
  return `<div class="sheet event">${band}<div class="facts">${facts}</div><div class="actions">${actions}</div></div>`;
}

export function openEvent(uid) {
  const ev = findEvent(uid);
  if (ev) showSheet(eventSheet(ev));
}

export function openDay(dateIso) {
  const d = state.week?.days.find((x) => x.date === dateIso);
  if (!d) return;
  const [y, m, day] = d.date.split("-").map(Number);
  const month = new Date(Date.UTC(y, m - 1, day)).toLocaleDateString("en-US", { month: "short", timeZone: "UTC" });
  showSheet(`<div class="sheet day-sheet"><div class="head"><div><div class="dow">${esc(d.dow_long)}</div>` +
    `<div class="big">${d.day} ${esc(month)}</div></div><button class="close" data-close>${icons.x(52, 8, "#1c1b1f")}</button></div>` +
    `<div class="rows">${d.events.map((ev) => `<button class="day-row" data-uid="${esc(ev.uid)}">` +
      `<span class="t">${esc(ev.time_label.toUpperCase())}</span><span class="pill" ${chipStyle(ev)}>${esc(ev.title)}</span>` +
      `</button>`).join("")}</div></div>`);
}

async function removeEvent(uid) {
  const ev = findEvent(uid);
  try {
    await request("DELETE", `/api/events/${encodeURIComponent(uid)}`);
    closeSheet();
    toast(`Removed ${esc(ev?.title ?? "event")}`, { ok: true });
    await loadWeek();
  } catch (err) {
    sheetEl.innerHTML = `<div class="scrim" data-close></div>${eventSheet(ev, "confirm", errorText(err))}`;
  }
}
```

In `startKitchen`, change the stage markup and click handler:

```js
  root.innerHTML = `<div class="stage" id="stage"><div class="dash" id="dash"></div>` +
    `<div id="sheet" hidden></div></div>`;
  stage = document.getElementById("stage");
  dash = document.getElementById("dash");
  sheetEl = document.getElementById("sheet");
  fitStage();
  window.addEventListener("resize", fitStage);
  stage.addEventListener("click", (e) => {
    const t = e.target.closest("[data-todo],[data-uid],[data-day],[data-close],[data-delete],[data-keep],[data-remove]");
    if (!t) return;
    const d = t.dataset;
    if (d.close !== undefined) closeSheet();
    else if (d.delete) showSheet(eventSheet(findEvent(d.delete), "confirm"));
    else if (d.keep) showSheet(eventSheet(findEvent(d.keep)));
    else if (d.remove) removeEvent(d.remove);
    else if (d.todo) toggleTodo(t);
    else if (d.uid) openEvent(d.uid);
    else if (d.day) openDay(d.day);
  });
```

Also make `render()` keep the `dimmed` class only while a sheet is open: in `render()`, replace `${dash.classList.contains("dimmed") ? "dimmed" : ""}` with `${sheetEl && !sheetEl.hidden ? "dimmed" : ""}`.

- [ ] **Step 3: Check it against the design**

Run: `scripts/dev.sh`, ego-browser at 3000×2000.
- Tap `+2 more` on the busy day → day sheet like 8d, with all 5 events.
- Tap a row → event sheet like 3a. For `Dentist · Ben` (a House event in the fixtures): WHERE shows the location; footer has `Delete`.
- Tap `Delete` → 3c confirm; `Keep it` returns to 3a; `Yes, remove` closes the sheet, shows the toast `Removed Dentist · Ben`, and the chip disappears.
- Open `Standup` (not a House event) → footer reads `Change it in your Calendar app`.
- Tap the scrim → the sheet closes.

- [ ] **Step 4: Commit**

```bash
git add app/static
git commit -m "Add kitchen day sheet, event detail and delete confirm

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Night mode (6a)

**Files:**
- Modify: `app/static/js/kitchen.js`, `app/static/css/kitchen.css`

**Interfaces:**
- Consumes: `chicagoParts`, `state.week.days[1]` (tomorrow), `state.today.people`, `status()`.
- Produces: `#night` overlay in the stage; `isNight(date) -> boolean` (22:00–05:59 Chicago); wake for 2 minutes on tap.

Reference markup: `python3 -I scripts/design_card.py 6a`.

- [ ] **Step 1: Add night styles to `app/static/css/kitchen.css`**

```css
/* Night mode (6a), 10 PM - 6 AM */
.night { position: absolute; inset: 0; background: #0f0e12; color: #d9d3c7; padding: 72px 80px; display: flex;
  flex-direction: column; justify-content: space-between; opacity: 0; pointer-events: none; transition: opacity 1s; }
.night.on { opacity: 1; pointer-events: auto; }
.night .top { display: flex; justify-content: space-between; align-items: flex-start; font: 600 32px var(--mono);
  letter-spacing: .12em; color: #6f6a7a; }
.night .top .st { display: flex; align-items: center; gap: 16px; font-weight: 400; letter-spacing: 0; }
.night .top .dot { width: 18px; height: 18px; border-radius: 50%; background: #3a7d55; }
.night .top .st.amber .dot { background: var(--warning); }
.night .mid { display: flex; flex-direction: column; align-items: center; gap: 24px; }
.night .big-clock { font: 600 420px/1 var(--sans); letter-spacing: -.04em; color: #e8e2d6; font-variant-numeric: tabular-nums; }
.night .big-date { font: 44px var(--mono); color: #8a8494; letter-spacing: .08em; }
.night .bottom { display: grid; grid-template-columns: 1fr 1fr; gap: 64px; align-items: end; }
.night .lbl { font: 600 32px var(--mono); letter-spacing: .12em; color: #6f6a7a; }
.night .tmrw { display: flex; flex-direction: column; gap: 20px; }
.night .tmrw-ev { display: flex; align-items: center; gap: 28px; }
.night .bar { width: 16px; height: 76px; border-radius: 8px; opacity: .7; }
.night .tmrw-title { font: 600 56px/1.1 var(--sans); color: #e8e2d6; }
.night .tmrw-meta { font: 36px var(--mono); color: #8a8494; margin-top: 10px; }
.night .open { display: flex; flex-direction: column; align-items: flex-end; gap: 20px; }
.night .pills { display: flex; gap: 16px; }
.night .pill { display: flex; align-items: center; gap: 16px; border: 3px solid #2a2832; border-radius: 999px;
  padding: 16px 36px 16px 16px; font: 40px var(--sans); color: #d9d3c7; }
.night .pill .ph { width: 64px; height: 64px; border-radius: 50%; background: #2a2832; }
.night .hint { position: absolute; left: 50%; bottom: 72px; transform: translateX(-50%); font: 32px var(--mono);
  color: #4a4752; letter-spacing: .08em; }
```

- [ ] **Step 2: Add night logic to `app/static/js/kitchen.js`**

```js
let nightEl;
let awakeUntil = 0;
const WAKE_MS = 2 * 60_000;

export const isNight = (d) => { const h = chicagoParts(d).hour; return h >= 22 || h < 6; };

function renderNight(now) {
  const st = status();
  const tomorrow = state.week?.days[1]?.events[0];
  const open = (state.today?.people ?? []).filter((p) => p.left > 0);
  nightEl.innerHTML =
    `<div class="top"><div>NIGHT · UNTIL 6:00 AM</div><div class="st ${st.tone === "amber" ? "amber" : ""}">` +
    `<span class="dot"></span>${esc(st.text)}</div></div>` +
    `<div class="mid"><div class="big-clock">${clockText(now)}</div><div class="big-date">${dateText(now)}</div></div>` +
    `<div class="bottom"><div class="tmrw">` + (tomorrow
      ? `<div class="lbl">TOMORROW</div><div class="tmrw-ev"><div class="bar" style="background:${esc(tomorrow.color)}"></div>` +
        `<div><div class="tmrw-title">${esc(tomorrow.title)}</div><div class="tmrw-meta">${esc(tomorrow.time_label.toUpperCase())}` +
        ` · ${esc(tomorrow.calendar)}</div></div></div>`
      : `<div class="lbl">TOMORROW</div><div class="tmrw-meta">Nothing planned</div>`) +
    `</div><div class="open">` + (open.length
      ? `<div class="lbl">STILL OPEN TODAY</div><div class="pills">${open.map((p) =>
          `<div class="pill"><span class="ph"></span>${esc(p.name)} · ${p.left}</div>`).join("")}</div>` : "") +
    `</div></div><div class="hint">TAP ANYWHERE FOR THE FULL DASHBOARD</div>`;
}

function updateNight(now) {
  const on = isNight(now) && Date.now() > awakeUntil;
  if (on) { closeSheet(); renderNight(now); }
  nightEl.classList.toggle("on", on);
}
```

In `startKitchen`:
- Add `<div class="night" id="night"></div>` to the stage markup after `#sheet`, and set `nightEl = document.getElementById("night");`.
- Add a tap handler before the stage click handler:
```js
  nightEl.addEventListener("click", (e) => {
    e.stopPropagation();  // the waking tap never reaches the dashboard
    awakeUntil = Date.now() + WAKE_MS;
    updateNight(new Date());
  });
```
- In the 1-second interval, after `const now = tickClock();`, add `updateNight(now);`. Also call `updateNight(new Date())` once right after the first `render()`.

- [ ] **Step 3: Check it**

Run `scripts/dev.sh`. To see night mode by day, add this temporary first line inside `isNight`: `if (location.search.includes("night")) return true;`. In ego-browser at 3000×2000, open `http://localhost:8081/?night` and take a screenshot. Remove the line when done.
Expected: matches 6a: dark screen, centered big clock, TOMORROW with a color bar, STILL OPEN TODAY pills for people with open items, hint at the bottom. A tap shows the full dashboard; after 2 minutes night returns with a 1 s fade.

- [ ] **Step 4: Commit** (make sure the `?night` line is removed)

```bash
git add app/static
git commit -m "Add night mode from 10 PM to 6 AM

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Phone home (4a) with event sheet (8h) and TODO edit (8i)

**Files:**
- Modify: `app/static/js/phone.js`, `app/static/css/phone.css`

**Interfaces:**
- Consumes: `api.js` (`state`, `onChange`, `request`, `loadToday`, `loadWeek`, `startPolling`, `status`), `ui.js` helpers.
- Produces: `startPhone(root)`; internal `view` state `{screen: "home"|"add"|"settings", person: id|null, sheet: null|{type:"event",uid,confirm,error}|{type:"todo",id}}`; `go(screen)` used by Task 12. Task 12 adds `renderAdd()` and `renderSettings()` to the same file; this task renders a placeholder for those two screens.

Reference markup: `python3 -I scripts/design_card.py 4a` (also `8h`, `8i`).

- [ ] **Step 1: Write `app/static/css/phone.css`**

```css
/* Phone layout (design 4a-4c, 8h, 8i). Designed at 430 wide; stretches to 900. */
body.is-phone { background: var(--bg); }
.phone { max-width: 900px; margin: 0 auto; padding: 60px 20px 140px; display: flex; flex-direction: column; gap: 28px; }
.p-head { display: flex; justify-content: space-between; align-items: flex-start; }
.p-clock { font: 600 64px/1 var(--sans); letter-spacing: -.04em; }
.p-sub { font: 13px var(--mono); color: var(--muted); letter-spacing: .06em; margin-top: 6px; }
.p-sub .dot { color: var(--success); }
.p-sub.amber, .p-sub.amber .dot { color: var(--warning-text); }
.gear { width: 48px; height: 48px; border-radius: 50%; background: var(--surface); display: flex; align-items: center;
  justify-content: center; }
.gear i { width: 20px; height: 20px; border-radius: 50%; border: 4px dotted var(--muted); }
.p-sec { display: flex; flex-direction: column; gap: 10px; }
.p-label { font: 600 11px var(--mono); letter-spacing: .12em; color: var(--muted); }
.p-next { background: var(--surface); border-radius: 20px; padding: 14px 16px; display: flex; justify-content: space-between;
  align-items: center; gap: 12px; min-height: 56px; width: 100%; text-align: left; }
.p-next .title { font: 600 17px/1.2 var(--sans); }
.p-chip { border-radius: 999px; padding: 6px 12px; font: 600 12px var(--mono); white-space: nowrap; }
.p-week-row { display: grid; grid-template-columns: 64px 1fr; gap: 10px; align-items: center; min-height: 48px; }
.p-week-row + .p-week-row { border-top: 1px solid #ebe8f0; }
.p-week-row .d { font: 600 13px var(--mono); color: var(--muted); }
.p-week-row .d.today { color: var(--accent); }
.p-week-row .chips { display: flex; gap: 6px; flex-wrap: wrap; padding: 6px 0; }
.p-wchip { border-radius: 999px; padding: 6px 12px; font: 600 13px var(--sans); min-height: 32px; }
.p-free { font: 13px var(--mono); color: var(--ring); }
.p-switch { display: flex; gap: 8px; }
.p-person { flex: 1; height: 52px; border-radius: 999px; background: var(--surface); display: flex; align-items: center;
  justify-content: center; gap: 8px; font: 600 15px var(--sans); }
.p-person.sel { background: var(--ink); color: #fff; }
.p-person .ph { width: 28px; height: 28px; border-radius: 50%; background: var(--photo); background-size: 8px 8px; }
.p-person .ph.ok { background: var(--success); }
.p-person .n { font: 12px var(--mono); opacity: .7; }
.p-person .n.ok { color: var(--success); opacity: 1; }
.p-list { background: var(--surface); border-radius: 24px; padding: 4px 16px; }
.p-todo { display: flex; align-items: center; gap: 14px; min-height: 56px; }
.p-todo + .p-todo { border-top: 1px solid var(--divider); }
.p-ring { width: 48px; height: 48px; margin: 0 -10px; display: flex; align-items: center; justify-content: center; flex: none; }
.p-ring span { width: 28px; height: 28px; border-radius: 50%; border: 2.5px solid var(--ring); display: flex;
  align-items: center; justify-content: center; }
.p-todo.done .p-ring span { background: var(--accent); border-color: var(--accent); }
.p-todo.overdue .p-ring span { border-color: var(--danger); }
.p-todo .text { font: 17px var(--sans); flex: 1; text-align: left; min-height: 48px; display: flex; align-items: center; }
.p-todo.done .text { color: var(--faint); text-decoration: line-through; }
.p-todo .when { font: 13px var(--mono); color: var(--muted); }
.p-todo.overdue .when { color: var(--danger); font-weight: 600; }
.p-empty { font: 600 17px var(--sans); color: var(--faint); padding: 16px 0; text-align: center; }
.p-bar { position: fixed; left: 0; right: 0; bottom: 0; padding: 16px 20px 34px; display: flex; gap: 12px;
  background: linear-gradient(rgba(250,249,247,0), var(--bg) 40%); max-width: 900px; margin: 0 auto; }
.p-talk { flex: 1; height: 64px; border-radius: 999px; background: var(--accent); color: #fff; display: flex;
  align-items: center; justify-content: center; gap: 12px; font: 600 18px var(--sans); box-shadow: 0 10px 30px rgba(107,69,217,.3); }
.p-add { width: 64px; height: 64px; border-radius: 50%; background: var(--ink); color: #fff; font: 300 34px/1 var(--sans); }

/* Bottom sheets */
.p-scrim { position: fixed; inset: 0; background: rgba(28,27,31,.45); z-index: 20; }
.p-sheet { position: fixed; left: 0; right: 0; bottom: 0; z-index: 21; background: var(--surface); border-radius: 32px 32px 0 0;
  overflow: hidden; display: flex; flex-direction: column; max-width: 900px; margin: 0 auto; animation: sheet-up .2s ease-out; }
@keyframes sheet-up { from { transform: translateY(40px); opacity: 0; } }
.p-band { padding: 22px 20px 20px; display: flex; justify-content: space-between; align-items: flex-start; }
.p-band .cal { font: 600 11px var(--mono); letter-spacing: .12em; opacity: .7; }
.p-band .title { font: 600 28px/1.1 var(--sans); margin-top: 6px; }
.p-x { width: 48px; height: 48px; border-radius: 50%; background: rgba(0,0,0,.12); display: flex; align-items: center;
  justify-content: center; flex: none; }
.p-rows { padding: 8px 20px; display: flex; flex-direction: column; }
.p-row { display: grid; grid-template-columns: 72px 1fr; gap: 12px; align-items: center; min-height: 60px;
  border-bottom: 1px solid var(--divider); font: 17px var(--sans); }
.p-row .k { font: 600 11px var(--mono); letter-spacing: .12em; color: var(--muted); }
.p-row .dotc { display: inline-block; width: 14px; height: 14px; border-radius: 50%; margin-right: 8px; vertical-align: -1px; }
.p-actions { padding: 8px 20px 34px; display: flex; gap: 10px; align-items: center; }
.p-btn { height: 56px; border-radius: 999px; display: flex; align-items: center; justify-content: center;
  font: 600 16px var(--sans); padding: 0 20px; }
.p-btn.outline { border: 2px solid var(--divider-2); }
.p-btn.danger-text { color: var(--danger); }
.p-btn.danger { background: var(--danger); color: #fff; }
.p-btn.primary { background: var(--accent); color: #fff; flex: 1; }
.p-btn.flex { flex: 1; }
.p-note { font: 15px var(--sans); color: var(--muted); flex: 1; }
.p-err { font: 14px var(--sans); color: var(--danger); }
.p-form { padding: 20px 20px 34px; display: flex; flex-direction: column; gap: 20px; }
.p-form-head { display: flex; justify-content: space-between; align-items: center; }
.p-form-head .h { font: 600 22px var(--sans); }
.p-link { font: 600 15px var(--sans); color: var(--muted); padding: 12px 4px; min-height: 48px; }
.p-input { background: var(--bg); border-radius: 16px; padding: 16px; font: 18px var(--sans); border: 2px solid var(--accent);
  width: 100%; color: var(--ink); }
.p-pills { display: flex; gap: 8px; }
.p-pill { flex: 1; height: 48px; border-radius: 999px; background: var(--bg); display: flex; align-items: center;
  justify-content: center; gap: 8px; font: 600 15px var(--sans); }
.p-pill.sel { background: var(--ink); color: #fff; }
.p-field { position: relative; flex: 1; display: flex; flex-direction: column; gap: 8px; }
.p-field input { height: 48px; border-radius: 999px; background: var(--bg); border: 0; padding: 0 18px;
  font: 600 15px var(--sans); color: var(--ink); width: 100%; }
.p-field input[type=time] { font-family: var(--mono); }

/* Phone toast */
.is-phone .toast { bottom: 110px; padding: 14px 20px; gap: 10px; font: 500 15px var(--sans); }
.is-phone .toast-ok { width: 24px; height: 24px; border-radius: 50%; background: #fff; display: flex; align-items: center;
  justify-content: center; }
.is-phone .toast-ok .i-check { width: 10px !important; height: 5px !important; border-width: 0 0 3px 3px !important; }
```

- [ ] **Step 2: Write `app/static/js/phone.js`**

```js
// Phone layout: home (4a), event sheet (8h), TODO edit (8i); add (4b) and settings (4c) are added in Task 12.
import { loadToday, loadWeek, onChange, request, startPolling, state, status } from "./api.js";
import { chipStyle, clockText, dateText, errorText, esc, icons, toast } from "./ui.js";

let root;
const view = { screen: "home", person: null, sheet: null };

export function go(screen) { view.screen = screen; view.sheet = null; render(); window.scrollTo(0, 0); }

const shortChip = (ev) => (ev.all_day ? ev.title : `${ev.time_label.replace(/ [AP]M$/, "")} ${ev.title}`);

function findEvent(uid) {
  for (const d of state.week?.days ?? []) {
    const ev = d.events.find((e) => e.uid === uid);
    if (ev) return ev;
  }
  return null;
}

function findTodo(id) {
  for (const p of state.today?.people ?? []) {
    const t = p.todos.find((x) => x.id === id);
    if (t) return t;
  }
  return null;
}

function currentPerson() {
  const people = state.today?.people ?? [];
  if (!people.some((p) => p.id === view.person)) view.person = people[0]?.id ?? null;
  return people.find((p) => p.id === view.person);
}

function home() {
  const st = status();
  const now = new Date();
  const w = state.week;
  const people = state.today?.people ?? [];
  const me = currentPerson();
  const next = w?.next?.length ? w.next.map((ev) => `<button class="p-next" data-uid="${esc(ev.uid)}">` +
      `<span class="title">${esc(ev.title)}</span><span class="p-chip" ${chipStyle(ev)}>${esc(ev.relative_label)}</span></button>`).join("")
    : `<div class="p-empty">Nothing coming up</div>`;
  const week = (w?.days ?? []).map((d) => `<div class="p-week-row"><div class="d ${d.is_today ? "today" : ""}">` +
    `${esc(d.dow)} ${d.day}</div><div class="chips">${d.events.length ? d.events.map((ev) =>
      `<button class="p-wchip" data-uid="${esc(ev.uid)}" ${chipStyle(ev)}>${esc(shortChip(ev))}</button>`).join("")
      : `<span class="p-free">free</span>`}</div></div>`).join("");
  const switcher = people.map((p) => {
    const ok = p.state === "all_done";
    return `<button class="p-person ${p.id === view.person ? "sel" : ""}" data-person="${p.id}">` +
      `<span class="ph ${ok ? "ok" : ""}"></span>${esc(p.name)} ` +
      `<span class="n ${ok ? "ok" : ""}">${ok ? "✓" : p.left || ""}</span></button>`;
  }).join("");
  const list = !me ? "" : me.todos.length ? me.todos.map((t) =>
      `<div class="p-todo ${t.done ? "done" : ""} ${t.overdue ? "overdue" : ""}">` +
      `<button class="p-ring" data-toggle="${t.id}" aria-label="Done"><span>${t.done ? icons.check(12, 3) : ""}</span></button>` +
      `<button class="text" data-edit="${t.id}">${esc(t.text)}</button>` +
      (t.time_label ? `<span class="when">${esc(t.time_label)}</span>` : "") + `</div>`).join("")
    : `<div class="p-empty">Nothing today</div>`;
  return `<div class="phone"><div class="p-head"><div><div class="p-clock" id="p-clock">${clockText(now)}</div>` +
    `<div class="p-sub ${st.tone === "amber" ? "amber" : ""}" id="p-sub">${dateText(now)} · <span class="dot">●</span> ` +
    `${esc(st.text)}</div></div><button class="gear" data-go="settings" aria-label="Settings"><i></i></button></div>` +
    `<div class="p-sec"><div class="p-label">NEXT UP</div>${next}</div>` +
    `<div class="p-sec" style="gap:6px"><div class="p-label" style="margin-bottom:4px">THIS WEEK</div>${week}</div>` +
    `<div class="p-sec" style="gap:12px"><div class="p-label">TODAY'S TODOS</div><div class="p-switch">${switcher}</div>` +
    `<div class="p-list">${list}</div></div></div>` +
    `<div class="p-bar"><button class="p-talk" aria-disabled="true">${icons.mic(20)}Talk to the house</button>` +
    `<button class="p-add" data-go="add" aria-label="Add a TODO">+</button></div>`;
}

function eventSheet() {
  const s = view.sheet;
  const ev = findEvent(s.uid);
  if (!ev) return "";
  const who = (state.today?.people ?? []).filter((p) => p.name === ev.calendar);
  const rows = `<div class="p-row"><span class="k">WHEN</span><span>${esc(ev.when_label)}</span></div>` +
    (ev.location ? `<div class="p-row"><span class="k">WHERE</span><span>${esc(ev.location)}</span></div>` : "") +
    (who.length ? `<div class="p-row"><span class="k">WHO</span><span>${who.map((p) => esc(p.name)).join(", ")}</span></div>` : "") +
    `<div class="p-row"><span class="k">CAL</span><span><i class="p-dotc" style="background:${esc(ev.color)}"></i>` +
    `${esc(ev.calendar)}</span></div>`;
  let actions;
  if (!ev.can_delete) actions = `<div class="p-note">Change it in your Calendar app</div>`;
  else if (s.error) actions = `<div class="p-err" style="flex:1">${esc(s.error)}</div><button class="p-btn outline" data-close>Close</button>`;
  else if (s.confirm) actions = `<button class="p-btn outline flex" data-keep>Keep it</button>` +
    `<button class="p-btn danger flex" data-remove="${esc(ev.uid)}">Yes, remove</button>`;
  else actions = `<span style="flex:1"></span><button class="p-btn outline danger-text" data-delete>Delete</button>`;
  return `<div class="p-scrim" data-close></div><div class="p-sheet">` +
    `<div class="p-band" style="background:${esc(ev.color)};color:${esc(ev.ink)}"><div>` +
    `<div class="cal">${esc(ev.calendar.toUpperCase())}</div><div class="title">${esc(ev.title)}</div></div>` +
    `<button class="p-x" data-close aria-label="Close">${icons.x(18, 3, ev.ink)}</button></div>` +
    `<div class="p-rows">${rows}</div><div class="p-actions">${actions}</div></div>`;
}

function todoSheet() {
  const t = findTodo(view.sheet.id);
  if (!t) return "";
  const people = state.today?.people ?? [];
  const pid = view.sheet.person ?? t.person_id;
  return `<div class="p-scrim" data-close></div><div class="p-sheet"><form class="p-form" id="todo-form">` +
    `<div class="p-form-head"><div class="h">Edit TODO</div><button type="button" class="p-link" data-close>Cancel</button></div>` +
    `<input class="p-input" name="text" maxlength="120" required value="${esc(t.text)}">` +
    `<div class="p-sec" style="gap:8px"><div class="p-label">WHO</div><div class="p-pills">${people.map((p) =>
      `<button type="button" class="p-pill ${p.id === pid ? "sel" : ""}" data-pick="${p.id}">${esc(p.name)}</button>`).join("")}</div></div>` +
    `<div class="p-pills"><label class="p-field"><span class="p-label">WHEN</span>` +
    `<input type="date" name="date" required value="${esc(t.date)}"></label>` +
    `<label class="p-field"><span class="p-label">TIME</span><input type="time" name="time" value="${esc(t.time ?? "")}"></label></div>` +
    `<div class="p-err" id="todo-err"></div>` +
    `<div class="p-pills" style="margin-top:8px"><button type="button" class="p-btn outline danger-text" data-del-todo="${t.id}"` +
    ` style="width:110px">Delete</button><button class="p-btn primary">Save</button></div></form></div>`;
}

function renderAdd() { return `<div class="phone"><button class="p-link" data-go="home">Back</button></div>`; }
function renderSettings() { return `<div class="phone"><button class="p-link" data-go="home">Back</button></div>`; }

function render() {
  const screen = view.screen === "add" ? renderAdd() : view.screen === "settings" ? renderSettings() : home();
  const sheet = !view.sheet ? "" : view.sheet.type === "event" ? eventSheet() : todoSheet();
  root.innerHTML = screen + sheet;
}

function rerenderUnlessEditing() {
  // Polling must never wipe a form the person is typing in.
  if (view.screen === "home" && !view.sheet) render();
}

async function act(fn, okMsg) {
  try {
    await fn();
    if (okMsg) toast(esc(okMsg), { ok: true, ms: 3000 });
    return true;
  } catch (err) {
    return err;
  }
}

async function onClick(e) {
  const t = e.target.closest("button,[data-close]");
  if (!t) return;
  const d = t.dataset;
  if (d.close !== undefined) { view.sheet = null; render(); return; }
  if (d.go) { go(d.go); return; }
  if (d.person) { view.person = Number(d.person); render(); return; }
  if (d.uid) { view.sheet = { type: "event", uid: d.uid }; render(); return; }
  if (d.delete !== undefined) { view.sheet.confirm = true; render(); return; }
  if (d.keep !== undefined) { view.sheet.confirm = false; render(); return; }
  if (d.remove) {
    const res = await act(() => request("DELETE", `/api/events/${encodeURIComponent(d.remove)}`), "Removed");
    if (res === true) { view.sheet = null; await loadWeek().catch(() => {}); render(); }
    else { view.sheet.error = errorText(res); render(); }
    return;
  }
  if (d.toggle) {
    const todo = findTodo(Number(d.toggle));
    const res = await act(() => request("PATCH", `/api/todos/${d.toggle}`, { done: !todo.done }));
    if (res !== true) toast("Couldn't save, try again");
    await loadToday().catch(() => {});
    render();
    return;
  }
  if (d.edit) { view.sheet = { type: "todo", id: Number(d.edit) }; render(); return; }
  if (d.pick) {
    const form = document.getElementById("todo-form");
    view.sheet.draft = { text: form.text.value, date: form.date.value, time: form.time.value };
    view.sheet.person = Number(d.pick);
    render();
    const f2 = document.getElementById("todo-form");
    Object.entries(view.sheet.draft).forEach(([k, v]) => { f2[k].value = v; });
    return;
  }
  if (d.delTodo) {
    const res = await act(() => request("DELETE", `/api/todos/${d.delTodo}`), "Deleted");
    if (res === true) { view.sheet = null; await loadToday().catch(() => {}); render(); }
    else document.getElementById("todo-err").textContent = errorText(res);
  }
}

async function onSubmit(e) {
  if (e.target.id !== "todo-form") return;
  e.preventDefault();
  const f = e.target;
  const t = findTodo(view.sheet.id);
  const body = { text: f.text.value, date: f.date.value, time: f.time.value || null,
    person_id: view.sheet.person ?? t.person_id };
  const res = await act(() => request("PATCH", `/api/todos/${t.id}`, body), "Saved");
  if (res === true) { view.sheet = null; await loadToday().catch(() => {}); render(); }
  else document.getElementById("todo-err").textContent = errorText(res);
}

function tick() {
  const c = document.getElementById("p-clock");
  if (!c) return;
  const now = new Date();
  const st = status();
  c.textContent = clockText(now);
  const sub = document.getElementById("p-sub");
  sub.className = `p-sub ${st.tone === "amber" ? "amber" : ""}`;
  sub.innerHTML = `${dateText(now)} · <span class="dot">●</span> ${esc(st.text)}`;
}

export function startPhone(el) {
  root = el;
  root.addEventListener("click", onClick);
  root.addEventListener("submit", onSubmit);
  onChange(rerenderUnlessEditing);
  render();
  startPolling({ alwaysOn: false });
  setInterval(tick, 1000);
}
```

Note: `rerenderUnlessEditing` is the only `onChange` listener. Task 12 keeps that rule for the add and settings screens.

- [ ] **Step 3: Check it against the design**

Run `scripts/dev.sh`; ego-browser at 430×932. Add a TODO for Bob with curl (as in Task 8).
Expected: matches 4a: clock + date + status; gear; NEXT UP cards with chips; THIS WEEK rows with short chips (`5:30 Soccer practice`); person switcher (Bob selected; Belen shows `✓` after all done); list rows with rings. Tap a ring → item done. Tap item text → 8i edit sheet; change the time and Save → list updates. Tap a week chip → 8h sheet; the House fixture event offers Delete → confirm → removed. Tap the scrim → closes. Pinned bottom bar with Talk (inert) and `+`.

- [ ] **Step 4: Commit**

```bash
git add app/static
git commit -m "Add phone home with event sheet and TODO edit

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Phone add TODO (4b) and settings (4c)

**Files:**
- Modify: `app/static/js/phone.js`, `app/static/css/phone.css`

**Interfaces:**
- Consumes: `view`, `go`, `render`, `act`, `state.settings`, `state.week.days`, `loadSettings`, `loadToday`, `loadWeek`, `request`.
- Produces: real `renderAdd()` and `renderSettings()`; `view.add = {text, person, date, time}`; `view.settings = {open: calendarName|null, editing: personId|"new"|null, error}`.

Reference markup: `python3 -I scripts/design_card.py 4b` and `4c`.

- [ ] **Step 1: Add styles to `app/static/css/phone.css`**

```css
.p-title-row { display: flex; justify-content: space-between; align-items: center; }
.p-title { font: 600 28px var(--sans); }
.p-big-input { background: var(--surface); border-radius: 20px; padding: 18px 16px; font: 20px var(--sans);
  border: 2px solid var(--accent); width: 100%; color: var(--ink); }
.p-who { flex: 1; height: 56px; border-radius: 999px; background: var(--surface); display: flex; align-items: center;
  justify-content: center; gap: 8px; font: 600 15px var(--sans); }
.p-who.sel { background: var(--ink); color: #fff; }
.p-who .ph { width: 30px; height: 30px; border-radius: 50%; background: var(--photo); background-size: 8px 8px; }
.p-days { display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; }
.p-day { height: 68px; border-radius: 16px; background: var(--surface); display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 2px; }
.p-day .w { font: 600 10px var(--mono); color: var(--muted); }
.p-day .n { font: 600 20px var(--sans); }
.p-day.sel { background: var(--accent); color: #fff; }
.p-day.sel .w { color: #fff; opacity: .8; }
.p-accent-link { font: 600 14px var(--sans); color: var(--accent); min-height: 48px; display: flex; align-items: center; }
.p-time { flex: 1; height: 56px; border-radius: 999px; background: var(--surface); display: flex; align-items: center;
  justify-content: center; font: 600 15px var(--sans); position: relative; }
.p-time.sel { background: var(--ink); color: #fff; }
.p-time input { position: absolute; inset: 0; opacity: 0; width: 100%; }
.p-time .mono { font: 600 17px var(--mono); }
.p-primary { height: 64px; border-radius: 999px; background: var(--accent); color: #fff; font: 600 18px var(--sans);
  box-shadow: 0 10px 30px rgba(107,69,217,.3); width: 100%; }
.p-primary:disabled { opacity: .5; }
.p-hidden-input { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.p-card { background: var(--surface); border-radius: 24px; padding: 4px 16px; }
.p-cal { display: flex; align-items: center; gap: 14px; min-height: 60px; width: 100%; text-align: left; }
.p-card > * + .p-cal { border-top: 1px solid var(--divider); }
.p-cal .sw { width: 32px; height: 32px; border-radius: 50%; flex: none; }
.p-cal .nm { font: 17px var(--sans); flex: 1; }
.p-cal .hex { font: 12px var(--mono); color: var(--muted); }
.p-swatches { padding: 4px 0 16px 46px; display: flex; flex-direction: column; gap: 12px; }
.p-swatches .row { display: flex; gap: 10px; flex-wrap: wrap; }
.p-sw { width: 40px; height: 40px; border-radius: 50%; }
.p-sw.sel { outline: 3px solid var(--ink); outline-offset: 3px; }
.p-sw.custom { background: conic-gradient(#e0457b, #f2c230, #2fb36a, #2b5fd9, #6b45d9, #e0457b); display: flex;
  align-items: center; justify-content: center; position: relative; }
.p-sw.custom i { width: 22px; height: 22px; border-radius: 50%; background: #fff; }
.p-sw.custom input { position: absolute; inset: 0; opacity: 0; width: 100%; height: 100%; }
.p-preview { display: flex; align-items: center; gap: 10px; }
.p-preview .p-wchip { font-size: 13px; }
.p-preview .hint { font: 12px var(--mono); color: var(--muted); }
.p-fam { display: flex; align-items: center; gap: 14px; min-height: 64px; }
.p-fam + .p-fam { border-top: 1px solid var(--divider); }
.p-fam .ph { width: 40px; height: 40px; border-radius: 50%; background: var(--photo); background-size: 8px 8px; flex: none; }
.p-fam .ph.add { background: none; border: 2px dashed var(--ring); display: flex; align-items: center; justify-content: center;
  font: 300 24px/1 var(--sans); color: var(--faint); }
.p-fam .nm { font: 17px var(--sans); flex: 1; }
.p-fam .edit { font: 600 14px var(--sans); color: var(--muted); min-height: 48px; padding: 0 4px; }
.p-fam.add-row { color: var(--accent); font: 600 17px var(--sans); width: 100%; text-align: left; }
.p-fam input { flex: 1; font: 17px var(--sans); border: 2px solid var(--accent); border-radius: 12px; padding: 10px;
  min-width: 0; }
.p-later { opacity: .5; }
.p-later .p-fam { min-height: 56px; font: 17px var(--sans); }
```

- [ ] **Step 2: Replace the `renderAdd` and `renderSettings` placeholders in `app/static/js/phone.js`**

Add `loadSettings` to the `api.js` import. Then:

```js
function addDefaults() {
  const days = state.week?.days ?? [];
  return { text: "", person: currentPerson()?.id ?? null, date: days[0]?.date ?? "", time: "" };
}

function fmtHHMM(hhmm) {
  if (!hhmm) return "";
  const [h, m] = hhmm.split(":").map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
}

function dowOf(dateIso) {
  const day = state.week?.days.find((d) => d.date === dateIso);
  if (day) return day.dow[0] + day.dow.slice(1).toLowerCase();
  const [y, m, d] = dateIso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" });
}

function renderAdd() {
  view.add ??= addDefaults();
  const a = view.add;
  const people = state.settings?.people ?? state.today?.people ?? [];
  const who = people.find((p) => p.id === a.person);
  const label = who ? `Add for ${esc(who.name)} · ${esc(dowOf(a.date))}${a.time ? ` ${fmtHHMM(a.time)}` : ""}` : "Add";
  const inStrip = (state.week?.days ?? []).some((d) => d.date === a.date);
  return `<form class="phone" id="add-form" autocomplete="off">` +
    `<div class="p-title-row"><div class="p-title">New TODO</div><button type="button" class="p-link" data-go="home">Cancel</button></div>` +
    `<input class="p-big-input" name="text" maxlength="120" placeholder="What needs doing?" value="${esc(a.text)}" autofocus>` +
    `<div class="p-sec"><div class="p-label">WHO</div><div class="p-pills">${people.map((p) =>
      `<button type="button" class="p-who ${p.id === a.person ? "sel" : ""}" data-add-person="${p.id}"><span class="ph"></span>` +
      `${esc(p.name)}</button>`).join("")}</div></div>` +
    `<div class="p-sec"><div class="p-title-row"><div class="p-label">WHEN</div>` +
    `<label class="p-accent-link">${inStrip ? "Pick another date" : esc(a.date)}` +
    `<input class="p-hidden-input" type="date" name="pickdate" value="${esc(a.date)}"></label></div>` +
    `<div class="p-days">${(state.week?.days ?? []).map((d) => `<button type="button" class="p-day ${d.date === a.date ? "sel" : ""}"` +
      ` data-add-date="${esc(d.date)}"><span class="w">${esc(d.dow)}</span><span class="n">${d.day}</span></button>`).join("")}</div></div>` +
    `<div class="p-sec"><div class="p-label">TIME · OPTIONAL</div><div class="p-pills">` +
    `<button type="button" class="p-time ${a.time ? "" : "sel"}" data-add-anytime>Any time</button>` +
    `<label class="p-time ${a.time ? "sel" : ""}"><span class="mono">${a.time ? fmtHHMM(a.time) : "Set a time"}</span>` +
    `<input type="time" name="time" value="${esc(a.time)}"></label></div></div>` +
    `<div class="p-err" id="add-err"></div>` +
    `<button class="p-primary" ${a.text.trim() && who ? "" : "disabled"}>${label}</button></form>`;
}

function renderSettings() {
  view.settings ??= { open: null, editing: null, error: "" };
  const s = view.settings;
  const cals = state.settings?.calendars ?? [];
  const people = state.settings?.people ?? [];
  const PRESETS = ["#f2c230", "#e0702a", "#d2382f", "#e0457b", "#6b45d9", "#2b5fd9", "#14a08a", "#2fb36a"];
  const calRows = cals.map((c) => `<button class="p-cal" data-cal="${esc(c.name)}"><span class="sw" style="background:${esc(c.color)}"></span>` +
    `<span class="nm">${esc(c.name)}</span><span class="hex">${esc(c.color.toUpperCase())}</span></button>` +
    (s.open === c.name ? `<div class="p-swatches"><div class="row">${PRESETS.map((p) =>
      `<button class="p-sw ${p === c.color ? "sel" : ""}" style="background:${p}" data-color="${p}" aria-label="${p}"></button>`).join("")}` +
      `<label class="p-sw custom ${PRESETS.includes(c.color) ? "" : "sel"}"><i></i><input type="color" name="custom" value="${esc(c.color)}"></label></div>` +
      `<div class="p-preview"><span class="p-wchip" style="background:${esc(c.color)};color:${esc(c.ink)}">Preview: Pizza night</span>` +
      `<span class="hint">text auto-flips</span></div></div>` : "")).join("");
  const famRows = people.map((p) => s.editing === p.id
    ? `<form class="p-fam" data-person-form="${p.id}"><span class="ph"></span><input name="pname" maxlength="40" value="${esc(p.name)}" required>` +
      `<button class="edit" style="color:var(--accent)">Save</button><button type="button" class="edit" style="color:var(--danger)" data-remove-person="${p.id}">Remove</button></form>`
    : `<div class="p-fam"><span class="ph"></span><span class="nm">${esc(p.name)}</span>` +
      `<button class="edit" data-edit-person="${p.id}">Edit</button></div>`).join("") +
    (s.editing === "new"
      ? `<form class="p-fam" data-person-form="new"><span class="ph add">+</span><input name="pname" maxlength="40" placeholder="Name" required autofocus>` +
        `<button class="edit" style="color:var(--accent)">Add</button></form>`
      : `<button class="p-fam add-row" data-edit-person="new"><span class="ph add">+</span>Add a person</button>`);
  return `<div class="phone"><div class="p-title-row"><div class="p-title">Settings</div>` +
    `<button class="p-link" style="color:var(--accent)" data-go="home">Done</button></div>` +
    `<div class="p-sec"><div class="p-label">CALENDARS</div><div class="p-card">${calRows || `<div class="p-empty">No calendars yet</div>`}</div></div>` +
    `<div class="p-sec"><div class="p-label">FAMILY</div><div class="p-card">${famRows}</div>` +
    (s.error ? `<div class="p-err">${esc(s.error)}</div>` : "") + `</div>` +
    `<div class="p-sec p-later"><div class="p-label">LATER</div><div class="p-card">` +
    `<div class="p-fam">Night mode · 10 PM – 6 AM</div><div class="p-fam">Photo slideshow after 5 min</div></div></div></div>`;
}

async function setColor(name, color) {
  await request("PUT", `/api/settings/calendars/${encodeURIComponent(name)}`, { color });
  await Promise.all([loadSettings(), loadWeek()]).catch(() => {});
  render();
}
```

Change `go()` so each visit to "add" starts fresh:
```js
export function go(screen) {
  view.screen = screen; view.sheet = null;
  if (screen === "add") view.add = null;
  if (screen === "settings") view.settings = null;
  render(); window.scrollTo(0, 0);
}
```

Add these branches at the top of `onClick` (after `const d = t.dataset;`):
```js
  if (d.addPerson) { syncAdd(); view.add.person = Number(d.addPerson); render(); return; }
  if (d.addDate) { syncAdd(); view.add.date = d.addDate; render(); return; }
  if (d.addAnytime !== undefined) { syncAdd(); view.add.time = ""; render(); return; }
  if (d.cal) { view.settings.open = view.settings.open === d.cal ? null : d.cal; render(); return; }
  if (d.color) { await setColor(view.settings.open, d.color); return; }
  if (d.editPerson) { view.settings.editing = d.editPerson === "new" ? "new" : Number(d.editPerson); view.settings.error = ""; render(); return; }
  if (d.removePerson) {
    const res = await act(() => request("DELETE", `/api/settings/people/${d.removePerson}`));
    view.settings.error = res === true ? "" : errorText(res);
    if (res === true) view.settings.editing = null;
    await Promise.all([loadSettings(), loadToday()]).catch(() => {});
    render();
    return;
  }
```

Add helpers and an `input`/`change` listener:
```js
function syncAdd() {
  const f = document.getElementById("add-form");
  if (f) view.add.text = f.text.value;
}

function onInput(e) {
  const f = e.target.form;
  if (f?.id === "add-form") {
    if (e.target.name === "text") {
      view.add.text = e.target.value;
      f.querySelector(".p-primary").disabled = !view.add.text.trim() || !view.add.person;
      return;
    }
    if (e.target.name === "time") { view.add.time = e.target.value; render(); }
    if (e.target.name === "pickdate" && e.target.value) { view.add.date = e.target.value; render(); }
  }
  if (e.target.name === "custom" && e.type === "change") setColor(view.settings.open, e.target.value);
}
```

Extend `onSubmit` to handle the add form and the person forms (put these before the `todo-form` check, and change that check to `if (e.target.id === "todo-form") { … }`):
```js
  if (e.target.id === "add-form") {
    e.preventDefault();
    const a = view.add;
    const res = await act(() => request("POST", "/api/todos",
      { person_id: a.person, text: a.text, date: a.date, time: a.time || null }), "Added");
    if (res === true) { await loadToday().catch(() => {}); view.person = a.person; go("home"); }
    else document.getElementById("add-err").textContent = errorText(res);
    return;
  }
  if (e.target.dataset.personForm) {
    e.preventDefault();
    const id = e.target.dataset.personForm;
    const name = e.target.pname.value;
    const res = await act(() => id === "new" ? request("POST", "/api/settings/people", { name })
      : request("PATCH", `/api/settings/people/${id}`, { name }));
    view.settings.error = res === true ? "" : errorText(res);
    if (res === true) view.settings.editing = null;
    await Promise.all([loadSettings(), loadToday()]).catch(() => {});
    render();
    return;
  }
```

In `startPhone`, register the new listeners:
```js
  root.addEventListener("input", onInput);
  root.addEventListener("change", onInput);
```

The person name input is called `pname`, not `name`, because `form.name` is the form's own attribute.

- [ ] **Step 3: Check it against the design**

Run `scripts/dev.sh`; ego-browser at 430×932.
- Tap `+` → 4b. Type `Return library books`, pick Belen, Wednesday, set 3:30 PM → button reads `Add for Belen · Wed 3:30 PM`. Tap it → back home on Belen with the new item, toast `Added`. Within 10 s the kitchen tab (open another ego-browser page at 3000×2000) shows it in Belen's card.
- `Pick another date` opens the native date picker; a date outside the strip shows in the link.
- Gear → 4c. Tap `Family` → presets row with the current one outlined and `Preview: Pizza night`. Tap blue → swatch, hex and preview update; text flips to white; the kitchen tab shows Family chips in blue within 60 s.
- Custom swatch opens the native color picker.
- Family: Edit Ben → Remove while Ben has TODOs → message `Move or delete this person's TODOs first`. Add a person → appears in the list and as a 4th card slot target on the phone switcher.

- [ ] **Step 4: Commit**

```bash
git add app/static
git commit -m "Add phone add-TODO form and settings screen

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Docker, compose and CI

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.github/workflows/ci.yml`

**Interfaces:**
- Produces: image with `test` stage (ruff + pytest) and runtime stage; `APP_VERSION` build arg; compose service `kitchen-dashboard`.

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.13-slim AS base
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=America/Chicago
COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore --disable-pip-version-check -r requirements.txt
COPY app ./app
COPY fixtures ./fixtures

# `docker build --target test .` gates every deploy: if this stage fails, nothing ships.
FROM base AS test
COPY requirements-dev.txt pyproject.toml ./
COPY tests ./tests
RUN pip install --no-cache-dir --root-user-action=ignore --disable-pip-version-check -r requirements-dev.txt \
 && ruff check app tests && pytest -q

FROM base
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION
RUN useradd --uid 10001 --no-create-home app && mkdir -p /data && chown app /data
USER app
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/version', timeout=5)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

After the first successful build, pin the base image by digest: run `docker pull python:3.13-slim && docker inspect --format '{{index .RepoDigests 0}}' python:3.13-slim` and replace the `FROM` line with `FROM python:3.13-slim@sha256:<digest> AS base`.

- [ ] **Step 2: Write `.dockerignore`**

```
.git
.venv
.dev.db
__pycache__
.pytest_cache
.ruff_cache
docs
ops
scripts
```

- [ ] **Step 3: Write `docker-compose.yml`**

```yaml
# Runs on home-ai next to the household-ai stack; joins its network to reach calendar-api.
services:
  kitchen-dashboard:
    build:
      context: .
      args:
        APP_VERSION: ${APP_VERSION:-dev}
    image: household/kitchen-dashboard:${APP_VERSION:-dev}
    container_name: kitchen-dashboard
    ports: ["8081:8000"]
    environment:
      CALENDAR_API: http://calendar-api:8000
      DASHBOARD_DB: /data/dashboard.db
    volumes:
      - ${HOME}/household-ai/data/dashboard:/data
    networks: [household]
    restart: unless-stopped

networks:
  household:
    external: true
    name: household-ai_default
```

- [ ] **Step 4: Write `.github/workflows/ci.yml`**

```yaml
name: ci
on:
  push:
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -r requirements-dev.txt
      - run: ruff check .
      - run: pytest -q
      - name: Docker test stage (same gate home-ai uses)
        run: docker build --target test -t kd:test . && docker build -t kd .
```

- [ ] **Step 5: Build locally**

Run: `docker build --target test -t kd:test . && docker build -t kd .`
Expected: test stage prints all tests passed; final image builds. If Docker is not available on the dev Mac, run this step on home-ai in Task 15.

Run: `mkdir -p /tmp/kd-data && chmod 777 /tmp/kd-data && docker run --rm -d -p 8082:8000 -e DASHBOARD_FAKE=1 -v /tmp/kd-data:/data --name kd-try kd && sleep 3 && curl -s localhost:8082/api/version; docker rm -f kd-try`
Expected: `{"version":"dev"}`.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile .dockerignore docker-compose.yml .github
git commit -m "Add Docker build with test gate, compose and CI

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: Deploy scripts for home-ai

**Files:**
- Create: `ops/deploy-here.sh`, `ops/watch-deploy.sh`, `ops/install-on-home-ai.sh`, `ops/com.household.kitchen-deploy.plist`, `scripts/deploy.sh`

**Interfaces:**
- Produces: on home-ai, checkout at `~/kitchen-dashboard`, launchd label `com.household.kitchen-deploy` running every 120 s, log at `~/household-ai/logs/kitchen-deploy.log`, ntfy topic `http://localhost:8090/home-ai-alerts`.

- [ ] **Step 1: Write `ops/deploy-here.sh`**

```sh
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
```

- [ ] **Step 2: Write `ops/watch-deploy.sh`**

```sh
#!/bin/sh
# Pull-based deploy. launchd runs this every 2 minutes on home-ai.
# New commit on origin/main -> test, start, health check. Any failure -> roll back and send an ntfy alert.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$HOME/kitchen-dashboard" || exit 1
notify() {
  curl -fs --max-time 5 -H "Title: kitchen-dashboard" -H "Tags: warning" -d "$1" \
    http://localhost:8090/home-ai-alerts >/dev/null 2>&1 || true
}
git fetch -q origin main 2>/dev/null || exit 0   # offline: try again next run
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] && exit 0
PREV=$(git rev-parse HEAD)
NEW=$(git rev-parse --short origin/main)
echo "$(date '+%F %T') deploying $NEW"
if ! git merge -q --ff-only origin/main; then
  notify "Can't fast-forward to $NEW (local changes or a force-push?). Not deployed."
  exit 1
fi
if sh ops/deploy-here.sh; then
  echo "$(date '+%F %T') live $NEW"
else
  git reset -q --hard "$PREV"
  sh ops/deploy-here.sh >/dev/null 2>&1
  notify "Deploy of $NEW failed (tests, build or health). Rolled back to $(git rev-parse --short HEAD). See ~/household-ai/logs/kitchen-deploy.log"
  echo "$(date '+%F %T') FAILED $NEW, rolled back"
fi
```

Note: after a rollback, `HEAD` is behind `origin/main`, so the next run tries the bad commit again and alerts again every 2 minutes until a fix is pushed. That is intended: the alert repeats until someone acts.

- [ ] **Step 3: Write `ops/com.household.kitchen-deploy.plist`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.household.kitchen-deploy</string>
  <key>ProgramArguments</key>
  <array><string>/bin/sh</string><string>/Users/bobg/kitchen-dashboard/ops/watch-deploy.sh</string></array>
  <key>StartInterval</key><integer>120</integer>
  <key>StandardOutPath</key><string>/Users/bobg/household-ai/logs/kitchen-deploy.log</string>
  <key>StandardErrorPath</key><string>/Users/bobg/household-ai/logs/kitchen-deploy.log</string>
</dict>
</plist>
```

- [ ] **Step 4: Write `ops/install-on-home-ai.sh`**

```sh
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
```

- [ ] **Step 5: Write `scripts/deploy.sh`**

```sh
#!/bin/sh
# Deploy origin/main to home-ai now, instead of waiting for the 2-minute watcher. Needs Tailscale + SSH key.
set -e
HOST="${HOME_AI:-bobg@home-ai}"
if [ -n "$(git status --porcelain)" ] || [ "$(git rev-parse HEAD)" != "$(git rev-parse '@{u}' 2>/dev/null)" ]; then
  echo "Commit and push first: only what is on origin/main gets deployed." >&2
  exit 1
fi
ssh "$HOST" 'cd ~/kitchen-dashboard && git fetch -q origin main && git merge -q --ff-only origin/main && sh ops/deploy-here.sh'
```

Run: `chmod +x ops/*.sh scripts/deploy.sh && sh -n ops/deploy-here.sh ops/watch-deploy.sh ops/install-on-home-ai.sh scripts/deploy.sh && plutil -lint ops/com.household.kitchen-deploy.plist`
Expected: no syntax errors; `OK` from plutil.

- [ ] **Step 6: Commit**

```bash
git add ops scripts/deploy.sh
git commit -m "Add pull-based deploy with rollback and ntfy alert for home-ai

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 15: CLAUDE.md, README, and go live

**Files:**
- Create: `CLAUDE.md`, `README.md`

- [ ] **Step 1: Write `CLAUDE.md`**

```markdown
# Kitchen Dashboard: notes for Claude Code

Family wall display for the Gibilaro household (Bob, Belen, Ben). Part of the private **household-ai** system.
Rule one: **family data stays in the house.**

## Where things are
- Spec: `docs/superpowers/specs/2026-10-26-kitchen-dashboard-part1-design.md` · Design: `docs/design/README.md`
  (print a design card: `python3 -I scripts/design_card.py 2a`).
- Server: `app/` (FastAPI). `store` (SQLite + change counter), `todos` (rules), `settings` (colors, people),
  `calendar` (calendar-api client, cache, week builder), `labels` (pure formatting), `api` (routes).
- Page: `app/static/` plain HTML/CSS/ES modules. `kitchen.js` (3000×2000 stage), `phone.js` (≤ 900px), shared `api.js`, `ui.js`.

## How it runs
- home-ai (M1 Mac, OrbStack): container `kitchen-dashboard`, port 8081 → 8000, network `household-ai_default`,
  data `~/household-ai/data/dashboard/dashboard.db`.
- Kiosk: Surface Book, Fedora, full-screen browser at `http://home-ai:8081`. Never deploy to it.
- Calendar: `calendar-api` (household-ai repo), read-only here except `DELETE /events/{uid}` for House-made events.

## Commands
- Dev with fake data: `scripts/dev.sh` → http://localhost:8081 (narrow the window for the phone layout)
- Tests: `pytest -q && ruff check .` (CI also runs `docker build --target test .`)
- Deploy: push to `main` → live within ~2 min. Right away: `scripts/deploy.sh`.
- Logs on home-ai: `~/household-ai/logs/kitchen-deploy.log`, `docker logs kitchen-dashboard`.

## Rules
- No external network calls, CDNs, web fonts or analytics. System fonts only.
- All dates/times America/Chicago, computed on the server. Never slice calendar ISO strings for dates.
- Kitchen: touch only, ≥ 100px targets, nothing below 30px; never use browser zoom to fix sizing.
- Escape all calendar/TODO text (`esc()` in `ui.js`).
- Polling: `/api/changes` every 10 s, week + today every 60 s. Writes to todos/people/colors must call `store.bump`.
- Ask Bob before touching household-ai, Tailscale rules, kiosk config, or what family data the screen shows.
- `main` is production. Branch + PR for anything bigger than a small tweak.

## Coming next
- Part 2: Talk to the house (voice/chat panel, local speech-to-text, House AI tools, HTTPS on the kiosk).
- Part 3: photo slideshow from a shared Apple Photos album synced on home-ai.
```

- [ ] **Step 2: Write `README.md`**

```markdown
# kitchen-dashboard

Family wall screen for the kitchen: this week's calendar, what's next, and a daily TODO list per person.
Runs on home-ai; shown full-screen on the kitchen kiosk and on phones over Tailscale. See `CLAUDE.md`.

    scripts/dev.sh            # fake data at http://localhost:8081
    pytest -q && ruff check .
    git push                  # deploys to home-ai within ~2 minutes
    scripts/deploy.sh         # or deploy right away after pushing

First-time setup on home-ai: `sh ops/install-on-home-ai.sh key`, add the printed key on GitHub as a read-only
deploy key, then `sh ops/install-on-home-ai.sh install`.
```

- [ ] **Step 3: Final checks and push**

Run: `pytest -q && ruff check . && git status`
Expected: all pass, clean tree after commit.

```bash
git add CLAUDE.md README.md
git commit -m "Add CLAUDE.md and README

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

Expected: GitHub Actions `ci` run is green (`gh run list --limit 1`).

- [ ] **Step 4: First-time setup on home-ai (needs Bob for one step)**

The repo is private, so copy the script over SSH:
Run: `scp ops/install-on-home-ai.sh bobg@home-ai:~/tmp-install-kitchen.sh && ssh bobg@home-ai 'sh ~/tmp-install-kitchen.sh key'`
Expected: prints a public key.

**Bob:** add that key at `https://github.com/BobTheGeek/kitchen-dashboard/settings/keys`, title `home-ai deploy`, **Allow write access unchecked**.

Then run: `ssh bobg@home-ai 'sh ~/tmp-install-kitchen.sh install && rm ~/tmp-install-kitchen.sh'`
Expected: `== live: <sha>` then `== watcher loaded`.

- [ ] **Step 5: Verify live**

Run: `curl -s http://home-ai:8081/api/version` and `curl -s http://home-ai:8081/api/week | python3 -m json.tool | head -20`
Expected: version equals `git rev-parse --short origin/main`. While calendar-api's iCloud error persists, `calendar_ok` is `false` and `fetched_at` is `null`; the page shows `no calendar data yet` in amber and `free` days. That is correct until Bob fixes the iCloud password in household-ai.

Push a trivial commit (for example a README typo fix) and confirm `~/household-ai/logs/kitchen-deploy.log` shows `live <sha>` within ~2 minutes.

- [ ] **Step 6: Check on the real screen (Bob)**

**Bob:** look at the kiosk (it already points at `http://home-ai:8081`). Send a photo from across the kitchen. Adjust sizes only from that photo. Add a TODO on a phone and confirm it shows on the kiosk within ~10 s; tap it done on the kiosk and confirm the phone updates within ~10 s.
```
