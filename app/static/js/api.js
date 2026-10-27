// Shared data + smart polling. The page asks for a tiny change number every 10 s and refetches only on change.
export const state = { week: null, today: null, settings: null, lastOk: null, startedAt: Date.now(), changes: null };
const listeners = new Set();

export const onChange = (fn) => listeners.add(fn);
export const emit = () => listeners.forEach((fn) => fn(state));

export async function request(method, url, body) {
  const r = await fetch(url, {
    method, cache: "no-store",
    headers: body !== undefined ? { "Content-Type": "application/json" } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = r.status === 204 ? null : await r.json().catch(() => null);
  state.lastOk = Date.now();  // any answer means the server is reachable
  if (!r.ok) {
    const err = new Error(`HTTP ${r.status}`);
    err.status = r.status;
    err.data = data;
    throw err;
  }
  return data;
}

export async function loadWeek() { state.week = await request("GET", "/api/week"); emit(); }
export async function loadToday() { state.today = await request("GET", "/api/today"); emit(); }
export async function loadSettings() { state.settings = await request("GET", "/api/settings"); emit(); }

async function pollChanges() {
  const { n } = await request("GET", "/api/changes");
  if (n !== state.changes) {
    state.changes = n;
    await Promise.all([loadToday(), loadSettings()]);
  } else {
    emit();  // keeps the status line fresh
  }
}

export function startPolling({ alwaysOn }) {
  const safe = (fn) => () => fn().catch((e) => { console.warn(e); emit(); });
  const fast = safe(pollChanges);
  // The 60 s tick also refreshes today, so timed TODOs turn overdue without a write.
  const slow = safe(() => Promise.all([loadWeek(), loadToday()]));
  let timers = [];
  const start = () => {
    if (timers.length) return;
    fast(); slow();
    timers = [setInterval(fast, 10_000), setInterval(slow, 60_000)];
  };
  const stop = () => { timers.forEach(clearInterval); timers = []; };
  start();
  if (!alwaysOn) document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
}

export function status(now = Date.now()) {
  const quiet = now - (state.lastOk ?? state.startedAt);
  if (quiet >= 30_000) return { tone: "amber", text: "last updated — offline" };
  if (!state.lastOk || !state.week) return { tone: "amber", text: "connecting to the home server…" };
  if (!state.week.fetched_at) return { tone: "amber", text: "no calendar data yet" };
  const mins = Math.floor((now - Date.parse(state.week.fetched_at)) / 60_000);
  if (mins >= 5) return { tone: "amber", text: `last updated ${mins} min ago` };
  return { tone: "green", text: "up to date" };
}
