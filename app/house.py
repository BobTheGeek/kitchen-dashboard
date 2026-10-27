"""What the House may do through the dashboard: calendar and TODO writes, each logged with its inverse for Undo."""
import sqlite3
from datetime import date, datetime, time

from app import actions, labels, settings, todos
from app.calendar import CalendarError, CalendarService, fields_from_event, local


def event_detail(ev: dict) -> str:
    if ev.get("all_day"):
        return labels.chip_detail(date.fromisoformat(ev["start"][:10]), None) + " · ALL DAY"
    start = local(ev["start"])
    return labels.chip_detail(start.date(), start)


def todo_detail(item: dict) -> str:
    at = time.fromisoformat(item["time"]) if item.get("time") else None
    return labels.chip_detail(date.fromisoformat(item["date"]), at)


class HouseOps:
    def __init__(self, cal: CalendarService):
        self.cal = cal

    def person_name(self, con: sqlite3.Connection, person_id: int) -> str:
        return next((p["name"] for p in settings.people(con) if p["id"] == person_id), "?")

    def _find(self, uid: str) -> dict | None:
        try:
            return self.cal.find(uid)
        except CalendarError:
            return None

    def add_event(self, con, now: datetime, sid: str | None, fields: dict) -> tuple[int, dict]:
        status, body = self.cal.create(fields)
        if status < 300:
            ev = body.get("event") or {}
            actions.record(con, now, session_id=sid, kind="event", verb="ADDED", title=ev.get("title", fields["title"]),
                           detail=event_detail(ev) if ev.get("start") else "", ref=ev.get("uid"),
                           calendar=ev.get("calendar"),
                           inverse={"op": "delete_event", "uid": ev["uid"]} if ev.get("uid") else None)
        return status, body

    def update_event(self, con, now: datetime, sid: str | None, uid: str, fields: dict) -> tuple[int, dict]:
        before = self._find(uid)
        status, body = self.cal.update(uid, fields)
        if status < 300:
            ev = body.get("event") or before or {}
            inverse = None
            if before:
                restore = fields_from_event(before)
                restore.pop("calendar", None)  # PATCH cannot move calendars
                inverse = {"op": "update_event", "uid": uid, "fields": restore}
            actions.record(con, now, session_id=sid, kind="event", verb="CHANGED", title=ev.get("title", "event"),
                           detail=event_detail(ev) if ev.get("start") else "", ref=uid, calendar=ev.get("calendar"),
                           inverse=inverse)
        return status, body

    def delete_event(self, con, now: datetime, sid: str | None, uid: str) -> tuple[int, dict]:
        before = self._find(uid)
        status, body = self.cal.delete(uid)
        if status < 300:
            actions.record(con, now, session_id=sid, kind="event", verb="REMOVED",
                           title=(before or {}).get("title") or body.get("title", "event"),
                           detail=event_detail(before) if before else body.get("when", ""), ref=uid,
                           calendar=(before or {}).get("calendar"),
                           inverse={"op": "create_event", "fields": fields_from_event(before)} if before else None)
        return status, body

    def add_todo(self, con, now: datetime, sid: str | None, *, person: str, text: str, date: str,
                 time: str | None = None) -> dict:
        p = next((p for p in settings.people(con) if p["name"].lower() == person.strip().lower()), None)
        if p is None:
            raise LookupError(f"No one called {person}. The family is Bob, Belen and Ben.")
        item = todos.create(con, now, person_id=p["id"], text=text, date=date, time=time, created_by="house")
        actions.record(con, now, session_id=sid, kind="todo", verb="ADDED", title=item["text"],
                       detail=todo_detail(item), ref=str(item["id"]), person=p["name"],
                       inverse={"op": "delete_todo", "id": item["id"]})
        return item | {"person": p["name"]}

    def set_todo_done(self, con, now: datetime, sid: str | None, todo_id: int, done: bool) -> dict:
        before = todos.get(con, todo_id)
        if before is None:
            raise KeyError(todo_id)
        item = todos.update(con, now, todo_id, {"done": done})
        name = self.person_name(con, item["person_id"])
        actions.record(con, now, session_id=sid, kind="todo", verb="DONE" if done else "REOPENED",
                       title=item["text"], detail=todo_detail(item), ref=str(todo_id), person=name,
                       inverse={"op": "set_todo_done", "id": todo_id, "done": before["done"]})
        return item | {"person": name}

    def delete_todo(self, con, now: datetime, sid: str | None, todo_id: int) -> dict:
        before = todos.get(con, todo_id)
        if before is None:
            raise KeyError(todo_id)
        todos.delete(con, todo_id)
        name = self.person_name(con, before["person_id"])
        actions.record(con, now, session_id=sid, kind="todo", verb="REMOVED", title=before["text"],
                       detail=todo_detail(before), ref=str(todo_id), person=name,
                       inverse={"op": "create_todo", "person_id": before["person_id"], "text": before["text"],
                                "date": before["date"], "time": before["time"], "done": before["done"]})
        return before | {"person": name}

    def undo(self, con, now: datetime, action_id: int) -> tuple[bool, str]:
        a = actions.get(con, action_id)
        if a is None:
            return False, "No such change"
        if a["undone_at"]:
            return True, "Already undone"
        inv = a["inverse"]
        if inv is None:
            return False, "This change can't be undone here"
        status, body = 200, {}
        op = inv["op"]
        if op == "delete_event":
            status, body = self.cal.delete(inv["uid"])
        elif op == "update_event":
            status, body = self.cal.update(inv["uid"], inv["fields"])
        elif op == "create_event":
            status, body = self.cal.create(inv["fields"])
        elif op == "delete_todo":
            if not todos.delete(con, inv["id"]):
                status, body = 404, {"detail": "That TODO is already gone"}
        elif op == "set_todo_done":
            try:
                todos.update(con, now, inv["id"], {"done": inv["done"]})
            except KeyError:
                status, body = 404, {"detail": "That TODO is gone"}
        elif op == "create_todo":
            item = todos.create(con, now, person_id=inv["person_id"], text=inv["text"], date=inv["date"],
                                time=inv["time"], created_by="house")
            if inv["done"]:
                todos.update(con, now, item["id"], {"done": True})
        else:
            return False, "Unknown change"
        if status >= 300:
            return False, body.get("detail", "Couldn't undo")
        actions.mark_undone(con, action_id, now)
        return True, "Undone"
