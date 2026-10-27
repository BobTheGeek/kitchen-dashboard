"""SQLite access: schema, first-run seed and the change counter the page polls."""
import sqlite3
from pathlib import Path

SEED_PEOPLE = ("Bob", "Belen", "Ben")

SCHEMA = """
create table if not exists people (
    id integer primary key,
    name text not null,
    sort integer not null
);
create table if not exists todos (
    id integer primary key,
    person_id integer not null references people(id),
    text text not null,
    date text not null,
    time text,
    done_at text,
    created_by text not null default 'phone',
    created_at text not null
);
create table if not exists calendar_colors (
    calendar text primary key,
    color text not null
);
create table if not exists calendar_cache (
    key text primary key,
    fetched_at text not null,
    body text not null
);
create table if not exists meta (
    key text primary key,
    value text not null
);
"""


class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        con = self.connect()
        try:
            con.executescript(SCHEMA)
            with con:
                con.execute("insert or ignore into meta (key, value) values ('changes', '0')")
                con.execute("insert or ignore into meta (key, value) values ('schema_version', '1')")
                if con.execute("select count(*) from people").fetchone()[0] == 0:
                    con.executemany("insert into people (name, sort) values (?, ?)",
                                    [(n, i) for i, n in enumerate(SEED_PEOPLE)])
        finally:
            con.close()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("pragma foreign_keys = on")
        return con


def bump(con: sqlite3.Connection) -> None:
    """Call inside the same transaction as any write the page must notice."""
    con.execute("update meta set value = cast(value as integer) + 1 where key = 'changes'")


def changes(con: sqlite3.Connection) -> int:
    return int(con.execute("select value from meta where key = 'changes'").fetchone()[0])
