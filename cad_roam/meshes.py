"""Models for the browser: an STL file turned into a small indexed mesh, made once per build.

An STL lists every triangle with its three corners written out, so each corner appears about six
times (70 MB for the Sagrada Família model, 1.4 million triangles). The browser gets the corners
once and the triangles as indices into them, gzipped (about a fifth of the STL), in this layout:

    offset  size  content
    0       4     b"RMSH"
    4       4     u32 version (1)
    8       4     u32 number of corners
    12      4     u32 number of triangles
    16      4     u32 bytes per index (2 or 4)
    20      24    f32 x 6 bounding box: min x, y, z, max x, y, z (the model's own units, Z up)
    44      4     u32 reserved (0)
    48      ...   f32 x 3 per corner, then the indices (u16 or u32), padded to 4 bytes

Coordinates stay in the model's units and axes; the browser scales and stands the model up
(:mod:`cad_roam.models` says how). A model with more than ``CAD_ROAM_MAX_TRIANGLES`` triangles is
simplified first (corners closer than a grid cell are merged).

The file is cached under ``CAD_ROAM_HOME/meshes/<collection>/<owner>/<item>/<stamp>.rmsh.gz``;
``stamp`` changes whenever the STL file does, so a rebuilt model gets a new mesh (and a new
URL, so browsers never show an old one from their cache).
"""

from __future__ import annotations

import gzip
import json
import os
import re
import struct
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from cad_roam import paths

MAGIC = b"RMSH"
VERSION = 1
HEADER = 48
MAX_TRIANGLES = int(os.environ.get("CAD_ROAM_MAX_TRIANGLES") or 3_000_000)

