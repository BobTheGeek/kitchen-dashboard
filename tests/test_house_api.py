import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from tests.fakes import FakeSource, ev

TOKEN = "t0ken"
AUTH = {"Authorization": f"Bearer {TOKEN}", "X-Talk-Session": "s1"}


@pytest.fixture
def src():
    return FakeSource([ev("Family", "Soccer", "2026-10-27T17:30:00-05:00", uid="u1"),
                       ev("Family", "House thing", "2026-10-28T10:00:00-05:00", "2026-10-28T11:00:00-05:00",
                          uid="h1", house=True)])


@pytest.fixture
def client(tmp_path, src, freeze):
    freeze("2026-10-27T09:00")
    return TestClient(create_app(db_path=str(tmp_path / "h.db"), source=src, version="t", house_token=TOKEN))


def test_token_required(client):
    assert client.get("/api/house/calendars").status_code == 401
    assert client.get("/api/house/calendars", headers={"Authorization": "Bearer nope"}).status_code == 401


@pytest.mark.parametrize("value", [b"Bearer \xe9", "Basic x", "Bearer", "Bearer "])
def test_malformed_authorization_is_401(client, value):
    assert client.get("/api/house/calendars", headers={"Authorization": value}).status_code == 401


def test_not_configured(tmp_path, src, freeze):
    freeze("2026-10-27T09:00")
    c = TestClient(create_app(db_path=str(tmp_path / "n.db"), source=src, version="t", house_token=""))
    r = c.get("/api/house/calendars", headers=AUTH)
    assert r.status_code == 503 and "not set up" in r.json()["detail"]


def test_add_todo_logs_and_undo(client):
    r = client.post("/api/house/todos", headers=AUTH, json={"person": "ben", "text": "Feed Milo"})
    assert r.status_code == 201
    todo = r.json()
    assert todo["person"] == "Ben" and todo["created_by"] == "house" and todo["date"] == "2026-10-27"
    changes = client.get("/api/talk/sessions/s1").json()["changes"]
    assert [(c["verb"], c["title"], c["person"]) for c in changes] == [("ADDED", "Feed Milo", "Ben")]
    assert client.post(f"/api/talk/actions/{changes[0]['id']}/undo").json() == {"ok": True}
    ben = next(p for p in client.get("/api/today").json()["people"] if p["name"] == "Ben")
    assert ben["todos"] == []


def test_unknown_person(client):
    r = client.post("/api/house/todos", headers=AUTH, json={"person": "Ana", "text": "x"})
    assert r.status_code == 404 and "Bob, Belen and Ben" in r.json()["detail"]


def test_done_reopen_delete_and_undo(client):
    tid = client.post("/api/house/todos", headers=AUTH, json={"person": "Bob", "text": "Call"}).json()["id"]
    assert client.post(f"/api/house/todos/{tid}/done", headers=AUTH).json()["done"] is True
    assert client.post(f"/api/house/todos/{tid}/reopen", headers=AUTH).json()["done"] is False
    assert client.delete(f"/api/house/todos/{tid}", headers=AUTH).status_code == 200
    removed = client.get("/api/talk/sessions/s1").json()["changes"][-1]
    assert removed["verb"] == "REMOVED"
    client.post(f"/api/talk/actions/{removed['id']}/undo")
    bob = next(p for p in client.get("/api/today").json()["people"] if p["name"] == "Bob")
    assert [t["text"] for t in bob["todos"]] == ["Call"]
    assert client.post("/api/house/todos/999/done", headers=AUTH).status_code == 404


def test_list_todos(client):
    client.post("/api/house/todos", headers=AUTH, json={"person": "Ben", "text": "Homework", "time": "16:00"})
    body = client.get("/api/house/todos", headers=AUTH, params={"person": "Ben"}).json()
    assert body["person"] == "Ben" and body["todos"][0]["time_label"] == "4:00 PM"


def test_add_event_logs_inverse(client, src):
    src.create_result = (200, {"saved": True, "event": ev("Benny Time", "Dentist", "2026-10-29T16:00:00-05:00",
                                                           uid="n1", house=True)})
    r = client.post("/api/house/events", headers=AUTH, json={"title": "Dentist", "date": "2026-10-29",
                                                             "start_time": "16:00", "calendar": "Benny Time"})
    assert r.status_code == 200 and src.created[0]["calendar"] == "Benny Time"
    c = client.get("/api/talk/sessions/s1").json()["changes"][0]
    assert (c["verb"], c["detail"], c["calendar"], c["ref"]) == ("ADDED", "THU 29 · 4:00 PM", "Benny Time", "n1")
    client.post(f"/api/talk/actions/{c['id']}/undo")
    assert src.deleted == ["n1"]


def test_update_and_delete_event_inverse(client, src):
    src.update_result = (200, {"saved": True, "event": ev("Family", "House thing", "2026-10-28T12:00:00-05:00",
                                                          uid="h1", house=True)})
    client.patch("/api/house/events/h1", headers=AUTH, json={"start_time": "12:00"})
    changed = client.get("/api/talk/sessions/s1").json()["changes"][0]
    client.post(f"/api/talk/actions/{changed['id']}/undo")
    assert src.updated[-1] == ("h1", {"title": "House thing", "location": None, "date": "2026-10-28",
                                      "start_time": "10:00", "end_time": "11:00"})
    src.delete_result = (200, {"deleted": True, "title": "House thing", "when": "Wed"})
    assert client.delete("/api/house/events/h1", headers=AUTH).status_code == 200
    removed = client.get("/api/talk/sessions/s1").json()["changes"][-1]
    client.post(f"/api/talk/actions/{removed['id']}/undo")
    assert src.created[-1]["title"] == "House thing" and src.created[-1]["start_time"] == "10:00"


def test_calendar_refusal_passes_through_and_is_not_logged(client, src):
    src.update_result = (403, {"detail": "House can only change or delete events it created."})
    r = client.patch("/api/house/events/u1", headers=AUTH, json={"title": "x"})
    assert r.status_code == 403 and "House can only" in r.json()["detail"]
    assert client.get("/api/talk/sessions/s1").json()["changes"] == []


def test_undo_twice_and_unknown(client):
    tid = client.post("/api/house/todos", headers=AUTH, json={"person": "Bob", "text": "x"}).json()["id"]
    assert tid
    aid = client.get("/api/talk/sessions/s1").json()["changes"][0]["id"]
    assert client.post(f"/api/talk/actions/{aid}/undo").json() == {"ok": True}
    assert client.post(f"/api/talk/actions/{aid}/undo").json() == {"ok": True}
    assert client.post("/api/talk/actions/999/undo").status_code == 409
