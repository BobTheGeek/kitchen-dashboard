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