_STL_RECORD = np.dtype([("normal", "<f4", (3,)), ("corners", "<f4", (3, 3)), ("attr", "<u2")])
_FLOAT = re.compile(rb"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


@dataclass(frozen=True)
class MeshInfo:
    """What a world needs to know about a model before anyone loads it."""

    stamp: str
    box: tuple[float, float, float, float, float, float]  # min x, y, z, max x, y, z
    triangles: int


def stamp(path: Path) -> str:
    """Changes whenever the file does (its size and modification time)."""
    st = path.stat()
    return f"{st.st_size:x}-{st.st_mtime_ns:x}"


def read_triangles(path: Path) -> np.ndarray:
    """The triangles of an STL file (binary or ASCII), as float32 ``(n, 3, 3)``."""
    data = path.read_bytes()
    if len(data) >= 84:
        (count,) = struct.unpack_from("<I", data, 80)
        if 84 + 50 * count == len(data):
            records = np.frombuffer(data, dtype=_STL_RECORD, count=count, offset=84)
            return np.ascontiguousarray(records["corners"], dtype=np.float32)
    if data.lstrip()[:5].lower() == b"solid":
        values = []
        for line in data.splitlines():
            line = line.strip()
            if line[:6].lower() == b"vertex":
                values.extend(_FLOAT.findall(line[6:])[:3])
        corners = np.array(values, dtype=np.float32)
        usable = len(corners) // 9 * 9
        return corners[:usable].reshape(-1, 3, 3)
    raise ValueError(f"{path.name} is not an STL file")


def _finite(tris: np.ndarray) -> np.ndarray:
    ok = np.isfinite(tris).all(axis=(1, 2))
    return tris if ok.all() else tris[ok]


def index(tris: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Corners written once: ``(positions (m, 3) float32, triangles (n, 3) uint32)``.

    Triangles whose corners collapse into fewer than three are left out.
    """
    corners = np.ascontiguousarray(tris.reshape(-1, 3), dtype=np.float32)
    corners[corners == 0] = 0  # -0.0 and 0.0 are the same corner
    keys = corners.view(np.dtype((np.void, 12))).ravel()
    unique, inverse = np.unique(keys, return_inverse=True)
    positions = np.ascontiguousarray(unique).view(np.float32).reshape(-1, 3)
    faces = inverse.reshape(-1, 3).astype(np.uint32)
    return positions, _proper(faces)


def _proper(faces: np.ndarray) -> np.ndarray:
    ok = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    return faces if ok.all() else faces[ok]


def simplify(positions: np.ndarray, faces: np.ndarray, budget: int) -> tuple[np.ndarray, np.ndarray]:
    """Fewer triangles than ``budget``: corners in the same grid cell become one (vertex
    clustering), with ever larger cells until the model fits."""
    lo, hi = positions.min(axis=0), positions.max(axis=0)
    size = float((hi - lo).max()) or 1.0
    cells = 4096
    while len(faces) > budget and cells >= 16:
        cell = size / cells
        grid = np.floor((positions - lo) / cell).astype(np.int64)
        keys = (grid[:, 0] * (cells + 1) + grid[:, 1]) * (cells + 1) + grid[:, 2]
        unique, first, inverse = np.unique(keys, return_index=True, return_inverse=True)
        positions = positions[first]
        faces = _proper(inverse.reshape(-1)[faces].astype(np.uint32))
        cells //= 2
    return np.ascontiguousarray(positions, dtype=np.float32), faces


def box_of(positions: np.ndarray) -> tuple[float, ...]:
    if len(positions) == 0:
        return (0.0,) * 6
    lo, hi = positions.min(axis=0), positions.max(axis=0)
    return tuple(float(v) for v in (*lo, *hi))


def encode(positions: np.ndarray, faces: np.ndarray, box: tuple[float, ...]) -> bytes:
    wide = len(positions) > 0xFFFF
    idx = faces.astype(np.uint32 if wide else np.uint16, copy=False)
    head = MAGIC + struct.pack("<IIII6fI", VERSION, len(positions), len(faces), 4 if wide else 2, *box, 0)
    body = idx.tobytes()
    pad = b"\0" * (-len(body) % 4)
    return head + positions.astype("<f4", copy=False).tobytes() + body + pad


def decode(data: bytes) -> tuple[np.ndarray, np.ndarray, tuple[float, ...]]:
    """The inverse of :func:`encode` (for tests and checks)."""
    if data[:4] != MAGIC:
        raise ValueError("not a Roam mesh")
    version, nverts, ntris, width, *rest = struct.unpack_from("<IIII6fI", data, 4)
    box = tuple(rest[:6])
    positions = np.frombuffer(data, dtype="<f4", count=nverts * 3, offset=HEADER).reshape(-1, 3)
    faces = np.frombuffer(data, dtype="<u4" if width == 4 else "<u2", count=ntris * 3, offset=HEADER + nverts * 12).reshape(-1, 3)
    return positions, faces, box


# ---------------------------------------------------------------------------- the cache

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_info: dict[tuple[str, str], MeshInfo] = {}


def _lock(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def _folder(collection: str, owner: str, item_id: str) -> Path:
    return paths.mesh_cache() / collection / owner / item_id


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _prune(folder: Path, st: str) -> None:
    """Removes what was made for earlier builds of the model."""
    for old in folder.glob("*"):
        if not old.name.startswith(st + ".") and not old.name.endswith(".tmp"):
            old.unlink(missing_ok=True)


def info(collection: str, owner: str, item_id: str, stl: Path) -> MeshInfo:
    """The model's size and triangle count, from the cache or read from its STL."""
    st = stamp(stl)
    key = (str(stl), st)
    found = _info.get(key)
    if found is not None:
        return found
    sidecar = _folder(collection, owner, item_id) / f"{st}.json"
    try:
        data = json.loads(sidecar.read_text("utf-8"))
        found = MeshInfo(st, tuple(data["box"]), int(data["triangles"]))
    except (OSError, ValueError, KeyError, TypeError):
        tris = _finite(read_triangles(stl))
        flat = tris.reshape(-1, 3)
        found = MeshInfo(st, box_of(flat), len(tris))
        _write(sidecar, json.dumps({"box": found.box, "triangles": found.triangles}).encode())
        _prune(sidecar.parent, st)
    _info[key] = found
    return found


def mesh_file(collection: str, owner: str, item_id: str, stl: Path) -> Path:
    """The gzipped mesh of this build of the model, made now if it isn't cached yet.

    Slow for big models (seconds): call it from a thread. Older builds' meshes are removed.
    """
    st = stamp(stl)
    folder = _folder(collection, owner, item_id)
    target = folder / f"{st}.rmsh.gz"
    with _lock(str(folder)):
        if target.is_file():
            return target
        tris = _finite(read_triangles(stl))
        positions, faces = index(tris)
        del tris
        if len(faces) > MAX_TRIANGLES:
            positions, faces = simplify(positions, faces, MAX_TRIANGLES)
        data = encode(positions, faces, box_of(positions))
        _write(target, gzip.compress(data, compresslevel=5))
        _prune(folder, st)
        return target
