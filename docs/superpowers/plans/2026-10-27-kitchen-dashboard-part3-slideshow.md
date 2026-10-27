# Part 3 Idle Photo Slideshow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the "Kitchen Tablet Slideshow" shared album full-screen on the kitchen wall after 5 idle daytime minutes.

**Architecture:** An hourly launchd job on home-ai exports the album with `osxphotos` and resizes it with `sips` into
`~/household-ai/data/photos/kitchen/`. The container mounts that folder read-only at `/photos`; FastAPI lists it at
`/api/photos` and serves files at `/photos/{name}`. A new page module `slideshow.js` runs the idle timer, crossfade and wake.

**Tech Stack:** FastAPI, pytest, plain ES modules + CSS, POSIX sh, launchd, osxphotos 0.77.2, macOS `sips`.

**Spec:** `docs/superpowers/specs/2026-10-27-kitchen-dashboard-part3-slideshow-design.md`

## Global Constraints

- Family data stays in the house. No external network calls, CDNs, web fonts or analytics.
- All dates/times America/Chicago, computed on the server (`app/clock.py`, `clock.now()`).
- Slideshow hours: `START_HOUR = 7`, `END_HOUR = 21` (7:00 AM to 9:00 PM Chicago).
- Idle 5 minutes; new photo every 20 s; crossfade 800 ms; wake animation 400 ms ease-out; list refresh every 10 minutes.
- Photo names must match `^[A-Za-z0-9-]{1,80}\.jpg$`; anything else is 404 and never listed.
- Photo responses: `Content-Type: image/jpeg`, `Cache-Control: public, max-age=31536000, immutable`; page URLs carry `?v=<mtime>`.
- Kitchen: touch only; nothing below 30px on the 3000×2000 stage. Phone layout gets no slideshow.
- Escape all calendar text with `esc()` from `ui.js`.
- Album name `Kitchen Tablet Slideshow` lives only in `ops/photo-sync.sh` (`ALBUM`).
- Tests: `.venv/bin/pytest -q && .venv/bin/ruff check .` must pass before every commit.
- `main` is production: work on branch `part3-slideshow`, merge by PR.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`

---

### Task 1: Photo folder and slideshow hours (`app/photos.py`)

**Files:**
- Create: `app/photos.py`
- Test: `tests/test_photos.py`

**Interfaces:**
- Produces: `list_photos(folder: Path | None) -> list[dict]` (`[{"name": str, "v": int}]`, sorted by name);
  `photo_path(folder: Path | None, name: str) -> Path | None`; `slideshow_hours(now: datetime) -> bool`;
  constants `START_HOUR`, `END_HOUR`, `NAME`.

- [ ] **Step 1: Write the failing tests** in `tests/test_photos.py`

```python
import os

from app import photos


def put(folder, name, mtime=1_700_000_000):
    p = folder / name
    p.write_bytes(b"\xff\xd8\xff")
    os.utime(p, (mtime, mtime))
    return p


def test_list_photos_filters_and_sorts(tmp_path):
    put(tmp_path, "b-2.jpg", 1_700_000_100)
    put(tmp_path, "A1.jpg")
    put(tmp_path, "x.png")
    put(tmp_path, ".tmp.jpg")
    put(tmp_path, "has space.jpg")
    (tmp_path / "sub.jpg").mkdir()
    assert photos.list_photos(tmp_path) == [{"name": "A1.jpg", "v": 1_700_000_000},
                                            {"name": "b-2.jpg", "v": 1_700_000_100}]


def test_list_photos_missing_folder(tmp_path):
    assert photos.list_photos(tmp_path / "nope") == []
    assert photos.list_photos(None) == []


def test_photo_path(tmp_path):
    put(tmp_path, "ok.jpg")
    assert photos.photo_path(tmp_path, "ok.jpg") == tmp_path / "ok.jpg"
    for bad in ("../ok.jpg", "ok.png", "missing.jpg", ".tmp.jpg", ""):
        assert photos.photo_path(tmp_path, bad) is None
    assert photos.photo_path(None, "ok.jpg") is None


