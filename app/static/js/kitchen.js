// Kitchen wall screen (design 2a and its states). Authored at 3000x2000; scaled to fit in dev windows.
import { loadToday, loadWeek, onChange, request, startPolling, state, status } from "./api.js";
import { initTalkWall, openTalk, talkOpen } from "./talk-wall.js";
import { initSlideshow } from "./slideshow.js";
import { chicagoParts, chipStyle, clockText, dateText, errorText, esc, icons, splitTime, toast, whoText } from "./ui.js";

let stage, dash, nightEl;
let awakeUntil = 0;
const WAKE_MS = 2 * 60_000;
const SHEET_CLOSE_MS = 60_000;  // a sheet left open must not dim the wall for the rest of the day

function fitStage() {
  const s = Math.min(window.innerWidth / 3000, window.innerHeight / 2000);
  document.documentElement.style.setProperty("--scale", String(s));
}

const MAX_ROW_CHIPS = 2;

// A name tag in the event's colors; on a filled card it swaps them so it stands out.
function whoTag(ev, onFill = false) {
  const [bg, fg] = onFill ? [ev.ink, ev.color] : [ev.color, ev.ink];
  return `<span class="who" style="background:${esc(bg)};color:${esc(fg)}">${esc(whoText(ev))}</span>`;
}

// Readable from across the kitchen: the time and who it's for. The title reads from a few steps closer.
function heroCard(ev) {
  if (!ev) return `<div class="hero-empty">Nothing coming up</div>`;
  const [digits, ampm] = splitTime(ev.time_label);
  return `<button class="hero" data-uid="${esc(ev.uid)}" ${chipStyle(ev)}>` +
    (ev.is_today ? "" : `<div class="hero-day">${esc(ev.day_word)}</div>`) +
    `<div class="hero-row"><span class="hero-time">${esc(digits)}<small>${esc(ampm)}</small></span>${whoTag(ev, true)}</div>` +
    `<div class="hero-title">${esc(ev.title)}</div></button>`;
}

function restRow(ev) {
  const t = ev.all_day ? "all day" : splitTime(ev.time_label)[0];
  return `<button class="rest-row" data-row data-uid="${esc(ev.uid)}"><span class="bar" style="background:${esc(ev.color)}"></span>` +
    `<span class="t">${esc(t)}</span><span class="n">${esc(ev.title)}</span>${ev.who?.length ? whoTag(ev) : ""}</button>`;
}

function restList(week) {
  const today = week.days[0]?.date ?? "";
  return week.today_rest.map(restRow).join("") + `<button class="rest-more" data-day="${esc(today)}" hidden></button>`;
}

function chip(ev) {
  const time = ev.all_day ? "" : `<span class="t">${esc(splitTime(ev.time_label)[0])}</span>`;
  const who = ev.who?.length ? `<span class="w" style="background:${esc(ev.ink)};color:${esc(ev.color)}">${esc(whoText(ev))}</span>` : "";
  return `<button class="ev" data-uid="${esc(ev.uid)}" ${chipStyle(ev)}>${time}<span class="n">${esc(ev.title)}</span>${who}</button>`;
}

function comingRow(d) {
  const extra = d.events.length - MAX_ROW_CHIPS;
  const body = !d.events.length ? `<div class="free">free</div>`
    : d.events.slice(0, MAX_ROW_CHIPS).map(chip).join("") +
      (extra > 0 ? `<button class="more" data-day="${esc(d.date)}">+${extra}</button>` : "");
  return `<div class="c-row"><div class="c-day"><span class="dow">${esc(d.dow)}</span><span class="num">${d.day}</span></div>` +
    `<div class="c-chips">${body}</div></div>`;
}

const CONFETTI = [[80, 180, "#f2c230", 20], [320, 160, "#fff", -35], [520, 220, "#e0457b", 60], [200, 300, "#fff", -10],
  [660, 300, "#f2c230", 45]];

function todoRow(t) {
  const when = t.carried ? "earlier" : t.time_label;
  return `<button class="todo ${t.done ? "done" : ""} ${t.overdue ? "overdue" : ""} ${t.carried ? "carried" : ""}" data-row data-todo="${t.id}">` +
    `<span class="ring">${icons.check(34, 7)}</span><span class="text">${esc(t.text)}</span>` +
    (when ? `<span class="when">${esc(when)}</span>` : "") + `</button>`;
}

function personCard(p) {
  const head = (count) => `<div class="person-head"><div class="name">${esc(p.name)}</div>${count}` +
    `<button class="see-all" data-person="${p.id}" hidden></button></div>`;
  if (p.state === "all_done") {
    return `<div class="person all-done">` +
      CONFETTI.map(([l, t, c, r]) => `<i class="confetti" style="left:${l}px;top:${t}px;background:${c};` +
        `transform:rotate(${r}deg)"></i>`).join("") +
      head(`<div class="count">${p.todos.length} of ${p.todos.length}</div>`) +
      `<div class="all-done-body"><div class="badge">${icons.check(66, 13, "var(--ink)")}</div>` +
      `<div class="word">All done!</div></div></div>`;
  }
  if (p.state === "empty") {
    return `<div class="person">${head("")}<div class="person-empty"><div class="big">Nothing today</div>` +
      `<div class="hint">say <span class="q">“add a todo for ${esc(p.name)}”</span><br>or use your phone</div></div></div>`;
  }
  return `<div class="person">${head(`<div class="count">${p.left} left</div>`)}<div class="list">${p.todos.map(todoRow).join("")}</div></div>`;
}

