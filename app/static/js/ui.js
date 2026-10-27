// Small shared helpers: escaping, Chicago time, icons, toast. No framework.
export const TZ = "America/Chicago";

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const timeFmt = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit", hour12: true });
const dateFmt = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "short", day: "numeric", month: "short" });
const partsFmt = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", hourCycle: "h23" });

export const clockText = (d) => timeFmt.format(d).replace(/\s?[AP]M$/, "");

export function dateText(d) {
  const p = Object.fromEntries(dateFmt.formatToParts(d).map((x) => [x.type, x.value]));
  return `${p.weekday} ${p.day} ${p.month}`.toUpperCase();
}

export function chicagoParts(d) {
  const p = Object.fromEntries(partsFmt.formatToParts(d).map((x) => [x.type, x.value]));
  return { iso: `${p.year}-${p.month}-${p.day}`, hour: Number(p.hour) };
}

export const chipStyle = (ev) => `style="background:${esc(ev.color)};color:${esc(ev.ink)}"`;

export const icons = {
  // Mic: capsule + U cradle + stem + base, drawn with boxes like the design.
  mic(w, color = "#fff") {
    const u = w / 50;
    return `<span class="i-mic" style="width:${w}px;height:${62 * u}px">` +
      `<b style="left:${14 * u}px;top:0;width:${22 * u}px;height:${38 * u}px;border-radius:999px;background:${color}"></b>` +
      `<b style="left:0;top:${20 * u}px;width:${50 * u}px;height:${30 * u}px;border:${6 * u}px solid ${color};` +
      `border-top:none;border-radius:0 0 999px 999px"></b>` +
      `<b style="left:${22 * u}px;top:${50 * u}px;width:${6 * u}px;height:${8 * u}px;background:${color}"></b>` +
      `<b style="left:${10 * u}px;top:${57 * u}px;width:${30 * u}px;height:${6 * u}px;border-radius:999px;` +
      `background:${color}"></b></span>`;
  },
  check(w, thick, color = "#fff") {
    return `<span class="i-check" style="width:${w}px;height:${w / 2}px;border-width:0 0 ${thick}px ${thick}px;` +
      `color:${color}"></span>`;
  },
  x(w, thick, color) {
    return `<span class="i-x" style="width:${w}px;height:${w}px;--t:${thick}px;--c:${color}"></span>`;
  },
};

let toastTimer;
export function toast(html, { ok = false, ms = 6000, cls = "" } = {}) {
  const el = document.getElementById("toast");
  el.className = `toast ${cls}`;
  el.innerHTML = (ok ? `<span class="toast-ok">${icons.check(24, 6, "var(--success)")}</span>` : "") +
    `<span>${html}</span>`;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, ms);
}

export function errorText(err) {
  const d = err?.data?.detail;
  if (Array.isArray(d)) return d.map((x) => x.msg).join(", ");
  if (d) return d;
  if (err?.status === undefined) return "Couldn't reach the home server";  // fetch/network failure
  return err.message || "Something went wrong";
}
