// Picks the kitchen or phone layout and reloads the page after a deploy.
import { startKitchen } from "./kitchen.js";
import { startPhone } from "./phone.js";

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
