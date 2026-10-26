"""Who is at which model, where they stand, and passing that on to the others.

Each model is a place of its own (keyed ``<owner>/<item>``, the "world" below). A browser tab
enters it in two steps:

1. its Reflex page (``ModelState.on_load``) puts it there with :func:`enter`: the person comes
   from the tab's sign-in, so nobody can pose as someone else; the tab gets a colour;
2. its 3D view opens ``WS /_roam/ws/<owner>/<item>`` and says hello with the tab's peer id and
   its Reflex client token; :meth:`Hub.attach` accepts the socket only for a tab entered at that
   model. From then on the socket carries where the person is (``pose``) to the others there,
   about ten times a second while they move.

A tab whose socket closes leaves at once (the others see it go); one entered but never connected
is dropped after ``IDLE`` seconds without its page's ping. Tabs are known to each other by
``peer`` only; the client token stays on the server.

Messages, JSON both ways:

    tab -> server   {"t": "hello", "peer", "token", "visible", "quality"}
                    {"t": "pose", "p": [x, y, z], "yaw", "pitch", "mode": "walk"|"fly", "moving", "time"}
                    {"t": "seen", "visible"}                the tab was shown or hidden
                    {"t": "shot", "id", ...}                the answer to a "shoot"
    server -> tab   {"t": "welcome", "peer", "rev"}       accepted; rev = the place's version
                    {"t": "rejoin"}                         unknown tab: enter again, then hello
                    {"t": "people", "people": [person...]}  whenever someone comes or goes
                    {"t": "pose", "id": peer, ...}          someone moved
                    {"t": "world", "rev"}                   the model changed: fetch it again
                    {"t": "shoot", "id", ...}               a picture for an AI (cad_roam/eyes.py)

    person = {"id", "user", "name", "color", "avatar", "p", "yaw", "pitch", "mode", "time"}

``visible`` says whether the tab is on a screen, ``quality`` how it draws ("high": shadows and
the light inside), ``time`` the sun's time of day it shows: what an AI's picture is taken with
(:func:`cameras`).
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import logging
import math
import threading
import time
import uuid
from typing import Any

log = logging.getLogger("roam.presence")

# Bright enough on a sunny sky and on grass, and apart from each other.
COLORS = ["#F97316", "#22C55E", "#A855F7", "#EF4444", "#EC4899", "#06B6D4", "#EAB308", "#3B82F6", "#14B8A6", "#F43F5E"]
# A tab without a socket that hasn't pinged for this long has left (its page pings every 5 s).
IDLE = 30.0
MODES = ("walk", "fly")


@dataclasses.dataclass
class Tab:
    peer: str
    token: str
    user: str
    name: str
    avatar: str = ""
    color: str = ""
    last_seen: float = 0.0
    p: list[float] = dataclasses.field(default_factory=lambda: [0.0, 0.0, 0.0])
    yaw: float = 0.0
    pitch: float = 0.0
    mode: str = "walk"
    socket: Any = None  # the open WebSocket, if any
    visible: bool = True  # on a screen (not a tab in the background)
    quality: str = ""  # "high" (shadows and the light inside) or "low"
    time: float | None = None  # the sun's time of day it shows (hours)

    def person(self) -> dict:
        return {
            "id": self.peer, "user": self.user, "name": self.name, "color": self.color, "avatar": self.avatar,
            "p": self.p, "yaw": self.yaw, "pitch": self.pitch, "mode": self.mode, "time": self.time,
        }


_lock = threading.Lock()
# model key -> peer -> tab, in the order they came.
_worlds: dict[str, dict[str, Tab]] = {}


def _color_for(tabs: dict[str, Tab], user: str) -> str:
    """The person's colour in the world: their other tabs' one, else a free one."""
    used: dict[str, str] = {}
    for t in tabs.values():
        if t.color:
            used.setdefault(t.user, t.color)
    if user in used:
        return used[user]
    taken = set(used.values())
    return next((c for c in COLORS if c not in taken), COLORS[len(used) % len(COLORS)])


def enter(world: str, peer: str, token: str, user: str, name: str, avatar: str = "", now: float | None = None) -> Tab:
    """Puts a tab in a world (or finds it there again); it leaves any other world."""
    now = time.time() if now is None else now
    with _lock:
        for other in [w for w, tabs in _worlds.items() if w != world and peer in tabs]:
            _drop(other, peer)
        tabs = _worlds.setdefault(world, {})
        tab = tabs.get(peer)
        if tab is None:
            tab = tabs[peer] = Tab(peer, token, user, name, avatar)
        else:
            tab.token, tab.user, tab.name, tab.avatar = token, user, name, avatar
        if not tab.color:
            tab.color = _color_for({k: t for k, t in tabs.items() if k != peer}, user)
        tab.last_seen = now
        return dataclasses.replace(tab, socket=None)


def _drop(world: str, peer: str) -> Tab | None:
    tabs = _worlds.get(world)
    if not tabs:
        return None
    tab = tabs.pop(peer, None)
    if not tabs:
        del _worlds[world]
    return tab


def leave(peer: str) -> str:
    """Takes a tab out of its world; returns the world ("" when it was in none)."""
    with _lock:
        for world in [w for w, tabs in _worlds.items() if peer in tabs]:
            _drop(world, peer)
            return world
    return ""


def where(peer: str) -> str:
    with _lock:
        return next((w for w, tabs in _worlds.items() if peer in tabs), "")


def touch(world: str, peer: str, now: float | None = None) -> bool:
    """The tab's page is still there; False when the tab isn't in the world (any more)."""
    with _lock:
        tab = _worlds.get(world, {}).get(peer)
        if tab is None:
            return False
        tab.last_seen = time.time() if now is None else now
        return True


def prune(idle: float = IDLE, now: float | None = None) -> list[str]:
    """Drops tabs without a socket not seen for ``idle`` seconds; returns the worlds they left."""
    now = time.time() if now is None else now
    left = []
    with _lock:
        for world, tabs in list(_worlds.items()):
            gone = [p for p, t in tabs.items() if t.socket is None and now - t.last_seen > idle]
            for peer in gone:
                _drop(world, peer)
            if gone:
                left.append(world)
    return left


def people(world: str, connected_only: bool = True) -> list[dict]:
    """The people in a world (one entry per tab), those with an open 3D view by default."""
    with _lock:
        return [t.person() for t in _worlds.get(world, {}).values() if t.socket is not None or not connected_only]


def users_in(world: str) -> list[str]:
    with _lock:
        return sorted({t.user for t in _worlds.get(world, {}).values()} - {""})


def visitors() -> dict[str, list[dict]]:
    """The people in each world, one entry per person: {world: [{"user", "name", "color", "avatar"}]}."""
    out: dict[str, list[dict]] = {}
    with _lock:
        for world, tabs in _worlds.items():
            seen: dict[str, dict] = {}
            for t in tabs.values():
                seen.setdefault(t.user or t.peer, {"user": t.user, "name": t.name, "color": t.color, "avatar": t.avatar})
            if seen:
                out[world] = list(seen.values())
    return out


def tab(world: str, peer: str) -> Tab | None:
    with _lock:
        t = _worlds.get(world, {}).get(peer)
        return dataclasses.replace(t, socket=None) if t is not None else None


def cameras(world: str) -> list[Tab]:
    """The tabs in a world that can take a picture (their 3D view is connected), the best first:
    drawing with shadows and the light inside, on a screen, the last heard from."""
    with _lock:
        tabs = [dataclasses.replace(t, socket=None) for t in _worlds.get(world, {}).values() if t.socket is not None]
    return sorted(tabs, key=lambda t: (t.quality != "high", not t.visible, -t.last_seen))


def opening(world: str) -> bool:
    """Someone has just come to the world: their 3D view hasn't connected yet."""
    with _lock:
        return any(t.socket is None for t in _worlds.get(world, {}).values())


