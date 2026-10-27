# Kitchen Dashboard, Part 3: Idle photo slideshow

Date: 2026-10-27 · Owner: Bob · Status: approved design, awaiting spec review · Beads: kd-lf1

## 1. Context

Parts 1 and 2 are live. Part 3 shows family photos on the kitchen wall when nobody is using it.
Design screens (from `docs/design/README.md`): **7a** idle slideshow, **7c** wake transition.

Main rule unchanged: **family data stays in the house.** Photos come from iCloud to home-ai through the
Photos app, and from there only to the kiosk over the tailnet. No new outside calls.

### What exists today (checked 2026-10-27)

- home-ai is signed in to Bob's Apple ID with **only Photos → Shared Albums** on (iCloud Photos, Keychain,
  Messages, Drive and the rest are off). A separate house Apple ID was tried; Apple refused to create it.
- Shared album **"Kitchen Tablet Slideshow"**: 18 photos (HEIC, JPEG, PNG). Some are still downloading.
- `osxphotos` 0.77.2 is installed on home-ai as a `uv` tool (Python 3.12, `~/.local/bin/osxphotos`).
  Over SSH it reads the Photos library without extra Full Disk Access.
- The page already has night mode (`isNight` in `kitchen.js`: 10 PM to 6 AM) and a "Next up" list from `/api/week`.

## 2. Decisions (Bob, 2026-10-27)

| Topic | Decision |
|---|---|
| Source | One shared Apple Photos album, "Kitchen Tablet Slideshow". Add or remove photos from any family phone. |
| Sync | `osxphotos` every hour by launchd on home-ai. Photos only, no videos. |
| When | Daytime only, **7:00 AM to 9:00 PM** America/Chicago. Never during night mode. |
| Start | After **5 minutes** with no touch, and only when no sheet (Talk, event, day) is open. |
| Timing | New photo every **20 s**, 800 ms crossfade. Random order; each photo once per round. |
| Portrait photos | Shown whole (`contain`), centered, over a blurred, darkened copy of itself that fills the screen. |
| Landscape photos | Fill the screen (`cover`). |
| Wake | Any touch. The touch is consumed and never reaches the dashboard. |
| Phone | No slideshow on phones. |
| Settings UI for hours | Not in Part 3 (design 4c lists it under LATER). Hours are constants in `app/photos.py`. |

## 3. Architecture

```
Family phones ──► iCloud shared album ──► Photos.app on home-ai (Shared Albums only)
                                                │  hourly launchd job: ops/photo-sync.sh
                                                ▼
            ~/household-ai/data/photos/.export/   (osxphotos export --update --cleanup, JPEG)
                                                │  sips -Z 3000, only new/changed files
                                                ▼
            ~/household-ai/data/photos/kitchen/   ──(read-only mount /photos)──► kitchen-dashboard
                                                                                   │ GET /api/photos
                                                                                   │ GET /photos/<name>
                                                                                   ▼
                                                                         Kiosk page (slideshow.js)
```

## 4. Photo sync (home-ai)

New files in `ops/`:

- `photo-sync.sh`:
  1. Takes a lock (`~/.kitchen-photo-sync.lock`); exits quietly if another run holds it.
  2. Runs
     `osxphotos export ~/household-ai/data/photos/.export --album "Kitchen Tablet Slideshow" --only-photos --skip-live --convert-to-jpeg --jpeg-ext jpg --filename "{uuid}" --update --cleanup`.
     Photos not downloaded yet are skipped by osxphotos and picked up on a later run.
  3. For each `.export/*.jpg` newer than its copy in `kitchen/` (or with no copy): `sips -Z 3000` into a temp file
     in `kitchen/`, then rename into place (the server never sees half a file).
  4. Deletes any `kitchen/*.jpg` with no matching file in `.export/` (photo removed from the album).
  5. Logs one line per run to `~/household-ai/logs/kitchen-photo-sync.log`: counts of added, updated, removed.
  6. On failure, leaves `kitchen/` as it is and exits non-zero. No alert (the wall keeps the old photos).
- `com.household.kitchen-photo-sync.plist`: launchd agent, `StartInterval` 3600, `RunAtLoad` true.
- `install-photo-sync.sh`: creates the folders, copies the plist into `~/Library/LaunchAgents/`, loads it,
  runs one sync. Safe to run again.

The album name lives in one place: `ALBUM` at the top of `photo-sync.sh`.

## 5. Server

`docker-compose.yml` adds a read-only mount:
`${HOME}/household-ai/data/photos/kitchen:/photos:ro`, and env `PHOTOS_DIR=/photos`.