def test_slideshow_hours(freeze):
    assert photos.slideshow_hours(freeze("2026-10-27T06:59")) is False
    assert photos.slideshow_hours(freeze("2026-10-27T07:00")) is True
    assert photos.slideshow_hours(freeze("2026-10-27T20:59")) is True
    assert photos.slideshow_hours(freeze("2026-10-27T21:00")) is False
    # DST ends Sun 1 Nov 2026; local wall time still decides.
    assert photos.slideshow_hours(freeze("2026-11-01T07:30")) is True
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest -q tests/test_photos.py`
Expected: FAIL with `ImportError: cannot import name 'photos'`.

- [ ] **Step 3: Write `app/photos.py`**

```python
"""Slideshow photos: the folder the home-ai sync job fills, and the hours the slideshow may run."""
import re
from datetime import datetime
from pathlib import Path

START_HOUR = 7   # 7:00 AM Chicago
END_HOUR = 21    # 9:00 PM Chicago
NAME = re.compile(r"^[A-Za-z0-9-]{1,80}\.jpg$")


def list_photos(folder: Path | None) -> list[dict]:
    if folder is None:
        return []
    try:
        names = sorted(p.name for p in folder.iterdir() if NAME.match(p.name))
    except OSError:
        return []
    out = []
    for name in names:
        try:
            st = (folder / name).stat()
        except OSError:
            continue  # removed by the sync job between the listing and now
        if (folder / name).is_file():
            out.append({"name": name, "v": int(st.st_mtime)})
    return out


def photo_path(folder: Path | None, name: str) -> Path | None:
    if folder is None or not NAME.match(name):
        return None
    path = folder / name
    return path if path.is_file() else None


def slideshow_hours(now: datetime) -> bool:
    return START_HOUR <= now.hour < END_HOUR
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest -q tests/test_photos.py && .venv/bin/ruff check app tests`
Expected: 4 passed, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add app/photos.py tests/test_photos.py
git commit -m "Photos: list the slideshow folder safely and decide slideshow hours"
```

---

### Task 2: Photo routes, container mount, fake photos

**Files:**
- Modify: `app/api.py` (imports line 16; `create_app` signature and body; new routes before `@app.get("/")`)
- Modify: `docker-compose.yml` (environment + volumes)
- Create: `fixtures/photos/landscape.jpg`, `fixtures/photos/portrait.jpg`, `fixtures/photos/square.jpg`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `photos.list_photos`, `photos.photo_path`, `photos.slideshow_hours` (Task 1).
- Produces: `create_app(..., photos_dir: str | None = None)`; `GET /api/photos` → `{"photos": [{"name", "v"}], "active": bool}`;
  `GET /photos/{name}` → JPEG or 404.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_api.py`)

```python
def photo_client(tmp_path, src, photos_dir):
    return TestClient(create_app(db_path=str(tmp_path / "p.db"), source=src, version="v", photos_dir=photos_dir))


def test_photos_list_and_file(tmp_path, src, freeze):
    folder = tmp_path / "photos"
    folder.mkdir()
    (folder / "abc-1.jpg").write_bytes(b"\xff\xd8\xffjpeg")
    (folder / "notes.txt").write_text("x")
    c = photo_client(tmp_path, src, str(folder))
    freeze("2026-10-27T10:00")
    body = c.get("/api/photos").json()
    assert [p["name"] for p in body["photos"]] == ["abc-1.jpg"] and body["active"] is True
    assert isinstance(body["photos"][0]["v"], int)
    freeze("2026-10-27T21:30")
    assert c.get("/api/photos").json()["active"] is False
    r = c.get("/photos/abc-1.jpg?v=1")
    assert r.status_code == 200 and r.content == b"\xff\xd8\xffjpeg"
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_photos_refuses_bad_names(tmp_path, src):
    folder = tmp_path / "photos"
    folder.mkdir()
    (tmp_path / "secret.jpg").write_bytes(b"x")
    (folder / "notes.png").write_bytes(b"x")
    c = photo_client(tmp_path, src, str(folder))
    for path in ("/photos/..%2Fsecret.jpg", "/photos/%2e%2e%2fsecret.jpg", "/photos/notes.png", "/photos/missing.jpg"):
        assert c.get(path).status_code == 404, path


