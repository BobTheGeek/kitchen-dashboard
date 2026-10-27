"""HTTP routes. Thin: validation and status codes here, rules in todos/settings/calendar."""
import datetime as dt
import hmac
import logging
import os
from contextlib import closing
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints, field_validator

from app import actions, clock, photos, settings, todos
from app import store as st
from app.calendar import CalendarService, FixtureSource, HttpSource, build_week
from app.house import HouseOps
from app.talk import FakeHouse, FakeWhisper, OpenWebUIClient, TalkError, TalkService, WhisperClient

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


Place = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class HouseEventIn(BaseModel):
    title: Text
    date: dt.date
    start_time: HHMM | None = None
    end_time: HHMM | None = None
    duration_minutes: int | None = Field(None, ge=5, le=1440)
    calendar: Name | None = None
    location: Place | None = None


class HouseEventPatch(BaseModel):
    title: Text | None = None
    date: dt.date | None = None
    start_time: HHMM | None = None
    end_time: HHMM | None = None
    location: Place | None = None


class HouseTodoIn(BaseModel):
    person: Name
    text: Text
    date: dt.date | None = None
    time: HHMM | None = None


EVENT_KEYS = ("uid", "title", "when_label", "calendar")


class TalkContext(BaseModel):
    event: dict[str, str] | None = None

    @field_validator("event")
    @classmethod
    def _bound_event(cls, v):
        if v is None:
            return None
        return {k: " ".join(str(v[k]).split())[:200] for k in EVENT_KEYS if k in v}


class SessionIn(BaseModel):
    context: TalkContext | None = None


class ClientErrorIn(BaseModel):
    message: Annotated[str, StringConstraints(max_length=2000)]
    where: Annotated[str, StringConstraints(max_length=300)] = ""


class MessageIn(BaseModel):
    session_id: str
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


def _fields(model: BaseModel) -> dict:
    out = model.model_dump(exclude_none=True)
    if "date" in out:
        out["date"] = out["date"].isoformat()
    return out


def _read_secret(env_name: str) -> str:
    path = os.environ.get(env_name)
    if not path:
        return ""
    try:
        if Path(path).is_file():
            return Path(path).read_text().strip()
    except OSError:
        logging.getLogger("uvicorn.error").warning("Can't read the secret file for %s at %s", env_name, path)
    return ""