def _number(value: Any, default: float = 0.0, limit: float = 1e6) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) and abs(f) <= limit else default


class Hub:
    """The open sockets of every world, and sending to them."""

    def __init__(self) -> None:
        self.rev_of = lambda world: 0  # set by the API: the world's current rev
        self._tasks: set[asyncio.Task] = set()
        # Requests to tabs waiting for their answer: id -> (the tab's socket, the answer).
        self._asks: dict[str, tuple[Any, asyncio.Future]] = {}

    def later(self, coro) -> None:
        """Runs ``coro`` on its own, e.g. telling the others someone left while that tab's
        handler is being cancelled."""
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _sockets(self, world: str, but: str = "") -> list[Any]:
        with _lock:
            return [t.socket for p, t in _worlds.get(world, {}).items() if t.socket is not None and p != but]

    async def _send(self, socket: Any, message: dict) -> None:
        with contextlib.suppress(Exception):
            await socket.send_text(json.dumps(message, ensure_ascii=False))

    async def broadcast(self, world: str, message: dict, but: str = "") -> None:
        sockets = self._sockets(world, but)
        if sockets:
            await asyncio.gather(*(self._send(s, message) for s in sockets))

    async def people_changed(self, world: str) -> None:
        await self.broadcast(world, {"t": "people", "people": people(world)})

    async def world_changed(self, world: str, rev: int) -> None:
        await self.broadcast(world, {"t": "world", "rev": rev})

    def attach(self, world: str, peer: str, token: str, socket: Any) -> bool:
        """Gives an entered tab its socket (replacing an older one of the same tab)."""
        with _lock:
            t = _worlds.get(world, {}).get(peer)
            if t is None or not token or t.token != token:
                return False
            t.socket = socket
            t.last_seen = time.time()
            return True

    def detach(self, world: str, peer: str, socket: Any) -> bool:
        """The tab's socket closed: the tab leaves. False when a newer socket took its place."""
        with _lock:
            t = _worlds.get(world, {}).get(peer)
            if t is None or t.socket is not socket:
                return False
            _drop(world, peer)
            return True

    def pose(self, world: str, peer: str, data: dict) -> dict | None:
        """Keeps where the tab's person is; the message for the others, or None if invalid."""
        p = data.get("p")
        if not isinstance(p, list) or len(p) != 3:
            return None
        mode = data.get("mode") if data.get("mode") in MODES else "walk"
        with _lock:
            t = _worlds.get(world, {}).get(peer)
            if t is None:
                return None
            t.p = [round(_number(v), 3) for v in p]
            t.yaw = round(_number(data.get("yaw"), limit=1e3), 4)
            t.pitch = round(_number(data.get("pitch"), limit=10), 4)
            t.mode = mode
            hours = _number(data.get("time"), default=-1.0, limit=24)
            if hours >= 0:
                t.time = hours
            t.last_seen = time.time()
            return {"t": "pose", "id": peer, "p": t.p, "yaw": t.yaw, "pitch": t.pitch, "mode": t.mode, "moving": bool(data.get("moving"))}

    def _note(self, world: str, peer: str, data: dict) -> None:
        """What the tab says of itself: on a screen or not, how it draws."""
        with _lock:
            t = _worlds.get(world, {}).get(peer)
            if t is None:
                return
            if isinstance(data.get("visible"), bool):
                t.visible = data["visible"]
            if data.get("quality") in ("high", "low"):
                t.quality = data["quality"]

    async def ask(self, world: str, peer: str, message: dict, timeout: float) -> dict:
        """Sends one tab a request (``message`` gets an ``id``) and waits for its answer, the
        message it sends back with that ``id``. TimeoutError when none comes in time,
        ConnectionError when the tab is gone (or goes meanwhile)."""
        with _lock:
            t = _worlds.get(world, {}).get(peer)
            socket = t.socket if t is not None else None
        if socket is None:
            raise ConnectionError("the tab has left")
        key = uuid.uuid4().hex[:12]
        answer = asyncio.get_running_loop().create_future()
        self._asks[key] = (socket, answer)
        try:
            try:
                await socket.send_text(json.dumps({**message, "id": key}, ensure_ascii=False))
            except Exception as e:
                raise ConnectionError("the tab has left") from e
            return await asyncio.wait_for(answer, timeout)
        finally:
            self._asks.pop(key, None)

    def _answered(self, socket: Any, data: dict) -> None:
        asked = self._asks.get(str(data.get("id") or ""))
        if asked is not None and asked[0] is socket and not asked[1].done():
            asked[1].set_result(data)

    def _closed(self, socket: Any) -> None:
        """A socket closed: what was asked of its tab won't be answered."""
        for asked, answer in list(self._asks.values()):
            if asked is socket and not answer.done():
                answer.set_exception(ConnectionError("the tab has left"))

    async def serve(self, world: str, socket: Any) -> None:
        """One tab's socket, from its hello until it closes."""
        peer = ""
        try:
            hello = json.loads(await asyncio.wait_for(socket.receive_text(), 15))
            peer, token = str(hello.get("peer") or ""), str(hello.get("token") or "")
            if hello.get("t") != "hello" or not self.attach(world, peer, token, socket):
                await self._send(socket, {"t": "rejoin"})
                peer = ""
                return
            self._note(world, peer, hello)
            await self._send(socket, {"t": "welcome", "peer": peer, "rev": self.rev_of(world)})
            await self.people_changed(world)
            while True:
                data = json.loads(await socket.receive_text())
                if not isinstance(data, dict):
                    continue
                if data.get("t") == "pose":
                    message = self.pose(world, peer, data)
                    if message is not None:
                        await self.broadcast(world, message, but=peer)
                elif data.get("t") == "ping":
                    touch(world, peer)
                elif data.get("t") == "seen":
                    self._note(world, peer, data)
                elif data.get("t") == "shot":
                    self._answered(socket, data)
        except (asyncio.TimeoutError, ValueError):
            pass
        except Exception:  # the socket closed (WebSocketDisconnect and friends)
            pass
        finally:
            self._closed(socket)
            if peer and self.detach(world, peer, socket):
                self.later(self.people_changed(world))


HUB = Hub()
