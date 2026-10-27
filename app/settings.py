"""Calendar colors and the family list (fixed at three people; names can be changed from the phone)."""
import sqlite3

from app import labels
from app import store as st


def ensure_colors(con: sqlite3.Connection, names: list[str]) -> dict[str, str]:
    colors = {r["calendar"]: r["color"] for r in con.execute("select calendar, color from calendar_colors")}
    new = [n for n in dict.fromkeys(names) if n not in colors]
    if new:
        with con:
            for name in new:
                used = set(colors.values())
                free = [c for c in labels.PRESETS if c not in used]
                color = free[0] if free else labels.PRESETS[len(colors) % len(labels.PRESETS)]
                con.execute("insert into calendar_colors (calendar, color) values (?, ?)", (name, color))
                colors[name] = color
            st.bump(con)
    return colors


def calendars(con: sqlite3.Connection) -> list[dict]:
    rows = con.execute("select calendar, color from calendar_colors order by rowid")
    return [{"name": r["calendar"], "color": r["color"], "ink": labels.ink_for(r["color"])} for r in rows]


def set_color(con: sqlite3.Connection, name: str, color: str) -> dict:
    color = color.lower()
    with con:
        con.execute("insert into calendar_colors (calendar, color) values (?, ?) "
                    "on conflict(calendar) do update set color = excluded.color", (name, color))
        st.bump(con)
    return {"name": name, "color": color, "ink": labels.ink_for(color)}


def people(con: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in con.execute("select id, name, sort from people order by sort, id")]


def _person(con: sqlite3.Connection, person_id: int) -> dict:
    row = con.execute("select id, name, sort from people where id = ?", (person_id,)).fetchone()
    if not row:
        raise KeyError(person_id)
    return dict(row)


def update_person(con: sqlite3.Connection, person_id: int, *, name: str | None = None,
                  sort: int | None = None) -> dict:
    _person(con, person_id)
    with con:
        if name is not None:
            con.execute("update people set name = ? where id = ?", (name, person_id))
        if sort is not None:
            con.execute("update people set sort = ? where id = ?", (sort, person_id))
        st.bump(con)
    return _person(con, person_id)


