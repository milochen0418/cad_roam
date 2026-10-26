"""An AI's pictures from inside a model: the model's coordinates in CAD Roam's world, asking a tab for
a picture over its socket, and the tools (roam.view, roam.tour, roam.where)."""

import asyncio
import base64
import json
import math

import pytest
from starlette.applications import Starlette

from cad_roam import ai_tools, eyes, presence
from cad_roam.eyes import LookError, View
from cad_roam.presence import HUB
from reflex_ddns_auth import tools as ddns_tools
from reflex_ddns_auth.tools import IMAGE_KEY, ToolContext

# A 10 x 8 x 3.2 m house in metres, and a 4 x 4 x 30 m tower drawn in millimetres on a 0.9 m base.
HOUSE = {"box": [-5.0, -4.0, 0.0, 5.0, 4.0, 3.2], "unit": 1.0, "ground": 0.0, "x": 0.0, "z": 0.0, "base": 0.0, "w": 10.0, "d": 8.0, "h": 3.2}
TOWER = {"box": [1000.0, 0.0, 500.0, 5000.0, 4000.0, 30500.0], "unit": 0.001, "ground": 500.0, "x": 0.0, "z": 0.0, "base": 0.9, "w": 4.0, "d": 4.0, "h": 30.0}
JPEG = b"\xff\xd8\xff\xe0 a picture"
CTX = ToolContext(user="Claude Code", caller="ai-hub")


@pytest.fixture(autouse=True)
def empty():
    presence._worlds.clear()
    HUB._asks.clear()
    yield
    presence._worlds.clear()
    HUB._asks.clear()


# ------------------------------------------------------------ coordinates


def test_the_front_of_a_model_faces_where_people_arrive():
    # The model's front (-Y) is towards +Z, its Z is up.
    assert eyes.to_world(HOUSE, [0, -4, 1.6]) == [0.0, 1.6, 4.0]
    assert eyes.to_world(HOUSE, [5, 0, 0]) == [5.0, 0.0, 0.0]
    # Millimetres, its middle on the ground, standing on a base.
    assert eyes.to_world(TOWER, [3000, 2000, 500]) == pytest.approx([0.0, 0.9, 0.0])
    assert eyes.to_world(TOWER, [3000, 0, 2100]) == pytest.approx([0.0, 2.5, 2.0])
    for thing, p in ((HOUSE, [1.5, -2.25, 1.62]), (TOWER, [1200.0, 3900.0, 25000.0])):
        assert eyes.to_model(thing, eyes.to_world(thing, p)) == pytest.approx(p)


def test_headings_are_compass_bearings_with_y_the_north():
    def aimed(**kw):
        return eyes.aim(HOUSE, View([0, 0, 1.6], **kw))

    # Towards +Y: the 3D view's yaw 0 (looking to -Z); towards +X (the east): a quarter turn right.
    assert aimed(heading=0)["yaw"] == pytest.approx(0)
    assert aimed(heading=90)["yaw"] == pytest.approx(-math.pi / 2, abs=1e-4)
    assert eyes.heading_of(aimed(heading=90)["yaw"]) == 90
    assert eyes.heading_of(aimed(heading=225)["yaw"]) == 225
    assert aimed(pitch=30)["pitch"] == pytest.approx(math.radians(30), abs=1e-4)
    # A point to look at: to the east and up.
    east = aimed(look_at=[3, 0, 4.6])
    assert eyes.heading_of(east["yaw"]) == 90 and east["pitch"] == pytest.approx(math.pi / 4, abs=1e-4)
    assert eyes.heading_of(aimed(look_at=[0, -3, 1.6])["yaw"]) == 180
    # Straight up is a little less than straight up; the field of view stays sensible.
    assert aimed(pitch=120)["pitch"] == pytest.approx(math.radians(89), abs=1e-4)
    assert aimed(fov=500)["fov"] == 120


