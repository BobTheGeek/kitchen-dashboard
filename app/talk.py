"""Talk to the house: speech-to-text, the House (Open WebUI) and short-lived panel sessions."""
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
import uuid

from app import actions, clock

TOOL_IDS = ["household_dates", "household_calendar", "household_todos"]


class TalkError(Exception):
    def __init__(self, message: str, status: int = 503):
        super().__init__(message)
        self.status = status


def clean_transcript(text: str) -> str:
    """Drop whisper's non-speech tags such as [BLANK_AUDIO] or (music)."""
    return " ".join(re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", text or "").split())


def clean_reply(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def _multipart(boundary: str, fields: list[tuple[str, str | None, bytes]]) -> bytes:
    out = []
    for name, filename, data in fields:
        disp = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename else "")
        head = f"--{boundary}\r\nContent-Disposition: {disp}\r\n"
        head += "Content-Type: audio/wav\r\n\r\n" if filename else "\r\n"
        out += [head.encode(), data, b"\r\n"]
    out.append(f"--{boundary}--\r\n".encode())
    return b"".join(out)


class WhisperClient:
    def __init__(self, url: str, timeout: float = 20):
        self.url = url.rstrip("/")
        self.timeout = timeout

    def transcribe(self, wav: bytes) -> str:
        boundary = "kd" + secrets.token_hex(8)
        body = _multipart(boundary, [("file", "speech.wav", wav), ("response_format", None, b"json"),
                                     ("temperature", None, b"0.0")])
        req = urllib.request.Request(f"{self.url}/inference", data=body, method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return clean_transcript(json.load(r).get("text", ""))
        except Exception as e:
            raise TalkError("Voice isn't working right now") from e


class FakeWhisper:
    def __init__(self, text: str = "add a todo for Ben to feed Milo"):
        self.text = text

    def transcribe(self, wav: bytes) -> str:
        return "" if len(wav) < 1000 else self.text


class OpenWebUIClient:
    def __init__(self, url: str, key: str, model: str = "house", timeout: float = 60):
        self.url, self.key, self.model, self.timeout = url.rstrip("/"), key, model, timeout

    def chat(self, messages: list[dict], session_id: str) -> str:
        body = {"model": self.model, "messages": messages, "tool_ids": TOOL_IDS, "session_id": session_id,
                "stream": False}
        req = urllib.request.Request(f"{self.url}/api/chat/completions", data=json.dumps(body).encode(),
                                     method="POST", headers={"Content-Type": "application/json",
                                                             "Authorization": f"Bearer {self.key}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.load(r)
        except TimeoutError as e:
            raise TalkError("The house took too long to answer", 504) from e
        except Exception as e:
            raise TalkError("The house isn't answering", 502) from e
        try:
            return clean_reply(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as e:
            raise TalkError("The house isn't answering", 502) from e


class FakeHouse:
    """Stand-in for the House in fake mode. Understands 'add a todo for <name> to <text>'."""

    def __init__(self, do_add_todo=None):
        self.do_add_todo = do_add_todo

    def chat(self, messages: list[dict], session_id: str) -> str:
        text = messages[-1]["content"]
        m = re.search(r"todo for (\w+) to (.+)", text, re.I)
        if m and self.do_add_todo:
            what = m.group(2).strip().rstrip(".!?")
            self.do_add_todo(session_id, m.group(1), what)
            return f"Done. “{what}” is on {m.group(1).capitalize()}'s list for today."
        return f"(fake house) You said: {text}"


class Sessions:
    def __init__(self, ttl: float = 600, clock=time.monotonic):
        self.ttl, self.clock = ttl, clock
        self._s: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _expire(self):
        now = self.clock()
        for k in [k for k, s in self._s.items() if not s["busy"] and now - s["used"] > self.ttl]:
            del self._s[k]

    def create(self, context: dict | None = None) -> dict:
        s = {"id": uuid.uuid4().hex, "messages": [], "context": context or {}, "busy": False, "used": self.clock()}
        with self._lock:
            self._expire()
            self._s[s["id"]] = s
        return s

    def get(self, session_id: str) -> dict | None:
        with self._lock:
            self._expire()
            s = self._s.get(session_id)
            if s:
                s["used"] = self.clock()
            return s

    def end(self, session_id: str) -> None:
        with self._lock:
            self._s.pop(session_id, None)


class TalkService:
    def __init__(self, store, house, whisper, sessions: Sessions | None = None):
        self.store, self.house, self.whisper = store, house, whisper
        self.sessions = sessions or Sessions()

    def listen(self, wav: bytes) -> str:
        if self.whisper is None:
            raise TalkError("Voice isn't working right now")
        return self.whisper.transcribe(wav)

    def system_prompt(self, session: dict) -> str:
        now = clock.now()
        lines = [
            f"You are the House, answering on the family's kitchen screen. Now: {now:%A %-d %B %Y, %-I:%M %p} "
            "(America/Chicago).",
            "The family is Bob, Belen and their son Ben. TODO lists exist only for these three.",
            "When asked to add, change, check off or remove something, do it with your tools right away, then say "
            "what you did in one or two short sentences.",
            "Keep every answer short: it is read on a wall screen.",
        ]
        ev = (session.get("context") or {}).get("event")
        if ev:
            lines.append(f"The person is looking at this event: “{ev.get('title')}”, {ev.get('when_label')}, "
                         f"{ev.get('calendar')} calendar, uid {ev.get('uid')}.")
        return "\n".join(lines)

    def message(self, session_id: str, text: str, change_cards) -> dict:
        s = self.sessions.get(session_id)
        if s is None:
            raise TalkError("That conversation has ended", 404)
        if self.house is None:
            raise TalkError("The house isn't answering", 502)
        con = self.store.connect()
        try:
            since = actions.last_id(con)
            with self.sessions._lock:
                if s["busy"]:
                    raise TalkError("Still working on the last one", 409)
                s["busy"] = True
            s["messages"].append({"role": "user", "content": text})
            try:
                reply = self.house.chat([{"role": "system", "content": self.system_prompt(s)}] + s["messages"],
                                        session_id)
            except TalkError:
                s["messages"].pop()
                # Tools may have written before the House timed out: keep those changes attributable.
                actions.claim_unattributed(con, session_id, since)
                raise
            finally:
                s["busy"] = False
            s["messages"].append({"role": "assistant", "content": reply})
            actions.claim_unattributed(con, session_id, since)
            return {"reply": reply, "changes": change_cards(con, session_id, since)}
        finally:
            con.close()