def test_photos_without_folder(tmp_path, src):
    c = photo_client(tmp_path, src, None)
    assert c.get("/api/photos").json()["photos"] == []
    assert c.get("/photos/a.jpg").status_code == 404
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest -q tests/test_api.py -k photos`
Expected: FAIL with `TypeError: create_app() got an unexpected keyword argument 'photos_dir'`.

- [ ] **Step 3: Add the routes to `app/api.py`**

Change the import line `from app import actions, clock, settings, todos` to:

```python
from app import actions, clock, photos, settings, todos
```

Add `photos_dir: str | None = None` as the last parameter of `create_app`:

```python
def create_app(db_path: str | None = None, source=None, version: str | None = None, whisper=None, house=None,
               house_token: str | None = None, photos_dir: str | None = None) -> FastAPI:
```

Right after the line `fake = os.environ.get("DASHBOARD_FAKE") == "1"`, add:

```python
    if photos_dir is None:
        photos_dir = os.environ.get("PHOTOS_DIR") or (str(ROOT / "fixtures" / "photos") if fake else "")
    photo_root = Path(photos_dir) if photos_dir else None
```

Directly above `@app.get("/")` (the index route), add:

```python
    @app.get("/api/photos")
    def get_photos():
        return {"photos": photos.list_photos(photo_root), "active": photos.slideshow_hours(clock.now())}

    @app.get("/photos/{name}")
    def get_photo(name: str):
        path = photos.photo_path(photo_root, name)
        if path is None:
            raise HTTPException(404, "No such photo")
        # Each URL carries ?v=<mtime>, so a changed photo gets a new URL and the cache never goes stale.
        return FileResponse(path, media_type="image/jpeg",
                            headers={"Cache-Control": "public, max-age=31536000, immutable"})
```

Note: the existing tests call `create_app` without `photos_dir`; with no `PHOTOS_DIR` env and no fake mode,
`photos_dir` becomes `""` and `photo_root` is `None`.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check .`
Expected: all pass.

- [ ] **Step 5: Mount the folder in `docker-compose.yml`**

Under `environment:` add `PHOTOS_DIR: /photos`. Under `volumes:` add:

```yaml
      - ${HOME}/household-ai/data/photos/kitchen:/photos:ro       # filled hourly by ops/photo-sync.sh
```

- [ ] **Step 6: Make the 3 fake photos** (dev Mac; no family content)

Save this as a scratch script (outside the repo), then run it with the repo root as the argument:

```python
# make_fake_photos.py: writes 3 gradient JPEGs to <repo>/fixtures/photos/ using only the stdlib and macOS sips.
import pathlib, struct, subprocess, sys, tempfile

def bmp(path, w, h, top, bottom):
    row = (w * 3 + 3) & ~3
    data = bytearray()
    for y in range(h):  # BMP rows go bottom-up
        t = y / (h - 1)
        px = bytes(int(bottom[i] * (1 - t) + top[i] * t) for i in (2, 1, 0))
        data += px * w + b"\0" * (row - w * 3)
    head = struct.pack("<2sIHHI", b"BM", 54 + len(data), 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(data), 2835, 2835, 0, 0)
    path.write_bytes(head + info + data)

out = pathlib.Path(sys.argv[1]) / "fixtures" / "photos"
out.mkdir(parents=True, exist_ok=True)
for name, w, h, top, bottom in [("landscape", 1500, 1000, (242, 194, 48), (224, 69, 123)),
                                ("portrait", 800, 1200, (58, 125, 85), (30, 60, 140)),
                                ("square", 1000, 1000, (120, 80, 200), (240, 240, 230))]:
    with tempfile.TemporaryDirectory() as tmp:
        src = pathlib.Path(tmp) / f"{name}.bmp"
        bmp(src, w, h, top, bottom)
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "70", str(src),
                        "--out", str(out / f"{name}.jpg")], check=True, capture_output=True)
```

