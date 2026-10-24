from cad_roam import links
from tests.conftest import publish_model


def test_pasted_links_find_the_model(root):
    publish_model(root, "e5172e80e3", "# 1 unit = 1 m\n", (10, 10, 10), title="House")
    for text in (
        "https://cad.reflex-ddns.com/room/e5172e80e3",
        "cad.reflex-ddns.com/room/e5172e80e3",
        "https://cad-roam.reflex-ddns.com/room/e5172e80e3",
        "cad-models:cad/e5172e80e3",
        "cad/e5172e80e3",
        "e5172e80e3",
        "https://aapps.reflex-ddns.com/intent/cad-roam-open?ref=cad-models%3Acad%2Fe5172e80e3",
        "  https://cad.reflex-ddns.com/room/e5172e80e3  ",
    ):
        assert links.read(text) == "cad/e5172e80e3", text
    for text in ("", "https://cad.reflex-ddns.com/room/nothing", "documents:md/e5172e80e3", "md/e5172e80e3", "../etc/passwd"):
        assert links.read(text) == "", text


def test_where_else_it_opens(monkeypatch):
    monkeypatch.delenv("SERVICE_ZONE", raising=False)
    assert links.zone("cad-roam.reflex-ddns.com") == "reflex-ddns.com"
    assert links.zone("localhost:3000") == "" and links.zone("127.0.0.1") == ""
    assert links.model_room("cad", "e5172e80e3", "cad-roam.reflex-ddns.com") == "https://cad.reflex-ddns.com/room/e5172e80e3"
    assert links.model_room("_user", "x1", "cad-roam.reflex-ddns.com") == ""
    assert links.model_room("cad", "x1", "localhost:3000") == ""
    monkeypatch.setenv("SERVICE_ZONE", "example.org")
    assert links.opener_url("viewer", "cad.view", "cad-models:cad/x1", "") == "https://viewer.example.org/intent/cad-view?ref=cad-models%3Acad%2Fx1"
