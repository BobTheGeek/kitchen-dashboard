// Kitchen wall screen (design 2a and its states). Authored at 3000x2000; scaled to fit in dev windows.
import { loadToday, loadWeek, onChange, request, startPolling, state, status } from "./api.js";
import { chicagoParts, chipStyle, clockText, dateText, errorText, esc, icons, toast } from "./ui.js";

let stage, dash, nightEl;
let awakeUntil = 0;
const WAKE_MS = 2 * 60_000;

function fitStage() {
  const s = Math.min(window.innerWidth / 3000, window.innerHeight / 2000);
  document.documentElement.style.setProperty("--scale", String(s));
}

const light = (ev) => ev.ink === "#1c1b1f";

function chip(ev) {
  return `<button class="ev ${light(ev) ? "light" : ""}" data-uid="${esc(ev.uid)}" ${chipStyle(ev)}>` +
    `<div class="t">${esc(ev.time_label)}</div><div class="n">${esc(ev.title)}</div></button>`;
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

// The dash is built once; each section is replaced only when its markup changed, so a poll with no change
// touches nothing (the All-done fade and confetti must play once, not every 10 s). Clock, date and status
// are updated by tickClock() and take no part in the comparison.
let slots = null;
const personEls = new Map();  // person id -> { el, html }

function buildShell() {
  dash.innerHTML =
    `<div class="rail"><div><div class="clock" id="clock"></div><div class="date" id="date"></div></div>` +
    `<div class="next"><div class="label">NEXT UP</div><div id="next-list" class="next-list"></div></div>` +
    `<button class="talk" id="talk" aria-disabled="true"></button>` +
    `<div class="status" id="status"></div></div>` +
    `<div class="right"><div class="week" id="week"></div><div class="people" id="people"></div></div>`;
  slots = { next: dash.querySelector("#next-list"), talk: dash.querySelector("#talk"), week: dash.querySelector("#week"),
    people: dash.querySelector("#people") };
  personEls.clear();
}

function setHtml(el, html) {
  if (el._html === html) return;
  el._html = html;
  el.innerHTML = html;
}

function renderPeople(loading, people, skHtml) {
  const box = slots.people;
  if (loading) {
    personEls.clear();
    setHtml(box, `${skHtml}<div class="slot">+</div>`);
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
      rec = { el, html };
      personEls.set(p.id, rec);
    }
    keep.add(p.id);
    const want = prev ? prev.nextElementSibling : box.firstElementChild;
    if (want !== rec.el) box.insertBefore(rec.el, want);
    prev = rec.el;
  }
  for (const [id, rec] of personEls) if (!keep.has(id)) { rec.el.remove(); personEls.delete(id); }
  let plus = box.querySelector(":scope > .slot");
  if (!plus) { plus = document.createElement("div"); plus.className = "slot"; plus.textContent = "+"; }
  if (box.lastElementChild !== plus) box.append(plus);
}

function updateStatus() {
  const st = status();
  const s = document.getElementById("status");
  s.className = `status ${st.tone === "amber" ? "amber" : ""}`;
  s.innerHTML = `<span class="dot"></span>${esc(st.text)}`;
}

function render() {
  const loading = !state.week || !state.today;
  const sk = loading ? skeleton() : null;
  dash.className = `dash ${loading ? "loading" : ""} ${sheetEl && !sheetEl.hidden ? "dimmed" : ""}`;
  if (!slots) { buildShell(); tickClock(); }
  setHtml(slots.next, loading ? sk.next : nextCards(state.week.next));
  slots.talk.className = `talk ${loading ? "skel" : ""}`;
  setHtml(slots.talk, loading ? "" : `<span class="mic">${icons.mic(50)}</span>Talk to the house`);
  setHtml(slots.week, loading ? sk.week : state.week.days.map(dayColumn).join(""));
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
  fitStage();
  window.addEventListener("resize", fitStage);
  nightEl.addEventListener("click", (e) => {
    e.stopPropagation();  // the waking tap never reaches the dashboard
    awakeUntil = Date.now() + WAKE_MS;
    updateNight(new Date());
  });
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