Run: `python3 -I <scratch>/make_fake_photos.py "$PWD" && ls -la fixtures/photos`
Expected: 3 `.jpg` files, each under 100 KB.

- [ ] **Step 7: Check fake mode serves them**

Run: `scripts/dev.sh` in the background, then `curl -s localhost:8081/api/photos` and
`curl -sI localhost:8081/photos/portrait.jpg`.
Expected: 3 photos listed; `200` with `content-type: image/jpeg`. Stop the dev server.

- [ ] **Step 8: Commit**

```bash
git add app/api.py tests/test_api.py docker-compose.yml fixtures/photos
git commit -m "Photos: serve the slideshow folder at /api/photos and /photos, mount it read-only"
```

---

### Task 3: Slideshow on the kitchen wall (`slideshow.js`)

**Files:**
- Create: `app/static/js/slideshow.js`
- Modify: `app/static/js/kitchen.js` (import; `startKitchen`)
- Modify: `app/static/css/kitchen.css` (append slideshow styles; `.dash` transition)

**Interfaces:**
- Consumes: `GET /api/photos` (Task 2); `request`, `state` from `api.js`; `clockText`, `dateText`, `chipStyle`, `esc` from `ui.js`;
  `state.week.next[0]` (`title`, `relative_label`, `color`, `ink`).
- Produces: `initSlideshow(stage: HTMLElement, { blocked: () => boolean }): void`.

- [ ] **Step 1: Write `app/static/js/slideshow.js`**