// Hides rows from the end until the list fits, and says how many are hidden. Nothing is ever silently cut off.
function fit(list, more, label) {
  if (!list || !more) return;
  const rows = [...list.querySelectorAll("[data-row]")];
  rows.forEach((r) => { r.hidden = false; });
  more.hidden = true;
  let hidden = 0;
  while (list.scrollHeight > list.clientHeight + 1 && hidden < rows.length) {
    hidden += 1;
    rows[rows.length - hidden].hidden = true;
    more.hidden = false;
    more.textContent = label(hidden);
  }
}

const fitPerson = (el) => fit(el.querySelector(".list"), el.querySelector(".see-all"), (n) => `+${n} more`);

function skeleton() {
  return {
    hero: `<div class="skel" style="height:460px;border-radius:56px"></div>`,
    rest: [1, 2].map(() => `<div class="skel" style="height:104px"></div>`).join(""),
    coming: Array.from({ length: 6 }, () => `<div class="c-row"><div class="c-day"></div><div class="skel"></div></div>`).join(""),
    people: [1, 2, 3].map(() => `<div class="skel" style="border-radius:48px"></div>`).join(""),
  };
}

// The dash is built once; each section is replaced only when its markup changed, so a poll with no change
// touches nothing (the All-done fade and confetti must play once, not every 10 s). Clock, date and status
// are updated by tickClock() and take no part in the comparison.
let slots = null;
const personEls = new Map();  // person id -> { el, html }

function buildShell() {
  dash.innerHTML =
    `<div class="today-panel"><div class="top-row"><div class="clock" id="clock"></div>` +
    `<div class="clock-side"><div class="date" id="date"></div><div class="status" id="status"></div></div></div>` +
    `<div id="hero"></div><div class="rest" id="rest"></div></div>` +
    `<div class="coming" id="coming"></div>` +
    `<div class="todo-band"><div class="people" id="people"></div><button class="talk" id="talk" data-talk></button></div>`;
  slots = { hero: dash.querySelector("#hero"), rest: dash.querySelector("#rest"), coming: dash.querySelector("#coming"),
    talk: dash.querySelector("#talk"), people: dash.querySelector("#people") };
  personEls.clear();
}

function setHtml(el, html) {
  if (el._html === html) return false;
  el._html = html;
  el.innerHTML = html;
  return true;
}

function renderPeople(loading, people, skHtml) {
  const box = slots.people;
  if (loading) {
    personEls.clear();
    setHtml(box, skHtml);
    return;
  }
  if (box._html !== undefined) { box._html = undefined; box.innerHTML = ""; }  // leaving the skeleton
  const keep = new Set();
  let prev = null;
  for (const p of people) {
    const html = personCard(p);
    let rec = personEls.get(p.id);
    if (!rec || rec.html !== html) {
      const tpl = document.createElement("template");
      tpl.innerHTML = html;
      const el = tpl.content.firstElementChild;
      if (rec) rec.el.replaceWith(el); else box.append(el);
      fitPerson(el);
      rec = { el, html };
      personEls.set(p.id, rec);
    }
    keep.add(p.id);
    const want = prev ? prev.nextElementSibling : box.firstElementChild;
    if (want !== rec.el) box.insertBefore(rec.el, want);
    prev = rec.el;
  }
  for (const [id, rec] of personEls) if (!keep.has(id)) { rec.el.remove(); personEls.delete(id); }
}

function updateStatus() {
  const st = status();
  const s = document.getElementById("status");
  // Quiet when all is well; only a problem earns space on the wall.
  s.className = `status ${st.tone === "amber" ? "amber" : ""}`;
  s.innerHTML = st.tone === "amber" ? `<span class="dot"></span>${esc(st.text)}` : "";
}

function render() {
  const loading = !state.week || !state.today;
  const sk = loading ? skeleton() : null;
  dash.className = `dash ${loading ? "loading" : ""} ${(sheetEl && !sheetEl.hidden) || talkOpen() ? "dimmed" : ""}`;
  if (!slots) { buildShell(); tickClock(); }
  setHtml(slots.hero, loading ? sk.hero : heroCard(state.week.hero));
  if (setHtml(slots.rest, loading ? sk.rest : restList(state.week)) && !loading) {
    fit(slots.rest, slots.rest.querySelector(".rest-more"), (n) => `+${n} more today`);
  }
  slots.talk.className = `talk ${loading ? "skel" : ""}`;
  setHtml(slots.talk, loading ? "" : `<span class="mic">${icons.mic(84)}</span>Talk to the house`);
  setHtml(slots.coming, loading ? sk.coming : state.week.days.slice(1).map(comingRow).join(""));
  renderPeople(loading, loading ? [] : state.today.people.slice(0, 3), loading ? sk.people : "");
  updateStatus();
}

