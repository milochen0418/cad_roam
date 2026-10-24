"""A small cad-models collection for the suites, made fresh in the suite's output folder:

- ``house``: a 10 x 8 m room you can walk into through a door, with steps up to a platform
  ("# 1 unit = 1 m");
- ``tower``: 4 x 4 x 30 m, in millimetres ("# units: mm");
- ``part``: a 60 mm block with no size in its code (millimetres, so it stands on a pedestal);
- ``sketch``: a model that never built (code, no STL).

    python testcases/fixtures.py <root>     # makes it (used by run_test_suite.sh)
"""

from __future__ import annotations

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


def model(root: Path, item_id: str, title: str, code: str, tris) -> None:
    col = Collection("cad-models", app_id="cad", root=root)
    with col.publish(item_id, kind="cad.build123d", primary="model.py", title=title, meta={"created_by_name": "Fixture"}) as item:
        with item.open("model.py") as fh:
            fh.write(code.encode())
        with item.open("model.stl") as fh:
            fh.write(stl(tris))


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
    col = Collection("cad-models", app_id="cad", root=root)
    with col.publish("sketch", kind="cad.build123d", primary="model.py", title="Sketch", meta={"created_by_name": "Fixture"}) as item:
        with item.open("model.py") as fh:
            fh.write(b"# 1 unit = 1 m\nresult = None\n")


def build_sketch(root: Path) -> None:
    """The sketch's first build (what pressing Run in Codoc in CAD does)."""
    col = Collection("cad-models", app_id="cad", root=root)
    with col.revise("sketch") as rev:
        with rev.open("model.stl") as fh:
            fh.write(stl(box(-2, -1.5, 0, 2, 1.5, 2.5)))

if __name__ == "__main__":
    make(Path(sys.argv[1]))
    print("made", sys.argv[1])
