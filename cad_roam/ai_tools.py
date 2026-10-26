"""What an AI may do in CAD Roam, offered to the AI Hub (see reflex_ddns_auth.tools): look at a
model from inside it as people walking in it see it, and see where they are in it.

The pictures are taken by a CAD Roam page open on the model (:mod:`cad_roam.eyes`), so each one
shows the model's latest build in its light. A "room" is a model's id, as in /room/<id>, the same
as in Codoc in CAD, whose tools change the model (cad.set_code, cad.run_preview).
"""

from __future__ import annotations

import asyncio
import math
import time as clock
from typing import Any

import reflex as rx
from reflex_ddns_auth.tools import ToolContext, image, tool

from cad_roam import eyes, models, presence
from cad_roam.eyes import LookError, View

ROOM = "The model's id, as in https://cad.reflex-ddns.com/room/<id> (the same id in CAD Roam)."
AT = (
    "Where the eyes are: [x, y, z] in the model's own coordinates, as its code has them (its units, "
    "Z up). A person's eyes are 1.6 m over the floor they stand on."
)
LOOK_AT = "A point to look at, [x, y, z] like at. Without it, heading and pitch say where to look."
HEADING = (
    "Without look_at, the way to look as a compass bearing in the model's plan: 0 towards +Y, 90 towards "
    "+X, 180 towards -Y, 270 towards -X."
)
PITCH = "Without look_at, degrees to look up (or down, below 0)."
TIME = (
    'The sun\'s time of day, from 6:30 to 17:30: hours (12.5) or "12:30"; 10:30 when left out. The sun '
    "comes up in the east (+X), is highest in the south (-Y) at noon and goes down in the west (-X)."
)
FOV = "How much of its height a picture shows, in degrees: 72 is what people see; up to 120 for a whole room."
STOPS = (
    'The places, in order, each {"at": [x, y, z], "look_at": [x, y, z], "name": "..."} or with "heading" '
    f'and "pitch" instead of "look_at". At most {eyes.MAX_STOPS}.'
)
STOP_KEYS = ("at", "look_at", "heading", "pitch", "name")


GUIDE = """\
CAD Roam shows one Codoc in CAD model at its real size; people walk in it (their eyes 1.62 m over \
the floor) or fly round it like a drone, and everyone at the same model sees each other. A room is \
a model's id, as in https://cad-roam.reflex-ddns.com/room/<id> (the same id as in Codoc in CAD). \
Places are in the model's own coordinates, as its code has them: its units, Z up, +X east, +Y \
north, its front towards -Y; headings are compass bearings (0 towards +Y, 90 towards +X); the \
sun's time runs from 6:30 to 17:30 (10:30 unless someone moved it).

Someone talking to you from CAD Roam says, at the start of each message, where they are and \
where they look. To see what they see, call roam.view with their room, at, heading and pitch; \
roam.where lists everyone at a model; roam.tour takes pictures from several places. Pictures are \
taken by a CAD Roam page open on the model (theirs counts), so they show the latest build in its \
light: the sun through openings and glass, lamps (parts that glow), the light walls throw back, \
and eyes used to the dark ("eyes" = how many times brighter the view is drawn, 1 outdoors, up to \
10). The model itself is edited in Codoc in CAD (cad.set_code, cad.run_preview, when those tools \
are offered to you); a rebuild shows up in CAD Roam at once."""


async def guide(ctx: ToolContext) -> str:
    """What CAD Roam is and how to talk about it: read this before the other roam tools."""
    return GUIDE


def _who(ctx: ToolContext) -> str:
    """How the AI is named on the page taking its picture (as in Codoc in CAD)."""
    return f"AI · {ctx.user}" if ctx.user else "AI"