```javascript
// Idle photo slideshow on the kitchen wall (designs 7a and 7c). Starts after 5 idle minutes in the daytime;
// any tap wakes the dashboard and is never passed on to it.
import { request, state } from "./api.js";
import { chipStyle, clockText, dateText, esc } from "./ui.js";

const SHOW_MS = 20_000;
const FADE_MS = 800;
const WAKE_MS = 400;
const LIST_MS = 10 * 60_000;
const RETRY_MS = 30_000;
// ?idle=<seconds> shortens the idle time, for testing.
const IDLE_MS = Number(new URLSearchParams(location.search).get("idle")) * 1000 || 5 * 60_000;

let stage, el, layers, blocked;
let photos = [], active = false, queue = [], last = null;
let running = false, run = 0, misses = 0, idleTimer = null, showTimer = null;

export function initSlideshow(stageEl, opts) {
  stage = stageEl;
  blocked = opts.blocked;
  el = document.createElement("div");
  el.className = "slides";
  el.innerHTML = `<div class="layer"></div><div class="layer"></div><div class="shade"></div>` +
    `<div class="wake-hint">TOUCH TO WAKE</div>` +
    `<div class="info"><div><div class="s-clock"></div><div class="s-date"></div></div><div class="s-next"></div></div>` +
    `<div class="progress"><i></i></div>`;
  stage.append(el);
  layers = [...el.querySelectorAll(".layer")];
  el.addEventListener("click", (e) => { e.stopPropagation(); stop(); });  // the waking tap stops here
  stage.addEventListener("pointerdown", resetIdle, true);  // capture: every touch counts, even on sheets
  loadList();
  setInterval(loadList, LIST_MS);
  setInterval(tick, 1000);
  resetIdle();
}

async function loadList() {
  try {
    const r = await request("GET", "/api/photos");
    photos = r.photos;
    active = r.active;
  } catch {
    return;  // keep the last list; try again at the next fetch
  }
  if (running && !active) stop();
}

function resetIdle() {
  if (running) return;
  clearTimeout(idleTimer);
  idleTimer = setTimeout(function tryStart() {
    start();
    if (!running) idleTimer = setTimeout(tryStart, RETRY_MS);  // a sheet is open, night, or no photos yet
  }, IDLE_MS);
}

function start() {
  if (running || !active || !photos.length || blocked()) return;
  running = true;
  run += 1;
  misses = 0;
  el.classList.remove("leaving");
  el.classList.add("on");
  stage.classList.add("photos");
  tick();
  showNext(run);
}

function stop() {
  if (!running) return;
  running = false;
  run += 1;
  clearTimeout(showTimer);
  stage.classList.remove("photos");  // the dashboard fades back up
  el.classList.add("leaving");       // the photo dims and slides down
  setTimeout(() => {
    if (running) return;
    el.classList.remove("on", "leaving");
    for (const l of layers) { l.classList.remove("shown"); l.replaceChildren(); }
  }, WAKE_MS);
  resetIdle();
}

function shuffle(list) {
  for (let i = list.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [list[i], list[j]] = [list[j], list[i]];
  }
  return list;
}

function pick() {
  if (!queue.length) {
    // A new round: every photo once, in a new random order, never the last one twice in a row.
    queue = shuffle(photos.slice());
    const n = queue.length;
    if (n > 1 && queue[n - 1].name === last) [queue[0], queue[n - 1]] = [queue[n - 1], queue[0]];
  }
  const p = queue.pop();
  last = p.name;
  return p;
}

async function showNext(id) {
  if (id !== run) return;
  const p = pick();
  const img = new Image();
  img.src = `/photos/${encodeURIComponent(p.name)}?v=${p.v}`;
  try {
    await img.decode();
  } catch {
    // Skip a photo that fails to load; if every photo fails, wait one turn before trying again.
    if (++misses < photos.length) return showNext(id);
    misses = 0;
    showTimer = setTimeout(() => showNext(id), SHOW_MS);
    return;
  }
  if (id !== run) return;
  misses = 0;
  paint(img);
  showTimer = setTimeout(() => showNext(id), SHOW_MS);
}

function paint(img) {
  const tall = img.naturalHeight > img.naturalWidth;
  const next = layers.find((l) => !l.classList.contains("shown")) ?? layers[0];
  const prev = layers.find((l) => l !== next);
  next.replaceChildren();
  if (tall) {
    const blur = img.cloneNode();
    blur.className = "blur";
    next.append(blur);
  }
  img.className = tall ? "fit" : "fill";
  next.append(img);
  next.style.zIndex = "2";
  prev.style.zIndex = "1";
  next.classList.add("shown");
  setTimeout(() => prev.classList.remove("shown"), FADE_MS);  // the old photo leaves once covered
  const bar = el.querySelector(".progress i");
  bar.style.animation = "none";
  void bar.offsetWidth;  // restart the 20 s progress animation
  bar.style.animation = "";
}

function tick() {
  if (!running) return;
  if (blocked()) return stop();  // night mode started
  const now = new Date();
  el.querySelector(".s-clock").textContent = clockText(now);
  el.querySelector(".s-date").textContent = dateText(now);
  const ev = state.week?.next?.[0];
  const html = ev ? `<div class="lbl">NEXT UP</div><div class="pill"><span class="chip" ${chipStyle(ev)}>` +
    `${esc(ev.relative_label)}</span><span class="title">${esc(ev.title)}</span></div>` : "";
  const box = el.querySelector(".s-next");
  if (box._html !== html) { box._html = html; box.innerHTML = html; }
}
```

- [ ] **Step 2: Wire it into `app/static/js/kitchen.js`**

Add the import after the `talk-wall.js` import:

```javascript
import { initSlideshow } from "./slideshow.js";
```

In `startKitchen`, right after the line `initTalkWall(stage, dash);`, add:

