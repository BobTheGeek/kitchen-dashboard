import pytest

from app import labels, settings
from app import store as st


def test_presets_assigned_in_order_and_kept(con):
    colors = settings.ensure_colors(con, ["Family", "School"])
    assert colors == {"Family": labels.PRESETS[0], "School": labels.PRESETS[1]}
    colors = settings.ensure_colors(con, ["School", "Belen"])
    assert colors["School"] == labels.PRESETS[1] and colors["Belen"] == labels.PRESETS[2]


def test_preset_skips_colors_in_use(con):
    settings.set_color(con, "Family", labels.PRESETS[0])
    settings.set_color(con, "Work", labels.PRESETS[1])
    assert settings.ensure_colors(con, ["New"])["New"] == labels.PRESETS[2]


def test_wraps_when_all_presets_used(con):
    names = [f"C{i}" for i in range(9)]
    colors = settings.ensure_colors(con, names)
    assert colors["C8"] == labels.PRESETS[0]


def test_set_color_and_calendar_list(con):
    settings.ensure_colors(con, ["Family"])
    out = settings.set_color(con, "Family", "#2B5FD9")
    assert out == {"name": "Family", "color": "#2b5fd9", "ink": "#fff"}
    assert settings.calendars(con) == [out]


def test_no_bump_when_nothing_new(con):
    settings.ensure_colors(con, ["Family"])
    n = st.changes(con)
    settings.ensure_colors(con, ["Family"])
    assert st.changes(con) == n


def test_people_crud(con):
    ana = settings.add_person(con, "Ana")
    assert ana["sort"] == 3 and [p["name"] for p in settings.people(con)][-1] == "Ana"
    assert settings.update_person(con, ana["id"], name="Anna")["name"] == "Anna"
    settings.delete_person(con, ana["id"])
    assert "Anna" not in [p["name"] for p in settings.people(con)]
    with pytest.raises(KeyError):
        settings.delete_person(con, 999)


def test_cannot_delete_person_with_todos(con):
    ben = next(p for p in settings.people(con) if p["name"] == "Ben")
    with con:
        con.execute("insert into todos (person_id, text, date, created_at) values (?, 'x', '2026-10-26', 'n')",
                    (ben["id"],))
    with pytest.raises(ValueError):
        settings.delete_person(con, ben["id"])