function tickClock() {
  const now = new Date();
  document.getElementById("clock").textContent = clockText(now);
  document.getElementById("date").textContent = dateText(now);
  updateStatus();
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

let sheetEl, sheetTimer;

function armSheetClose() {
  clearTimeout(sheetTimer);
  sheetTimer = setTimeout(closeSheet, SHEET_CLOSE_MS);
}

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
  armSheetClose();
}

export function closeSheet() {
  clearTimeout(sheetTimer);
  sheetEl.hidden = true;
  sheetEl.innerHTML = "";
  dash.classList.remove("dimmed");
}

function eventSheet(ev, mode = "view", error = "") {
  const who = ev.who ?? [];
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
    (who.length ? `<div class="k">WHO</div><div>${who.map((n) => `<span class="who-pill">${esc(n)}</span>`).join(" ")}</div>` : "");
  const actions = ev.can_delete
    ? `<button class="btn soft flex" data-voice="${esc(ev.uid)}">${icons.mic(40, "currentColor")}Change by voice</button>` +
      `<button class="btn outline w460" data-delete="${esc(ev.uid)}">Delete</button>`
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

function openPerson(id) {
  const p = state.today?.people.find((x) => x.id === id);
  if (!p) return;
  showSheet(`<div class="sheet day-sheet"><div class="head"><div><div class="dow">TODAY</div><div class="big">${esc(p.name)}</div></div>` +
    `<button class="close" data-close>${icons.x(52, 8, "#1c1b1f")}</button></div>` +
    `<div class="rows person-rows">${p.todos.map(todoRow).join("")}</div></div>`);
}

async function removeEvent(uid) {
  const ev = findEvent(uid);
  try {
    await request("DELETE", `/api/events/${encodeURIComponent(uid)}`);
  } catch (err) {
    sheetEl.innerHTML = `<div class="scrim" data-close></div>${eventSheet(ev, "confirm", errorText(err))}`;
    return;
  }
  closeSheet();
  toast(`Removed ${esc(ev?.title ?? "event")}`, { ok: true });
  loadWeek().catch(() => {});
}

export const isNight = (d) => { const h = chicagoParts(d).hour; return h >= 22 || h < 6; };

function renderNight(now) {
  const st = status();
  // After midnight the day being woken into is days[0]; the label stays "TOMORROW".
  const tomorrow = state.week?.days[chicagoParts(now).hour < 6 ? 0 : 1]?.events[0];
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

export function startKitchen(root) {
  root.innerHTML = `<div class="stage" id="stage"><div class="dash" id="dash"></div>` +
    `<div id="sheet" hidden></div><div class="night" id="night"></div></div>`;
  stage = document.getElementById("stage");
  dash = document.getElementById("dash");
  sheetEl = document.getElementById("sheet");
  nightEl = document.getElementById("night");
  initTalkWall(stage, dash);
  initSlideshow(stage, { blocked: () => !sheetEl.hidden || talkOpen() || nightEl.classList.contains("on") });
  fitStage();
  window.addEventListener("resize", fitStage);
  stage.addEventListener("pointerdown", () => { if (!sheetEl.hidden) armSheetClose(); }, true);
  nightEl.addEventListener("click", (e) => {
    e.stopPropagation();  // the waking tap never reaches the dashboard
    awakeUntil = Date.now() + WAKE_MS;
    updateNight(new Date());
  });
  stage.addEventListener("click", (e) => {
    const t = e.target.closest("[data-talk],[data-voice],[data-todo],[data-uid],[data-day],[data-close],[data-delete],[data-keep],[data-remove],[data-person]");
    if (!t) return;
    const d = t.dataset;
    if (d.talk !== undefined) return openTalk({ night: isNight(new Date()) });
    if (d.voice) {
      const ev = findEvent(d.voice);
      closeSheet();
      return openTalk({ context: ev ? { event: { uid: ev.uid, title: ev.title, when_label: ev.when_label,
                                                 calendar: ev.calendar } } : null });
    }
    if (d.close !== undefined) closeSheet();
    else if (d.delete) showSheet(eventSheet(findEvent(d.delete), "confirm"));
    else if (d.keep) showSheet(eventSheet(findEvent(d.keep)));
    else if (d.remove) removeEvent(d.remove);
    else if (d.todo) toggleTodo(t);
    else if (d.uid) openEvent(d.uid);
    else if (d.day) openDay(d.day);
    else if (d.person) openPerson(Number(d.person));
  });
  onChange(render);
  render();
  updateNight(new Date());
  startPolling({ alwaysOn: true });
  let day = chicagoParts(new Date()).iso;
  setInterval(() => {
    const now = tickClock();
    updateNight(now);
    const today = chicagoParts(now).iso;
    if (today !== day) { day = today; Promise.all([loadWeek(), loadToday()]).catch(() => {}); }  // midnight
  }, 1000);
}
