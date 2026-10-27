"""
title: Household Calendar
author: household-ai
description: Read the family calendars and add or change events (House may change or delete only events it created).
version: 0.1.0
"""
import json
import urllib.error
import urllib.parse
import urllib.request

from pydantic import BaseModel, Field

_open = urllib.request.urlopen


class Tools:
    class Valves(BaseModel):
        dashboard_url: str = Field("http://kitchen-dashboard:8000", description="Kitchen dashboard base URL")
        token: str = Field("", description="House tools token (~/household-ai/secrets/kitchen/house_token)")

    def __init__(self):
        self.valves = self.Valves()

    def _call(self, method: str, path: str, body: dict | None = None, metadata: dict | None = None):
        headers = {"Authorization": f"Bearer {self.valves.token}"}
        sid = (metadata or {}).get("session_id")
        if sid:
            headers["X-Talk-Session"] = str(sid)
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.valves.dashboard_url.rstrip("/") + path, data=data, method=method,
                                     headers=headers)
        try:
            with _open(req, timeout=20) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            except ValueError:
                return e.code, {"detail": str(e.reason)}
        except Exception:
            return 0, {}

    @staticmethod
    def _err(status: int, body: dict) -> str:
        if status in (0, 401, 503):
            return "I can't reach the kitchen dashboard right now, so I couldn't do that."
        detail = body.get("detail")
        if isinstance(detail, list):
            detail = "; ".join(str(x.get("msg", "")) for x in detail)
        return f"That didn't work: {detail or 'unknown error'}"

    def list_calendars(self, __metadata__: dict = None) -> str:
        """
        List the family calendars and what each one is for. Use it to pick the right calendar.
        """
        status, body = self._call("GET", "/api/house/calendars", metadata=__metadata__)
        if status != 200:
            return self._err(status, body)
        lines = [f"- {c['name']}: {c.get('purpose', '')}" for c in body.get("calendars", [])]
        return f"Default calendar: {body.get('default', 'Family')}\n" + "\n".join(lines)

    def list_events(self, start_date: str = "", days: int = 7, __metadata__: dict = None) -> str:
        """
        List events from a start day.
        :param start_date: First day as YYYY-MM-DD; empty for today.
        :param days: How many days to include (1-60).
        """
        query = {"days": days} | ({"start": start_date} if start_date else {})
        status, body = self._call("GET", "/api/house/events?" + urllib.parse.urlencode(query), metadata=__metadata__)
        if status != 200:
            return self._err(status, body)
        events = body.get("events", [])
        if not events:
            return "Nothing on the calendar in that range."
        return "\n".join(f"- {e.get('when') or e['start']} | {e['title']} | {e['calendar']} | uid {e['uid']}"
                         + (" | made by House" if e.get("added_by_house") else "") for e in events)

    def add_event(self, title: str, date: str, start_time: str = "", end_time: str = "", duration_minutes: int = 60,
                  calendar: str = "", location: str = "", __metadata__: dict = None) -> str:
        """
        Add an event to a family calendar.
        :param title: Short title, e.g. "Dentist · Ben".
        :param date: Day as YYYY-MM-DD.
        :param start_time: 24-hour HH:MM; leave empty for an all-day event.
        :param end_time: 24-hour HH:MM; leave empty to use duration_minutes.
        :param duration_minutes: Length when end_time is empty (default 60).
        :param calendar: Calendar name from list_calendars; empty for the default (Family).
        :param location: Optional place.
        """
        body = {"title": title, "date": date}
        if start_time:
            body["start_time"] = start_time
            if end_time:
                body["end_time"] = end_time
            else:
                body["duration_minutes"] = int(duration_minutes or 60)
        if calendar:
            body["calendar"] = calendar
        if location:
            body["location"] = location
        status, res = self._call("POST", "/api/house/events", body, __metadata__)
        if status != 200:
            return self._err(status, res)
        e = res.get("event", {})
        return (f"Added “{e.get('title', title)}” to {e.get('calendar', calendar or 'Family')} "
                f"({e.get('when', date)}), uid {e.get('uid')}.")

    def update_event(self, uid: str, title: str = "", date: str = "", start_time: str = "", end_time: str = "",
                     location: str = "", __metadata__: dict = None) -> str:
        """
        Change an event the House created. Leave a field empty to keep it.
        :param uid: The event uid from list_events.
        """
        body = {k: v for k, v in {"title": title, "date": date, "start_time": start_time, "end_time": end_time,
                                  "location": location}.items() if v}
        status, res = self._call("PATCH", f"/api/house/events/{urllib.parse.quote(uid, safe='')}", body, __metadata__)
        if status != 200:
            return self._err(status, res)
        e = res.get("event", {})
        return f"Changed “{e.get('title', '')}” ({e.get('when', '')})."

    def delete_event(self, uid: str, __metadata__: dict = None) -> str:
        """
        Delete an event the House created.
        :param uid: The event uid from list_events.
        """
        status, res = self._call("DELETE", f"/api/house/events/{urllib.parse.quote(uid, safe='')}",
                                 metadata=__metadata__)
        if status not in (200, 204):
            return self._err(status, res)
        return f"Removed “{res.get('title', 'the event')}”."
