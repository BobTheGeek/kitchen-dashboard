#!/bin/sh
# Installs or updates the House tools in Open WebUI and sets their Valves. Run on home-ai:
#   OWUI_ADMIN_KEY=<an admin API key> sh ops/install-house-tools.sh
# The admin key is used for this call only and never stored. The House token is read from the secrets file.
set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$(dirname "$0")/.."
: "${OWUI_ADMIN_KEY:?set OWUI_ADMIN_KEY to an Open WebUI admin API key}"
OWUI="${OWUI_URL:-http://localhost:3000}"
TOKEN_FILE="$HOME/household-ai/secrets/kitchen/house_token"
[ -s "$TOKEN_FILE" ] || { echo "missing $TOKEN_FILE"; exit 1; }
for id in household_calendar household_todos; do
  python3 - "$OWUI" "$id" "house_tools/$id.py" "$TOKEN_FILE" <<'PY'
import json, os, re, sys, urllib.error, urllib.request
owui, tid, path, token_file = sys.argv[1:5]
key = os.environ["OWUI_ADMIN_KEY"]
src = open(path).read()
name = re.search(r"^title:\s*(.+)$", src, re.M).group(1).strip()
desc = re.search(r"^description:\s*(.+)$", src, re.M).group(1).strip()
def call(method, url, body=None):
    req = urllib.request.Request(owui + url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)
form = {"id": tid, "name": name, "content": src, "meta": {"description": desc}}
try:
    call("GET", f"/api/v1/tools/id/{tid}")
    call("POST", f"/api/v1/tools/id/{tid}/update", form)
    print("updated", tid)
except urllib.error.HTTPError:
    call("POST", "/api/v1/tools/create", form)
    print("created", tid)
call("POST", f"/api/v1/tools/id/{tid}/valves/update",
     {"dashboard_url": "http://kitchen-dashboard:8000", "token": open(token_file).read().strip()})
print("valves set", tid)
PY
  cp "house_tools/$id.py" "$HOME/household-ai/tools/$id.py"
done
echo "== Now share both tools with the Kitchen account: Open WebUI > Workspace > Tools > (tool) > Access."