def test_bad_places_are_explained():
    with pytest.raises(LookError, match=r"\[x, y, z\]"):
        eyes.aim(HOUSE, View([0, 1]))
    with pytest.raises(LookError, match="look_at"):
        eyes.aim(HOUSE, View([0, 0, 1], look_at=["a", 0, 1]))
    with pytest.raises(LookError, match="where the eyes are"):
        eyes.aim(HOUSE, View([0, 0, 1], look_at=[0, 0, 1]))


def test_times_of_day():
    assert eyes.hours(None) == eyes.DAYTIME
    assert eyes.hours("12:30") == 12.5
    assert eyes.hours("7") == 7
    assert eyes.hours(12.3333) == pytest.approx(12 + 20 / 60)
    assert eyes.hours(22) == eyes.LAST and eyes.hours(3) == eyes.FIRST
    assert eyes.clock_text(12 + 20 / 60) == "12:20" and eyes.clock_text(6.5) == "6:30"
    with pytest.raises(LookError):
        eyes.hours("noon")


# ------------------------------------------------------------ asking a tab


class FakeTab:
    """A tab's socket: answers each "shoot" as a page would (or not at all)."""

    def __init__(self, answer=None):
        self.sent: list[dict] = []
        self.answer = answer

    async def send_text(self, text: str) -> None:
        message = json.loads(text)
        self.sent.append(message)
        if self.answer is not None and message.get("t") == "shoot":
            reply = self.answer(message) if callable(self.answer) else self.answer
            asyncio.get_running_loop().call_soon(HUB._answered, self, {"t": "shot", "id": message["id"], **reply})


def a_picture(message: dict) -> dict:
    return {"ok": True, "jpeg": base64.b64encode(JPEG).decode(), "info": {"eyes": 3.2, "light": 0.05, "mean": 90, "dark": 0.1, "bright": 0.0, "ahead": 4.2, "lit": True, "quality": "high", "sun": {"bearing": 135.0, "elevation": 40.0}}}


def at_model(peer: str, socket, *, visible=True, quality="high", world="cad/house", now=None):
    presence.enter(world, peer, "t-" + peer, peer + "@x", peer.title(), now=now)
    assert HUB.attach(world, peer, "t-" + peer, socket)
    HUB._note(world, peer, {"visible": visible, "quality": quality})


def test_pictures_are_asked_of_the_best_tab():
    at_model("fast", FakeTab(), quality="low")
    at_model("hidden", FakeTab(), visible=False)
    at_model("shown", FakeTab())
    assert [t.peer for t in presence.cameras("cad/house")] == ["shown", "hidden", "fast"]
    presence.enter("cad/house", "opening", "t", "x@x", "X")
    assert presence.opening("cad/house") and len(presence.cameras("cad/house")) == 3


def test_ask_gets_the_answer_with_its_id():
    async def run():
        sock = FakeTab(answer={"ok": True, "value": 7})
        at_model("ann", sock)
        answer = await HUB.ask("cad/house", "ann", {"t": "shoot"}, timeout=2)
        assert answer["value"] == 7 and answer["id"] == sock.sent[0]["id"]
        assert not HUB._asks

    asyncio.run(run())


def test_an_unanswered_ask_times_out_and_a_closed_tab_fails_it():
    async def run():
        sock = FakeTab()
        at_model("ann", sock)
        with pytest.raises(TimeoutError):
            await HUB.ask("cad/house", "ann", {"t": "shoot"}, timeout=0.05)
        waiting = asyncio.ensure_future(HUB.ask("cad/house", "ann", {"t": "shoot"}, timeout=5))
        await asyncio.sleep(0.01)
        HUB._closed(sock)
        with pytest.raises(ConnectionError):
            await waiting
        # Another tab's socket can't answer for it.
        other = FakeTab()
        waiting = asyncio.ensure_future(HUB.ask("cad/house", "ann", {"t": "shoot"}, timeout=0.1))
        await asyncio.sleep(0.01)
        HUB._answered(other, {"t": "shot", "id": sock.sent[-1]["id"], "ok": True})
        with pytest.raises(TimeoutError):
            await waiting

    asyncio.run(run())


