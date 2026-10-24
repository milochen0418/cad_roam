"""A scratch collections folder and Roam home for every test, and helpers to fill them."""

from __future__ import annotations

import json
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


def glb_bytes(parts: list[tuple[np.ndarray, tuple[float, float, float, float]]], move: tuple[float, float, float] = (0.0, 0.0, 0.0), required: tuple[str, ...] = ()) -> bytes:
    """A GLB as Codoc in CAD writes one: a root node turning the model's Z up into glTF's Y up, a
    node per part (moved by ``move``, in the model's axes), each part's triangles in a material of
    its colour (r, g, b, alpha; under 1: blended)."""
    blob = bytearray()
    views, accessors, meshes, materials = [], [], [], []
    nodes: list[dict] = [{"children": [], "rotation": [-0.7071067811865476, 0.0, 0.0, 0.7071067811865476]}]

    def add(array: np.ndarray, kind: str, component: int) -> int:
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": array.nbytes})
        accessor = {"bufferView": len(views) - 1, "componentType": component, "count": len(array), "type": kind}
        if kind == "VEC3":
            accessor["min"], accessor["max"] = array.min(axis=0).tolist(), array.max(axis=0).tolist()
        accessors.append(accessor)
        blob.extend(array.tobytes())
        return len(accessors) - 1

    for tris, (r, g, b, a) in parts:
        corners = np.ascontiguousarray(tris.reshape(-1, 3), dtype="<f4")
        normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
        normals = np.repeat(normals, 3, axis=0).astype("<f4")
        position, normal = add(corners, "VEC3", 5126), add(normals, "VEC3", 5126)
        indices = add(np.arange(len(corners), dtype="<u4"), "SCALAR", 5125)
        material = {"pbrMetallicRoughness": {"baseColorFactor": [r, g, b, a], "metallicFactor": 0.1, "roughnessFactor": 0.6}, "doubleSided": True}
        if a < 1:
            material["alphaMode"] = "BLEND"
        materials.append(material)
        meshes.append({"primitives": [{"attributes": {"POSITION": position, "NORMAL": normal}, "indices": indices, "material": len(materials) - 1}]})
        nodes.append({"mesh": len(meshes) - 1, "translation": list(move)})
        nodes[0]["children"].append(len(nodes) - 1)
    doc = {
        "asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": nodes, "meshes": meshes,
        "materials": materials, "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(blob)}],
    }
    if required:
        doc["extensionsUsed"] = doc["extensionsRequired"] = list(required)
    text = json.dumps(doc).encode()
    text += b" " * (-len(text) % 4)
    blob.extend(b"\0" * (-len(blob) % 4))
    body = struct.pack("<I4s", len(text), b"JSON") + text + struct.pack("<I4s", len(blob), b"BIN\0") + bytes(blob)
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


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


def publish_model(root: Path, item_id: str, code: str, size: tuple[float, float, float], title: str = "", owner: str = "cad", collection: str = "cad-models", glb: bytes = b"") -> None:
    col = Collection(collection, app_id=owner, root=root)
    with col.publish(item_id, kind="cad.build123d", primary="model.py", title=title or item_id, meta={"created_by_name": "Ann"}) as item:
        with item.open("model.py") as fh:
            fh.write(code.encode())
        with item.open("model.stl") as fh:
            fh.write(stl_bytes(box_triangles(*size)))
        if glb:
            with item.open("model.glb") as fh:
                fh.write(glb)


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