```javascript
  initSlideshow(stage, { blocked: () => !sheetEl.hidden || talkOpen() || nightEl.classList.contains("on") });
```

- [ ] **Step 3: Add the styles to `app/static/css/kitchen.css`**

Change the `.dash` transition line to:

```css
  transition: opacity .4s ease-out, filter .25s; }
```

Append at the end of the file:

```css
/* Idle slideshow (7a) and wake (7c) */
.stage.photos .dash { opacity: 0; }
.slides { position: absolute; inset: 0; background: #0f0e12; opacity: 0; pointer-events: none;
  transition: opacity .8s, transform .4s ease-out; }
.slides.on { opacity: 1; pointer-events: auto; }
.slides.leaving { opacity: 0; transform: translateY(120px); transition: opacity .4s ease-out, transform .4s ease-out; }
.slides .layer { position: absolute; inset: 0; opacity: 0; transition: opacity .8s; overflow: hidden; }
.slides .layer.shown { opacity: 1; }
.slides .layer img { position: absolute; inset: 0; width: 100%; height: 100%; }
.slides .layer img.fill { object-fit: cover; }
.slides .layer img.fit { object-fit: contain; }
.slides .layer img.blur { object-fit: cover; filter: blur(60px) brightness(.6); transform: scale(1.15); }
.slides .shade { position: absolute; inset: 0; z-index: 3;
  background: linear-gradient(to top, rgba(15,14,18,.75), transparent 45%); }
.slides .wake-hint { position: absolute; top: 72px; right: 80px; z-index: 4; font: 600 32px var(--mono);
  letter-spacing: .12em; color: rgba(255,255,255,.75); }
.slides .info { position: absolute; left: 80px; right: 80px; bottom: 84px; z-index: 4; display: flex;
  justify-content: space-between; align-items: flex-end; color: #fff; }
.slides .s-clock { font: 600 240px/1 var(--sans); letter-spacing: -.04em; font-variant-numeric: tabular-nums;
  text-shadow: 0 4px 30px rgba(0,0,0,.3); }
.slides .s-date { font: 40px var(--mono); letter-spacing: .08em; opacity: .85; margin-top: 12px; }
.slides .s-next { display: flex; flex-direction: column; align-items: flex-end; gap: 20px; max-width: 1300px; }
.slides .s-next .lbl { font: 600 32px var(--mono); letter-spacing: .12em; opacity: .7; }
.slides .s-next .pill { display: flex; align-items: center; gap: 28px; padding: 20px 40px 20px 20px; border-radius: 999px;
  background: rgba(255,255,255,.14); backdrop-filter: blur(20px); }
.slides .s-next .chip { border-radius: 999px; padding: 10px 24px; font: 600 32px var(--mono); white-space: nowrap; }
.slides .s-next .title { font: 600 48px var(--sans); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.slides .progress { position: absolute; left: 0; right: 0; bottom: 0; height: 12px; z-index: 4;
  background: rgba(255,255,255,.15); }
.slides .progress i { display: block; height: 100%; background: rgba(255,255,255,.7); transform-origin: 0 50%;
  animation: slide-progress 20s linear forwards; }
@keyframes slide-progress { from { transform: scaleX(0); } to { transform: scaleX(1); } }
```

- [ ] **Step 4: Run the test suite** (no JS tests exist; this guards the server)

Run: `.venv/bin/pytest -q && .venv/bin/ruff check .`
Expected: all pass.

- [ ] **Step 5: Check it in the browser** (ego-browser skill; run `ego-browser skill` first)

