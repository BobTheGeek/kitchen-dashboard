import importlib.util
import io
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from tests.fakes import FakeSource, ev

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "t0ken"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "house_tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Resp(io.BytesIO):
    def __init__(self, status, data):
        super().__init__(data)
        self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): return False


@pytest.fixture
def wired(tmp_path, freeze):
    freeze("2026-10-27T09:00")
    src = FakeSource([ev("Family", "House thing", "2026-10-28T10:00:00-05:00", uid="h1", house=True)])
    client = TestClient(create_app(db_path=str(tmp_path / "x.db"), source=src, version="t", house_token=TOKEN))

    def route(req, timeout):
        path = req.full_url.replace("http://kitchen-dashboard:8000", "")
        r = client.request(req.get_method(), path, content=req.data, headers=dict(req.header_items()))
        if r.status_code >= 400:
            raise urllib.error.HTTPError(req.full_url, r.status_code, "err", {}, io.BytesIO(r.content))
        return Resp(r.status_code, r.content)

    tools = {}
    for name in ("household_todos", "household_calendar"):
        mod = load(name)
        mod._open = route
        t = mod.Tools()
        t.valves.token = TOKEN
        tools[name] = t
    return client, src, tools


META = {"session_id": "s1"}


def test_todo_tool_roundtrip(wired):
    client, _, tools = wired
    t = tools["household_todos"]
    out = t.add_todo("ben", "Feed Milo", __metadata__=META)
    assert out.startswith("Added TODO #") and "Ben" in out and "Feed Milo" in out
    assert "Feed Milo" in t.list_todos("Ben", __metadata__=META)
    tid = int(out.split("#")[1].split()[0])
    assert "Done" in t.complete_todo(tid, __metadata__=META)
    assert "[x]" in t.list_todos("Ben")
    assert "Removed" in t.delete_todo(tid, __metadata__=META)
    verbs = [c["verb"] for c in client.get("/api/talk/sessions/s1").json()["changes"]]
    assert verbs == ["ADDED", "DONE", "REMOVED"]


def test_todo_tool_errors(wired):
    _, _, tools = wired
    t = tools["household_todos"]
    assert "Bob, Belen and Ben" in t.add_todo("Ana", "x")
    t.valves.token = "wrong"
    assert "can't reach the kitchen dashboard" in t.list_todos("Ben")


def test_calendar_tool(wired):
    _, src, tools = wired
    c = tools["household_calendar"]
    src.create_result = (200, {"saved": True, "event": ev("Benny Time", "Dentist", "2026-10-29T16:00:00-05:00",
                                                           uid="n1", house=True) | {"when": "Thu 29 Oct, 4:00 PM"}})
    out = c.add_event("Dentist", "2026-10-29", start_time="16:00", calendar="Benny Time", __metadata__=META)
    assert "Added" in out and "Dentist" in out and "n1" in out
    assert src.created[0] == {"title": "Dentist", "date": "2026-10-29", "start_time": "16:00",
                              "duration_minutes": 60, "calendar": "Benny Time"}
    assert "House thing" in c.list_events("2026-10-27", 7)
    src.update_result = (403, {"detail": "House can only change or delete events it created."})
    assert "House can only" in c.update_event("zzz", title="x")
    assert "Family" in c.list_calendars()
