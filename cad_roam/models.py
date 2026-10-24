"""The CAD models CAD Roam shows, and one of them as a place to walk around in.

The models are the items of the shared collection ``cad-models`` (re_ddns' Owned Collections, read
with ``reflex_ddns_auth``): Codoc in CAD's models (kind ``cad.build123d``: ``model.py`` and, once
it built, ``model.stl``) and STL files imported on the App Store's storage page. A model is known
by its key ``<owner>/<item>`` (``cad/e5172e80e3``); Codoc in CAD's models are owned by ``cad``,
so ``/room/<id>`` here is the same model as ``/room/<id>`` in Codoc in CAD.

A model stands at its real size: metres per unit from what someone chose here
(:mod:`cad_roam.settings`), else from its code's comments (:mod:`cad_roam.units`), else
millimetres (build123d's unit). Under 1.5 m it stands on a pedestal. It is drawn from the GLB its
build wrote beside the STL (Codoc in CAD's ``model.glb``: each part in its colour, see-through
parts as glass), else from the STL, in one colour (:func:`look`); its mesh is made when a browser
first asks for it (:mod:`cad_roam.meshes`).

A model as a place (``build``, sent as JSON by ``GET /_roam/world/<owner>/<item>``):

    {"key", "rev", "spawn": key, "things": [thing]}     no thing while it has no STL (never built)

    thing = {"key", "ref", "kind", "title", "type": "model",
             "x": 0, "z": 0, "w", "d", "h", "base",      # metres: centre of the footprint, its
                                                          # size, height, the pedestal's height
             "pedestal", "plot": [w, d],                  # the pedestal's side (0 = none), the paving
             "mesh", "box" (model units, Z up), "ground" (model z on the floor),
             "unit", "unit_from" ("set", "code" or "default"), "tris", "thumb", "updated", "by"}

The browser stands the model up: model Z becomes world Y, the model's front (-Y) faces +Z, where
people arrive. ``rev`` changes whenever something that shows changes (a rebuild in Codoc in CAD,
a title, a size): :class:`Worlds` rebuilds only when the item's manifest or the sizes changed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from reflex_ddns_auth.collections import BY_APP, MANIFEST_NAME, META_DIR, Collection, Item
from reflex_ddns_auth.collections.refs import valid_item_id, valid_owner

from cad_roam import meshes, settings, units

log = logging.getLogger("cad_roam.models")

COLLECTION = "cad-models"
IMAGES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
SMALL = 1.5  # metres: below this a model stands on a pedestal
PEDESTAL = 0.9


def collection() -> Collection:
    return Collection(COLLECTION)


def key_of(item: Item) -> str:
    return f"{item.owner}/{item.id}"


def split(key: str) -> tuple[str, str] | None:
    owner, _, item_id = (key or "").partition("/")
    return (owner, item_id) if valid_owner(owner) and valid_item_id(item_id) else None


def item(key: str) -> Item | None:
    parts = split(key)
    if parts is None:
        return None
    try:
        return collection().get(f"{COLLECTION}:{parts[0]}/{parts[1]}", remote=False)
    except Exception:
        return None


def find(item_id: str) -> str:
    """The key of the model with this id ("" when there is none); Codoc in CAD's first."""
    if not valid_item_id(item_id or ""):
        return ""
    base = collection().path / BY_APP
    try:
        owners = sorted((e.name for e in os.scandir(base) if e.is_dir() and valid_owner(e.name)), key=lambda o: (o != "cad", o))
    except OSError:
        return ""
    for owner in owners:
        if (base / owner / item_id / META_DIR / MANIFEST_NAME).is_file():
            return f"{owner}/{item_id}"
    return ""


def _named(it: Item, suffix: str) -> list[str]:
    """The item's files ending in ``suffix``, ``model<suffix>`` first."""
    names = (str(f.get("path") or "") for f in it.files)
    return sorted((n for n in names if n.lower().endswith(suffix)), key=lambda n: (n != "model" + suffix, n))


def stl_of(it: Item) -> Path | None:
    """The model's STL file (``model.stl`` first), once it has one."""
    if it.path is None:
        return None
    for name in _named(it, ".stl"):
        path = it.file(name)
        if path.is_file():
            return path
    return None


