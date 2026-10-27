import pytest

from app import store as st
from app import todos


def ids(con):
    return {r["name"]: r["id"] for r in con.execute("select id, name from people")}


def add(con, now, who, text, date, time=None):
    return todos.create(con, now, person_id=ids(con)[who], text=text, date=date, time=time)


def person(view, name):
    return next(p for p in view["people"] if p["name"] == name)


def test_empty_state(con, freeze):
    now = freeze("2026-10-26T09:00")
    view = todos.today_view(con, now)
    assert view["date"] == "2026-10-26"
    assert [p["name"] for p in view["people"]] == ["Bob", "Belen", "Ben"]
    ben = person(view, "Ben")
    assert ben["state"] == "empty" and ben["todos"] == [] and ben["initial"] == "B"


def test_today_carry_over_and_future(con, freeze):
    now = freeze("2026-10-26T09:00")
    add(con, now, "Bob", "old open", "2026-10-24")
    add(con, now, "Bob", "today", "2026-10-26")
    add(con, now, "Bob", "tomorrow", "2026-10-27")
    bob = person(todos.today_view(con, now), "Bob")
    texts = [t["text"] for t in bob["todos"]]
    assert texts == ["old open", "today"]
    assert bob["todos"][0]["carried"] and bob["todos"][0]["overdue"]
    assert bob["left"] == 2 and bob["overdue"] == 1 and bob["state"] == "open"


def test_timed_item_becomes_overdue(con, freeze):
    now = freeze("2026-10-26T14:30")
    add(con, now, "Bob", "plumber", "2026-10-26", "14:00")
    add(con, now, "Bob", "pick up", "2026-10-26", "17:00")
    bob = person(todos.today_view(con, now), "Bob")
    by = {t["text"]: t for t in bob["todos"]}
    assert by["plumber"]["overdue"] and not by["pick up"]["overdue"]
    assert by["plumber"]["time_label"] == "2:00 PM"


def test_order_overdue_then_timed_then_untimed_then_done(con, freeze):
    now = freeze("2026-10-26T15:00")
    a = add(con, now, "Ben", "untimed", "2026-10-26")
    add(con, now, "Ben", "late", "2026-10-26", "18:00")
    add(con, now, "Ben", "early", "2026-10-26", "16:00")
    add(con, now, "Ben", "overdue", "2026-10-26", "09:00")
    add(con, now, "Ben", "carried", "2026-10-25")
    todos.update(con, now, a["id"], {"done": True})
    ben = person(todos.today_view(con, now), "Ben")
    assert [t["text"] for t in ben["todos"]] == ["carried", "overdue", "early", "late", "untimed"]
    assert ben["todos"][-1]["done"]


def test_done_today_from_old_date_still_shows(con, freeze):
    now = freeze("2026-10-26T10:00")
    t = add(con, now, "Belen", "old", "2026-10-20")
    todos.update(con, now, t["id"], {"done": True})
    belen = person(todos.today_view(con, now), "Belen")
    assert [x["text"] for x in belen["todos"]] == ["old"]
    assert belen["state"] == "all_done" and belen["left"] == 0


def test_done_yesterday_is_hidden(con, freeze):
    yesterday = freeze("2026-10-25T20:00")
    t = add(con, yesterday, "Belen", "done yesterday", "2026-10-25")
    todos.update(con, yesterday, t["id"], {"done": True})
    now = freeze("2026-10-26T08:00")
    assert person(todos.today_view(con, now), "Belen")["state"] == "empty"


def test_undo_restores_open(con, freeze):
    now = freeze("2026-10-26T10:00")
    t = add(con, now, "Bob", "x", "2026-10-26")
    todos.update(con, now, t["id"], {"done": True})
    again = todos.update(con, now, t["id"], {"done": False})
    assert again["done"] is False and again["date"] == "2026-10-26"


def test_writes_bump_changes(con, freeze):
    now = freeze("2026-10-26T10:00")
    t = add(con, now, "Bob", "x", "2026-10-26")
    todos.update(con, now, t["id"], {"text": "y"})
    todos.delete(con, t["id"])
    assert st.changes(con) == 3


def test_errors(con, freeze):
    now = freeze("2026-10-26T10:00")
    with pytest.raises(LookupError):
        todos.create(con, now, person_id=999, text="x", date="2026-10-26", time=None)
    with pytest.raises(KeyError):
        todos.update(con, now, 999, {"text": "x"})
    assert todos.delete(con, 999) is False


def test_move_to_other_person(con, freeze):
    now = freeze("2026-10-26T10:00")
    t = add(con, now, "Bob", "x", "2026-10-26")
    moved = todos.update(con, now, t["id"], {"person_id": ids(con)["Ben"], "time": "15:30"})
    assert moved["person_id"] == ids(con)["Ben"] and moved["time"] == "15:30"


def test_new_todo_after_all_done_reopens_the_list(con, freeze):
    now = freeze("2026-10-26T09:00")
    t = add(con, now, "Bob", "dishes", "2026-10-26")
    todos.update(con, now, t["id"], {"done": True})
    assert person(todos.today_view(con, now), "Bob")["state"] == "all_done"
    add(con, now, "Bob", "laundry", "2026-10-26")
    bob = person(todos.today_view(con, now), "Bob")
    assert bob["state"] == "open" and bob["left"] == 1
    assert [x["text"] for x in bob["todos"]] == ["laundry", "dishes"]
