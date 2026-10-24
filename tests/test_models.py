import time

import pytest

from cad_roam import models, settings
from tests.conftest import PNG, publish_file, publish_model, revise_model

TAJ = "# Taj Mahal (scale: 1 unit = 0.5 m)\nresult = None\n"
CATHEDRAL = "# 單位：1 = 1 公尺\nresult = None\n"
BRACKET = "# L-bracket\nresult = None\n"


@pytest.fixture
def cad(root):
    publish_model(root, "taj0000001", TAJ, (380, 380, 150), title="Taj Mahal")
    publish_model(root, "sagrada001", CATHEDRAL, (250, 220, 170), title="Sagrada")
    publish_model(root, "bracket001", BRACKET, (80, 50, 56), title="L-bracket")
    return root


def only(world):
    assert len(world["things"]) == 1
    return world["things"][0]


def test_a_model_stands_at_its_size(cad):
    taj = only(models.build("cad/taj0000001"))
    assert taj["type"] == "model" and taj["unit"] == 0.5 and taj["unit_from"] == "code"
    assert (taj["x"], taj["z"]) == (0.0, 0.0)
    assert (taj["w"], taj["d"], taj["h"]) == (190.0, 190.0, 75.0)
    assert taj["base"] == 0 and taj["pedestal"] == 0
    assert taj["mesh"].startswith("/_roam/mesh/cad/taj0000001?v=")
    # Paving around it: 15.2 m on each side (8 % of 190 m).
    assert taj["plot"] == [220.4, 220.4]
    assert only(models.build("cad/sagrada001"))["unit"] == 1.0


def test_a_small_model_stands_on_a_pedestal(cad):
    b = only(models.build("cad/bracket001"))
    assert b["unit"] == 0.001 and b["unit_from"] == "default"
    assert b["base"] == models.PEDESTAL and b["pedestal"] == 0.8 and abs(b["w"] - 0.08) < 1e-6
    assert b["by"] == "Ann"


def test_a_size_someone_chose_wins(cad):
    settings.set_unit("cad/bracket001", 1.0)
    b = only(models.build("cad/bracket001"))
    assert b["unit"] == 1.0 and b["unit_from"] == "set" and b["base"] == 0 and b["w"] == 80
    settings.set_unit("cad/bracket001", None)
    assert only(models.build("cad/bracket001"))["unit_from"] == "default"


def test_the_list_newest_first_with_sizes(cad, root):
    from reflex_ddns_auth.collections import Collection

    col = Collection("cad-models", app_id="cad", root=root)
    with col.publish("unbuilt001", kind="cad.build123d", primary="model.py", title="Sketch") as item:
        with item.open("model.py") as fh:
            fh.write(b"x = 1\n")
    rows = {m.key: m for m in models.models()}
    assert set(rows) == {"cad/taj0000001", "cad/sagrada001", "cad/bracket001", "cad/unbuilt001"}
    assert rows["cad/taj0000001"].built and (rows["cad/taj0000001"].w, rows["cad/taj0000001"].h) == (190.0, 75.0)
    assert not rows["cad/unbuilt001"].built and rows["cad/unbuilt001"].w == 0
    # A model that never built is a place with nothing in it yet.
    assert models.build("cad/unbuilt001")["things"] == []


def test_find_and_pictures(cad, root):
    assert models.find("taj0000001") == "cad/taj0000001"
    assert models.find("nope") == "" and models.find("../x") == ""
    # An STL imported on the storage page is a model too (owner _user).
    publish_file(root, "cad-models", "_user", "imported01", "file.generic", "bridge.stl", (root / "cad-models/by-app/cad/sagrada001/model.stl").read_bytes(), thumbnail=PNG)
    assert models.find("imported01") == "_user/imported01"
    t = only(models.build("_user/imported01"))
    assert t["unit_from"] == "default" and t["thumb"].startswith("/_roam/thumb/_user/imported01")
    with pytest.raises(KeyError):
        models.build("cad/nope")


def test_the_place_changes_when_the_model_is_rebuilt(cad):
    store = models.Worlds()
    w1 = store.get("cad/taj0000001")
    assert store.get("cad/taj0000001") is w1  # nothing changed: not built again
    assert not store.changed("cad/taj0000001")
    time.sleep(0.01)
    revise_model(cad, "taj0000001", (380, 380, 300))
    assert store.changed("cad/taj0000001")
    w2 = store.get("cad/taj0000001")
    assert w2["rev"] == w1["rev"] + 1
    assert only(w2)["mesh"] != only(w1)["mesh"] and only(w2)["h"] == 150.0
    settings.set_unit("cad/taj0000001", 1.0)
    assert store.changed("cad/taj0000001") and only(store.get("cad/taj0000001"))["h"] == 300.0
    # A model that is gone is a change too, once.
    from reflex_ddns_auth.collections import Collection

    Collection("cad-models", app_id="cad", root=cad).remove("taj0000001")
    assert store.changed("cad/taj0000001")
    assert not store.changed("cad/taj0000001")
