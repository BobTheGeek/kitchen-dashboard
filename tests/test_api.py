import logging

import pytest
from fastapi.testclient import TestClient

from app.api import QuietPolls, create_app
from tests.fakes import FakeSource, ev


@pytest.fixture
def src():
    return FakeSource([ev("Family", "Soccer", "2026-10-26T17:30:00-05:00", uid="u1"),
                       ev("Family", "House thing", "2026-10-27T10:00:00-05:00", uid="h1", house=True)])


@pytest.fixture
def client(tmp_path, src, freeze):
    freeze("2026-10-26T15:00")
    return TestClient(create_app(db_path=str(tmp_path / "api.db"), source=src, version="abc123"))


def people(client):
    return {p["name"]: p["id"] for p in client.get("/api/settings").json()["people"]}


def test_page_and_version(client):
    r = client.get("/")
    assert r.status_code == 200 and "<title>Kitchen</title>" in r.text
    assert r.headers["cache-control"] == "no-cache"
    assert client.get("/api/version").json() == {"version": "abc123"}


def test_client_error_is_logged(client, caplog):
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        r = client.post("/api/client-error", json={"message": "TypeError: x is undefined", "where": "talk-wall.js:9:1"})
    assert r.status_code == 204
    assert "TypeError: x is undefined" in caplog.text and "talk-wall.js:9:1" in caplog.text
    assert client.post("/api/client-error", json={"message": "x" * 2001}).status_code == 422


def test_week(client):
    w = client.get("/api/week").json()
    assert len(w["days"]) == 7 and w["calendar_ok"] is True and w["fetched_at"].startswith("2026-10-26T15:00")
    assert w["days"][0]["events"][0]["title"] == "Soccer"
    assert w["next"][0]["relative_label"] == "Today, 5:30 PM"
    assert w["calendars"] == [{"name": "Family", "color": "#f2c230", "ink": "#1c1b1f"}]


def test_week_when_calendar_down(client, src):
    src.fail = True
    w = client.get("/api/week").json()
    assert w["calendar_ok"] is False and w["fetched_at"] is None and len(w["days"]) == 7


def test_todo_roundtrip_and_changes(client):
    n0 = client.get("/api/changes").json()["n"]
    bob = people(client)["Bob"]
    r = client.post("/api/todos", json={"person_id": bob, "text": "  Call the plumber ", "date": "2026-10-26",
                                        "time": "14:00"})
    assert r.status_code == 201
    todo = r.json()
    assert todo["text"] == "Call the plumber" and todo["created_by"] == "phone"
    assert client.get("/api/changes").json()["n"] == n0 + 1
    today = client.get("/api/today").json()
    bob_card = next(p for p in today["people"] if p["name"] == "Bob")
    assert bob_card["todos"][0]["overdue"] is True and bob_card["overdue"] == 1
    assert client.patch(f"/api/todos/{todo['id']}", json={"done": True}).json()["done"] is True
    assert client.patch(f"/api/todos/{todo['id']}", json={"time": None}).json()["time"] is None
    assert client.delete(f"/api/todos/{todo['id']}").status_code == 204
    assert client.delete(f"/api/todos/{todo['id']}").status_code == 404


def test_todo_validation(client):
    bob = people(client)["Bob"]
    assert client.post("/api/todos", json={"person_id": bob, "text": "   ", "date": "2026-10-26"}).status_code == 422
    assert client.post("/api/todos", json={"person_id": bob, "text": "x", "date": "2026-10-26",
                                           "time": "25:00"}).status_code == 422
    assert client.post("/api/todos", json={"person_id": 999, "text": "x", "date": "2026-10-26"}).status_code == 422
    assert client.post("/api/todos", json={"person_id": bob, "text": "x" * 121, "date": "2026-10-26"}).status_code \
        == 422
    assert client.patch("/api/todos/999", json={"text": "x"}).status_code == 404


def test_house_can_create(client):
    ben = people(client)["Ben"]
    r = client.post("/api/todos", json={"person_id": ben, "text": "Feed Milo", "date": "2026-10-26",
                                        "created_by": "house"})
    assert r.json()["created_by"] == "house"


def test_settings(client):
    client.get("/api/week")  # registers Family
    r = client.put("/api/settings/calendars/Family", json={"color": "#2B5FD9"})
    assert r.json() == {"name": "Family", "color": "#2b5fd9", "ink": "#fff"}
    assert client.put("/api/settings/calendars/Family", json={"color": "blue"}).status_code == 422
    ben = people(client)["Ben"]
    assert client.patch(f"/api/settings/people/{ben}", json={"name": "Benny"}).json()["name"] == "Benny"
    assert client.patch("/api/settings/people/999", json={"name": "x"}).status_code == 404


def test_family_is_fixed_at_three(client):
    """The family is always Bob, Belen and Ben: people can be renamed, never added or removed."""
    assert client.post("/api/settings/people", json={"name": "Ana"}).status_code in (404, 405)
    assert client.delete(f"/api/settings/people/{people(client)['Ben']}").status_code in (404, 405)
    assert list(people(client)) == ["Bob", "Belen", "Ben"]


def test_delete_event_passthrough(client, src):
    assert client.delete("/api/events/h1").status_code == 204
    src.delete_result = (403, {"detail": "House can only delete events it created"})
    r = client.delete("/api/events/u1")
    assert r.status_code == 403 and r.json()["detail"] == "House can only delete events it created"


def test_quiet_polls_filter():
    f = QuietPolls()

    def rec(path):
        return logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                                 ("127.0.0.1:1", "GET", path, "1.1", 200), None)
    assert f.filter(rec("/api/changes")) is False
    assert f.filter(rec("/api/version?x=1")) is False
    assert f.filter(rec("/api/week")) is True


def photo_client(tmp_path, src, photos_dir):
    return TestClient(create_app(db_path=str(tmp_path / "p.db"), source=src, version="v", photos_dir=photos_dir))


def test_photos_list_and_file(tmp_path, src, freeze):
    folder = tmp_path / "photos"
    folder.mkdir()
    (folder / "abc-1.jpg").write_bytes(b"\xff\xd8\xffjpeg")
    (folder / "notes.txt").write_text("x")
    c = photo_client(tmp_path, src, str(folder))
    freeze("2026-10-27T10:00")
    body = c.get("/api/photos").json()
    assert [p["name"] for p in body["photos"]] == ["abc-1.jpg"] and body["active"] is True
    assert isinstance(body["photos"][0]["v"], int)
    freeze("2026-10-27T21:30")
    assert c.get("/api/photos").json()["active"] is False
    r = c.get("/photos/abc-1.jpg?v=1")
    assert r.status_code == 200 and r.content == b"\xff\xd8\xffjpeg"
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_photos_refuses_bad_names(tmp_path, src):
    folder = tmp_path / "photos"
    folder.mkdir()
    (tmp_path / "secret.jpg").write_bytes(b"x")
    (folder / "notes.png").write_bytes(b"x")
    c = photo_client(tmp_path, src, str(folder))
    for path in ("/photos/..%2Fsecret.jpg", "/photos/%2e%2e%2fsecret.jpg", "/photos/notes.png", "/photos/missing.jpg"):
        assert c.get(path).status_code == 404, path


def test_photos_without_folder(tmp_path, src):
    c = photo_client(tmp_path, src, None)
    assert c.get("/api/photos").json()["photos"] == []
    assert c.get("/photos/a.jpg").status_code == 404
