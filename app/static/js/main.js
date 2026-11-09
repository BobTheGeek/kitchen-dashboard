// Picks the kitchen or phone layout, reports page errors and reloads the page after a deploy.
import { startKitchen } from "./kitchen.js";
import { startPhone } from "./phone.js";

// The kiosk has no console, so errors go to the server log (at most 20 per page load).
let reported = 0;
function report(message, where) {
  if (reported++ >= 20) return;
  fetch("/api/client-error", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: String(message).slice(0, 2000), where: String(where || "").slice(0, 300) }) })
    .catch(() => {});
}
window.addEventListener("error", (e) => report(e.error?.stack || e.message, `${e.filename}:${e.lineno}:${e.colno}`));
window.addEventListener("unhandledrejection", (e) => report(e.reason?.stack || e.reason, "unhandled promise"));

const root = document.getElementById("root");
const isPhone = window.matchMedia("(max-width: 900px)").matches;
document.body.classList.add(isPhone ? "is-phone" : "is-kitchen");
(isPhone ? startPhone : startKitchen)(root);

let version = null;
async function checkVersion() {
  try {
    const r = await fetch("/api/version", { cache: "no-store" });
    const { version: v } = await r.json();
    if (version && v !== version) location.reload();
    version = v;
  } catch { /* offline; try again next minute */ }
}
checkVersion();
setInterval(checkVersion, 60_000);

// TEMPORARY touch diagnostics for the kiosk: logs only event types, positions and class names. Remove after testing.
if (!isPhone) {
  const counts = {};
  let last = "";
  const send = (message) => fetch("/api/client-error", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: `TOUCHDEBUG ${message}`, where: "kiosk" }) }).catch(() => {});
  for (const type of ["touchstart", "touchend", "touchcancel", "pointerdown", "pointerup", "pointercancel", "mousedown", "click"]) {
    window.addEventListener(type, (e) => {
      counts[type] = (counts[type] ?? 0) + 1;
      const p = e.changedTouches?.[0] ?? e;
      const hit = document.elementFromPoint(p.clientX, p.clientY);
      last = `${type} ${e.pointerType ?? ""} ${Math.round(p.clientX)},${Math.round(p.clientY)} ` +
        `on .${String(hit?.className ?? "none").slice(0, 40)} trusted=${e.isTrusted}`;
    }, { capture: true, passive: true });
  }
  send(`load touchPoints=${navigator.maxTouchPoints} coarse=${matchMedia("(pointer: coarse)").matches} ` +
    `size=${window.innerWidth}x${window.innerHeight} dpr=${window.devicePixelRatio} focus=${document.hasFocus()}`);
  setInterval(() => {
    if (!Object.keys(counts).length) return;
    send(`${JSON.stringify(counts)} last: ${last}`);
    for (const k of Object.keys(counts)) delete counts[k];
  }, 2000);
}
