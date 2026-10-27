from app import actions


def rec(con, now, sid="s1", **kw):
    base = dict(session_id=sid, kind="todo", verb="ADDED", title="Feed Milo", detail="TUE 27", ref="5",
                person="Ben", inverse={"op": "delete_todo", "id": 5})
    return actions.record(con, now, **(base | kw))


def test_record_and_get(con, freeze):
    now = freeze("2026-10-27T09:00")
    a = rec(con, now)
    got = actions.get(con, a["id"])
    assert got["inverse"] == {"op": "delete_todo", "id": 5} and got["undone_at"] is None
    assert got["created_at"].startswith("2026-10-27T09:00") and got["ref"] == "5"


def test_for_session_and_after(con, freeze):
    now = freeze("2026-10-27T09:00")
    a1 = rec(con, now)
    rec(con, now, sid="other")
    a3 = rec(con, now, title="Second")
    assert [a["title"] for a in actions.for_session(con, "s1")] == ["Feed Milo", "Second"]
    assert [a["id"] for a in actions.for_session(con, "s1", after_id=a1["id"])] == [a3["id"]]


def test_claim_unattributed(con, freeze):
    now = freeze("2026-10-27T09:00")
    before = actions.last_id(con)
    rec(con, now, sid=None)
    assert actions.claim_unattributed(con, "s2", before) == 1
    assert [a["session_id"] for a in actions.for_session(con, "s2")] == ["s2"]


def test_mark_undone_and_no_inverse(con, freeze):
    now = freeze("2026-10-27T09:00")
    a = rec(con, now, inverse=None)
    assert actions.get(con, a["id"])["inverse"] is None
    actions.mark_undone(con, a["id"], now)
    assert actions.get(con, a["id"])["undone_at"] is not None
    assert actions.get(con, 999) is None
