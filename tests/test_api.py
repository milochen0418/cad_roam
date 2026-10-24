import json

import pytest
from starlette.testclient import TestClient

from cad_roam import meshes, presence
from tests.conftest import PNG, box_triangles, glb_bytes, publish_file, publish_model

KEY = "cad/house00001"


@pytest.fixture
def client(root):
    presence._worlds.clear()
    publish_model(root, "house00001", "# 1 unit = 1 m\n", (12, 10, 8), title="House")
    from cad_roam import api

    with TestClient(api.api) as c:
        yield c
    presence._worlds.clear()


def test_the_place_the_mesh_and_the_picture(client, root):
    r = client.get(f"/_roam/world/{KEY}")
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "*"
    house = r.json()["things"][0]
    assert house["title"] == "House" and r.json()["spawn"] == KEY

    r = client.get(house["mesh"])
    assert r.status_code == 200 and r.headers["cache-control"].endswith("immutable")
    # httpx unpacks the gzip itself.
    p, f, box = meshes.decode(r.content)
    assert len(p) == 8 and len(f) == 12 and box == (-6.0, -5.0, 0.0, 6.0, 5.0, 8.0)
    assert int(r.headers["x-roam-bytes"]) == len(r.content)

    assert client.get("/_roam/world/cad/nope").status_code == 404
    assert client.get("/_roam/world/..%2F/x").status_code == 404
    assert client.get("/_roam/mesh/cad/nope").status_code == 404
    assert client.get(f"/_roam/thumb/{KEY}").status_code == 404  # no picture yet

    publish_file(root, "cad-models", "_user", "imported01", "file.generic", "part.stl", b"solid x\nendsolid x\n", thumbnail=PNG)
    assert client.get("/_roam/thumb/_user/imported01").content == PNG


def test_a_model_with_colours_sends_its_glb(client, root):
    glb = glb_bytes([(box_triangles(6, 5, 4), (0.8, 0.2, 0.2, 1.0))])
    publish_model(root, "chapel0001", "# 1 unit = 1 m\n", (6, 5, 4), title="Chapel", glb=glb)
    chapel = client.get("/_roam/world/cad/chapel0001").json()["things"][0]
    r = client.get(chapel["mesh"])
    assert r.status_code == 200 and r.content == glb and r.headers["cache-control"].endswith("immutable")
    assert int(r.headers["x-roam-bytes"]) == len(glb)


def test_people_see_each_other_move(client):
    presence.enter(KEY, "pa", "ta", "ann@x", "Ann")
    presence.enter(KEY, "pb", "tb", "ben@x", "Ben")
    with client.websocket_connect(f"/_roam/ws/{KEY}") as a:
        a.send_text(json.dumps({"t": "hello", "peer": "pa", "token": "ta"}))
        assert a.receive_json()["t"] == "welcome"
        assert [p["name"] for p in a.receive_json()["people"]] == ["Ann"]
        with client.websocket_connect(f"/_roam/ws/{KEY}") as b:
            b.send_text(json.dumps({"t": "hello", "peer": "pb", "token": "tb"}))
            assert b.receive_json()["t"] == "welcome"
            assert len(b.receive_json()["people"]) == 2
            assert len(a.receive_json()["people"]) == 2
            b.send_text(json.dumps({"t": "pose", "p": [1, 2, 3], "yaw": 0.5, "pitch": 0, "mode": "fly", "moving": True}))
            moved = a.receive_json()
            assert moved == {"t": "pose", "id": "pb", "p": [1.0, 2.0, 3.0], "yaw": 0.5, "pitch": 0.0, "mode": "fly", "moving": True}
        # Ben's view closed: Ann sees him go.
        assert [p["name"] for p in a.receive_json()["people"]] == ["Ann"]
    assert presence.where("pb") == ""


def test_an_unknown_tab_is_asked_to_enter_again(client):
    with client.websocket_connect(f"/_roam/ws/{KEY}") as s:
        s.send_text(json.dumps({"t": "hello", "peer": "px", "token": "tx"}))
        assert s.receive_json() == {"t": "rejoin"}
