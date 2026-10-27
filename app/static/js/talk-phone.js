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
  const cur = s;
  try { cur.id = (await talkApi.start(context)).id; } catch (err) { if (s === cur) cur.items.push({ role: "house", text: errorText(err), changes: [] }); }
  if (s !== cur) {  // closed while starting: don't leave the session open on the server
    if (cur.id) talkApi.end(cur.id);
    return;
  }
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
  const cur = s;
  s.items.push({ role: "you", text, changes: [] });
  s.busy = true;
  rerender();
  try {
    const res = await talkApi.message(cur.id, text);
    if (res.changes.length) Promise.all([loadWeek(), loadToday()]).catch(() => {});
    if (s !== cur) return;
    cur.items.push({ role: "house", text: res.reply, changes: res.changes });
  } catch (err) {
    if (s !== cur) return;
    cur.items.push({ role: "house", text: errorText(err), changes: [] });
  }
  cur.busy = false;
  rerender();
  window.scrollTo(0, document.body.scrollHeight);
}

async function toggleMic() {
  if (!micAvailable()) return toast("The microphone needs the secure (https) address");
  const cur = s;
  if (!cur || cur.starting) return;  // a tap while the mic is still opening is ignored
  if (cur.rec) {
    const rec = cur.rec;
    cur.rec = null;
    rerender();
    const { wav, heard } = await rec.stop();
    if (s !== cur) return;
    if (!heard) return toast("Didn't catch that");
    try {
      const text = await talkApi.listen(wav);
      if (s !== cur) return;
      if (text) send(text); else toast("Didn't catch that");
    } catch (err) { if (s === cur) toast(esc(errorText(err))); }
    return;
  }
  const rec = new Recorder({ onSilence: () => { if (s === cur && cur.rec === rec) toggleMic(); } });
  cur.rec = rec;
  cur.starting = true;
  try { await rec.start(); } catch { if (cur.rec === rec) cur.rec = null; if (s === cur) toast("The microphone is off"); }
  cur.starting = false;
  if (s === cur) rerender();
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
    `<form class="p-tbar" id="talk-form" autocomplete="off"><input name="msg" placeholder="Ask or tell the house…" maxlength="500">` +
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
