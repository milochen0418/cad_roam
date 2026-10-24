import gzip

import numpy as np

import pytest

from cad_roam import meshes
from tests.conftest import box_triangles, glb_bytes, stl_bytes

STONE, BLUE_GLASS = (0.8, 0.7, 0.5, 1.0), (0.03, 0.16, 0.67, 0.55)


def test_binary_and_ascii_stl(tmp_path):
    tris = box_triangles(2, 3, 4)
    binary = tmp_path / "b.stl"
    binary.write_bytes(stl_bytes(tris))
    assert np.allclose(meshes.read_triangles(binary), tris)

    lines = ["solid box"]
    for t in tris:
        lines += ["facet normal 0 0 0", " outer loop"] + [f"  vertex {x} {y} {z}" for x, y, z in t] + [" endloop", "endfacet"]
    ascii_ = tmp_path / "a.stl"
    ascii_.write_text("\n".join(lines + ["endsolid box"]))
    assert np.allclose(meshes.read_triangles(ascii_), tris)


def test_corners_are_written_once():
    positions, faces = meshes.index(box_triangles(2, 2, 2))
    assert len(positions) == 8 and len(faces) == 12
    # The triangles are the same ones.
    again = positions[faces]
    assert sorted(map(tuple, again.reshape(-1, 3).round(4).tolist())) == sorted(map(tuple, box_triangles(2, 2, 2).reshape(-1, 3).round(4).tolist()))


def test_minus_zero_is_zero_and_flat_triangles_go():
    tris = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[-0.0, 0, 0], [1, 0, 0], [1, 0, 0]]], dtype=np.float32)
    positions, faces = meshes.index(tris)
    assert len(positions) == 3 and len(faces) == 1


def test_round_trip():
    positions, faces = meshes.index(box_triangles(5, 6, 7))
    box = meshes.box_of(positions)
    p, f, b = meshes.decode(meshes.encode(positions, faces, box))
    assert np.allclose(p, positions) and (f == faces).all() and np.allclose(b, box)
    assert b == (-2.5, -3.0, 0.0, 2.5, 3.0, 7.0)


def test_simplify_keeps_under_the_budget():
    rng = np.random.default_rng(1)
    # A bumpy grid: 2 * 99 * 99 triangles.
    n = 100
    xs, ys = np.meshgrid(np.arange(n, dtype=np.float32), np.arange(n, dtype=np.float32))
    zs = rng.random((n, n)).astype(np.float32)
    grid = np.stack([xs, ys, zs], axis=-1)
    tris = []
    for i in range(n - 1):
        for j in range(n - 1):
            a, b, c, d = grid[i, j], grid[i, j + 1], grid[i + 1, j + 1], grid[i + 1, j]
            tris += [(a, b, c), (a, c, d)]
    positions, faces = meshes.index(np.array(tris, dtype=np.float32))
    small_p, small_f = meshes.simplify(positions, faces, 2000)
    assert 0 < len(small_f) <= 2000
    assert small_f.max() < len(small_p)


def test_cache_follows_the_stl(tmp_path, monkeypatch):
    monkeypatch.setenv("CAD_ROAM_HOME", str(tmp_path / "home"))
    stl = tmp_path / "model.stl"
    stl.write_bytes(stl_bytes(box_triangles(10, 20, 30)))
    info = meshes.info("c", "cad", "m1", stl)
    assert info.triangles == 12 and info.box == (-5.0, -10.0, 0.0, 5.0, 10.0, 30.0)
    first = meshes.mesh_file("c", "cad", "m1", stl)
    assert meshes.mesh_file("c", "cad", "m1", stl) == first
    p, f, _ = meshes.decode(gzip.decompress(first.read_bytes()))
    assert len(p) == 8 and len(f) == 12

    import os
    import time

    stl.write_bytes(stl_bytes(box_triangles(1, 1, 1)))
    os.utime(stl, ns=(time.time_ns(), time.time_ns() + 10_000))
    second = meshes.mesh_file("c", "cad", "m1", stl)
    assert second != first and not first.exists()
    assert meshes.info("c", "cad", "m1", stl).box == (-0.5, -0.5, 0.0, 0.5, 0.5, 1.0)


def test_a_glb_in_the_models_axes(tmp_path):
    # A 10 x 8 x 3 room and a glass pane in its front, both moved by (1, 2, 3): glTF is Y up,
    # the box comes back Z up, as the STL has it.
    glb = tmp_path / "model.glb"
    glb.write_bytes(glb_bytes([(box_triangles(10, 8, 3), STONE), (box_triangles(2, 0.1, 2, 0, -4, 1), BLUE_GLASS)], move=(1, 2, 3)))
    box, triangles = meshes.glb_box(glb)
    assert np.allclose(box, (-4, -2.05, 3, 6, 6, 6)) and triangles == 24


def test_a_glb_the_browser_cant_draw(tmp_path):
    glb = tmp_path / "model.glb"
    glb.write_bytes(glb_bytes([(box_triangles(1, 1, 1), STONE)], required=("KHR_draco_mesh_compression",)))
    with pytest.raises(ValueError, match="KHR_draco_mesh_compression"):
        meshes.glb_box(glb)
    glb.write_bytes(b"solid not a glb\n")
    with pytest.raises(ValueError):
        meshes.glb_box(glb)


def test_a_glb_is_cached_as_it_is_beside_its_stl(tmp_path, monkeypatch):
    monkeypatch.setenv("CAD_ROAM_HOME", str(tmp_path / "home"))
    stl, glb = tmp_path / "model.stl", tmp_path / "model.glb"
    stl.write_bytes(stl_bytes(box_triangles(10, 8, 3)))
    data = glb_bytes([(box_triangles(10, 8, 3), STONE)])
    glb.write_bytes(data)
    info = meshes.info("c", "cad", "m1", glb)
    assert info.triangles == 12 and np.allclose(info.box, (-5, -4, 0, 5, 4, 3))
    sent = meshes.mesh_file("c", "cad", "m1", glb)
    assert sent.name.endswith(".glb.gz") and sent.parent.name == "glb"
    assert gzip.decompress(sent.read_bytes()) == data
    # The STL's mesh lives beside it: making one doesn't remove the other.
    mesh = meshes.mesh_file("c", "cad", "m1", stl)
    assert mesh.name.endswith(".rmsh.gz") and sent.exists() and mesh.exists()
