"""Calendar data: read from calendar-api (or fixtures), cache it, and shape the week the page shows."""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from app import clock, labels
from app.store import Store

MAX_CHIPS = 3
NEXT_UP = 4
UNKNOWN_COLOR = "#6b6875"
CACHE_KEY = "events"


class CalendarError(Exception):
    pass


class HttpSource:
    def __init__(self, base_url: str, timeout: float = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def events(self, start: date, days: int) -> list[dict]:
        query = urllib.parse.urlencode({"start": start.isoformat(), "days": days, "kitchen_only": "true"})
        try:
            with urllib.request.urlopen(f"{self.base_url}/events?{query}", timeout=self.timeout) as r:
                return json.load(r)["events"]
        except Exception as e:
            raise CalendarError(f"calendar-api unavailable: {type(e).__name__}") from e

    def _send(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.base_url}{path}", data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, {"detail": raw.decode(errors="replace") or e.reason}
        except Exception as e:
            return 502, {"detail": f"calendar-api unavailable: {type(e).__name__}"}

    def delete(self, uid: str) -> tuple[int, dict]:
        return self._send("DELETE", f"/events/{urllib.parse.quote(uid, safe='')}")

    def create(self, fields: dict) -> tuple[int, dict]:
        return self._send("POST", "/events", fields)

    def update(self, uid: str, fields: dict) -> tuple[int, dict]:
        return self._send("PATCH", f"/events/{urllib.parse.quote(uid, safe='')}", fields)

    def find(self, uid: str, start: date, days: int) -> dict | None:
        query = urllib.parse.urlencode({"start": start.isoformat(), "days": days})
        status, body = self._send("GET", f"/events?{query}")
        if status >= 300:
            raise CalendarError(body.get("detail", "calendar-api error"))
        return next((e for e in body.get("events", []) if e["uid"] == uid), None)


class FixtureSource:
    """Fake calendar-api for dev and CI. Fixture dates are day offsets from today."""

    def __init__(self, path: Path):
        self.items = json.loads(Path(path).read_text(encoding="utf-8"))["events"]
        self.deleted: set[str] = set()
        self.extra: list[dict] = []
        self._n = 0

    def _materialize(self) -> list[dict]:
        today = clock.now().date()
        out = []
        for i, f in enumerate(self.items):
            d = today + timedelta(days=f["offset"])
            if f.get("all_day"):
                start, end = d.isoformat(), (d + timedelta(days=1)).isoformat()
            else:
                hh, mm = map(int, f["time"].split(":"))
                s = datetime(d.year, d.month, d.day, hh, mm, tzinfo=clock.TZ)
                start, end = s.isoformat(), (s + timedelta(minutes=f.get("minutes", 60))).isoformat()
            out.append({"calendar": f["calendar"], "title": f["title"], "when": "", "start": start, "end": end,
                        "all_day": bool(f.get("all_day")), "location": f.get("location"), "uid": f"fake-{i}",
                        "added_by_house": bool(f.get("house"))})
        return [e for e in out if e["uid"] not in self.deleted] + list(self.extra)

    def events(self, start: date, days: int) -> list[dict]:
        return self._materialize()

    def _event(self, fields: dict, uid: str) -> dict:
        d = date.fromisoformat(fields["date"])
        if fields.get("start_time"):
            hh, mm = map(int, fields["start_time"].split(":"))
            s = datetime(d.year, d.month, d.day, hh, mm, tzinfo=clock.TZ)
            if fields.get("end_time"):
                eh, em = map(int, fields["end_time"].split(":"))
                e = s.replace(hour=eh, minute=em)
            else:
                e = s + timedelta(minutes=int(fields.get("duration_minutes") or 60))
            start, end, all_day = s.isoformat(), e.isoformat(), False
        else:
            start, end, all_day = d.isoformat(), (d + timedelta(days=1)).isoformat(), True
        return {"calendar": fields.get("calendar") or "Family", "title": fields["title"], "when": "", "start": start,
                "end": end, "all_day": all_day, "location": fields.get("location"), "uid": uid, "added_by_house": True}

    def create(self, fields: dict) -> tuple[int, dict]:
        self._n += 1
        ev = self._event(fields, f"fake-new-{self._n}")
        self.extra.append(ev)
        return 200, {"saved": True, "event": ev}

    def find(self, uid: str, start, days) -> dict | None:
        return next((e for e in self._materialize() if e["uid"] == uid), None)

    def update(self, uid: str, fields: dict) -> tuple[int, dict]:
        cur = self.find(uid, None, 0)
        if cur is None:
            return 404, {"detail": f"No House-created event with uid {uid}."}
        if not cur["added_by_house"]:
            return 403, {"detail": "House can only change or delete events it created."}
        new = self._event(fields_from_event(cur) | {k: v for k, v in fields.items() if v is not None}, uid)
        self.extra = [e for e in self.extra if e["uid"] != uid]
        self.deleted.add(uid)  # hides the base copy if it was a fixture event
        self.extra.append(new)
        return 200, {"saved": True, "event": new}

    def delete(self, uid: str) -> tuple[int, dict]:
        if any(e["uid"] == uid for e in self.extra):
            self.extra = [e for e in self.extra if e["uid"] != uid]
            return 204, {}
        match = next((e for e in self._materialize() if e["uid"] == uid), None)
        if match is None:
            return 404, {"detail": "No such event"}
        if not match["added_by_house"]:
            return 403, {"detail": "House can only delete events it created"}
        self.deleted.add(uid)
        return 204, {}


class CalendarService:
    """60 s cache in memory; last good data also kept in SQLite so a restart never blanks the screen."""

    def __init__(self, source, store: Store, ttl: int = 60):
        self.source = source
        self.store = store
        self.ttl = ttl
        self._mem: tuple[str, datetime, list[dict]] | None = None  # (request key, fetched_at, events)

    def invalidate(self) -> None:
        self._mem = None

    def events(self, days: int = 7) -> dict:
        now = clock.now()
        key = f"{now.date().isoformat()}:{days}"
        if self._mem and self._mem[0] == key and (now - self._mem[1]).total_seconds() < self.ttl:
            return {"events": self._mem[2], "fetched_at": self._mem[1], "ok": True}
        try:
            events = self.source.events(now.date(), days)
        except CalendarError:
            return self._stale()
        self._mem = (key, now, events)
        con = self.store.connect()
        try:
            with con:
                con.execute("insert into calendar_cache (key, fetched_at, body) values (?, ?, ?) "
                            "on conflict(key) do update set fetched_at = excluded.fetched_at, body = excluded.body",
                            (CACHE_KEY, now.isoformat(), json.dumps(events)))
        finally:
            con.close()
        return {"events": events, "fetched_at": now, "ok": True}

    def _stale(self) -> dict:
        if self._mem:
            return {"events": self._mem[2], "fetched_at": self._mem[1], "ok": False}
        con = self.store.connect()
        try:
            row = con.execute("select fetched_at, body from calendar_cache where key = ?", (CACHE_KEY,)).fetchone()
        finally:
            con.close()
        if not row:
            return {"events": [], "fetched_at": None, "ok": False}
        return {"events": json.loads(row["body"]), "fetched_at": datetime.fromisoformat(row["fetched_at"]),
                "ok": False}

    def delete(self, uid: str) -> tuple[int, dict]:
        status, body = self.source.delete(uid)
        if status < 300:
            self.invalidate()
        return status, body

    def create(self, fields: dict) -> tuple[int, dict]:
        status, body = self.source.create(fields)
        if status < 300:
            self.invalidate()
        return status, body

    def update(self, uid: str, fields: dict) -> tuple[int, dict]:
        status, body = self.source.update(uid, fields)
        if status < 300:
            self.invalidate()
        return status, body

    def find(self, uid: str) -> dict | None:
        for e in (self._mem[2] if self._mem else []):
            if e["uid"] == uid:
                return e
        return self.source.find(uid, clock.now().date(), 60)


def local(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(clock.TZ)


_local = local


def fields_from_event(ev: dict) -> dict:
    """calendar-api event → NewEvent fields (used to re-create or restore an event on Undo)."""
    out = {"title": ev["title"], "calendar": ev.get("calendar"), "location": ev.get("location")}
    if ev.get("all_day"):
        out["date"] = date.fromisoformat(ev["start"][:10]).isoformat()  # all-day start is a plain date
        return out
    start, end = local(ev["start"]), local(ev.get("end"))
    out |= {"date": start.date().isoformat(), "start_time": start.strftime("%H:%M")}
    if end is not None:
        out["end_time"] = end.strftime("%H:%M")
    return out


def build_week(events: list[dict], now: datetime, colors: dict[str, str], days: int = 7) -> dict:
    today = now.date()
    by_day: dict[date, list[tuple]] = {today + timedelta(days=i): [] for i in range(days)}
    upcoming = []
    for raw in events:
        all_day = bool(raw.get("all_day"))
        start = None if all_day else _local(raw["start"])
        end = None if all_day else _local(raw.get("end"))
        d = date.fromisoformat(raw["start"][:10]) if all_day else start.date()
        if d not in by_day:
            continue
        color = colors.get(raw["calendar"], UNKNOWN_COLOR)
        item = {
            "uid": raw["uid"], "calendar": raw["calendar"], "title": raw["title"],
            "start": start.isoformat() if start else d.isoformat(),
            "end": end.isoformat() if end else None, "all_day": all_day, "location": raw.get("location"),
            "time_label": labels.time_label(start), "relative_label": labels.relative_label(d, start, today),
            "when_label": labels.when_label(d, start, end), "color": color, "ink": labels.ink_for(color),
            "can_delete": bool(raw.get("added_by_house")), "is_today": d == today,
        }
        sort_key = (d, 0 if all_day else 1, start or now, raw["title"])
        by_day[d].append((sort_key, item))
        if (all_day and d == today) or (start is not None and start >= now):
            upcoming.append((sort_key, item))
    day_list = []
    for d, items in by_day.items():
        ordered = [item for _, item in sorted(items, key=lambda x: x[0])]
        day_list.append({"date": d.isoformat(), "dow": d.strftime("%a").upper(), "dow_long": d.strftime("%A").upper(),
                         "day": d.day, "month": d.strftime("%b").upper(), "is_today": d == today,
                         "events": ordered, "more": max(0, len(ordered) - MAX_CHIPS)})
    nxt = [item for _, item in sorted(upcoming, key=lambda x: x[0])[:NEXT_UP]]
    return {"days": day_list, "next": nxt}
