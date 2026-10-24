"""A small cad-models collection for the suites, made fresh in the suite's output folder:

- ``house``: a 10 x 8 m room you can walk into through a door, with steps up to a platform
  ("# 1 unit = 1 m");
- ``tower``: 4 x 4 x 30 m, in millimetres ("# units: mm");
- ``part``: a 60 mm block with no size in its code (millimetres, so it stands on a pedestal);
- ``sketch``: a model that never built (code, no STL);
- ``chapel``: an 8 x 12 m chapel in its colours (``model.glb`` beside its STL, as Codoc in CAD
  builds write them): stone walls, a light floor, a red roof, a door at the front and a blue
  stained-glass window (4 x 2.5 m) in its east wall ("# 1 unit = 1 m").

    python testcases/fixtures.py <root>     # makes it (used by run_test_suite.sh)
"""

from __future__ import annotations

import json
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# The items are published as the apps that make them (cad, md, ...); DDNS_APP_ID would win.
os.environ.pop("DDNS_APP_ID", None)

from reflex_ddns_auth.collections import Collection  # noqa: E402

# The house, in metres (model coordinates: Z up, the front is -Y).
W, D, H, WALL = 10.0, 8.0, 3.0, 0.25
DOOR = 1.4
STEP_RISE, STEP_RUN, STEPS = 0.17, 0.32, 6


def box(x0, y0, z0, x1, y1, z1):
    c = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    tris = []
    for a, b, cc, dd in quads:
        tris += [(c[a], c[b], c[cc]), (c[a], c[cc], c[dd])]
    return tris


def house() -> list:
    hw, hd = W / 2, D / 2
    t = []
    t += box(-hw, -hd, 0, hw, hd, 0.05)  # floor
    t += box(-hw, hd - WALL, 0, hw, hd, H)  # back wall
    t += box(-hw, -hd, 0, -hw + WALL, hd, H)  # left wall
    t += box(hw - WALL, -hd, 0, hw, hd, H)  # right wall
    t += box(-hw, -hd, 0, -DOOR / 2, -hd + WALL, H)  # front wall, left of the door
    t += box(DOOR / 2, -hd, 0, hw, -hd + WALL, H)  # front wall, right of the door
    t += box(-DOOR / 2, -hd, 2.2, DOOR / 2, -hd + WALL, H)  # over the door
    t += box(-hw, -hd, H, hw, hd, H + 0.2)  # roof
    # Steps up to a platform along the back wall, on the right.
    x0, x1 = 1.5, 4.5
    y = hd - WALL - 2.0 - STEPS * STEP_RUN
    for i in range(STEPS):
        t += box(x0, y + i * STEP_RUN, 0, x1, y + (i + 1) * STEP_RUN, (i + 1) * STEP_RISE)
    t += box(x0, hd - WALL - 2.0, 0, x1, hd - WALL, STEPS * STEP_RISE)  # the platform
    return t


# The chapel, in metres, by colour (r, g, b, alpha; linear, as glTF has them).
STONE, FLOOR, ROOF, BLUE_GLASS = (0.6, 0.48, 0.3, 1.0), (0.72, 0.67, 0.58, 1.0), (0.45, 0.08, 0.05, 1.0), (0.03, 0.16, 0.67, 0.55)
CW, CD, CH, CWALL = 8.0, 12.0, 5.0, 0.3


def chapel() -> list:
    hw, hd = CW / 2, CD / 2
    walls = []
    walls += box(-hw, hd - CWALL, 0, hw, hd, CH)  # back
    walls += box(-hw, -hd, 0, -hw + CWALL, hd, CH)  # west
    walls += box(-hw, -hd, 0, -DOOR / 2, -hd + CWALL, CH)  # front, left of the door
    walls += box(DOOR / 2, -hd, 0, hw, -hd + CWALL, CH)  # front, right of the door
    walls += box(-DOOR / 2, -hd, 2.2, DOOR / 2, -hd + CWALL, CH)  # over the door
    # The east wall round a window 4 m wide, from 1.5 m to 4 m up.
    x0 = hw - CWALL
    walls += box(x0, -hd, 0, hw, hd, 1.5) + box(x0, -hd, 4.0, hw, hd, CH)
    walls += box(x0, -hd, 1.5, hw, -2.0, 4.0) + box(x0, 2.0, 1.5, hw, hd, 4.0)
    return [
        (walls, STONE),
        (box(-hw, -hd, 0, hw, hd, 0.05), FLOOR),
        (box(-hw, -hd, CH, hw, hd, CH + 0.2), ROOF),
        (box(hw - 0.18, -2.0, 1.5, hw - 0.12, 2.0, 4.0), BLUE_GLASS),
    ]