New module `app/photos.py` (pure, testable):

- `list_photos(dir) -> list[dict]`: every `*.jpg` directly in `dir` whose name matches `^[A-Za-z0-9-]{1,80}\.jpg$`,
  as `{"name": ..., "v": <int mtime>}`, sorted by name. Missing or unreadable dir → `[]`.
- `slideshow_hours(now) -> bool`: true when `7 <= now.hour < 21` in America/Chicago (`START_HOUR = 7`, `END_HOUR = 21`).

Routes in `app/api.py`:

- `GET /api/photos` → `{"photos": [...], "active": bool}`. `active` is `slideshow_hours(now)`.
- `GET /photos/{name}` → the file, `Content-Type: image/jpeg`, `Cache-Control: public, max-age=31536000, immutable`.
  The page always asks with `?v=<mtime>`, so a changed photo gets a new URL.
  Any name that fails the regex, or a file that does not exist → 404. Never follow paths outside `PHOTOS_DIR`.
- No `PHOTOS_DIR` set → both act as an empty folder.

Fake mode (`DASHBOARD_FAKE=1`): `PHOTOS_DIR` defaults to `fixtures/photos/` with 3 small sample JPEGs
(one landscape, one portrait, one square), generated with no family content.

## 6. Page (kitchen only)

New module `app/static/js/slideshow.js`, used by `kitchen.js`. `phone.js` does not load it.

- **Photo list:** fetch `/api/photos` at start and every 10 minutes.
- **Idle timer:** any `pointerdown` on the stage resets it. After 5 minutes the slideshow starts if
  `active` is true, the list is not empty, no sheet is open, and night mode is off.
- **Show:** two stacked layers for the crossfade. The next image is loaded (`img.decode()`) before it fades in;
  if it fails to load, it is skipped. Each 20 s a new photo fades in over 800 ms.
- **Fit:** after load, if `naturalHeight > naturalWidth` the layer uses `contain` plus a blurred background copy
  (`filter: blur(60px) brightness(.6)`, scaled to hide blur edges); otherwise `cover`.
- **Order:** shuffle the list; play it through; reshuffle (never the same photo twice in a row across rounds).
  A refreshed list takes effect at the next round.
- **Overlay (7a):** bottom gradient; bottom-left clock 600/240 + date mono 40; bottom-right `NEXT UP` + frosted
  pill with the first item of the existing next-up data; top-right `TOUCH TO WAKE`; 12 px progress bar for
  time to the next photo. Clock and next-up reuse the page's existing data and formatters; no new server calls.
- **Wake (7c):** the full-screen slideshow layer catches the tap (`click`, stop propagation, the same way night
  mode does), so nothing under it is pressed. Photo dims and slides down while the dashboard fades up, 400 ms ease-out.
  The idle timer restarts.
- **Stop by itself:** when `active` turns false (9 PM; seen at the next 10-minute list fetch) or night mode starts, the slideshow ends with the same
  wake animation.
- **Kiosk reload on new version** works as today; the slideshow simply starts again after 5 idle minutes.

Sizes follow the Part 1 rules: nothing under 30 px on the 3000×2000 stage.

## 7. Errors

| Case | What happens |
|---|---|
| Sync fails or home-ai Photos is signed out | Old photos stay; slideshow keeps working. Log line in `kitchen-photo-sync.log`. |
| Album empty or folder missing | `photos: []`; slideshow never starts; wall unchanged. |
| One photo fails to load | Skipped; next photo shows. |
| `/api/photos` fails | Page keeps the last list; tries again in 10 minutes. |

## 8. Testing

- `tests/test_photos.py`: `list_photos` (filters non-JPEG, bad names, subfolders; missing dir → `[]`);
  `slideshow_hours` at 6:59, 7:00, 20:59, 21:00 Chicago, and across DST.
- `tests/test_api.py`: `/api/photos` shape; `/photos/<name>` 200 with cache header; 404 for `../x.jpg`,
  `%2e%2e%2fx.jpg`, `x.png`, and a missing file; empty when `PHOTOS_DIR` is unset.
- Page: check in fake mode at 3000×2000 with a short idle time (`?idle=5` query param: idle seconds, for testing only):
  start, crossfade, portrait fit, wake consumes the touch, no slideshow with a sheet open.
- Sync script: run once on home-ai; confirm `kitchen/` count matches the album's downloaded photos;
  remove one photo from the album and confirm it leaves `kitchen/` after the next run.

## 9. Out of scope

- Videos and Live Photo motion.
- Settings UI for slideshow hours or timing.
- Captions, people names or dates on photos.
- Slideshow on phones.
