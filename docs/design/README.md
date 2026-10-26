# Handoff: Kitchen Family Dashboard

## Overview
A wall-mounted touch screen in a family kitchen (3000×2000, 1× pixel scale) showing the household calendar, each person's TODOs for today, and a large "Talk to the house" button that opens a voice/chat panel to the home AI. A companion phone layout (one column, up to 900px wide) is the only place people type: it adds an "add TODO" form, settings (calendar colors, family members) and the same Talk entry.

Family: Bob, Belen, Ben. Three TODO columns side by side with a dashed slot reserved for a 4th person.

## About the Design Files
`Kitchen Dashboard.dc.html` is a **design reference built in HTML**. It is a canvas of option cards; the kitchen screens are rendered at ⅓ scale inside 1000×667 cards (inner frame 3000×2000, `transform: scale(.3333)`), the phone screens at 1× (430px wide). It is **not production code**. Recreate the chosen screens below in **plain HTML, CSS and JavaScript with no frameworks**, served from the home server. Hard limits from the brief: **no web fonts, no CDNs, no outside images — system fonts only**.

The design file uses a small runtime for preview purposes only; ignore it. Everything you need is in the inline styles of each card.

## Fidelity
**High-fidelity.** Colors, type sizes, spacing, radii and copy are final. Match them.

## Chosen screens (the build list)
Each id is the card badge in the design file (`#2a` etc.).

Kitchen
- **2a** Dashboard (default). Layout from 1b, calendar chips from 1e.
- **2b** Talk panel: Listening. Then **5a** Thinking, **5b** Answer, **5c** Close, **5d** Didn't catch that.
- **8g** Talk panel: Type instead (on-screen keyboard).
- **3a** Event detail sheet. **3c** Delete confirm.
- **8d** Day sheet (from "+2 more"). **8c** Busy-day column.
- **8a** Overdue TODO. **8b** Empty states. **8f** Loading.
- **6a** Night mode (10 PM–6 AM). **8e** Talk panel at night.
- **7a** Idle slideshow. **7c** Wake transition.

Phone
- **4a** Home, **4b** Add TODO, **4c** Settings, **4d** Talk thread, **8h** Event detail sheet, **8i** TODO edit.

Not chosen (reference only): 1a, 1c, 1d, 1f, 1h–1l, 3b, 6b. Bills-due is out of scope.

## Design tokens

Fonts (system only)
- Sans: `system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif`
- Mono (labels, times, status, dates): `ui-monospace, Menlo, Consolas, "Liberation Mono", monospace`

Colors
- Background `#faf9f7` · Surface `#fff` · Surface-2 `#f4f2f7` · Divider `#f0eef4` / `#e6e3ee` · Dashed slot `#d9d5e3`
- Ink `#1c1b1f` · Muted `#6b6875` · Faint `#9995a3` · Disabled ring `#c9c4d6`
- Accent (UI only) `#6b45d9` · Accent soft `#efe9fb` · Accent on dark `#9d87e6`
- Success `#2fb36a` · Warning `#e9a23b` (text `#b5742a`) · Danger `#d2382f` (tint `#fdf1f0`)
- Night: bg `#0f0e12` · surface `#18171d` / `#1a1920` · line `#2a2832` / `#3a3744` · text `#e8e2d6` / `#d9d3c7` · muted `#8a8494` / `#6f6a7a` · success `#3a7d55`
- Sample calendar colors (user-picked, replaceable): Family `#f2c230`, Bob work `#2b5fd9`, School `#e0457b`, Belen `#14a08a`

Calendar color rule (1e): chips are **filled with the calendar color**; text is `#1c1b1f` when relative luminance > 0.55, else `#fff`. Mono time inside a chip sits at opacity .85 on dark fills, .7 on light fills. This must work for any color the user picks in settings.

Kitchen type scale (px): clock 260 (6a: 420) · section number 64 · person name 52 · sheet title 96 · body/TODO 38–44 · chip 34 · mono labels 30–36 · status 32. Nothing on the wall below 30px.
Phone type scale: clock 64 · title 28 · body 17 · chip 13 · mono labels 11–13.

Radii: cards 48 · day chips 28 · sheets 80 · pills 999. Phone: cards 24, chips 20, sheet 32.
Shadows: Talk button `0 20px 60px rgba(107,69,217,.3)`; sheets `0 60px 160px rgba(0,0,0,.35)`; toast `0 30px 80px rgba(0,0,0,.3)`.
Tap targets: every kitchen target ≥ 100px (TODO rows 100, Talk 220, sheet buttons 200, keyboard keys 120). Phone ≥ 48px.

