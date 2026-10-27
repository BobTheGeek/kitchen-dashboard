#!/bin/sh
# Builds whisper.cpp with Metal on home-ai and runs whisper-server on 127.0.0.1:8178 under launchd.
# Usage on home-ai: sh ops/install-whisper.sh   (needs Xcode command line tools and cmake: brew install cmake)
set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
TAG="${WHISPER_TAG:-v1.9.5}"
MODEL="${WHISPER_MODEL:-small.en}"
DIR="$HOME/household-ai/whisper"
PLIST="$HOME/Library/LaunchAgents/com.household.whisper.plist"
mkdir -p "$HOME/household-ai/logs"
if [ ! -d "$DIR/.git" ]; then
  git clone -q https://github.com/ggml-org/whisper.cpp "$DIR"
fi
cd "$DIR"
git fetch -q --tags
git checkout -q "$TAG"
cmake -B build -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build build -j --config Release --target whisper-server
[ -f "models/ggml-$MODEL.bin" ] || sh models/download-ggml-model.sh "$MODEL"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.household.whisper</string>
  <key>ProgramArguments</key><array>
    <string>$DIR/build/bin/whisper-server</string>
    <string>-m</string><string>$DIR/models/ggml-$MODEL.bin</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>8178</string>
    <string>-t</string><string>4</string>
  </array>
  <key>KeepAlive</key><true/>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$HOME/household-ai/logs/whisper.log</string>
  <key>StandardErrorPath</key><string>$HOME/household-ai/logs/whisper.log</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
sleep 1
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "== whisper.cpp $TAG ($MODEL) on 127.0.0.1:8178"
