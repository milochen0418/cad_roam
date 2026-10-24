"""The backend's own routes (next to Reflex's), all under ``/_roam/`` (backend-paths.txt sends them
to the backend behind re-ddns' nginx); a model is ``<owner>/<item>`` of the ``cad-models``
collection:

- ``GET /_roam/world/<owner>/<item>``: the model as a place, JSON (:mod:`cad_roam.models`).
- ``GET /_roam/mesh/<owner>/<item>?v=<stamp>``: its mesh, gzipped (:mod:`cad_roam.meshes`); made
  on the first request after a build, cached for good after that.
- ``GET /_roam/thumb/<owner>/<item>``: its picture (Codoc in CAD's last build).
- ``WS /_roam/ws/<owner>/<item>``: being there with others (:mod:`cad_roam.presence`).

The collection is shared with the apps that read it, so these are readable by whoever can open
CAD Roam, like Codoc in CAD's own pages. Paths are checked with the collections library's rules.

The lifespan task watches the models people are in: a rebuild in Codoc in CAD (or a size chosen
here) rebuilds the place and tells everyone in it to fetch it again.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import mimetypes
import struct
from pathlib import Path

from reflex_ddns_auth.collections.refs import valid_item_id, valid_owner
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket

from cad_roam import meshes, models, presence
from cad_roam.presence import HUB

log = logging.getLogger("cad_roam.api")

WATCH_EVERY = 2.0
# Pages and the 3D view may come from another port in a local run (frontend 3000, backend 8000).
OPEN = {"Access-Control-Allow-Origin": "*"}
FOREVER = "public, max-age=31536000, immutable"


def _missing(what: str = "Not found") -> Response:
    return Response(what, status_code=404, headers=OPEN)


def _key(params) -> str:
    owner, item_id = params["owner"], params["item"]
    return f"{owner}/{item_id}" if valid_owner(owner) and valid_item_id(item_id) else ""


async def world(request: Request) -> Response:
    key = _key(request.path_params)
    if not key:
        return _missing("No such model")
    try:
        data = await asyncio.to_thread(models.WORLDS.get, key)
    except KeyError:
        return _missing("No such model")
    except Exception:
        log.exception("%s: can't build its place", key)
        return Response("The model could not be read", status_code=500, headers=OPEN)
    return JSONResponse(data, headers={**OPEN, "Cache-Control": "no-store"})


def _gzip_size(path: Path) -> int:
    """The unpacked size a gzip file says it has (its last four bytes)."""
    with path.open("rb") as fh:
        fh.seek(-4, 2)
        return struct.unpack("<I", fh.read(4))[0]


async def mesh(request: Request) -> Response:
    key = _key(request.path_params)
    it = models.item(key) if key else None
    stl = models.stl_of(it) if it is not None else None
    if stl is None:
        return _missing("No such model")
    try:
        path = await asyncio.to_thread(meshes.mesh_file, models.COLLECTION, it.owner, it.id, stl)
    except (OSError, ValueError) as exc:
        log.warning("%s: no mesh (%s)", it.ref, exc)
        return Response("The model could not be read", status_code=422, headers=OPEN)
    current = request.query_params.get("v") == meshes.stamp(stl)
    headers = {
        **OPEN,
        "Content-Encoding": "gzip",
        "Cache-Control": FOREVER if current else "no-cache",
        # fetch() reports the unpacked bytes as they arrive: this is what they add up to.
        "X-Roam-Bytes": str(_gzip_size(path)),
        "Access-Control-Expose-Headers": "X-Roam-Bytes",
    }
    return FileResponse(path, media_type="application/octet-stream", headers=headers)


async def thumb(request: Request) -> Response:
    key = _key(request.path_params)
    it = models.item(key) if key else None
    path = models.thumbnail(it) if it is not None else None
    media = mimetypes.guess_type(path.name)[0] if path is not None else None
    if path is None or not (media or "").startswith("image/"):
        return _missing("No picture")
    return FileResponse(path, media_type=media, headers={**OPEN, "Cache-Control": "public, max-age=300"})


async def socket(ws: WebSocket) -> None:
    key = _key(ws.path_params)
    await ws.accept()
    if not key or models.item(key) is None:
        await ws.close(code=4404)
        return
    await HUB.serve(key, ws)


HUB.rev_of = lambda key: models.WORLDS.rev(key)

api = Starlette(
    routes=[
        Route("/_roam/world/{owner}/{item}", world, methods=["GET"]),
        Route("/_roam/mesh/{owner}/{item}", mesh, methods=["GET"]),
        Route("/_roam/thumb/{owner}/{item}", thumb, methods=["GET"]),
        WebSocketRoute("/_roam/ws/{owner}/{item}", socket),
    ]
)


async def watch_once() -> None:
    """Rebuilds the places of the models people are in when their model changed, and tells them;
    drops tabs that went quiet."""
    for key in presence.prune():
        await HUB.people_changed(key)
    for key in list(presence.visitors()):
        try:
            if await asyncio.to_thread(models.WORLDS.changed, key):
                await HUB.world_changed(key, models.WORLDS.rev(key))
        except Exception:
            log.exception("%s: can't rebuild its place", key)


async def _watcher() -> None:
    while True:
        await asyncio.sleep(WATCH_EVERY)
        await watch_once()


@contextlib.asynccontextmanager
async def lifespan():
    task = asyncio.create_task(_watcher())
    try:
        yield
    finally:
        task.cancel()
