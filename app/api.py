"""HTTP routes. Thin: validation and status codes here, rules in todos/settings/calendar."""
import datetime as dt
import logging
import os
from contextlib import closing
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints

from app import clock, settings, todos
from app import store as st
from app.calendar import CalendarService, FixtureSource, HttpSource, build_week

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
QUIET_PATHS = {"/api/changes", "/api/version"}

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
HHMM = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Color = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]


class TodoIn(BaseModel):
    person_id: int
    text: Text
    date: dt.date
    time: HHMM | None = None
    created_by: Literal["phone", "house"] = "phone"


class TodoPatch(BaseModel):
    person_id: int | None = None
    text: Text | None = None
    date: dt.date | None = None
    time: HHMM | None = None
    done: bool | None = None


class ColorIn(BaseModel):
    color: Color



class PersonPatch(BaseModel):
    name: Name | None = None
    sort: int | None = Field(None, ge=0)


class QuietPolls(logging.Filter):
    """Keep the 10-second polls out of the access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3:
            return str(args[2]).split("?")[0] not in QUIET_PATHS
        return True


def create_app(db_path: str | None = None, source=None, version: str | None = None) -> FastAPI:
    db_path = db_path or os.environ.get("DASHBOARD_DB", "/data/dashboard.db")
    version = version or os.environ.get("APP_VERSION", "dev")
    if source is None:
        if os.environ.get("DASHBOARD_FAKE") == "1":
            source = FixtureSource(ROOT / "fixtures" / "events.json")
        else:
            source = HttpSource(os.environ.get("CALENDAR_API", "http://calendar-api:8000"))
    store = st.Store(db_path)
    cal = CalendarService(source, store)
    logging.getLogger("uvicorn.access").addFilter(QuietPolls())

    app = FastAPI(title="Kitchen Dashboard", version=version)

    def db():
        with closing(store.connect()) as con:
            yield con

    Con = Annotated[object, Depends(db)]

    @app.middleware("http")
    async def no_cache_static(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/api/version")
    def get_version():
        return {"version": version}

    @app.get("/api/changes")
    def get_changes(con: Con):
        return {"n": st.changes(con)}

    @app.get("/api/week")
    def get_week(con: Con):
        res = cal.events(days=7)
        colors = settings.ensure_colors(con, [e["calendar"] for e in res["events"]])
        body = build_week(res["events"], clock.now(), colors)
        body["fetched_at"] = res["fetched_at"].isoformat(timespec="seconds") if res["fetched_at"] else None
        body["calendar_ok"] = res["ok"]
        body["calendars"] = settings.calendars(con)
        return body

    @app.get("/api/today")
    def get_today(con: Con):
        return todos.today_view(con, clock.now())

    @app.post("/api/todos", status_code=201)
    def post_todo(body: TodoIn, con: Con):
        try:
            return todos.create(con, clock.now(), person_id=body.person_id, text=body.text,
                                date=body.date.isoformat(), time=body.time, created_by=body.created_by)
        except LookupError:
            raise HTTPException(422, "Unknown person") from None

    @app.patch("/api/todos/{todo_id}")
    def patch_todo(todo_id: int, body: TodoPatch, con: Con):
        fields = body.model_dump(exclude_unset=True)
        if "date" in fields and fields["date"] is not None:
            fields["date"] = fields["date"].isoformat()
        for key in ("text", "person_id", "date", "done"):
            if key in fields and fields[key] is None:
                raise HTTPException(422, f"{key} can't be empty")
        try:
            return todos.update(con, clock.now(), todo_id, fields)
        except KeyError:
            raise HTTPException(404, "No such TODO") from None
        except LookupError:
            raise HTTPException(422, "Unknown person") from None

    @app.delete("/api/todos/{todo_id}", status_code=204)
    def delete_todo(todo_id: int, con: Con):
        if not todos.delete(con, todo_id):
            raise HTTPException(404, "No such TODO")

    @app.get("/api/settings")
    def get_settings(con: Con):
        return {"calendars": settings.calendars(con), "people": settings.people(con)}

    @app.put("/api/settings/calendars/{name}")
    def put_color(name: str, body: ColorIn, con: Con):
        return settings.set_color(con, name, body.color)

    # The family is fixed at three people (seeded on first run); they can be renamed, not added or removed.
    @app.patch("/api/settings/people/{person_id}")
    def patch_person(person_id: int, body: PersonPatch, con: Con):
        try:
            return settings.update_person(con, person_id, name=body.name, sort=body.sort)
        except KeyError:
            raise HTTPException(404, "No such person") from None

    @app.delete("/api/events/{uid}")
    def delete_event(uid: str):
        status, body = cal.delete(uid)
        if status == 204:
            return Response(status_code=204)
        return JSONResponse(body, status_code=status)

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
