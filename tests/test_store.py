from app import store as st


def test_seeds_people_once(store):
    with store.connect() as c:
        names = [r["name"] for r in c.execute("select name from people order by sort")]
    assert names == ["Bob", "Belen", "Ben"]
    st.Store(store.path)  # opening again must not seed twice
    with store.connect() as c:
        assert c.execute("select count(*) from people").fetchone()[0] == 3


def test_change_counter(con):
    assert st.changes(con) == 0
    with con:
        st.bump(con)
        st.bump(con)
    assert st.changes(con) == 2


def test_foreign_keys_on(con):
    import sqlite3

    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        with con:
            con.execute("insert into todos (person_id, text, date, created_at) values (999, 'x', '2026-10-26', 'now')")