## Screens

### 2a · Kitchen dashboard (3000×2000)
Padding 72px top/bottom, 80px sides. Grid: 2 columns `820px 1fr`, gap 72.

Left rail (820px, flex column, gap 48)
- Clock `4:12` 600/260px, letter-spacing −.04em. Below, date `MON 26 OCT` mono 40px muted, letter-spacing .06em, margin-top 12.
- `NEXT UP` mono 32 muted, letter-spacing .1em. Then up to 4 cards (white, radius 40, padding 28×36, min-height 120, gap 18): title 600/44 sans; below it a filled calendar chip (pill, padding 10×24, mono 600/32) with the relative time: `Today, 5:30 PM`, `Tomorrow, 9:00 AM`, `Wed, 4:00 PM`.
- Talk to the house: pill 220px high, full width, bg accent, white text 600/56, mic icon in a 100px translucent white circle (`rgba(255,255,255,.2)`), gap 36, shadow above.
- Status line: mono 32 muted with an 18px dot: green `up to date`; amber dot + `last updated 14 min ago` (text `#b5742a`) when data is older than ~5 min.

Right column: grid rows `760px 1fr`, gap 64.
- Week strip: 7 columns, gap 20, rolling 7 days from today. Column header centered: weekday mono 600/30 letter-spacing .08em, number 600/64. Today's header is a filled accent pill (padding 18×0, white text). Events: filled chips radius 28, padding 22×26, sans 600/34; first line mono 30 time (`5:30 PM`, `all day`). Max 3 chips, then a `+2 more` pill (100px, 5px ink outline) with calendar dots → opens 8d. Empty day: dashed `#e6e3ee` 4px box with mono `free` in `#c9c4d6`.
- TODO row: grid `repeat(3,1fr) 120px`, gap 28. Each person card white radius 48 padding 32: header row (100px round photo slot, name 600/52, right-aligned mono 30 count `3 left`), then rows min-height 100 gap 14. Row: 60px circle (open: 5px `#c9c4d6` ring; done: filled accent with white check) + text 38px + optional mono 30 time. Done text `#9995a3` with line-through; its time `#c9c4d6`. 4th slot: 5px dashed `#d9d5e3`, radius 48, centered `+` in `#c9c4d6`.
- All done: the whole person card turns success green `#2fb36a`, white text; count `3 of 3`; centered 150px white circle with green check and `All done!` 600/56; 5–7 static confetti rects (20×36, radius 6, rotated) in yellow/white/pink.

### TODO interactions
- Tap row → toggles done. 150ms: ring fills accent, check scales in; text fades to faint + strikethrough; count updates. Tap again un-does.
- When the last open item is checked, the card transitions to the All-done state (300ms bg fade, confetti fades in).
- Overdue (8a): a timed item whose time has passed moves to the top of its list, row gets `#fdf1f0` tint (radius 24, bleed 20px into padding), ring and time turn `#d2382f` 600; header count reads `1 overdue · 3 left`.
- Empty (8b): `Nothing today` 600/44 faint, under it mono 30 `say "add a todo for Ben" / or use your phone` in `#c9c4d6`.

### Talk to the house (sheet over dimmed dashboard)
Dashboard behind: opacity .35, blur 6px, plus overlay `rgba(28,27,31,.45)`. Sheet 2200×1480 centered (left 400, top 260), white, radius 80, padding 80×96, shadow. Opens in 250ms (scale .96→1, fade); mic starts listening immediately.

