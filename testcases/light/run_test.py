"""The light inside a model (assets/roam/light.js), with shadows on: in the fixture's chapel (its
blue window in the east wall, its warm lamp 4 m up in the middle) the light is worked out, and then
its lamp lights what is round it (beside it, a face turned to it gets many times the light of one
turned away, in the lamp's warm colour; the same under it, looking up); in the morning, the sun
through the blue window fills the chapel with blue light, in the evening (the sun in the west) not;
inside, the view is brighter than outside, as eyes get used to the dark, and outside it is as it
was. The house, an STL (one colour, no glass, no lamps), gets its light through its door: its floor
inside is darker than its roof under the sky. Fast (no shadows) works out no light."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from common import launch, light_at, log, model_place, new_page, open_model, settle, shot, state, wait_for, wait_light  # noqa: E402

CHAPEL, HOUSE = "cad/chapel", "cad/house"
UP, DOWN, EAST, WEST, ALL = (0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 0, 0)


def lum(rgb) -> float:
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def at_time(page, hours: float) -> dict:
    page.fill(".rm-sun-range", str(hours))
    wait_for(lambda: state(page)["time"] == hours, f"the sun at {hours}")
    settle(page, 0.3)
    return wait_light(page)


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = launch(pw)
        page = new_page(browser, errors, "A", quality="high")
        open_model(page, "chapel")
        light = wait_light(page)
        log("chapel's light:", light)
        assert light["cells"] and light["cell"] >= 0.35, light

        # The lamp lights what is round it: beside it (the lamp is 0.6 m wide, 4 to 4.3 m up), a face
        # turned to it gets many times the light of one turned away, in its warm colour; the same
        # under it.
        light = at_time(page, 16.5)
        toward, away = light_at(page, CHAPEL, 0.9, 0.0, 4.15, WEST), light_at(page, CHAPEL, 0.9, 0.0, 4.15, EAST)
        up, down = light_at(page, CHAPEL, 0.0, 0.0, 3.4, UP), light_at(page, CHAPEL, 0.0, 0.0, 3.4, DOWN)
        log("beside the lamp, toward it:", toward, "away:", away, "under it, up:", up, "down:", down)
        for lit, dark in ((toward, away), (up, down)):
            assert lit["sure"] > 0.5 and dark["sure"] > 0.5, (lit, dark)
            r, g, b = lit["light"]
            assert r > g > b and r > 2 * b, lit
            assert lum(lit["light"]) > 3 * lum(dark["light"]), (lit, dark)

        # From under it: the lamp in its own colour, the roof round it lit.
        model_place(page, CHAPEL, 0.0, 0.0, 0.0, 0.0, 1.57)
        settle(page, 1.0)
        shot(page, "01-lamp")

        # The evening sun is behind the chapel: no blue light in it; the morning sun comes in
        # through its blue window and fills it with blue light.
        evening = light_at(page, CHAPEL, 0.0, 0.0, 1.6, ALL)
        light = at_time(page, 7.5)
        morning = light_at(page, CHAPEL, 0.0, 0.0, 1.6, ALL)
        log("in the middle of the chapel, evening:", evening, "morning:", morning)
        r, g, b = morning["light"]
        assert b > 1.15 * r and b > g, morning
        r, g, b = evening["light"]
        assert b < 0.8 * r, evening
        model_place(page, CHAPEL, -2.0, 1.0, 0.0, -1.2, -0.2)
        settle(page, 1.0)
        shot(page, "02-morning")

        # Inside, eyes get used to the dark; outside, the view is as it was.
        inside = state(page)["light"]["brightness"]
        model_place(page, CHAPEL, 0.0, -14.0, 0.0, 0.0, 0.1)
        wait_for(lambda: state(page)["light"]["brightness"] < 1.1, "eyes used to the outside", 60)
        outside = state(page)["light"]["brightness"]
        log("brightness inside:", inside, "outside:", outside)
        assert inside > 1.5, inside
        shot(page, "03-outside")

        # The house: light only through its door.
        open_model(page, "house")
        light = wait_light(page)
        log("house's light:", light)
        floor = light_at(page, HOUSE, -3.0, 2.0, 0.06, UP)
        roof = light_at(page, HOUSE, 0.0, 0.0, 3.21, UP)
        log("house's floor:", floor, "its roof:", roof)
        assert lum(floor["light"]) < 0.5 * lum(roof["light"]), (floor, roof)

        # Fast: no light worked out.
        fast = new_page(browser, errors, "B", quality="low")
        open_model(fast, "chapel")
        settle(fast, 1.0)
        light = state(fast)["light"]
        log("Fast:", light)
        assert light["cells"] is None and light["brightness"] == 1, light
        browser.close()
    if errors:
        print("\n".join(errors))
        return 1
    log("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