def test_take_sends_the_camera_in_the_world_and_reads_the_picture():
    async def run():
        sock = FakeTab(answer=a_picture)
        at_model("ann", sock)
        shot = await eyes.take("cad/house", "house", HOUSE, 4, View([0, -4, 1.6], heading=0), 12.5, (640, 400), "AI · x", asyncio.get_running_loop().time() + 30)
        asked = sock.sent[0]
        assert asked["t"] == "shoot" and asked["rev"] == 4 and asked["time"] == 12.5 and asked["size"] == [640, 400]
        assert asked["view"]["p"] == [0.0, 1.6, 4.0] and asked["view"]["yaw"] == 0 and asked["by"] == "AI · x"
        assert 0 < asked["wait"] < 30
        assert shot.jpeg == JPEG and shot.info["eyes"] == 3.2

    asyncio.run(run())


def test_no_page_says_what_to_ask(monkeypatch):
    monkeypatch.setattr(eyes, "CONNECT", 0.2)

    async def run():
        deadline = asyncio.get_running_loop().time() + 30
        with pytest.raises(LookError, match=r"https://cad-roam\.reflex-ddns\.com/room/house"):
            await eyes.take("cad/house", "house", HOUSE, 1, View([0, 0, 1.6]), 10.5, (64, 64), "AI", deadline)
        # Someone is opening it: waits a moment for its 3D view, then says the same.
        presence.enter("cad/house", "p", "t", "x@x", "X")
        started = asyncio.get_running_loop().time()
        with pytest.raises(LookError, match="Nobody has this model open"):
            await eyes.take("cad/house", "house", HOUSE, 1, View([0, 0, 1.6]), 10.5, (64, 64), "AI", deadline)
        assert asyncio.get_running_loop().time() - started >= 0.2

    # eyes.take reads time.monotonic(); the loop's clock is the same one.
    asyncio.run(run())


def test_a_page_that_refuses_says_why():
    async def run():
        at_model("ann", FakeTab(answer={"ok": False, "error": "The model is big", "why": "big"}))
        with pytest.raises(LookError, match="The model is big"):
            await eyes.take("cad/house", "house", HOUSE, 1, View([0, 0, 1.6]), 10.5, (64, 64), "AI", asyncio.get_running_loop().time() + 30)
        presence._worlds.clear()
        at_model("ben", FakeTab(answer={"ok": True, "jpeg": base64.b64encode(b"not a jpeg").decode()}))
        with pytest.raises(LookError, match="no picture"):
            await eyes.take("cad/house", "house", HOUSE, 1, View([0, 0, 1.6]), 10.5, (64, 64), "AI", asyncio.get_running_loop().time() + 30)

    asyncio.run(run())


# ------------------------------------------------------------ the tools


@pytest.fixture
def house(monkeypatch):
    world = {"key": "cad/house", "title": "The house", "rev": 3, "things": [HOUSE]}
    monkeypatch.setattr(ai_tools.models, "find", lambda room: "cad/house" if room == "house" else "")
    monkeypatch.setattr(ai_tools.models.WORLDS, "get", lambda key: world)
    return world


def test_the_tools_are_offered(monkeypatch):
    monkeypatch.setattr(ddns_tools, "_tools", {})
    app = type("App", (), {"_api": Starlette()})()
    ai_tools.register(app)
    manifest = {t["name"]: t for t in ddns_tools.manifest()["tools"]}
    assert set(manifest) == {"roam.view", "roam.tour", "roam.where"}
    assert all(t["kind"] == "read" for t in manifest.values())
    view = manifest["roam.view"]["input_schema"]
    assert view["required"] == ["room", "at"]
    assert view["properties"]["at"] == {"type": "array", "items": {"type": "number"}, "description": ai_tools.AT}
    assert view["properties"]["time"]["anyOf"] == [{"type": "number"}, {"type": "string"}]
    assert manifest["roam.tour"]["input_schema"]["properties"]["stops"]["items"] == {"type": "object"}


