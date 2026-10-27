// Kitchen "Talk to the house" panel (design 2b, 5a-5d, 8g, 8e). One panel at a time, over the dimmed dashboard.
import { loadToday, loadWeek } from "./api.js";
import { Recorder, micAvailable, talkApi } from "./talk.js";
import { errorText, esc, icons, toast } from "./ui.js";

const AUTO_CLOSE_MS = 20_000;
const TYPING_CLOSE_MS = 60_000;
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
        bars: new Array(16).fill(0.25), context, id: null, rec: null, closeTimer: null, seen: new Set() };
  const cur = t;
  dash.classList.add("dimmed");
  el.hidden = false;
  draw();
  if (!(await ensureSession())) return;
  if (t !== cur || cur.mode !== "starting") return;  // closed, or the person chose typing meanwhile
  if (typing) return setMode("typing");
  if (!micAvailable()) return setMode("nomic");
  listen();
}

// Starts the talk session if it is not running yet (the first start can fail). Shows the error and
// returns false if it still fails, or if the panel was closed meanwhile.
async function ensureSession() {
  const cur = t;
  if (!cur) return false;
  if (cur.id) return true;
  try {
    const id = (await talkApi.start(cur.context)).id;
    if (t !== cur) { talkApi.end(id); return false; }
    cur.id = id;
    return true;
  } catch (err) {
    if (t === cur) fail(errorText(err), "start");
    return false;
  }
}

// Idle auto-close: the panel never stays open forever. Answer/miss/error/nomic 20 s, typing 60 s.
function arm() {
  if (!t) return;
  clearTimeout(t.closeTimer);
  const ms = t.mode === "typing" ? TYPING_CLOSE_MS : ["answer", "miss", "error", "nomic"].includes(t.mode) ? AUTO_CLOSE_MS : 0;
  if (ms) t.closeTimer = setTimeout(() => close(), ms);
}

function setMode(mode) { if (t) { t.mode = mode; draw(); arm(); } }

async function listen() {
  const cur = t;
  cur.text = "";
  setMode("listening");
  if (!(await ensureSession())) return;
  if (t !== cur || cur.mode !== "listening") return;
  const rec = new Recorder({ onLevel: level, onSilence: () => finishListening() });
  cur.rec = rec;
  try {
    await rec.start();
    if (t !== cur || cur.rec !== rec) rec.cancel();  // closed or switched to typing while the mic opened
  } catch {
    if (t === cur && cur.rec === rec) { cur.rec = null; setMode("nomic"); }
  }
}

async function finishListening() {
  const cur = t;
  const rec = cur?.rec;
  if (!rec) return;
  cur.rec = null;
  let out;
  try {
    out = await rec.stop();
  } catch {
    if (t === cur) fail("Voice isn't working right now", "voice");
    return;
  }
  if (t !== cur) return;
  const { wav, heard } = out;
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
  if (!(await ensureSession())) return;
  try {
    const res = await talkApi.message(cur.id, text);
    if (t !== cur) return;
    cur.reply = res.reply;
    cur.changes = res.changes;
    res.changes.forEach((c) => cur.seen.add(c.id));
    setMode("answer");
    if (res.changes.length) Promise.all([loadWeek(), loadToday()]).catch(() => {});
  } catch (err) {
    if (t !== cur) return;
    // The House can time out after its tools already wrote: show what landed instead of an error + Retry.
    let late = [];
    try { late = (await talkApi.status(cur.id)).changes.filter((c) => !cur.seen.has(c.id)); } catch { /* keep the error */ }
    if (t !== cur) return;
    if (late.length) {
      late.forEach((c) => cur.seen.add(c.id));
      cur.reply = "Done \u2014 the house finished, but slowly.";
      cur.changes = late;
      setMode("answer");
      Promise.all([loadWeek(), loadToday()]).catch(() => {});
    } else {
      fail(errorText(err), "house");
    }
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
  if (cur.id && (cancelled || !changes.length)) {  // late writes (slow House, Cancel) still get the toast
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
  await act(b);
  arm();  // any touch restarts the idle auto-close for the mode the panel is now in
}

async function act(b) {
  const a = b.dataset.t;
  if (a === "stop" || a === "close" || a === "never") return close();
  if (a === "cancel") return close({ cancelled: true });
  if (a === "type") { t.rec?.cancel(); t.rec = null; return setMode("typing"); }
  if (a === "voice") return micAvailable() ? listen() : setMode("nomic");
  if (a === "again" || a === "more") return listen();
  if (a === "retry") return (t.errKind === "house" || t.errKind === "start") && t.text ? send(t.text) : listen();
  if (a === "undo-all") { for (const c of t.changes.filter((x) => x.undoable && !x.undone)) await undoCard(c.id); return; }
  if (a === "undo") return undoCard(Number(b.dataset.id));
  if (a === "key") return typeKey(b.dataset.k);
  if (a === "suggest") { t.typed = b.dataset.s.replace("…", " "); return draw(); }
  if (a === "send") { const text = t.typed.trim(); if (text) { t.typed = ""; send(text); } }
}

function card(c) {
  const chip = c.kind === "event"
    ? `<span class="tchip" style="background:${esc(c.color)};color:${esc(c.ink)}"><b>${esc(c.detail)}</b>${esc(c.title)}</span>`
    : `<span class="tchip ttodo"><b>${esc(c.person || "")} · ${esc(c.detail)}</b>${esc(c.title)}</span>`;
  const meta = c.kind === "event" ? `${esc(c.calendar || "")} calendar` : `${esc(c.person || "")}'s TODOs`;
  return `<div class="tcard ${c.undone ? "undone" : ""}">${chip}<div class="tmeta">${meta}</div>` +
    `<span class="tverb">${c.undone ? "UNDONE" : esc(c.verb)}</span>` +
    (t.changes.length > 1 && c.undoable && !c.undone ? `<button class="tsmall" data-t="undo" data-id="${c.id}">Undo</button>` : "") +
    `</div>`;
}

function draw() {
  if (!t) return;
  const night = t.night ? " tnight" : "";
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
