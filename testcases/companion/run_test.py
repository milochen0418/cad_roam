"""The talking AI at the fixture's house (testcases/fixtures.py): the page tells a dialog over it
what it shows (window.__ddnsContext: the model, where you are in its own coordinates, where you look,
the sun's time, who else is here, and how to see it with roam.view); the AI button in the top bar
and Alt+A open the AI Hub's ai.talk dialog (one at a time) with this app, the model's id and the
language; closed, it opens again; the button in 繁體中文."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from common import launch, log, new_page, open_model, place, settle, shot, state, wait_for  # noqa: E402

EYE = 1.62


def context(page) -> dict:
    return page.evaluate("() => (typeof window.__ddnsContext === 'function' ? window.__ddnsContext() : null)")


def dialogs(page) -> list[str]:
    return page.evaluate("() => [...document.querySelectorAll('iframe[data-intent-action=\"ai.talk\"]')].map((f) => f.src)")


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = launch(pw)
        page = new_page(browser, errors, "ann")
        open_model(page, "house")
        settle(page, 0.5)

        # --- what the page tells the AI: in front of the house, outside, facing it.
        c = context(page)
        log("context:", c["text"])
        assert c["app"] == "cad-roam" and c["room"] == "house" and c["mode"] == "walking", c
        assert c["title"] == "House" and c["inside"] is False, c
        s = state(page)
        # The house is 10 x 8 m in metres at the origin: the model's coordinates equal the world's
        # (x, -z) with the eyes 1.62 m up.
        assert abs(c["at"][0] - s["position"][0]) < 0.02 and abs(c["at"][1] + s["position"][2]) < 0.02, (c["at"], s["position"])
        assert abs(c["at"][2] - (s["position"][1] + EYE)) < 0.02, (c["at"], s["position"])
        assert c["heading"] == round((-math.degrees(s["yaw"])) % 360, 1), (c["heading"], s["yaw"])
        for words in ("walking outside", 'the model "House"', "10 × 8 m, 3.2 m high", "roam.view", 'room="house"', "Nobody else is here", "Sun time 10:30"):
            assert words in c["text"], (words, c["text"])

        # --- inside, looking east along the back wall: the numbers follow.
        place(page, 0.0, 0.0, 0.0, -math.pi / 2, 0.0)
        settle(page, 0.3)
        c = context(page)
        log("inside:", c["text"])
        assert c["inside"] is True and abs(c["heading"] - 90) < 0.6 and c["ahead"] is not None and 4 < c["ahead"] < 5.5, c
        assert "walking inside" in c["text"] and f"at=[{c['at'][0]}, {c['at'][1]}, {c['at'][2]}]" in c["text"], c["text"]

        # --- the AI button opens the hub's dialog for this model, once.
        page.click("#ddns-ai-button")
        wait_for(lambda: len(dialogs(page)) == 1, "the AI dialog")
        src = dialogs(page)[0]
        log("dialog:", src)
        assert src.startswith("http://127.0.0.1:9/intent/ai-talk?") and "in_app=cad-roam" in src and "room=house" in src and "lang=en" in src, src
        assert page.evaluate("() => document.querySelector('[data-intent-dialog][data-intent-front=\"1\"]') !== null")
        shot(page, "01-dialog")
        # Pressed again (Alt+A reaches the page while the dialog is in front): the same dialog.
        page.evaluate("() => document.getElementById('ddns-ai-button').click()")
        settle(page, 0.5)
        assert len(dialogs(page)) == 1, "a second press must not open a second dialog"

        # --- closed with its ×, Alt+A opens it again (a pointer lock, if any, is released first).
        page.click("[data-intent-dialog][data-intent-front='1'] button[aria-label='Close']")
        wait_for(lambda: len(dialogs(page)) == 0, "the dialog closed")
        page.keyboard.press("Alt+A")
        wait_for(lambda: len(dialogs(page)) == 1, "the AI dialog again")
        assert page.evaluate("() => document.pointerLockElement") is None
        page.click("[data-intent-dialog][data-intent-front='1'] button[aria-label='Close']")
        wait_for(lambda: len(dialogs(page)) == 0, "the dialog closed again")

        # --- in 繁體中文.
        page.click("#lang-toggle")
        wait_for(lambda: "跟 AI 聊聊" in (page.get_attribute("#ddns-ai-button", "title") or ""), "the Chinese title")
        page.click("#ddns-ai-button")
        wait_for(lambda: len(dialogs(page)) == 1, "the dialog in Chinese")
        assert "lang=zh-TW" in dialogs(page)[0], dialogs(page)
        shot(page, "02-zh")
        browser.close()
    if errors:
        for e in errors:
            log("ERROR", e)
        return 1
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
