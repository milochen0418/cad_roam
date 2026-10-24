"""Two people at one model: each sees the other (a figure and a chip with their name), sees them
move and take off as a drone, can go to them with a click on their chip, and sees them go when
their tab closes. Someone at another model is not seen."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from common import launch, log, new_page, open_model, place, shot, state, thing, wait_for  # noqa: E402


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = launch(pw)
        a = new_page(browser, errors, "A", width=1100, height=720)
        b = new_page(browser, errors, "B", width=1100, height=720)
        c = new_page(browser, errors, "C", width=800, height=600)
        open_model(a, "house")
        open_model(b, "house")
        open_model(c, "tower")
        wait_for(lambda: len(state(a)["people"]) == 2 and len(state(b)["people"]) == 2, "both see two people")
        assert len(state(c)["people"]) == 1, "the tower is another place"
        peer_b = b.evaluate("() => window.__roam.opts.me.peer")
        wait_for(lambda: peer_b in state(a)["figures"], "A draws B")
        wait_for(lambda: a.locator(f'.rm-chip[data-peer="{peer_b}"]').count() == 1, "B's chip on A's screen")
        log("A sees", [p["name"] for p in state(a)["people"]])

        # B takes off over the house: A sees where.
        h = thing(b, "cad/house")
        b.keyboard.press("f")
        wait_for(lambda: state(b)["mode"] == "fly", "B flies")
        target = [h["x"] + 6, 9.0, h["z"] + 7]
        place(b, *target, 0.6)

        def b_on_a():
            p = next((p for p in state(a)["people"] if p["id"] == peer_b), None)
            return p and p["mode"] == "fly" and abs(p["p"][0] - target[0]) < 0.5 and abs(p["p"][1] - target[1]) < 0.5

        wait_for(b_on_a, "A sees B flying over the house", 20)
        shot(b, "01-b-flying")

        # A goes to B with a click on B's chip.
        a.click(f'.rm-chip[data-peer="{peer_b}"]')
        wait_for(lambda: a.evaluate("() => !window.__roam._tween") and state(a)["mode"] == "fly", "A flew to B")
        pa = state(a)["position"]
        dist = sum((pa[i] - target[i]) ** 2 for i in range(3)) ** 0.5
        log("A is", round(dist, 1), "m from B")
        assert dist < 6, pa
        shot(a, "02-a-near-b")

        # B's tab closes: A sees B go.
        b.context.close()
        wait_for(lambda: len(state(a)["people"]) == 1 and not state(a)["figures"], "A sees B leave", 15)
        log("B left")
        browser.close()
    if errors:
        print("\n".join(errors))
        return 1
    log("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
