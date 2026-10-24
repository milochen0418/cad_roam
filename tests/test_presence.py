import pytest

from cad_roam import presence


@pytest.fixture(autouse=True)
def empty():
    presence._worlds.clear()
    yield
    presence._worlds.clear()


def test_colours_follow_the_person():
    a = presence.enter("w", "p1", "t1", "ann@x", "Ann", now=0)
    b = presence.enter("w", "p2", "t2", "ben@x", "Ben", now=0)
    a2 = presence.enter("w", "p3", "t3", "ann@x", "Ann", now=0)
    assert a.color != b.color and a2.color == a.color
    assert presence.users_in("w") == ["ann@x", "ben@x"]
    assert [p["name"] for p in presence.visitors()["w"]] == ["Ann", "Ben"]


def test_a_tab_is_in_one_world():
    presence.enter("w1", "p1", "t1", "ann@x", "Ann")
    presence.enter("w2", "p1", "t1", "ann@x", "Ann")
    assert presence.where("p1") == "w2" and "w1" not in presence.visitors()
    assert presence.leave("p1") == "w2" and presence.where("p1") == ""


def test_quiet_tabs_without_a_socket_are_dropped():
    presence.enter("w", "p1", "t1", "ann@x", "Ann", now=100)
    presence.enter("w", "p2", "t2", "ben@x", "Ben", now=100)
    presence.HUB.attach("w", "p2", "t2", object())
    assert presence.prune(now=100 + presence.IDLE + 1) == ["w"]
    assert [p["id"] for p in presence.people("w")] == ["p2"]


def test_a_socket_needs_the_tabs_token():
    presence.enter("w", "p1", "t1", "ann@x", "Ann")
    sock = object()
    assert not presence.HUB.attach("w", "p1", "wrong", sock)
    assert not presence.HUB.attach("w", "nobody", "t1", sock)
    assert presence.HUB.attach("w", "p1", "t1", sock)
    newer = object()
    assert presence.HUB.attach("w", "p1", "t1", newer)
    assert not presence.HUB.detach("w", "p1", sock)  # an older socket closing doesn't count
    assert presence.HUB.detach("w", "p1", newer) and presence.where("p1") == ""


def test_poses_are_cleaned():
    presence.enter("w", "p1", "t1", "ann@x", "Ann")
    msg = presence.HUB.pose("w", "p1", {"p": [1.23456, "2", float("nan")], "yaw": 1e9, "pitch": 0.5, "mode": "jump"})
    assert msg == {"t": "pose", "id": "p1", "p": [1.235, 2.0, 0.0], "yaw": 0.0, "pitch": 0.5, "mode": "walk", "moving": False}
    assert presence.HUB.pose("w", "p1", {"p": [1, 2]}) is None
    assert presence.HUB.pose("w", "ghost", {"p": [1, 2, 3]}) is None
