from app.calendar import CalendarError


def ev(calendar, title, start, end=None, all_day=False, uid=None, house=False, location=None):
    return {"calendar": calendar, "title": title, "start": start, "end": end, "all_day": all_day,
            "location": location, "uid": uid or f"{calendar}-{title}-{start}", "added_by_house": house,
            "when": ""}


class FakeSource:
    def __init__(self, events=None):
        self.items = list(events or [])
        self.fail = False
        self.calls = 0
        self.delete_result = (204, {})
        self.deleted = []

    def events(self, start, days):
        self.calls += 1
        if self.fail:
            raise CalendarError("calendar-api unavailable")
        return list(self.items)

    def delete(self, uid):
        self.deleted.append(uid)
        return self.delete_result
