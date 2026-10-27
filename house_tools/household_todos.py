"""
title: Household TODOs
author: household-ai
description: Read and change the family's daily TODO lists (Bob, Belen, Ben) shown on the kitchen screen.
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

    def list_todos(self, person: str, __metadata__: dict = None) -> str:
        """
        List today's TODOs for one person, including open items carried over from earlier days.
        :param person: Bob, Belen or Ben.
        """
        status, body = self._call("GET", "/api/house/todos?" + urllib.parse.urlencode({"person": person}),
                                  metadata=__metadata__)
        if status != 200:
            return self._err(status, body)
        if not body["todos"]:
            return f"{body['person']} has nothing on the list today."
        lines = []
        for t in body["todos"]:
            line = f"- [{'x' if t['done'] else ' '}] #{t['id']} {t['text']}"
            if t.get("time_label"):
                line += f" at {t['time_label']}"
            if t.get("overdue"):
                line += " (overdue)"
            lines.append(line)
        return f"{body['person']}'s TODOs today:\n" + "\n".join(lines)

    def add_todo(self, person: str, text: str, date: str = "", time: str = "", __metadata__: dict = None) -> str:
        """
        Add a TODO to one person's list.
        :param person: Bob, Belen or Ben.
        :param text: What to do, short (e.g. "Feed Milo").
        :param date: Day as YYYY-MM-DD; leave empty for today.
        :param time: Optional 24-hour time HH:MM.
        """
        body = {"person": person, "text": text}
        if date:
            body["date"] = date
        if time:
            body["time"] = time
        status, res = self._call("POST", "/api/house/todos", body, __metadata__)
        if status not in (200, 201):
            return self._err(status, res)
        when = res["date"] + (f" at {res['time']}" if res.get("time") else "")
        return f"Added TODO #{res['id']} for {res['person']}: “{res['text']}” on {when}."

    def _set(self, todo_id: int, action: str, metadata: dict | None) -> str:
        status, res = self._call("POST", f"/api/house/todos/{int(todo_id)}/{action}", metadata=metadata)
        if status != 200:
            return self._err(status, res)
        return f"{'Done' if action == 'done' else 'Reopened'}: #{res['id']} “{res['text']}” for {res['person']}."

    def complete_todo(self, todo_id: int, __metadata__: dict = None) -> str:
        """
        Check off a TODO. Use list_todos first to find its number.
        :param todo_id: The TODO number, e.g. 12.
        """
        return self._set(todo_id, "done", __metadata__)

    def reopen_todo(self, todo_id: int, __metadata__: dict = None) -> str:
        """
        Mark a checked-off TODO as not done again.
        :param todo_id: The TODO number.
        """
        return self._set(todo_id, "reopen", __metadata__)

    def delete_todo(self, todo_id: int, __metadata__: dict = None) -> str:
        """
        Remove a TODO from a list.
        :param todo_id: The TODO number.
        """
        status, res = self._call("DELETE", f"/api/house/todos/{int(todo_id)}", metadata=__metadata__)
        if status != 200:
            return self._err(status, res)
        return f"Removed #{res['id']} “{res['text']}” from {res['person']}'s list."