def glb(parts) -> bytes:
    """A GLB as Codoc in CAD writes one: a root node turning Z up into glTF's Y up, a node and a
    material per colour."""
    blob, views, accessors, meshes, materials, children = bytearray(), [], [], [], [], []
    for tris, (r, g, b, a) in parts:
        corners = [v for tri in tris for v in tri]
        normals = []
        for t in tris:
            (ax, ay, az), (bx, by, bz), (cx, cy, cz) = t
            ux, uy, uz, vx, vy, vz = bx - ax, by - ay, bz - az, cx - ax, cy - ay, cz - az
            n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
            k = max(sum(c * c for c in n) ** 0.5, 1e-12)
            normals += [tuple(c / k for c in n)] * 3
        refs = []
        for values, kind, fmt, component in ((corners, "VEC3", "<3f", 5126), (normals, "VEC3", "<3f", 5126), (list(range(len(corners))), "SCALAR", "<I", 5125)):
            views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(values) * struct.calcsize(fmt)})
            accessor = {"bufferView": len(views) - 1, "componentType": component, "count": len(values), "type": kind}
            if kind == "VEC3":
                accessor["min"] = [min(v[i] for v in values) for i in range(3)]
                accessor["max"] = [max(v[i] for v in values) for i in range(3)]
            for v in values:
                blob += struct.pack(fmt, *(v if kind == "VEC3" else (v,)))
            accessors.append(accessor)
            refs.append(len(accessors) - 1)
        material = {"pbrMetallicRoughness": {"baseColorFactor": [r, g, b, a], "metallicFactor": 0.1, "roughnessFactor": 0.6}, "doubleSided": True}
        if a < 1:
            material["alphaMode"] = "BLEND"
        materials.append(material)
        meshes.append({"primitives": [{"attributes": {"POSITION": refs[0], "NORMAL": refs[1]}, "indices": refs[2], "material": len(materials) - 1}]})
        children.append(len(meshes))
    nodes = [{"children": children, "rotation": [-0.7071067811865476, 0.0, 0.0, 0.7071067811865476]}]
    nodes += [{"mesh": i} for i in range(len(meshes))]
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": nodes, "meshes": meshes, "materials": materials, "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(blob)}]}
    text = json.dumps(doc).encode()
    text += b" " * (-len(text) % 4)
    body = struct.pack("<I4s", len(text), b"JSON") + text + struct.pack("<I4s", len(blob), b"BIN\0") + bytes(blob)
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def stl(tris) -> bytes:
    out = bytearray(b"roam fixture".ljust(80, b" "))
    out += struct.pack("<I", len(tris))
    for tri in tris:
        out += struct.pack("<3f", 0, 0, 0)
        for v in tri:
            out += struct.pack("<3f", *v)
        out += b"\0\0"
    return bytes(out)


def scaled(tris, k):
    return [tuple(tuple(c * k for c in v) for v in tri) for tri in tris]


PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def model(root: Path, item_id: str, title: str, code: str, tris, colours: bytes = b"") -> None:
    col = Collection("cad-models", app_id="cad", root=root)
    with col.publish(item_id, kind="cad.build123d", primary="model.py", title=title, meta={"created_by_name": "Fixture"}) as item:
        with item.open("model.py") as fh:
            fh.write(code.encode())
        with item.open("model.stl") as fh:
            fh.write(stl(tris))
        if colours:
            with item.open("model.glb") as fh:
                fh.write(colours)


def rebuild_house(root: Path, height: float) -> None:
    """The house's STL again, taller (what a rebuild in Codoc in CAD does to the item)."""
    global H
    old, H = H, height
    try:
        col = Collection("cad-models", app_id="cad", root=root)
        with col.revise("house") as rev:
            with rev.open("model.stl") as fh:
                fh.write(stl(house()))
    finally:
        H = old


def make(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    model(root, "part", "Part", "# A small block\nresult = None\n", box(-30, -20, 0, 30, 20, 25))
    model(root, "house", "House", "# A room to walk into (1 unit = 1 m)\nresult = None\n", house())
    model(root, "tower", "Tower", "# units: mm\nresult = None\n", scaled(box(-2, -2, 0, 2, 2, 30), 1000))
    parts = chapel()
    model(root, "chapel", "Chapel", "# A chapel with a blue window (1 unit = 1 m)\nresult = None\n", [t for tris, _ in parts for t in tris], glb(parts))
    col = Collection("cad-models", app_id="cad", root=root)
    with col.publish("sketch", kind="cad.build123d", primary="model.py", title="Sketch", meta={"created_by_name": "Fixture"}) as item:
        with item.open("model.py") as fh:
            fh.write(b"# 1 unit = 1 m\nresult = None\n")


def rebuild_chapel(root: Path) -> None:
    """The chapel built again, unchanged (pressing Run in Codoc in CAD writes both files anew)."""
    parts = chapel()
    col = Collection("cad-models", app_id="cad", root=root)
    with col.revise("chapel") as rev:
        with rev.open("model.stl") as fh:
            fh.write(stl([t for tris, _ in parts for t in tris]))
        with rev.open("model.glb") as fh:
            fh.write(glb(parts))


def build_sketch(root: Path) -> None:
    """The sketch's first build (what pressing Run in Codoc in CAD does)."""
    col = Collection("cad-models", app_id="cad", root=root)
    with col.revise("sketch") as rev:
        with rev.open("model.stl") as fh:
            fh.write(stl(box(-2, -1.5, 0, 2, 1.5, 2.5)))

if __name__ == "__main__":
    make(Path(sys.argv[1]))
    print("made", sys.argv[1])