- **Listening (2b):** header mono 600/36 accent `● LISTENING` letter-spacing .12em. Center: waveform of 16 bars (44px wide, gap 28, max 400 tall, accent, each `scaleY` animating .25↔1 at 1–1.6s staggered 70ms) driven by mic level; below, live transcript 500/72 sans, in quotes, unconfirmed tail in `#9995a3`. Bottom row gap 32: `Stop` pill (flex 1, 200 high, ink bg, white 600/56, 44px white square icon) and `Type instead` (560 wide, 6px `#e6e3ee` outline, muted 600/48). Stop = cancel listening and close.
- **Thinking (5a):** header `THINKING` muted. Transcript 500/56 muted centered. Three 64px accent dots bouncing (1.4s, staggered 200ms). Full-width `Cancel` (6px ink outline).
- **Answer (5b):** header `ANSWER` left, the user's utterance right-aligned 40px muted. Reply 500/72. A change card (bg `#f4f2f7`, radius 48, padding 32×40): the filled calendar chip for the new item (`THU 29 · 4:00 PM / Dentist · Ben`), mono 36 `Family calendar`, and a green `ADDED` pill (mono 600/32). Buttons: `Undo` (520 wide outline), `Ask more` (flex 1, accent-soft bg, accent text, mic icon; restarts listening), `Done` (flex 1, ink).
- **Close (5c):** sheet dismisses (200ms). The new chip appears in its day column with an 8px `#2fb36a` outline (offset 6) for 3s. Bottom-center toast (ink pill, padding 36×48, 56px green check circle, 500/44 text `Added Dentist for Ben, Thu 4:00 PM`, `UNDO` mono outline) for 6s.
- **Didn't catch that (5d):** header `DIDN'T CATCH THAT`. Question 500/72, explanation 44 muted, tappable option pills (160 high, `#f4f2f7`, 600/48). Buttons: `Say it again` (accent, mic icon) and `Never mind` (outline).
- **Type instead (8g):** sheet grows to 2400×1700 (left 300, top 160). Header `TYPE TO THE HOUSE`, right link `Use voice instead` accent 600/40. Input box 6px accent border radius 40, 56px text, caret. Suggestion pills (`Add a todo for…`, `Add an event…`, `What's on this weekend?`). QWERTY keyboard: keys 120 high radius 24 bg `#f4f2f7` 600/48, modifier keys `#e6e3ee` mono 36, bottom row 140 high, `Send` ink pill. Send → Thinking.
- **Night (8e):** sheet bg `#1a1920`, 3px `#2a2832` border, header in `#9d87e6`, content at opacity .8, Stop pill `#e8e2d6` with `#0f0e12` text.

Voice panel also auto-closes 20s after Answer with no touch.

### Event detail (3a) and delete (3c)
Tap any chip. Sheet 1700×1240 (left 650, top 380), radius 80, overflow hidden. Header band filled with the calendar color (text color by the luminance rule), padding 72×96: calendar name mono 600/32 letter-spacing .12em at .7 opacity, title 600/96. Close: 120px circle `rgba(0,0,0,.12)` with an X. Body padding 64×96, grid `260px 1fr`, labels mono 600/30 muted (`WHEN`, `WHERE`, `WHO`, `NOTE`), values 44px; WHO shows person pills (`#f4f2f7`, 56px photo slot). Footer: `Change by voice` (flex 1, 180 high, accent-soft, accent text, mic) and `Delete` (460 wide, outline). Delete → 3c: header dims to .5, body shows `Remove this from the Family calendar?` 600/72 + `Everyone's phone will update too.` 40 muted; buttons `Keep it` (outline) and `Yes, remove` (`#d2382f`, white).

### Day sheet (8d)
Opened from `+2 more`. Sheet 1700×1480 (left 650, top 260). Header: weekday mono 36 muted, date 600/96, X circle. Rows min-height 140 with 3px dividers: time mono 600/36 muted (220 wide) + full-width filled chip (pill, padding 20×36, 600/44). Tap a row → 3a.

### Loading (8f)
Clock and date render immediately from the device clock. Everything else is a skeleton in `#f0eef4` with the same geometry (cards, 7 columns, 3 person cards). Talk button `#e6e3ee`. Status: amber dot + `connecting to the home server…`. If no response in 30s, status becomes `last updated — offline`, still amber.

### Night mode (6a) · 10 PM – 6 AM
Bg `#0f0e12`. Top-left mono 32 `NIGHT · UNTIL 6:00 AM` in `#6f6a7a`; top-right status (green dot `#3a7d55`). Centered clock 600/420 in `#e8e2d6`, date mono 44 `#8a8494`. Bottom-left `TOMORROW` label + first event: 16px color bar at .7 opacity, title 600/56, mono 36 `9:00 AM · Bob work`. Bottom-right `STILL OPEN TODAY` + pills for people with open items (3px `#2a2832` outline, 64px dark photo circle, 40px text `Bob · 2`). Bottom-center mono 32 `TAP ANYWHERE FOR THE FULL DASHBOARD` in `#4a4752`. Any tap shows 2a for 2 minutes, then returns to 6a. Transition at 10 PM: 1s crossfade. Idle slideshow is disabled at night.