Start `scripts/dev.sh`. Open `http://localhost:8081/?idle=5` in a window at least 1500×1000 (stage scales).
Note: fake mode only shows photos between 7 AM and 9 PM Chicago time on the dev Mac's clock.
Check, with a screenshot for each:
1. After 5 s with no tap, the slideshow fades in: photo, clock, date, NEXT UP pill, `TOUCH TO WAKE`, progress bar.
2. After 20 s the photo crossfades to another one. `portrait.jpg` shows whole, with a blurred fill on both sides.
3. Tap the middle of the screen where a TODO row sits underneath. The dashboard comes back and the TODO did **not** toggle.
4. Open an event sheet and wait 10 s: no slideshow starts.
5. Narrow the window below 900 px and reload: the phone layout never shows the slideshow.
Stop the dev server.

- [ ] **Step 6: Commit**

```bash
git add app/static/js/slideshow.js app/static/js/kitchen.js app/static/css/kitchen.css
git commit -m "Kitchen: idle photo slideshow with crossfade, portrait fit and tap-to-wake"
```

---

### Task 4: Hourly photo sync on home-ai, docs

**Files:**
- Create: `ops/photo-sync.sh`, `ops/com.household.kitchen-photo-sync.plist`, `ops/install-photo-sync.sh`
- Modify: `CLAUDE.md` (replace "Coming next" with a "Photo slideshow (Part 3)" section)

**Interfaces:**
- Produces: `~/household-ai/data/photos/kitchen/*.jpg` named `<uuid>.jpg` (matches the Task 1 name rule), max side 3000 px.

- [ ] **Step 1: Write `ops/photo-sync.sh`**

```sh
#!/bin/sh
# Hourly (launchd): copy the shared album into the folder the kitchen-dashboard container reads as /photos.
# If anything fails, the old photos stay and the wall keeps working.
set -eu
ALBUM="Kitchen Tablet Slideshow"
BASE="$HOME/household-ai/data/photos"
EXPORT="$BASE/.export"
OUT="$BASE/kitchen"
LOG="$HOME/household-ai/logs/kitchen-photo-sync.log"
LOCK="$HOME/.kitchen-photo-sync.lock"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }
mkdir -p "$EXPORT" "$OUT" "$(dirname "$LOG")"
find "$LOCK" -maxdepth 0 -mmin +120 -exec rmdir {} \; 2>/dev/null || true  # a lock left by a killed run
mkdir "$LOCK" 2>/dev/null || exit 0
trap 'rmdir "$LOCK"' EXIT

# Photos still downloading from iCloud are skipped and picked up by a later run.
if ! osxphotos export "$EXPORT" --album "$ALBUM" --only-photos --skip-live --convert-to-jpeg --jpeg-ext jpg \
    --filename "{uuid}" --update --cleanup >/dev/null 2>"$BASE/.last-error"; then
  log "FAILED: osxphotos export: $(tail -1 "$BASE/.last-error")"
  exit 1
fi

added=0 updated=0 removed=0
for src in "$EXPORT"/*.jpg; do
  [ -e "$src" ] || continue
  dst="$OUT/$(basename "$src")"
  if [ -e "$dst" ] && [ ! "$src" -nt "$dst" ]; then continue; fi
  # Resize into a hidden temp name (the server ignores it), then rename: the wall never sees half a file.
  if ! sips -Z 3000 -s format jpeg "$src" --out "$OUT/.tmp.jpg" >/dev/null 2>&1; then
    log "skipped $(basename "$src"): sips failed"
    continue
  fi
  if [ -e "$dst" ]; then updated=$((updated + 1)); else added=$((added + 1)); fi
  mv "$OUT/.tmp.jpg" "$dst"
done
for dst in "$OUT"/*.jpg; do
  [ -e "$dst" ] || continue
  if [ ! -e "$EXPORT/$(basename "$dst")" ]; then rm -f "$dst"; removed=$((removed + 1)); fi
done
log "ok: $(find "$OUT" -name '*.jpg' ! -name '.*' | wc -l | tr -d ' ') photos (added $added, updated $updated, removed $removed)"
```

