"""Slideshow photos: the folder the home-ai sync job fills, and the hours the slideshow may run."""
import re
from datetime import datetime
from pathlib import Path

START_HOUR = 7   # 7:00 AM Chicago
END_HOUR = 21    # 9:00 PM Chicago
NAME = re.compile(r"^[A-Za-z0-9-]{1,80}\.jpg$")


def list_photos(folder: Path | None) -> list[dict]:
    if folder is None:
        return []
    try:
        names = sorted(p.name for p in folder.iterdir() if NAME.match(p.name))
    except OSError:
        return []
    out = []
    for name in names:
        try:
            st = (folder / name).stat()
        except OSError:
            continue  # removed by the sync job between the listing and now
        if (folder / name).is_file():
            out.append({"name": name, "v": int(st.st_mtime)})
    return out


def photo_path(folder: Path | None, name: str) -> Path | None:
    if folder is None or not NAME.match(name):
        return None
    path = folder / name
    return path if path.is_file() else None


def slideshow_hours(now: datetime) -> bool:
    return START_HOUR <= now.hour < END_HOUR