### Idle slideshow (7a) and wake (7c)
After 5 min without touch (daytime). Full-bleed family photo (`object-fit: cover`), crossfade every 20s (800ms). Bottom gradient `linear-gradient(to top, rgba(15,14,18,.75), transparent 45%)`. Bottom-left clock 600/240 white with `0 4px 30px rgba(0,0,0,.3)` text shadow, date mono 40 at .85. Bottom-right `NEXT UP` mono 32 at .7 and a frosted pill (`rgba(255,255,255,.14)`, blur 20) holding the filled time chip + title 600/48. Top-right mono 32 `TOUCH TO WAKE` at .75. 12px progress bar across the bottom shows time to next photo. Wake: the touch is consumed (never forwarded to the dashboard); photo dims and slides down while the dashboard fades up, 400ms ease-out.

### Phone
Single column, padding 20, bg `#faf9f7`. Designed at 430; stretches to 900 (max-width 900, centered).
- **4a Home:** clock 600/64 + mono 13 date/status; gear 48px. `NEXT UP` cards (white, radius 20, padding 14×16, title 600/17, filled time chip mono 600/12). `THIS WEEK` list: 7 rows min-height 48, grid `64px 1fr`, day mono 600/13 (today in accent), chips pill padding 6×12 600/13 wrap. `TODAY'S TODOS`: person switcher (3 pills 52 high; selected ink/white; counts mono 12; all-done shows green dot + ✓), list card radius 24 rows 56 high with 28px rings. Pinned bottom bar (gradient fade): `Talk to the house` pill 64 high accent with mic, round `+` 64px ink → 4b.
- **4b Add TODO:** title 600/28, `Cancel`. Text field (white, radius 20, 2px accent border, 20px). `WHO` three pills 56 high with 30px photo slots. `WHEN` 7-day strip (68 high, radius 16, selected accent) + `Pick another date` link. `TIME · OPTIONAL`: `Any time` / time pill (mono 17). Primary `Add for Belen · Wed 3:30 PM` 64 high accent. System keyboard below.
- **4c Settings:** `CALENDARS` list rows 60 high: 32px swatch, name 17, hex mono 12. Tapping a row expands presets (9 swatches 40px: yellow, orange, red, pink, violet, blue, teal, green, plus a conic "custom" that opens the native color input), selected swatch gets 3px ink outline offset 3, and a live `Preview: Pizza night` chip showing the auto text color. `FAMILY` rows 64 high: 40px photo, name, `Edit`; `Add a person` row. `LATER` block (greyed) for night mode and slideshow timing.
- **4d Talk thread:** header `● The house`, `Close`. User bubbles ink, radius `22 22 6 22`, 17px. House bubbles white radius `22 22 22 6`. Change card (white, 8px color bar, title 600/16, mono 12 line, green `ADDED` pill) with `Undo` / `Remind Bob` outline chips. Input bar: text field 56 high pill + 56px accent mic button (hold to talk, or tap to toggle).
- **8h Event detail:** bottom sheet radius 32; calendar-colored header; rows 60 high with chevrons (editable: when/where/who/calendar), note; `Ask the house to change it` (accent-soft) and `Delete` (danger text).
- **8i TODO edit:** bottom sheet; text field, `WHO` pills 48 high, `WHEN`/`TIME` dropdown pills, `Delete` + `Save` (accent).

## State
- `now` (ticks every second; drives clock, relative times, overdue, night mode, rolling week)
- `calendars[]` {id, name, color} · `events[]` {id, calendarId, title, start, end?, allDay, location?, people[], note?}
- `people[]` {id, name, photo?} · `todos[]` {id, personId, text, date, time?, done}
- `sync` {lastUpdated, status: ok|stale|offline}
- `ui.mode`: dashboard | night | slideshow · `ui.sheet`: none | talk | event | day · `ui.talk`: listening | thinking | answer | miss | typing · `ui.idleSince`
- Relative time format: `Today, 5:30 PM` · `Tomorrow, 9:00 AM` · else `Wed, 4:00 PM`; all-day events show `Today` / `all day`.
- Data refresh: poll or SSE from the home server; `stale` after 5 min, `offline` after 30 s without a response.

## Assets
No images in the design. Photo slots are striped placeholders (`repeating-linear-gradient(45deg,#e9e6f3 0 12px,#f5f3fa 12px 24px)`) — replace with family photos served locally. Icons are drawn with CSS boxes (mic = capsule + U cradle + stem + base; check = rotated L; X = two bars); keep them CSS or use a local SVG sprite. No icon font, no CDN.

## Files
- `Kitchen Dashboard.dc.html` — all option cards; chosen ones are badged **CHOSEN** or listed above. Turn 8 (top) → turn 1 (bottom).