async def _place(room: str) -> tuple[str, str, dict, dict]:
    """The model's key, its id, its place and the model in it (ValueError, for the AI to read,
    when there is none)."""
    room = (room or "").strip()
    key = await asyncio.to_thread(models.find, room)
    if not key:
        raise ValueError(f"there is no model {room!r}: its id is the one in /room/<id> (cad.list_models lists them)")
    try:
        world = await asyncio.to_thread(models.WORLDS.get, key)
    except KeyError:
        raise ValueError(f"there is no model {room!r}") from None
    things = world.get("things") or []
    if not things:
        raise ValueError("this model has never been built: build it in Codoc in CAD first (cad.run_preview)")
    return key, room, world, things[0]


def _rounded(values: Any, digits: int = 3) -> list[float]:
    return [round(float(v), digits) for v in values]


def _number(value: Any, what: str) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        raise LookError(f"{what} must be a number") from None
    if not math.isfinite(f):
        raise LookError(f"{what} must be a number")
    return f


def _described(thing: dict, shot: eyes.Shot, hours: float) -> dict:
    """What comes with a picture: where it was taken from and what the page measured there."""
    info, aimed = shot.info, shot.aimed
    out: dict[str, Any] = {
        "at": _rounded(eyes.to_model(thing, aimed["p"])),
        "heading": eyes.heading_of(aimed["yaw"]),
        "pitch": round(math.degrees(aimed["pitch"]), 1),
        "time": eyes.clock_text(hours),
    }
    if isinstance(info.get("sun"), dict):
        out["sun"] = info["sun"]
    out["light_here"] = info.get("light")
    out["eyes"] = info.get("eyes")
    out["picture_brightness"] = {k: info.get(k) for k in ("mean", "dark", "bright")}
    out["ahead_m"] = info.get("ahead")
    if info.get("lit"):
        out["drawn_with"] = "shadows and the light inside"
    elif info.get("quality") == "high":
        out["drawn_with"] = "shadows; the model is too small to have its light inside worked out"
    else:
        out["drawn_with"] = "Fast quality (the page's choice): no shadows and no light inside, so it can't show the light"
    return out


async def view(
    ctx: ToolContext,
    room: str,
    at: list[float],
    look_at: list[float] | None = None,
    heading: float = 0.0,
    pitch: float = 0.0,
    time: float | str | None = None,
    fov: float = eyes.FOV,
) -> dict:
    """A picture from inside (or round) a model as people walking in it see it in CAD Roam, at its
    real size: daylight through its openings and glass at a time of the day, the light of its lamps
    (parts that glow), the light walls and floors throw back, eyes used to the dark indoors. Check
    rooms, stairs and light from inside with it; change the code (cad.set_code, cad.run_preview)
    and look again: each picture shows the latest build.

    With the picture come: light_here, the light where the eyes are against the open sky's (1 = as
    outdoors); eyes, how many times brighter the view is drawn there, as eyes get used to the dark (1
    outdoors, at most 10, so a very dark place still looks dim); picture_brightness, the picture's
    mean (0 to 255) and its shares of nearly black and nearly white pixels; ahead_m, how far the
    first surface straight ahead is (a wall right in front of the eyes hides everything).

    It needs a CAD Roam page open on the model: its error says what to ask the person."""
    key, item_id, world, thing = await _place(room)
    deadline = clock.monotonic() + eyes.WAIT
    hours = eyes.hours(time)
    look = View(at, look_at, _number(heading, "heading"), _number(pitch, "pitch"), _number(fov, "fov"))
    shot = await eyes.take(key, item_id, thing, world.get("rev", 0), look, hours, eyes.VIEW_SIZE, _who(ctx), deadline)
    return {"room": item_id, "picture": image(shot.jpeg, "image/jpeg"), **_described(thing, shot, hours)}


def _stop(spec: Any, i: int, fov: float) -> View:
    if not isinstance(spec, dict) or "at" not in spec:
        raise LookError(f'stop {i + 1} needs at least "at": [x, y, z]')
    unknown = sorted(set(spec) - set(STOP_KEYS))
    if unknown:
        raise LookError(f"stop {i + 1}: unknown {unknown}; a stop has {', '.join(STOP_KEYS)}")
    return View(
        spec["at"],
        spec.get("look_at"),
        _number(spec.get("heading") or 0.0, f"stop {i + 1}'s heading"),
        _number(spec.get("pitch") or 0.0, f"stop {i + 1}'s pitch"),
        fov,
        str(spec.get("name") or f"stop {i + 1}"),
    )


