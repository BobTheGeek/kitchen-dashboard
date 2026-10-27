from datetime import date, datetime

from app import labels
from app.clock import TZ

TODAY = date(2026, 10, 26)  # a Monday


def at(h, m, d=TODAY):
    return datetime(d.year, d.month, d.day, h, m, tzinfo=TZ)


def test_clock_time_has_no_leading_zero():
    assert labels.clock_time(at(9, 0)) == "9:00 AM"
    assert labels.clock_time(at(17, 30)) == "5:30 PM"
    assert labels.clock_time(at(0, 5)) == "12:05 AM"


def test_relative_label():
    assert labels.relative_label(TODAY, at(17, 30), TODAY) == "Today, 5:30 PM"
    tue = date(2026, 10, 27)
    assert labels.relative_label(tue, at(9, 0, tue), TODAY) == "Tomorrow, 9:00 AM"
    wed = date(2026, 10, 28)
    assert labels.relative_label(wed, at(16, 0, wed), TODAY) == "Wed, 4:00 PM"
    assert labels.relative_label(TODAY, None, TODAY) == "Today"


def test_time_label():
    assert labels.time_label(None) == "all day"
    assert labels.time_label(at(6, 30)) == "6:30 AM"


def test_when_label():
    thu = date(2026, 10, 29)
    assert labels.when_label(thu, at(16, 0, thu), at(16, 45, thu)) == "Thursday 29 Oct, 4:00 – 4:45 PM"
    assert labels.when_label(thu, at(11, 0, thu), at(13, 0, thu)) == "Thursday 29 Oct, 11:00 AM – 1:00 PM"
    assert labels.when_label(thu, at(16, 0, thu), None) == "Thursday 29 Oct, 4:00 PM"
    assert labels.when_label(thu, None, None) == "Thursday 29 Oct, all day"


def test_todo_time_label():
    assert labels.todo_time_label("14:00") == "2:00 PM"
    assert labels.todo_time_label(None) is None


def test_ink_for_light_and_dark():
    assert labels.ink_for("#f2c230") == labels.DARK_INK   # yellow
    assert labels.ink_for("#2b5fd9") == labels.LIGHT_INK  # blue
    assert labels.ink_for("#e0457b") == labels.LIGHT_INK  # pink
    assert labels.ink_for("#FFFFFF") == labels.DARK_INK


def test_presets():
    assert labels.PRESETS == ["#f2c230", "#e0702a", "#d2382f", "#e0457b",
                              "#6b45d9", "#2b5fd9", "#14a08a", "#2fb36a"]


def test_chip_detail():
    thu = date(2026, 10, 29)
    assert labels.chip_detail(thu, at(16, 0, thu)) == "THU 29 · 4:00 PM"
    assert labels.chip_detail(thu, None) == "THU 29"
