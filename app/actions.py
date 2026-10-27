"""House action log: every change the House makes, with how to reverse it (change cards and Undo)."""
import json
import sqlite3
from datetime import datetime

COLUMNS = "id, session_id, kind, verb, title, detail, ref, calendar, person, inverse, created_at, undone_at"


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["inverse"] = json.loads(d["inverse"]) if d["inverse"] else None
    return d


def record(con: sqlite3.Connection, now: datetime, *, session_id: str | None, kind: str, verb: str, title: str,
           detail: str, ref: str | None = None, calendar: str | None = None, person: str | None = None,
           inverse: dict | None = None) -> dict:
    with con:
        cur = con.execute(
            "insert into house_actions (session_id, kind, verb, title, detail, ref, calendar, person, inverse,"
            " created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, kind, verb, title, detail, ref, calendar, person,
             json.dumps(inverse) if inverse is not None else None, now.isoformat(timespec="seconds")))
    return get(con, cur.lastrowid)


def get(con: sqlite3.Connection, action_id: int) -> dict | None:
    r = con.execute(f"select {COLUMNS} from house_actions where id = ?", (action_id,)).fetchone()
    return _row(r) if r else None


def last_id(con: sqlite3.Connection) -> int:
    return con.execute("select coalesce(max(id), 0) from house_actions").fetchone()[0]


def claim_unattributed(con: sqlite3.Connection, session_id: str, after_id: int) -> int:
    """Fallback when a tool call carried no session id: give this session the unowned rows made during its call."""
    with con:
        cur = con.execute("update house_actions set session_id = ? where session_id is null and id > ?",
                          (session_id, after_id))
    return cur.rowcount


def for_session(con: sqlite3.Connection, session_id: str, after_id: int = 0) -> list[dict]:
    rows = con.execute(f"select {COLUMNS} from house_actions where session_id = ? and id > ? order by id",
                       (session_id, after_id))
    return [_row(r) for r in rows]


def mark_undone(con: sqlite3.Connection, action_id: int, now: datetime) -> None:
    with con:
        con.execute("update house_actions set undone_at = ? where id = ?",
                    (now.isoformat(timespec="seconds"), action_id))