def test_view_returns_the_picture_with_what_it_saw(house):
    async def run():
        at_model("ann", FakeTab(answer=a_picture))
        out = await ai_tools.view(CTX, "house", [0, -4, 1.6], look_at=[3, -4, 1.6], time="12:30")
        assert out["picture"] == {IMAGE_KEY: True, "mime": "image/jpeg", "data": base64.b64encode(JPEG).decode()}
        assert out["at"] == [0.0, -4.0, 1.6] and out["heading"] == 90 and out["pitch"] == 0
        assert out["time"] == "12:30" and out["eyes"] == 3.2 and out["light_here"] == 0.05 and out["ahead_m"] == 4.2
        assert out["picture_brightness"] == {"mean": 90, "dark": 0.1, "bright": 0.0}
        assert out["drawn_with"] == "shadows and the light inside"
        with pytest.raises(ValueError, match="no model"):
            await ai_tools.view(CTX, "nothing", [0, 0, 0])

    asyncio.run(run())


def test_a_tour_takes_each_stop_and_names_those_left(house, monkeypatch):
    async def run():
        sock = FakeTab(answer=a_picture)
        at_model("ann", sock)
        stops = [{"at": [0, -4, 1.6], "name": "door"}, {"at": [0, 0, 1.6], "heading": 180, "pitch": -10}]
        out = await ai_tools.tour(CTX, "house", stops, time=16.5)
        assert [s["name"] for s in out["stops"]] == ["door", "stop 2"] and out["time"] == "16:30"
        assert out["stops"][1]["heading"] == 180 and out["stops"][1]["pitch"] == -10 and "not_taken" not in out
        assert [m["size"] for m in sock.sent] == [list(eyes.TOUR_SIZE)] * 2
        # Bad stops are found before any picture.
        with pytest.raises(LookError, match="stop 2"):
            await ai_tools.tour(CTX, "house", [{"at": [0, 0, 1]}, {"at": [0, 0]}])
        with pytest.raises(LookError, match="unknown"):
            await ai_tools.tour(CTX, "house", [{"at": [0, 0, 1], "yaw": 1}])
        # The page stops answering after the first picture: the rest are named.
        answers = iter([a_picture({}), None, None])

        def first_only(message):
            reply = next(answers)
            return reply if reply is not None else {"ok": False, "error": "The CAD Roam page is still loading the model: call again in a moment.", "why": "loading"}

        presence._worlds.clear()
        at_model("ben", FakeTab(answer=first_only))
        out = await ai_tools.tour(CTX, "house", [{"at": [0, 0, 1], "name": n} for n in ("a", "b", "c")])
        assert [s["name"] for s in out["stops"]] == ["a"] and out["not_taken"] == ["b", "c"]
        assert "still loading" in out["note"]

    asyncio.run(run())


def test_where_says_where_people_look_from(house):
    async def run():
        at_model("ann", FakeTab())
        HUB.pose("cad/house", "ann", {"p": [0, 0, 4], "yaw": -math.pi / 2, "pitch": 0.1, "mode": "walk", "time": 16.5})
        at_model("ben", FakeTab())
        HUB.pose("cad/house", "ben", {"p": [2, 5, 0], "yaw": 0, "pitch": 0, "mode": "fly"})
        out = await ai_tools.where(CTX, "house")
        ann, ben = out["people"]
        assert ann["name"] == "Ann" and ann["at"] == [0.0, -4.0, 1.62] and ann["heading"] == 90 and ann["time"] == "16:30"
        assert ann["mode"] == "walking" and ann["pitch"] == pytest.approx(5.7)
        assert ben["at"] == [2.0, 0.0, 5.0] and ben["mode"] == "flying" and ben["time"] is None
        assert out["unit_m"] == 1.0 and out["box"] == HOUSE["box"] and out["pages"] == 2
        assert out["address"].endswith("/room/house")

    asyncio.run(run())
