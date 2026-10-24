"""The place follows its model: the house rebuilt (as Codoc in CAD does when someone presses Run)
is swapped in while you stand at it, and a model that had never built appears the moment it does,
with you in front of it."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

import fixtures  # noqa: E402
from common import COLLECTIONS, launch, log, new_page, open_model, shot, state, thing, wait_for  # noqa: E402


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = launch(pw)
        page = new_page(browser, errors, "A")
        open_model(page, "house")
        before = thing(page, "cad/house")
        rev = state(page)["rev"]
        log("house", before["h"], "m high, rev", rev)

        fixtures.rebuild_house(COLLECTIONS, 5.0)
        wait_for(lambda: state(page)["rev"] > rev, "the place changed", 30)
        wait_for(lambda: abs(thing(page, "cad/house")["h"] - 5.2) < 1e-6, "the house is 5.2 m high", 30)
        wait_for(lambda: state(page)["things"]["cad/house"] == "ready", "its new mesh is in", 120)
        after = thing(page, "cad/house")
        assert after["mesh"] != before["mesh"] and (after["x"], after["z"]) == (before["x"], before["z"])
        assert page.evaluate("() => window.__roam.replacing.size") == 0
        log("rebuilt: house", after["h"], "m high")
        shot(page, "01-rebuilt")

        open_model(page, "sketch")
        assert state(page)["things"] == {}
        wait_for(lambda: "hasn't been built yet" in page.inner_text("body"), "the not-built notice")
        fixtures.build_sketch(COLLECTIONS)
        wait_for(lambda: "cad/sketch" in state(page)["things"], "the sketch appears", 30)
        wait_for(lambda: state(page)["things"]["cad/sketch"] == "ready", "the sketch loaded", 120)
        wait_for(lambda: "hasn't been built yet" not in page.inner_text("body"), "the notice is gone")
        s = thing(page, "cad/sketch")
        z = state(page)["position"][2]
        log("sketch", s["w"], "x", s["d"], "m; standing at z", round(z, 2))
        assert z > s["z"] + s["d"] / 2, "in front of it"
        shot(page, "02-built")
        browser.close()
    if errors:
        print("\n".join(errors))
        return 1
    log("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