class QuietPolls(logging.Filter):
    """Keep the 10-second polls out of the access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3:
            return str(args[2]).split("?")[0] not in QUIET_PATHS
        return True


def create_app(db_path: str | None = None, source=None, version: str | None = None, whisper=None, house=None,
               house_token: str | None = None, photos_dir: str | None = None) -> FastAPI:
    db_path = db_path or os.environ.get("DASHBOARD_DB", "/data/dashboard.db")
    version = version or os.environ.get("APP_VERSION", "dev")
    if source is None:
        if os.environ.get("DASHBOARD_FAKE") == "1":
            source = FixtureSource(ROOT / "fixtures" / "events.json")
        else:
            source = HttpSource(os.environ.get("CALENDAR_API", "http://calendar-api:8000"))
    store = st.Store(db_path)
    cal = CalendarService(source, store)
    ops = HouseOps(cal)
    fake = os.environ.get("DASHBOARD_FAKE") == "1"
    if photos_dir is None:
        photos_dir = os.environ.get("PHOTOS_DIR") or (str(ROOT / "fixtures" / "photos") if fake else "")
    photo_root = Path(photos_dir) if photos_dir else None
    if house_token is None:
        token = "dev-token" if fake else _read_secret("HOUSE_TOKEN_FILE")
    else:
        token = house_token
    if whisper is None and fake:
        whisper = FakeWhisper()
    elif whisper is None and os.environ.get("WHISPER_URL"):
        whisper = WhisperClient(os.environ["WHISPER_URL"])
    if house is None and fake:
        house = FakeHouse()
    elif house is None:
        key = _read_secret("OPENWEBUI_KEY_FILE")
        house = OpenWebUIClient(os.environ.get("OPENWEBUI_URL", "http://open-webui:8080"), key) if key else None

    def _fake_add(session_id: str, person: str, text: str) -> None:
        with closing(store.connect()) as con:
            now = clock.now()
            ops.add_todo(con, now, session_id, person=person, text=text, date=now.date().isoformat())

    if isinstance(house, FakeHouse) and house.do_add_todo is None:
        house.do_add_todo = _fake_add
    talk = TalkService(store, house, whisper)
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

    def house_auth(authorization: Annotated[str | None, Header()] = None):
        if not token:
            raise HTTPException(503, "House tools are not set up on the dashboard")
        if not authorization or not hmac.compare_digest(authorization.encode("utf-8"),
                                                        f"Bearer {token}".encode()):
            raise HTTPException(401, "Bad house token")

    House = Annotated[None, Depends(house_auth)]
    Sid = Annotated[str | None, Header(alias="X-Talk-Session")]

    def passthrough(status: int, body: dict):
        return JSONResponse(body, status_code=status) if status != 204 else Response(status_code=204)

    @app.get("/api/house/calendars")
    def house_calendars(_: House):
        if isinstance(cal.source, HttpSource):
            return passthrough(*cal.source._send("GET", "/calendars"))
        return {"default": "Family", "calendars": [
            {"name": "Family", "purpose": "Our primary shared family calendar for most events", "writable": True},
            {"name": "Benny Time", "purpose": "Events specific to our son, Ben", "writable": True}]}

    @app.get("/api/house/events")
    def house_events(_: House, start: dt.date | None = None, days: int = 7):
        try:
            evs = cal.source.events(start or clock.now().date(), max(1, min(days, 60)))
        except Exception:
            raise HTTPException(502, "Couldn't read the calendar") from None
        return {"events": evs}

    @app.post("/api/house/events")
    def house_add_event(body: HouseEventIn, _: House, con: Con, sid: Sid = None):
        return passthrough(*ops.add_event(con, clock.now(), sid, _fields(body)))

    @app.patch("/api/house/events/{uid}")
    def house_update_event(uid: str, body: HouseEventPatch, _: House, con: Con, sid: Sid = None):
        return passthrough(*ops.update_event(con, clock.now(), sid, uid, _fields(body)))

    @app.delete("/api/house/events/{uid}")
    def house_delete_event(uid: str, _: House, con: Con, sid: Sid = None):
        return passthrough(*ops.delete_event(con, clock.now(), sid, uid))

    @app.get("/api/house/todos")
    def house_list_todos(person: str, _: House, con: Con):
        view = todos.today_view(con, clock.now())
        p = next((p for p in view["people"] if p["name"].lower() == person.strip().lower()), None)
        if p is None:
            raise HTTPException(404, f"No one called {person}. The family is Bob, Belen and Ben.")
        return {"person": p["name"], "date": view["date"], "todos": p["todos"]}

    @app.post("/api/house/todos", status_code=201)
    def house_add_todo(body: HouseTodoIn, _: House, con: Con, sid: Sid = None):
        now = clock.now()
        try:
            return ops.add_todo(con, now, sid, person=body.person, text=body.text,
                                date=(body.date or now.date()).isoformat(), time=body.time)
        except LookupError as e:
            raise HTTPException(404, str(e)) from None

    def _todo_op(fn, *args):
        try:
            return fn(*args)
        except KeyError:
            raise HTTPException(404, "No such TODO") from None

    @app.post("/api/house/todos/{todo_id}/done")
    def house_done(todo_id: int, _: House, con: Con, sid: Sid = None):
        return _todo_op(ops.set_todo_done, con, clock.now(), sid, todo_id, True)

    @app.post("/api/house/todos/{todo_id}/reopen")
    def house_reopen(todo_id: int, _: House, con: Con, sid: Sid = None):
        return _todo_op(ops.set_todo_done, con, clock.now(), sid, todo_id, False)

    @app.delete("/api/house/todos/{todo_id}")
    def house_delete_todo(todo_id: int, _: House, con: Con, sid: Sid = None):
        return _todo_op(ops.delete_todo, con, clock.now(), sid, todo_id)

    def change_cards(con, session_id: str, after_id: int = 0) -> list[dict]:
        colors = {c["name"]: (c["color"], c["ink"]) for c in settings.calendars(con)}
        out = []
        for a in actions.for_session(con, session_id, after_id):
            color, ink = colors.get(a["calendar"], ("#6b45d9", "#fff"))
            out.append({"id": a["id"], "kind": a["kind"], "verb": a["verb"], "title": a["title"],
                        "detail": a["detail"], "ref": a["ref"], "calendar": a["calendar"], "person": a["person"],
                        "color": color, "ink": ink, "undone": a["undone_at"] is not None,
                        "undoable": a["inverse"] is not None})
        return out

    @app.exception_handler(TalkError)
    async def talk_error(request: Request, exc: TalkError):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    # The kiosk has no console: the page reports its JavaScript errors here so they reach `docker logs`.
    @app.post("/api/client-error", status_code=204)
    def client_error(body: ClientErrorIn, user_agent: Annotated[str, Header()] = ""):
        logging.getLogger("uvicorn.error").warning("Page error: %r at %r (%s)", body.message[:500], body.where,
                                                   user_agent[:120])

    @app.post("/api/talk/sessions")
    def talk_start(body: SessionIn):
        context = body.context.model_dump(exclude_none=True) if body.context else {}
        return {"id": talk.sessions.create(context)["id"]}

    @app.get("/api/talk/sessions/{session_id}")
    def talk_session(session_id: str, con: Con):
        s = talk.sessions.get(session_id)
        return {"busy": bool(s and s["busy"]), "changes": change_cards(con, session_id)}

    @app.delete("/api/talk/sessions/{session_id}", status_code=204)
    def talk_end(session_id: str):
        talk.sessions.end(session_id)

    @app.post("/api/talk/listen")
    async def talk_listen(request: Request):
        wav = await request.body()
        if len(wav) > 2 * 1024 * 1024:
            raise HTTPException(413, "That recording is too long")
        return {"text": await run_in_threadpool(talk.listen, wav)}

    @app.post("/api/talk/message")
    def talk_message(body: MessageIn):
        return talk.message(body.session_id, body.text, change_cards)

    @app.post("/api/talk/actions/{action_id}/undo")
    def talk_undo(action_id: int, con: Con):
        ok, message = ops.undo(con, clock.now(), action_id)
        if not ok:
            raise HTTPException(409, message)
        cal.invalidate()
        return {"ok": True}

    @app.get("/api/photos")
    def get_photos():
        return {"photos": photos.list_photos(photo_root), "active": photos.slideshow_hours(clock.now())}

    @app.get("/photos/{name}")
    def get_photo(name: str):
        path = photos.photo_path(photo_root, name)
        if path is None:
            raise HTTPException(404, "No such photo")
        # Each URL carries ?v=<mtime>, so a changed photo gets a new URL and the cache never goes stale.
        return FileResponse(path, media_type="image/jpeg",
                            headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
