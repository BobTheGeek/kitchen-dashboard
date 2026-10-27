"""The one place the app reads the time. Tests replace `now` with monkeypatch."""
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Chicago")


def now() -> datetime:
    return datetime.now(TZ)
