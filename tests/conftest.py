"""A scratch collections folder and Roam home for every test, and helpers to fill them."""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest

from reflex_ddns_auth.collections import Collection


def box_triangles(w: float, d: float, h: float, x0: float = 0.0, y0: float = 0.0, z0: float = 0.0) -> np.ndarray:
    """The 12 triangles of a box (model units), centred on x0/y0, standing on z0."""
    xs, ys, zs = (x0 - w / 2, x0 + w / 2), (y0 - d / 2, y0 + d / 2), (z0, z0 + h)
    c = [(x, y, z) for x in xs for y in ys for z in zs]  # index = 4*ix + 2*iy + iz
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    tris = []
    for a, b, cc, dd in quads:
        tris += [(c[a], c[b], c[cc]), (c[a], c[cc], c[dd])]
    return np.array(tris, dtype=np.float32)


def stl_bytes(tris: np.ndarray) -> bytes:
    out = bytearray(b"roam test".ljust(80, b" "))
    out += struct.pack("<I", len(tris))
    for t in tris:
        out += struct.pack("<3f", 0, 0, 0) + t.astype("<f4").tobytes() + b"\0\0"
    return bytes(out)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty collections tree, CAD Roam's home beside it, and no re-ddns node."""
    tree = tmp_path / "collections"
    tree.mkdir()
    monkeypatch.setenv("DDNS_COLLECTIONS_ROOT", str(tree))
    monkeypatch.setenv("CAD_ROAM_HOME", str(tmp_path / "roam-home"))
    # Unset, so the helpers below can publish as other apps (the variable would win).
    for var in ("DDNS_APP_ID", "DDNS_COLLECTIONS_NODE_URL", "RE_DDNS_API_URL"):
        monkeypatch.delenv(var, raising=False)
    from cad_roam import meshes, models

    meshes._info.clear()
    models.WORLDS = models.Worlds()
    return tree


def publish_model(root: Path, item_id: str, code: str, size: tuple[float, float, float], title: str = "", owner: str = "cad", collection: str = "cad-models") -> None:
    col = Collection(collection, app_id=owner, root=root)
    with col.publish(item_id, kind="cad.build123d", primary="model.py", title=title or item_id, meta={"created_by_name": "Ann"}) as item:
        with item.open("model.py") as fh:
            fh.write(code.encode())
        with item.open("model.stl") as fh:
            fh.write(stl_bytes(box_triangles(*size)))


def revise_model(root: Path, item_id: str, size: tuple[float, float, float], owner: str = "cad", collection: str = "cad-models") -> None:
    col = Collection(collection, app_id=owner, root=root)
    with col.revise(item_id) as rev:
        with rev.open("model.stl") as fh:
            fh.write(stl_bytes(box_triangles(*size)))


def publish_file(root: Path, collection: str, owner: str, item_id: str, kind: str, name: str, data: bytes, title: str = "", meta: dict | None = None, thumbnail: bytes = b"") -> None:
    col = Collection(collection, app_id=owner, root=root)
    with col.publish(item_id, kind=kind, primary=name, title=title or item_id, meta=meta or {}) as item:
        with item.open(name) as fh:
            fh.write(data)
        if thumbnail:
            item.set_thumbnail(thumbnail)


# The smallest valid PNG (1 x 1 pixel).
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)