def glb_of(it: Item, stl: Path) -> Path | None:
    """The GLB its build wrote beside the STL, under the same name (Codoc in CAD's
    ``model.glb``), if it has one."""
    for name in _named(it, ".glb"):
        path = it.file(name)
        if path.parent == stl.parent and path.stem == stl.stem and path.is_file():
            return path
    return None


_passed_over: set[tuple[str, str]] = set()


def look(it: Item) -> tuple[Path, meshes.MeshInfo] | None:
    """The file the model is drawn from, and its size: its GLB when the browser can draw it
    (each part in its colour) and it has no more than ``CAD_ROAM_MAX_TRIANGLES`` triangles, else
    its STL (in one colour, simplified when it is too big). None while it has no STL (never built).
    """
    stl = stl_of(it)
    if stl is None:
        return None
    glb = glb_of(it, stl)
    if glb is not None:
        try:
            found = meshes.info(COLLECTION, it.owner, it.id, glb)
            why = f"{found.triangles} triangles" if found.triangles > meshes.MAX_TRIANGLES else ""
        except (OSError, ValueError) as exc:
            why = str(exc) or type(exc).__name__
        if not why:
            return glb, found
        if (str(glb), why) not in _passed_over:
            _passed_over.add((str(glb), why))
            log.warning("%s: drawn from its STL, in one colour (its GLB: %s)", it.ref, why)
    return stl, meshes.info(COLLECTION, it.owner, it.id, stl)


def thumbnail(it: Item) -> Path | None:
    """The picture of a model: its preview (Codoc in CAD's last build), or its main file when that
    is a picture."""
    if it.thumbnail is not None:
        return it.thumbnail
    p = it.primary
    if p is not None and p.suffix.lower() in IMAGES and p.is_file() and p.stat().st_size <= 8_000_000:
        return p
    return None


def thumb_url(it: Item) -> str:
    return f"/_roam/thumb/{it.owner}/{it.id}?v={it.revision}" if thumbnail(it) is not None else ""


def _code_unit(it: Item) -> float | None:
    p = it.primary
    if p is None or p.suffix.lower() != ".py" or not p.is_file():
        return None
    try:
        return units.from_code(p.read_bytes()[:200_000].decode("utf-8", errors="replace"))
    except OSError:
        return None


def margin(w: float, d: float) -> float:
    """Paving around a model: 1.5 m for small things, up to 20 m for a cathedral."""
    return min(20.0, max(1.5, 0.08 * max(w, d)))


def thing(it: Item) -> dict | None:
    """The model as it stands in its place (see the module's docstring); None without an STL."""
    found = look(it)
    if found is None:
        return None
    key = key_of(it)
    info = found[1]
    chosen = settings.unit(key)
    if chosen:
        unit, unit_from = chosen, "set"
    else:
        from_code = _code_unit(it)
        unit, unit_from = (from_code, "code") if from_code else (units.DEFAULT, "default")
    x0, y0, z0, x1, y1, z1 = info.box
    ground = 0.0 if z0 <= 0.0 <= z1 else z0
    w, d, h = (x1 - x0) * unit, (y1 - y0) * unit, max(0.0, (z1 - ground) * unit)
    base = side = 0.0
    if max(w, d, h) < SMALL:
        base = PEDESTAL
        side = round(max(0.8, max(w, d) + 0.5), 4)
        fw = fd = side
    else:
        fw, fd = max(w, 0.2), max(d, 0.2)
    m = margin(fw, fd)
    meta = it.meta
    return {
        "key": key,
        "ref": it.ref,
        "kind": it.kind,
        "title": it.title,
        "type": "model",
        "x": 0.0,
        "z": 0.0,
        "w": round(w, 4),
        "d": round(d, 4),
        "h": round(h, 4),
        "base": base,
        "pedestal": side,
        "plot": [round(fw + 2 * m, 4), round(fd + 2 * m, 4)],
        "mesh": f"/_roam/mesh/{it.owner}/{it.id}?v={info.stamp}",
        "box": [round(v, 5) for v in info.box],
        "ground": ground,
        "unit": unit,
        "unit_from": unit_from,
        "tris": info.triangles,
        "thumb": thumb_url(it),
        "updated": it.updated_at,
        "by": str(meta.get("last_editor") or meta.get("created_by_name") or ""),
    }


