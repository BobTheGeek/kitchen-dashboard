#!/bin/sh
# Local dev with fake calendar data: http://localhost:8081 (narrow the window below 900px for the phone layout)
set -e
cd "$(dirname "$0")/.."
[ -d .venv ] || python3.13 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements-dev.txt
DASHBOARD_FAKE=1 DASHBOARD_DB=.dev.db exec uvicorn app.main:app --reload --port 8081
