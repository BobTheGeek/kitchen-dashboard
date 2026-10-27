#!/bin/sh
# Hourly (launchd): copy the shared album into the folder the kitchen-dashboard container reads as /photos.
# If anything fails, the old photos stay and the wall keeps working.
set -eu
ALBUM="Kitchen Tablet Slideshow"
BASE="$HOME/household-ai/data/photos"
EXPORT="$BASE/.export"
OUT="$BASE/kitchen"
LOG="$HOME/household-ai/logs/kitchen-photo-sync.log"
LOCK="$HOME/.kitchen-photo-sync.lock"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }
mkdir -p "$EXPORT" "$OUT" "$(dirname "$LOG")"
find "$LOCK" -maxdepth 0 -mmin +120 -exec rmdir {} \; 2>/dev/null || true  # a lock left by a killed run
mkdir "$LOCK" 2>/dev/null || exit 0
trap 'rmdir "$LOCK"' EXIT

# Photos still downloading from iCloud are skipped and picked up by a later run.
if ! osxphotos export "$EXPORT" --album "$ALBUM" --only-photos --skip-live --convert-to-jpeg --jpeg-ext jpg \
    --filename "{uuid}" --update --cleanup >/dev/null 2>"$BASE/.last-error"; then
  log "FAILED: osxphotos export: $(tail -1 "$BASE/.last-error")"
  exit 1
fi

# An empty export (album renamed, Photos signed out) must not wipe the wall.
if [ -z "$(find "$EXPORT" -maxdepth 1 -name '*.jpg' | head -1)" ] \
    && [ -n "$(find "$OUT" -maxdepth 1 -name '*.jpg' ! -name '.*' | head -1)" ]; then
  log "export empty, keeping existing photos"
  exit 1
fi

added=0 updated=0 removed=0
for src in "$EXPORT"/*.jpg; do
  [ -e "$src" ] || continue
  dst="$OUT/$(basename "$src")"
  if [ -e "$dst" ] && [ ! "$src" -nt "$dst" ]; then continue; fi
  # Resize into a hidden temp name (the server ignores it), then rename: the wall never sees half a file.
  # sips -Z also enlarges small photos, so only shrink the ones longer than 3000 px.
  w=$(sips -g pixelWidth "$src" 2>/dev/null | awk '/pixelWidth/ {print $2}')
  h=$(sips -g pixelHeight "$src" 2>/dev/null | awk '/pixelHeight/ {print $2}')
  if [ "${w:-0}" -gt 3000 ] || [ "${h:-0}" -gt 3000 ]; then resize="-Z 3000"; else resize=""; fi
  # shellcheck disable=SC2086
  if ! sips $resize -s format jpeg "$src" --out "$OUT/.tmp.jpg" >/dev/null 2>&1; then
    log "skipped $(basename "$src"): sips failed"
    continue
  fi
  if [ -e "$dst" ]; then updated=$((updated + 1)); else added=$((added + 1)); fi
  mv "$OUT/.tmp.jpg" "$dst"
done
for dst in "$OUT"/*.jpg; do
  [ -e "$dst" ] || continue
  if [ ! -e "$EXPORT/$(basename "$dst")" ]; then rm -f "$dst"; removed=$((removed + 1)); fi
done
log "ok: $(find "$OUT" -name '*.jpg' ! -name '.*' | wc -l | tr -d ' ') photos (added $added, updated $updated, removed $removed)"
