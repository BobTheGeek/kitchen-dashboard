"""Daily TODOs per person: what today's list holds, its order, and its counts."""
import sqlite3
from datetime import datetime

from app import labels
from app import store as st

FIELDS = ("text", "person_id", "date", "time", "done")


def _item(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "person_id": row["person_id"], "text": row["text"],
        "date": row["date"], "time": row["time"], "time_label": labels.todo_time_label(row["time"]),
        "done": row["done_at"] is not None, "created_by": row["created_by"],
    }


def get(con: sqlite3.Connection, todo_id: int) -> dict | None:
    row = con.execute("select * from todos where id = ?", (todo_id,)).fetchone()
    return _item(row) if row else None


def today_view(con: sqlite3.Connection, now: datetime) -> dict:
    today, hhmm = now.date().isoformat(), now.strftime("%H:%M")
    rows = con.execute(
        """select * from todos
           where (done_at is null and date <= ?) or (done_at is not null and substr(done_at, 1, 10) = ?)""",
        (today, today)).fetchall()
    by_person: dict[int, list[dict]] = {}
    for row in rows:
        item = _item(row)
        open_ = not item["done"]
        item["carried"] = open_ and item["date"] < today
        item["overdue"] = open_ and (item["carried"] or (item["date"] == today and bool(item["time"])
                                                          and item["time"] < hhmm))
        item["_done_at"] = row["done_at"]
        by_person.setdefault(item["person_id"], []).append(item)

    def order(t: dict) -> tuple:
        if t["done"]:
            return (3, t["_done_at"], "", t["id"])
        if t["overdue"]:
            return (0, t["date"], t["time"] or "", t["id"])
        if t["time"]:
            return (1, t["time"], "", t["id"])
        return (2, "", "", t["id"])

    people = []
    for p in con.execute("select id, name from people order by sort, id"):
        items = sorted(by_person.get(p["id"], []), key=order)
        for t in items:
            del t["_done_at"]
        left = sum(not t["done"] for t in items)
        state = "empty" if not items else "all_done" if left == 0 else "open"
        people.append({"id": p["id"], "name": p["name"], "initial": p["name"][:1].upper(), "todos": items,
                       "left": left, "overdue": sum(t["overdue"] for t in items), "state": state})
    return {"date": today, "people": people}


def _check_person(con: sqlite3.Connection, person_id: int) -> None:
    if not con.execute("select 1 from people where id = ?", (person_id,)).fetchone():
        raise LookupError("unknown person")


def create(con: sqlite3.Connection, now: datetime, *, person_id: int, text: str, date: str,
           time: str | None, created_by: str = "phone") -> dict:
    _check_person(con, person_id)
    with con:
        cur = con.execute(
            "insert into todos (person_id, text, date, time, created_by, created_at) values (?, ?, ?, ?, ?, ?)",
            (person_id, text, date, time, created_by, now.isoformat(timespec="seconds")))
        st.bump(con)
    return get(con, cur.lastrowid)


def update(con: sqlite3.Connection, now: datetime, todo_id: int, fields: dict) -> dict:
    if get(con, todo_id) is None:
        raise KeyError(todo_id)
    if "person_id" in fields:
        _check_person(con, fields["person_id"])
    sets, values = [], []
    for key in FIELDS:
        if key not in fields:
            continue
        if key == "done":
            sets.append("done_at = ?")
            values.append(now.isoformat(timespec="seconds") if fields["done"] else None)
        else:
            sets.append(f"{key} = ?")
            values.append(fields[key])
    if sets:
        with con:
            con.execute(f"update todos set {', '.join(sets)} where id = ?", (*values, todo_id))
            st.bump(con)
    return get(con, todo_id)


def delete(con: sqlite3.Connection, todo_id: int) -> bool:
    with con:
        cur = con.execute("delete from todos where id = ?", (todo_id,))
        if cur.rowcount:
            st.bump(con)
    return cur.rowcount > 0