- [ ] **Step 2: Write `ops/com.household.kitchen-photo-sync.plist`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.household.kitchen-photo-sync</string>
  <key>ProgramArguments</key>
  <array><string>/bin/sh</string><string>/Users/bobg/kitchen-dashboard/ops/photo-sync.sh</string></array>
  <key>StartInterval</key><integer>3600</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>/Users/bobg/household-ai/logs/kitchen-photo-sync.log</string>
  <key>StandardErrorPath</key><string>/Users/bobg/household-ai/logs/kitchen-photo-sync.log</string>
</dict>
</plist>
```

- [ ] **Step 3: Write `ops/install-photo-sync.sh`**

```sh
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
```

- [ ] **Step 4: Check the scripts**

Run: `sh -n ops/photo-sync.sh && sh -n ops/install-photo-sync.sh && plutil -lint ops/com.household.kitchen-photo-sync.plist`
Run: `ssh bobg@home-ai '~/.local/bin/osxphotos export --help' | grep -E -- '--(only-photos|skip-live|convert-to-jpeg|jpeg-ext|cleanup|update)\b'`
Expected: syntax OK, plist OK, all 6 options listed. If one is missing, stop and report it.

- [ ] **Step 5: Update `CLAUDE.md`**

Replace the `## Coming next` section with:

```markdown
## Photo slideshow (Part 3)
- Spec: `docs/superpowers/specs/2026-10-27-kitchen-dashboard-part3-slideshow-design.md`.
- Source: shared album "Kitchen Tablet Slideshow" (name in `ops/photo-sync.sh`). home-ai is signed in to Bob's Apple ID
  with only Photos → Shared Albums on. Never turn on iCloud Photos, Keychain or Messages there.
- Sync: launchd `com.household.kitchen-photo-sync` runs `ops/photo-sync.sh` hourly (osxphotos as a uv tool → `sips -Z 3000`)
  into `~/household-ai/data/photos/kitchen/`, mounted read-only at `/photos`. Log: `~/household-ai/logs/kitchen-photo-sync.log`.
  Install/update: `sh ops/install-photo-sync.sh` on home-ai.
- Server: `app/photos.py` (name rule, hours 7 AM–9 PM), routes `/api/photos` and `/photos/{name}`. Page: `slideshow.js` (kitchen only).
- Test the page fast with `?idle=5` (idle seconds).
```

- [ ] **Step 6: Commit**

```bash
git add ops/photo-sync.sh ops/install-photo-sync.sh ops/com.household.kitchen-photo-sync.plist CLAUDE.md
git commit -m "Ops: hourly photo sync from the shared album on home-ai; docs for Part 3"
```

---

### Task 5: Roll out (after the PR is merged to `main`)

Needs Bob: merging the PR. Everything else runs over SSH as `bobg@home-ai`.

- [ ] **Step 1:** Wait for the watcher to deploy (`curl -s http://home-ai:8081/api/version` shows the merge commit).
- [ ] **Step 2:** Install the sync: `ssh bobg@home-ai 'cd ~/kitchen-dashboard && sh ops/install-photo-sync.sh'`.
- [ ] **Step 3:** After about 1 minute: `ssh bobg@home-ai 'tail -3 ~/household-ai/logs/kitchen-photo-sync.log; ls ~/household-ai/data/photos/kitchen | wc -l'`.
  Expected: an `ok:` line and a count equal to the album's downloaded photos.
  If the log shows a permission error (launchd jobs can lack Photos access that SSH has), stop and ask Bob to add
  `/bin/sh` to System Settings → Privacy & Security → Full Disk Access on home-ai, then re-run Step 2.
- [ ] **Step 4:** Restart the container so it sees the new mount if the folder was created after the deploy:
  `ssh bobg@home-ai 'cd ~/kitchen-dashboard && docker compose up -d'`; then `curl -s http://home-ai:8081/api/photos` lists the photos.
- [ ] **Step 5:** Ask Bob to leave the kiosk alone for 5 minutes in the daytime and send a photo of the wall.
- [ ] **Step 6:** Close beads `kd-lf1`; update the memory file `project-status.md`.
