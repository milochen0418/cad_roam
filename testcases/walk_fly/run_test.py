"""Walking and flying at the fixture's house (testcases/fixtures.py): in through its door until
the back wall stops you, its front wall stops you outside, up its steps onto the platform, a jump;
the drone climbs, bumps into the house and, as a ghost, flies through its wall; the Details card
has its real size from its code; at the part (a 6 cm block), a size chosen on the card makes it
bigger for everyone; the switcher takes you to another model."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from common import BASE_URL, hold, launch, log, new_page, open_model, place, settle, shot, state, thing, wait_for, wait_world  # noqa: E402


def pos(page):
    return state(page)["position"]


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = launch(pw)
        page = new_page(browser, errors, "A")
        open_model(page, "house")
        h = thing(page, "cad/house")
        X, Z = h["x"], h["z"]
        log("house at", X, Z, "size", h["w"], h["d"], h["h"])
        assert (h["w"], h["d"]) == (10.0, 8.0) and h["unit"] == 1.0 and h["unit_from"] == "code"

        # In through the door: the back wall (inner face Z - 3.75) stops us.
        place(page, X, 0, Z + 7, 0)
        hold(page, "w", 3.5)
        x, y, z = pos(page)
        log("through the door:", round(x, 2), round(y, 2), round(z, 2))
        assert Z - 3.75 + 0.2 < z < Z - 3.0, f"stopped by the back wall, z={z}"
        assert abs(x - X) < 0.3
        shot(page, "01-inside")

        # Outside, right of the door: the front wall (outer face Z + 4) stops us.
        place(page, X + 3, 0, Z + 7, 0)
        hold(page, "w", 2.0)
        z = pos(page)[2]
        log("against the front wall:", round(z, 2))
        assert Z + 4.15 < z < Z + 4.5, z

        # Up the steps (0.17 m each) onto the 1.02 m platform.
        place(page, X + 3, 0, Z + 1.2, 0)
        hold(page, "w", 2.5)
        x, y, z = pos(page)
        log("up the steps:", round(y, 2), round(z, 2))
        assert y > 0.95 and z < Z - 1.75, (y, z)
        shot(page, "02-platform")

        # A jump on flat ground.
        place(page, X, 0, Z + 12, 0)
        settle(page, 0.5)
        page.keyboard.down(" ")
        top = 0.0
        for _ in range(40):
            top = max(top, pos(page)[1])
            page.wait_for_timeout(50)
        page.keyboard.up(" ")
        log("jumped to", round(top, 2))
        assert top > 0.5, top

        # The drone: F, then up.
        page.keyboard.press("f")
        wait_for(lambda: state(page)["mode"] == "fly", "drone mode")
        hold(page, " ", 2.0)
        st = state(page)
        log("drone up:", [round(v, 1) for v in st["position"]], "alt", round(st["altitude"], 1))
        assert st["position"][1] > 8, st["position"]
        shot(page, "03-drone")

        # Into the house's front wall at 2 m (its face at Z + 4): it stops the drone ...
        place(page, X + 3, 2.0, Z + 9, 0)
        hold(page, "w", 2.0)
        z = pos(page)[2]
        log("drone at the wall:", round(z - Z, 2))
        assert Z + 4.2 < z < Z + 4.7, z
        # ... unless it is a ghost.
        page.keyboard.press("g")
        wait_for(lambda: state(page)["ghost"], "ghost on")
        hold(page, "w", 0.6)
        z = pos(page)[2]
        log("ghost inside:", round(z - Z, 2))
        assert z < Z + 3.5, z
        page.keyboard.press("g")
        page.keyboard.press("f")
        wait_for(lambda: state(page)["mode"] == "walk", "walking again")

        # The Details card: its real size, from its code; back to the entrance.
        page.click("#details-toggle")
        page.wait_for_selector("#card")
        measures, note = page.inner_text("#card-measures"), page.inner_text("#card-size-note")
        log("card:", measures, "|", note)
        assert measures == "10 × 8 m, 3.2 m high", measures
        assert note == "1 m per unit, as its code says", note
        page.click("#card-entrance")
        wait_for(lambda: page.evaluate("() => !window.__roam._tween") and pos(page)[2] > Z + 4, "back at the entrance")
        shot(page, "04-card")

        # The part: a 6 cm block on a pedestal; 1 cm per unit makes it 60 cm, for everyone.
        open_model(page, "part")
        p0 = thing(page, "cad/part")
        assert p0["unit_from"] == "default" and p0["pedestal"] > 0 and abs(p0["w"] - 0.06) < 1e-6
        rev = state(page)["rev"]
        page.click("#details-toggle")
        page.wait_for_selector("#card-unit")
        page.select_option("#card-unit", "0.01")
        wait_for(lambda: state(page)["rev"] > rev, "the place changed")
        wait_for(lambda: abs(thing(page, "cad/part")["w"] - 0.6) < 1e-6, "the part is 0.6 m wide")
        wait_for(lambda: "chosen here" in page.inner_text("#card-size-note"), "the card says it was chosen")
        wait_for(lambda: state(page)["things"]["cad/part"] == "ready", "the part loaded again")
        log("part now", thing(page, "cad/part")["w"], "m wide")
        shot(page, "05-part")
        page.select_option("#card-unit", "")
        wait_for(lambda: abs(thing(page, "cad/part")["w"] - 0.06) < 1e-6, "back to its code's size")

        # The switcher: to the tower.
        page.click("#switch-toggle")
        page.wait_for_selector('.rm-model[data-key="cad/tower"]')
        page.click('.rm-model[data-key="cad/tower"]')
        wait_for(lambda: page.evaluate("() => location.pathname") == "/room/tower", "the tower's page", 60)
        # The part's view stays until the page has opened the tower.
        wait_for(lambda: list((state(page) or {}).get("things", {})) == ["cad/tower"], "the tower in view", 60)
        wait_world(page)
        browser.close()
    if errors:
        print("\n".join(errors))
        return 1
    log("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
