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
  if (running && (!active || !photos.length)) stop();
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
  if (!photos.length) return stop();  // the folder emptied while showing
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
