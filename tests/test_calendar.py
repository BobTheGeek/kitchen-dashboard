from datetime import datetime, timedelta

from app import calendar as cal
from app.clock import TZ
from tests.fakes import FakeSource, ev

COLORS = {"Family": "#f2c230", "School": "#e0457b"}


def week(events, now):
    return cal.build_week(events, now, COLORS)


def test_evening_utc_event_lands_on_chicago_day(freeze):
    now = freeze("2026-10-26T09:00")
    # 8:30 PM Chicago on Mon 26 Oct is 01:30 UTC on Tue 27 Oct.
    w = week([ev("Family", "Late dinner", "2026-10-27T01:30:00Z", "2026-10-27T02:30:00Z")], now)
    assert [e["title"] for e in w["days"][0]["events"]] == ["Late dinner"]
    assert w["days"][0]["events"][0]["time_label"] == "8:30 PM"
    assert w["days"][1]["events"] == []


def test_dst_change_keeps_local_times(freeze):
    now = freeze("2026-10-31T09:00")
    # DST ends Sun 1 Nov 2026 at 2 AM. 9 AM CST that Sunday = 15:00 UTC.
    w = week([ev("Family", "Brunch", "2026-11-01T15:00:00+00:00")], now)
    sunday = w["days"][1]
    assert sunday["date"] == "2026-11-01" and sunday["events"][0]["time_label"] == "9:00 AM"


def test_day_fields_and_sorting(freeze):
    now = freeze("2026-10-26T09:00")
    events = [
        ev("School", "Piano", "2026-10-26T16:00:00-05:00"),
        ev("Family", "Grandma visits", "2026-10-26", "2026-10-27", all_day=True),
        ev("Family", "Standup", "2026-10-26T09:30:00-05:00"),
    ]
    day = week(events, now)["days"][0]
    assert (day["dow"], day["dow_long"], day["day"], day["month"], day["is_today"]) == \
        ("MON", "MONDAY", 26, "OCT", True)
    assert [e["title"] for e in day["events"]] == ["Grandma visits", "Standup", "Piano"]
    first = day["events"][0]
    assert first["time_label"] == "all day" and first["color"] == "#f2c230" and first["ink"] == "#1c1b1f"


def test_more_count(freeze):
    now = freeze("2026-10-26T09:00")
    events = [ev("Family", f"E{h}", f"2026-10-31T{h:02d}:00:00-05:00") for h in range(10, 15)]
    sat = week(events, now)["days"][5]
    assert len(sat["events"]) == 5 and sat["more"] == 2


def test_next_up(freeze):
    now = freeze("2026-10-26T15:00")
    events = [
        ev("Family", "Earlier today", "2026-10-26T09:00:00-05:00"),
        ev("Family", "All day today", "2026-10-26", all_day=True),
        ev("School", "Soccer", "2026-10-26T17:30:00-05:00"),
        ev("Family", "Standup", "2026-10-27T09:00:00-05:00"),
        ev("School", "Piano", "2026-10-28T16:00:00-05:00"),
        ev("Family", "Later", "2026-10-29T16:00:00-05:00"),
    ]
    nxt = week(events, now)["next"]
    assert [e["title"] for e in nxt] == ["All day today", "Soccer", "Standup", "Piano"]
    assert [e["relative_label"] for e in nxt] == ["Today", "Today, 5:30 PM", "Tomorrow, 9:00 AM", "Wed, 4:00 PM"]
    assert [e["is_today"] for e in nxt] == [True, True, False, False]


def test_out_of_range_dropped_and_can_delete(freeze):
    now = freeze("2026-10-26T09:00")
    events = [ev("Family", "Old", "2026-10-25T10:00:00-05:00"),
              ev("Family", "House made", "2026-10-27T10:00:00-05:00", house=True),
              ev("Family", "Far", "2026-11-05T10:00:00-06:00")]
    w = week(events, now)
    titles = [e["title"] for d in w["days"] for e in d["events"]]
    assert titles == ["House made"] and w["days"][1]["events"][0]["can_delete"] is True


def test_unknown_calendar_gets_default_color(freeze):
    now = freeze("2026-10-26T09:00")
    e = week([ev("Mystery", "x", "2026-10-26T10:00:00-05:00")], now)["days"][0]["events"][0]
    assert e["color"] == "#6b6875"


def test_service_caches_for_ttl(store, freeze):
    src = FakeSource([ev("Family", "a", "2026-10-26T10:00:00-05:00")])
    svc = cal.CalendarService(src, store, ttl=60)
    freeze("2026-10-26T09:00:00")
    svc.events()
    freeze("2026-10-26T09:00:30")
    svc.events()
    assert src.calls == 1
    freeze("2026-10-26T09:01:30")
    svc.events()
    assert src.calls == 2


def test_service_serves_stale_when_down_and_after_restart(store, freeze):
    src = FakeSource([ev("Family", "a", "2026-10-26T10:00:00-05:00")])
    t0 = freeze("2026-10-26T09:00")
    cal.CalendarService(src, store).events()
    src.fail = True
    freeze("2026-10-26T09:10")
    fresh_service = cal.CalendarService(src, store)  # simulates a restart: empty memory
    res = fresh_service.events()
    assert res["ok"] is False and res["fetched_at"] == t0 and res["events"][0]["title"] == "a"


def test_service_with_no_data_ever(store, freeze):
    src = FakeSource()
    src.fail = True
    freeze("2026-10-26T09:00")
    res = cal.CalendarService(src, store).events()
    assert res == {"events": [], "fetched_at": None, "ok": False}


def test_delete_invalidates_cache(store, freeze):
    src = FakeSource([ev("Family", "a", "2026-10-26T10:00:00-05:00", house=True)])
    svc = cal.CalendarService(src, store)
    freeze("2026-10-26T09:00")
    svc.events()
    assert svc.delete("u1") == (204, {})
    svc.events()
    assert src.calls == 2 and src.deleted == ["u1"]


def test_fixture_source_materializes_offsets(tmp_path, freeze):
    p = tmp_path / "f.json"
    p.write_text('{"events": [{"calendar": "Family", "title": "T", "offset": 1, "time": "09:00", "minutes": 30},'
                 '{"calendar": "Family", "title": "A", "offset": 0, "all_day": true, "house": true}]}')
    freeze("2026-10-26T08:00")
    src = cal.FixtureSource(p)
    items = src.events(datetime(2026, 10, 26, tzinfo=TZ).date(), 7)
    timed = next(e for e in items if e["title"] == "T")
    assert datetime.fromisoformat(timed["start"]) == datetime(2026, 10, 27, 9, 0, tzinfo=TZ)
    assert datetime.fromisoformat(timed["end"]) - datetime.fromisoformat(timed["start"]) == timedelta(minutes=30)
    house = next(e for e in items if e["title"] == "A")
    assert src.delete(timed["uid"])[0] == 403
    assert src.delete(house["uid"]) == (204, {})
    assert [e["title"] for e in src.events(datetime(2026, 10, 26, tzinfo=TZ).date(), 7)] == ["T"]