async def tour(ctx: ToolContext, room: str, stops: list[dict], time: float | str | None = None, fov: float = eyes.FOV) -> dict:
    """Pictures from several places in one call, as roam.view takes them, all at one time of the
    day: walk through a building (its entrance, hall, stairs, rooms) to compare its light. When
    time runs out before the last stops, the answer names them: call again with those."""
    key, item_id, world, thing = await _place(room)
    if not stops:
        raise LookError('stops is empty: give at least one, {"at": [x, y, z], ...}')
    if len(stops) > eyes.MAX_STOPS:
        raise LookError(f"at most {eyes.MAX_STOPS} stops in one call: call again for the rest")
    looks = [_stop(s, i, _number(fov, "fov")) for i, s in enumerate(stops)]
    for look in looks:  # every stop makes sense before any picture is taken
        try:
            eyes.aim(thing, look)
        except LookError as e:
            raise LookError(f"{look.name}: {e}") from None
    hours = eyes.hours(time)
    deadline = clock.monotonic() + eyes.WAIT
    taken: list[dict] = []
    left: list[str] = []
    why = ""
    for look in looks:
        if left:
            left.append(look.name)
            continue
        try:
            shot = await eyes.take(key, item_id, thing, world.get("rev", 0), look, hours, eyes.TOUR_SIZE, _who(ctx), deadline)
        except LookError as e:
            if not taken:
                raise
            left.append(look.name)
            why = str(e)
            continue
        taken.append({"name": look.name, "picture": image(shot.jpeg, "image/jpeg"), **_described(thing, shot, hours)})
    out: dict[str, Any] = {"room": item_id, "time": eyes.clock_text(hours), "stops": taken}
    if left:
        out["not_taken"] = left
        out["note"] = f"{why} Call roam.tour again with the stops not taken."
    return out


async def where(ctx: ToolContext, room: str) -> dict:
    """Where a model stands in CAD Roam and who is in it: its box in its own coordinates, metres per
    unit of its code, its size in metres, and each person there: where their eyes are and where
    they look (in the model's coordinates and bearings, as roam.view takes them), walking or
    flying, and the sun's time they see. Look from there when someone says a place is too dark."""
    key, item_id, world, thing = await _place(room)
    people = []
    for p in presence.people(key):
        eye = [p["p"][0], p["p"][1] + (eyes.EYE if p["mode"] == "walk" else 0.0), p["p"][2]]
        people.append(
            {
                "name": p["name"],
                "at": _rounded(eyes.to_model(thing, eye)),
                "heading": eyes.heading_of(p["yaw"]),
                "pitch": round(math.degrees(p["pitch"]), 1),
                "mode": "flying" if p["mode"] == "fly" else "walking",
                "time": eyes.clock_text(p["time"]) if p.get("time") is not None else None,
            }
        )
    return {
        "room": item_id,
        "title": world.get("title") or item_id,
        "box": _rounded(thing["box"], 4),
        "unit_m": thing["unit"],
        "size_m": [thing["w"], thing["d"], thing["h"]],
        "ground_z": thing["ground"],
        "people": people,
        "pages": len(presence.cameras(key)),
        "address": eyes.page_url(item_id),
    }


def register(app: rx.App) -> None:
    """Offers the CAD Roam tools on ``app``'s backend."""
    tool(
        app,
        "roam.view",
        title="Look from inside a model",
        params={"room": ROOM, "at": AT, "look_at": LOOK_AT, "heading": HEADING, "pitch": PITCH, "time": TIME, "fov": FOV},
    )(view)
    tool(
        app,
        "roam.tour",
        title="Look from several places in a model",
        params={"room": ROOM, "stops": STOPS, "time": TIME, "fov": FOV},
    )(tour)
    tool(app, "roam.where", title="Where people are in a model", params={"room": ROOM})(where)
    tool(app, "roam.guide", title="How CAD Roam works, for an AI")(guide)
