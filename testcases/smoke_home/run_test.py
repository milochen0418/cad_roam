"""The list page and arriving: the models with their real sizes (and the one not built yet), a
pasted Codoc in CAD link lands in front of that model, a link CAD Roam can't find says so,
繁體中文, a card opens its model, and a model that never built says how to build it."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from common import BASE_URL, launch, log, new_page, shot, state, thing, wait_for, wait_world  # noqa: E402


def path(page) -> str:
    return page.evaluate("() => location.pathname + location.search")


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = launch(pw)
        page = new_page(browser, errors, "A")
        page.goto(BASE_URL + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".rm-card", timeout=120000)
        cards = page.eval_on_selector_all(".rm-card", "els => els.map(e => [e.dataset.key, e.innerText])")
        log("cards", [c[0] for c in cards])
        assert {c[0] for c in cards} == {"cad/house", "cad/tower", "cad/part", "cad/sketch"}, cards
        text = dict(cards)
        assert "10 × 8 m, 3.2 m high" in text["cad/house"], text["cad/house"]
        assert "4 × 4 m, 30 m high" in text["cad/tower"], text["cad/tower"]
        assert "Not built yet" in text["cad/sketch"], text["cad/sketch"]
        shot(page, "01-home")

        # A pasted Codoc in CAD link: in front of that model.
        page.fill("#paste", "https://cad.reflex-ddns.com/room/house")
        page.click("#paste-go")
        # The first visit of a model page compiles its 3D code in a fresh dev server: be patient.
        wait_for(lambda: path(page) == "/room/house", "the house's page", 240)
        st = wait_world(page)
        house = thing(page, "cad/house")
        log("arrived at", [round(v, 2) for v in st["position"]], "house", house["x"], house["z"])
        assert list(st["things"]) == ["cad/house"] and st["things"]["cad/house"] == "ready"
        assert abs(st["position"][0] - house["x"]) < 0.5 and st["position"][2] > house["z"] + house["d"] / 2
        assert page.inner_text("#model-title") == "House"
        shot(page, "02-house")

        page.goto(BASE_URL + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".rm-card")
        page.fill("#paste", "https://cad.reflex-ddns.com/room/nothing-here")
        page.click("#paste-go")
        page.wait_for_selector("#paste-error")
        log("unknown link:", page.inner_text("#paste-error"))

        page.click("#lang-toggle")
        wait_for(lambda: "走進你的 CAD 模型" in page.inner_text("h1"), "the Chinese title")
        wait_for(lambda: "10 × 8 公尺，高 3.2 公尺" in page.inner_text("#models"), "Chinese sizes")
        shot(page, "03-home-zh")
        page.click("#lang-toggle")
        wait_for(lambda: "Walk into" in page.inner_text("h1"), "English again")

        # A card opens its model.
        page.click('.rm-card[data-key="cad/tower"]')
        wait_for(lambda: path(page) == "/room/tower", "the tower's page", 60)
        st = wait_world(page)
        assert list(st["things"]) == ["cad/tower"]
        shot(page, "04-tower")

        # A model that never built: nothing to walk around yet, and how to build it.
        page.goto(BASE_URL + "/room/sketch", wait_until="domcontentloaded")
        st = wait_world(page)
        assert st["things"] == {}
        wait_for(lambda: "hasn't been built yet" in page.inner_text("body"), "the not-built notice")
        page.goto(BASE_URL + "/room/no-such-model", wait_until="domcontentloaded")
        wait_for(lambda: "no such model" in page.inner_text("body"), "the no-such-model notice")
        browser.close()
    if errors:
        print("\n".join(errors))
        return 1
    log("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
