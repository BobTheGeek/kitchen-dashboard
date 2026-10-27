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
    else todoFail(res);
  }
}

// 422 keeps the inline field message; anything else also gets the short toast.
function todoFail(err) {
  document.getElementById("todo-err").textContent = errorText(err);
  if (err?.status !== 422) toast("Couldn't save, try again");
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
  else todoFail(res);
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
