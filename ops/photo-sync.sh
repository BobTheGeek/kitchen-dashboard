#!/bin/sh
# Hourly (launchd): copy the shared album into the folder the kitchen-dashboard container reads as /photos.
# If anything fails, the old photos stay and the wall keeps working.
#
# osxphotos 0.77 cannot export shared-album photos on this macOS (it sees them but finds no file, and its
# AppleScript fallback fails). Photos keeps the downloaded originals in scopes/collectionshare/originals/<X>/<UUID>.<ext>,
# so we ask osxphotos only for the album's UUIDs and convert those files ourselves.
set -eu
ALBUM="Kitchen Tablet Slideshow"
SRC="$HOME/Pictures/Photos Library.photoslibrary/scopes/collectionshare/originals"
BASE="$HOME/household-ai/data/photos"
OUT="$BASE/kitchen"
LIST="$BASE/.album-uuids"
LOG="$HOME/household-ai/logs/kitchen-photo-sync.log"
LOCK="$HOME/.kitchen-photo-sync.lock"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }
mkdir -p "$OUT" "$(dirname "$LOG")"
find "$LOCK" -maxdepth 0 -mmin +120 -exec rmdir {} \; 2>/dev/null || true  # a lock left by a killed run
mkdir "$LOCK" 2>/dev/null || { log "skipped: another sync is running"; exit 0; }
trap 'rmdir "$LOCK"' EXIT

if ! osxphotos query --album "$ALBUM" --only-photos --quiet --print "{uuid}" >"$LIST" 2>"$BASE/.last-error"; then
  log "FAILED: osxphotos query: $(tail -1 "$BASE/.last-error")"
  exit 1
fi

# An empty album list (album renamed, Photos signed out) must not wipe the wall.
if [ ! -s "$LIST" ] && [ -n "$(find "$OUT" -maxdepth 1 -name '*.jpg' ! -name '.*' | head -1)" ]; then
  log "album list empty, keeping existing photos"
  exit 1
fi

added=0 updated=0 removed=0 waiting=0
while read -r uuid; do
  case "$uuid" in *[!A-F0-9-]*|"") continue ;; esac
  # Photos not downloaded yet have no file; a later run picks them up.
  src=$(find "$SRC/$(printf %.1s "$uuid")" -maxdepth 1 -name "$uuid.*" 2>/dev/null | head -1)
  if [ -z "$src" ]; then waiting=$((waiting + 1)); continue; fi
  dst="$OUT/$uuid.jpg"
  if [ -e "$dst" ] && [ ! "$src" -nt "$dst" ]; then continue; fi
  # Convert into a hidden temp name (the server ignores it), then rename: the wall never sees half a file.
  # sips -Z also enlarges small photos, so only shrink the ones longer than 3000 px.
  w=$(sips -g pixelWidth "$src" 2>/dev/null | awk '/pixelWidth/ {print $2}')
  h=$(sips -g pixelHeight "$src" 2>/dev/null | awk '/pixelHeight/ {print $2}')
  if [ "${w:-0}" -gt 3000 ] || [ "${h:-0}" -gt 3000 ]; then resize="-Z 3000"; else resize=""; fi
  case "$src" in
    *.jpg|*.jpeg|*.JPG|*.JPEG) [ -z "$resize" ] && copy=1 || copy="" ;;
    *) copy="" ;;
  esac
  if [ -n "$copy" ]; then
    if ! cp "$src" "$OUT/.tmp.jpg"; then log "skipped $uuid: copy failed"; continue; fi
  else
    # shellcheck disable=SC2086
    if ! sips $resize -s format jpeg "$src" --out "$OUT/.tmp.jpg" >/dev/null 2>&1; then
      log "skipped $uuid: sips failed"
      continue
    fi
  fi
  if [ -e "$dst" ]; then updated=$((updated + 1)); else added=$((added + 1)); fi
  mv "$OUT/.tmp.jpg" "$dst"
done <"$LIST"

for dst in "$OUT"/*.jpg; do
  [ -e "$dst" ] || continue
  if ! grep -qx "$(basename "$dst" .jpg)" "$LIST"; then rm -f "$dst"; removed=$((removed + 1)); fi
done
log "ok: $(find "$OUT" -name '*.jpg' ! -name '.*' | wc -l | tr -d ' ') photos (added $added, updated $updated, removed $removed, waiting for download $waiting)"
