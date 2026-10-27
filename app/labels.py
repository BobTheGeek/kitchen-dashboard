"""Text the page shows, built on the server so pytest can check it. Pure functions only."""
from datetime import date, datetime, time

PRESETS = ["#f2c230", "#e0702a", "#d2382f", "#e0457b", "#6b45d9", "#2b5fd9", "#14a08a", "#2fb36a"]
DARK_INK = "#1c1b1f"
LIGHT_INK = "#fff"


def clock_time(dt: datetime | time) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def day_word(d: date, today: date) -> str:
    delta = (d - today).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    return d.strftime("%a")


def relative_label(d: date, start: datetime | None, today: date) -> str:
    word = day_word(d, today)
    return word if start is None else f"{word}, {clock_time(start)}"


def time_label(start: datetime | None) -> str:
    return "all day" if start is None else clock_time(start)


def when_label(d: date, start: datetime | None, end: datetime | None) -> str:
    head = f"{d.strftime('%A')} {d.day} {d.strftime('%b')}"
    if start is None:
        return f"{head}, all day"
    if end is None:
        return f"{head}, {clock_time(start)}"
    s, e = clock_time(start), clock_time(end)
    if s[-2:] == e[-2:]:
        s = s[:-3]
    return f"{head}, {s} – {e}"


def todo_time_label(hhmm: str | None) -> str | None:
    if not hhmm:
        return None
    h, m = map(int, hhmm.split(":"))
    return clock_time(time(h, m))


def chip_detail(d: date, at: datetime | time | None) -> str:
    """Change-card line: 'THU 29 · 4:00 PM', or 'THU 29' with no time."""
    head = f"{d.strftime('%a').upper()} {d.day}"
    return head if at is None else f"{head} · {clock_time(at)}"


def _channel(c: int) -> float:
    v = c / 255
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def ink_for(color: str) -> str:
    """Design rule 1e: dark text on light fills, white text on dark fills."""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    lum = 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)
    return DARK_INK if lum > 0.55 else LIGHT_INK
