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
        self.create_result = (200, {"saved": True, "event": {}})
        self.update_result = (200, {"saved": True, "event": {}})
        self.created = []
        self.updated = []
        self.found = None

    def events(self, start, days):
        self.calls += 1
        if self.fail:
            raise CalendarError("calendar-api unavailable")
        return list(self.items)

    def delete(self, uid):
        self.deleted.append(uid)
        return self.delete_result

    def create(self, fields):
        self.created.append(fields)
        return self.create_result

    def update(self, uid, fields):
        self.updated.append((uid, fields))
        return self.update_result

    def find(self, uid, start, days):
        if self.fail:
            raise CalendarError("calendar-api unavailable")
        if self.found and self.found["uid"] == uid:
            return self.found
        return next((e for e in self.items if e["uid"] == uid), None)