def build(key: str) -> dict:
    """The place of one model (see the module's docstring); KeyError when there is no such model."""
    it = item(key)
    if it is None or it.path is None:
        raise KeyError(key)
    things = []
    try:
        t = thing(it)
    except (OSError, ValueError) as exc:
        log.warning("%s: can't read its model (%s)", it.ref, exc)
        t = None
    if t is not None:
        things.append(t)
    return {"key": key, "title": it.title, "spawn": key, "things": things}


# ---------------------------------------------------------------------------- the list

@dataclass
class Model:
    """A row of the list page."""

    key: str
    id: str
    owner: str
    title: str
    by: str = ""
    updated: str = ""
    thumb: str = ""
    built: bool = False
    w: float = 0.0  # metres, once built
    d: float = 0.0
    h: float = 0.0
    unit: float = 0.0
    unit_from: str = ""
    tris: int = 0


def models() -> list[Model]:
    """Every model on this host, the most recently changed first."""
    try:
        items = collection().local_items()
    except Exception:
        log.exception("can't list %s", COLLECTION)
        return []
    out = []
    for it in items:
        meta = it.meta
        row = Model(
            key=key_of(it), id=it.id, owner=it.owner, title=it.title,
            by=str(meta.get("last_editor") or meta.get("created_by_name") or ""),
            updated=it.updated_at, thumb=thumb_url(it),
        )
        try:
            t = thing(it)
        except (OSError, ValueError):
            t = None
        if t is not None:
            row.built = True
            row.w, row.d, row.h, row.unit, row.unit_from, row.tris = t["w"], t["d"], t["h"], t["unit"], t["unit_from"], t["tris"]
        out.append(row)
    out.sort(key=lambda m: m.updated, reverse=True)
    return out


# ---------------------------------------------------------------------------- watching

# What shows in the place; a change of anything else ("updated", "by") doesn't make a new rev.
_VISIBLE = ("key", "title", "mesh", "unit", "w", "d", "h", "base", "pedestal", "thumb")


def visible_hash(world: dict) -> str:
    rows = [{k: t.get(k) for k in _VISIBLE} for t in world.get("things", [])]
    return hashlib.sha1(json.dumps([world.get("title"), rows], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def signature(key: str) -> tuple:
    """Changes when the model is revised (Codoc in CAD saves and builds) or removed, or someone
    chose a size (one stat each)."""
    parts = split(key)
    marks: list = [settings.mtime()]
    if parts is None:
        return tuple(marks)
    try:
        st = os.stat(collection().path / BY_APP / parts[0] / parts[1] / META_DIR / MANIFEST_NAME)
        marks.append((st.st_mtime_ns, st.st_size))
    except OSError:
        marks.append(None)
    return tuple(marks)


@dataclass
class _Cached:
    sig: tuple
    world: dict
    visible: str
    rev: int


class Worlds:
    """The places of the models people are in, kept built; rebuilt when their model changes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[str, _Cached] = {}
        self._revs: Counter = Counter()

    def get(self, key: str) -> dict:
        """The model's place (KeyError when there is no such model), built again only when it
        changed."""
        sig = signature(key)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and cached.sig == sig:
                return cached.world
        world = build(key)
        visible = visible_hash(world)
        with self._lock:
            cached = self._cache.get(key)
            if cached is None or cached.visible != visible:
                self._revs[key] += 1
            rev = self._revs[key]
            world["rev"] = rev
            self._cache[key] = _Cached(sig, world, visible, rev)
        return world

    def rev(self, key: str) -> int:
        with self._lock:
            cached = self._cache.get(key)
            return cached.rev if cached is not None else 0

    def changed(self, key: str) -> bool:
        """Rebuilds the place when its model changed; True when what shows changed (a model
        that is gone counts as changed: everyone in it should hear)."""
        before = self.rev(key)
        try:
            self.get(key)
        except KeyError:
            with self._lock:
                gone = self._cache.pop(key, None) is not None
            return gone
        return self.rev(key) != before


WORLDS = Worlds()
