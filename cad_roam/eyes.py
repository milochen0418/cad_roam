"""Pictures of a model from inside it, for an AI (:mod:`cad_roam.ai_tools`), taken by a CAD Roam
page open on the model and drawn as that page draws it: the sun at a time of the day with its
shadows, the light inside (through openings and glass, from lamps, thrown back by walls), eyes
used to the dark indoors. The person on that page keeps their own view; their light follows the
picture's time for a moment, and a note says who took a picture.

A picture is asked of one tab through its people socket (:mod:`cad_roam.presence`):

    server -> tab   {"t": "shoot", "id", "rev", "time", "size": [w, h], "wait", "by",
                     "view": {"p": [x, y, z], "yaw", "pitch", "fov"}}      the world's metres, Y up
    tab -> server   {"t": "shot", "id", "ok": true, "jpeg": <base64>, "info": {...}}
                    {"t": "shot", "id", "ok": false, "error", "why"}

``rev`` is the place's version: a tab with another one loads the place again first (the model was
rebuilt in Codoc in CAD a moment ago), then its model, then works out its light for that time
(``assets/roam/eyes.js``), also in a tab in the background, where nothing is drawn. ``wait`` is how
many seconds it has for all that.

An AI says where to look from in the model's own coordinates, as its code has them (its units,
Z up, its front towards -Y): :func:`to_world` places them as the 3D view places the model
(``assets/roam/things.js``). Headings are compass bearings with +Y as the north (+X is the east,
where the sun comes up).
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import math
import os
import re
import time as clock
from typing import Any

from cad_roam import presence
from cad_roam.presence import HUB

# The sun's day in CAD Roam (assets/roam/engine.js), and its time when nobody says one.
FIRST, LAST, DAYTIME = 6.5, 17.5, 10.5
# Walking, the eyes are this high over the feet (assets/roam/player.js).
EYE = 1.62
# How much of its height a picture shows, in degrees: what people see.
FOV = 72.0
# A call answers within a minute (Claude Code gives up on one after 60 s): a picture, or a tour of
# them, takes at most this long.
WAIT = 45.0
# A page someone has just opened: how long its 3D view may take to connect.
CONNECT = 15.0
VIEW_SIZE = (1280, 800)
TOUR_SIZE = (1024, 640)
MAX_STOPS = 8


class LookError(Exception):
    """Why no picture was taken, in words for the AI."""


def page_url(item_id: str) -> str:
    """The model in CAD Roam, on this host."""
    app = os.environ.get("SERVICE_SUBDOMAIN", "").strip() or "cad-roam"
    zone = os.environ.get("SERVICE_ZONE", "").strip() or "reflex-ddns.com"
    return f"https://{app}.{zone}/room/{item_id}"


def hours(value: Any) -> float:
    """The sun's time of day from 12.5 or "12:30" (DAYTIME when None), within CAD Roam's day, to
    the minute."""
    if value is None or value == "":
        return DAYTIME
    if isinstance(value, str):
        m = re.fullmatch(r"\s*(\d{1,2})(?:[:.](\d{2}))?\s*", value)
        if m is None:
            raise LookError(f'time {value!r}: give hours (12.5) or "12:30"')
        value = int(m.group(1)) + int(m.group(2) or 0) / 60
    h = float(value)
    if not math.isfinite(h):
        raise LookError(f"time {value!r}: give hours (12.5) or \"12:30\"")
    return min(LAST, max(FIRST, round(h * 60) / 60))


def clock_text(h: float) -> str:
    m = round(h * 60)
    return f"{m // 60}:{m % 60:02d}"


# ------------------------------------------------------------ the model's coordinates


def _frame(thing: dict) -> tuple[float, float, float, float]:
    x0, y0, _, x1, y1, _ = thing["box"]
    return (x0 + x1) / 2, (y0 + y1) / 2, float(thing["unit"]), float(thing["ground"])


def to_world(thing: dict, point: list[float]) -> list[float]:
    """A point of the model (its units, Z up) where it is in CAD Roam (metres, Y up, the model's
    front towards +Z)."""
    cx, cy, u, g = _frame(thing)
    x, y, z = (float(v) for v in point)
    return [(x - cx) * u + thing["x"], (z - g) * u + thing["base"], -(y - cy) * u + thing["z"]]


def to_model(thing: dict, p: list[float]) -> list[float]:
    """A point of CAD Roam's world in the model's coordinates (the other way from to_world)."""
    cx, cy, u, g = _frame(thing)
    x, y, z = (float(v) for v in p)
    return [(x - thing["x"]) / u + cx, -(z - thing["z"]) / u + cy, (y - thing["base"]) / u + g]


def heading_of(yaw: float) -> float:
    """A 3D view's turn (radians, 0 looking towards -Z) as a compass bearing in the model (degrees,
    0 towards +Y, 90 towards +X)."""
    return round(math.degrees(-yaw) % 360, 1)


def _point(value: Any, what: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise LookError(f"{what} needs three numbers, [x, y, z] in the model's coordinates")
    try:
        p = [float(v) for v in value]
    except (TypeError, ValueError):
        raise LookError(f"{what} needs three numbers, [x, y, z] in the model's coordinates") from None
    if not all(math.isfinite(v) for v in p):
        raise LookError(f"{what} needs three numbers, [x, y, z] in the model's coordinates")
    return p


@dataclasses.dataclass
class View:
    """Where to look from (the model's coordinates), and where to: at a point, or along a compass
    bearing and up or down (degrees)."""

    at: Any
    look_at: Any = None
    heading: float = 0.0
    pitch: float = 0.0
    fov: float = FOV
    name: str = ""


def aim(thing: dict, view: View) -> dict:
    """The view as the 3D view's camera: {"p": [x, y, z] world, "yaw", "pitch" (radians), "fov"}."""
    p = to_world(thing, _point(view.at, "at"))
    if view.look_at is not None:
        q = to_world(thing, _point(view.look_at, "look_at"))
        dx, dy, dz = q[0] - p[0], q[1] - p[1], q[2] - p[2]
        if math.hypot(dx, dy, dz) < 1e-6:
            raise LookError("look_at is where the eyes are: look at another point")
        yaw, pitch = math.atan2(-dx, -dz), math.atan2(dy, math.hypot(dx, dz))
    else:
        yaw, pitch = -math.radians(float(view.heading or 0.0)), math.radians(float(view.pitch or 0.0))
    limit = math.radians(89)
    pitch = max(-limit, min(limit, pitch))
    fov = max(20.0, min(120.0, float(view.fov or FOV)))
    return {"p": [round(v, 4) for v in p], "yaw": round(yaw, 5), "pitch": round(pitch, 5), "fov": fov}


# ------------------------------------------------------------ taking it


@dataclasses.dataclass
class Shot:
    jpeg: bytes
    info: dict  # what the page saw (see assets/roam/eyes.js)
    aimed: dict  # the camera it was taken with


def no_page(item_id: str) -> str:
    return (
        "Nobody has this model open in CAD Roam, and pictures are taken there (by a browser, with "
        f"its graphics card). Ask the person to open {page_url(item_id)} (it may stay in a tab in "
        "the background), then call again."
    )


async def _camera(key: str, item_id: str, deadline: float) -> presence.Tab:
    """The tab to take the picture: the best one with its 3D view open on the model, waiting a
    little for one that is just opening."""
    until = min(deadline, clock.monotonic() + CONNECT)
    while True:
        tabs = presence.cameras(key)
        if tabs:
            return tabs[0]
        if not presence.opening(key) or clock.monotonic() >= until:
            raise LookError(no_page(item_id))
        await asyncio.sleep(0.5)


async def take(key: str, item_id: str, thing: dict, rev: int, view: View, time: float, size: tuple[int, int], by: str, deadline: float) -> Shot:
    """One picture of the model (LookError when none can be taken), asked of the best tab on it;
    ``deadline`` (time.monotonic()) bounds the wait."""
    aimed = aim(thing, view)
    tab = await _camera(key, item_id, deadline)
    left = deadline - clock.monotonic()
    if left < 2:
        raise LookError("No time was left for this picture: call again.")
    message = {"t": "shoot", "rev": rev, "time": time, "size": list(size), "wait": round(left - 1.5, 1), "by": by, "view": aimed}
    try:
        answer = await HUB.ask(key, tab.peer, message, timeout=left)
    except TimeoutError:
        raise LookError(
            "The CAD Roam page didn't finish the picture in time: it may still be loading the model or "
            "working out its light. It goes on meanwhile: call again."
        ) from None
    except ConnectionError:
        raise LookError("The CAD Roam page taking the picture closed meanwhile: call again.") from None
    if not answer.get("ok"):
        raise LookError(str(answer.get("error") or "The CAD Roam page couldn't take the picture."))
    try:
        jpeg = base64.b64decode(str(answer.get("jpeg") or ""), validate=True)
    except ValueError:
        jpeg = b""
    if not jpeg.startswith(b"\xff\xd8"):
        raise LookError("The CAD Roam page sent no picture: call again.")
    info = answer.get("info")
    return Shot(jpeg, info if isinstance(info, dict) else {}, aimed)
