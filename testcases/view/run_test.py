"""Seeing yourself from behind at the fixture's house (testcases/fixtures.py): through your eyes at
first (the camera at your eyes, your figure not drawn); V puts the camera a little behind and above
you, your figure drawn in your colour, the torch still where you are, and the camera follows as you
walk; inside, turned to the door, the back wall behind you keeps the camera inside, and with your
back against the wall your figure isn't drawn; the drone is seen from behind too, and its camera
stops at a wall unless it is a ghost; V again is your eyes; the Behind and Eyes buttons, kept over a
reload; the buttons in 繁體中文."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from common import hold, launch, log, new_page, open_model, place, settle, shot, state, thing, wait_for, wait_world  # noqa: E402

# view.js: how far behind and above your eyes (walking) or your drone (flying) the camera is, and
# how far it keeps from a wall.
BACK, ABOVE, FLY_BACK, FLY_ABOVE, CLEAR = 4.0, 0.45, 2.0, 0.5, 0.25
EYE = 1.62

# Draws a frame and counts the pixels in your colour (hue within 18°, clearly coloured): your
# figure's clothes, which nothing else at the house has.
MY_SHARE = """() => {
  const e = window.__roam, r = e.renderer;
  e.look.frame();
  r.render(e.scene, e.camera);
  const gl = r.getContext(), w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
  const px = new Uint8Array(w * h * 4);
  gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
  const hue = (r, g, b) => {
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
    if (d < 1) return [0, 0];
    const h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return [(h * 60 + 360) % 360, d / mx];
  };
  const hex = e.view.color;
  const [mine] = hue(...[1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)));
  let n = 0, hits = 0;
  for (let y = 0; y < h; y += 2) {
    for (let x = 0; x < w; x += 2) {
      const i = (y * w + x) * 4, [hh, s] = hue(px[i], px[i + 1], px[i + 2]);
      const dh = Math.abs(hh - mine);
      n++;
      if (s > 0.45 && Math.min(dh, 360 - dh) < 18) hits++;
    }
  }
  return hits / n;
}"""


def cam(page):
    st = state(page)
    return st["camera"], st["position"], st


def near(a, b, tol):
    return abs(a - b) <= tol


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = launch(pw)
        page = new_page(browser, errors, "A")
        open_model(page, "house")
        h = thing(page, "cad/house")
        X, Z = h["x"], h["z"]

        # Through your eyes: the camera is where your eyes are, your figure isn't drawn.
        place(page, X, 0, Z + 12, 0)
        settle(page, 0.5)
        c, p, st = cam(page)
        log("eyes:", [round(v, 2) for v in c], "feet", [round(v, 2) for v in p])
        assert st["view"] == "eyes" and not st["myFigure"], st
        assert near(c[0], p[0], 0.01) and near(c[2], p[2], 0.01) and near(c[1], p[1] + EYE, 0.05), (c, p)
        eyes_share = page.evaluate(MY_SHARE)
        assert eyes_share < 0.001, eyes_share
        assert page.get_attribute("#rm-eyes", "class").endswith("is-on")

        # V: a little behind and above you (you face -Z, so behind is +Z), your figure drawn.
        page.keyboard.press("v")
        wait_for(lambda: state(page)["view"] == "behind", "the view from behind")
        settle(page, 2.0)
        c, p, st = cam(page)
        log("behind:", [round(c[i] - p[i], 2) for i in range(3)], "figure", st["myFigure"])
        assert st["myFigure"], st
        assert near(c[2] - p[2], BACK, 0.08) and near(c[1] - p[1], EYE + ABOVE, 0.05) and near(c[0], p[0], 0.02), (c, p)
        share = page.evaluate(MY_SHARE)
        log("your colour on screen:", round(share, 4), "through your eyes:", round(eyes_share, 4))
        assert share > 0.004, share
        assert page.get_attribute("#rm-behind", "class").endswith("is-on")
        # The torch shines from you (just over your head), not from the camera behind you.
        torch = page.evaluate("() => { const e = window.__roam; return e.torch.getWorldPosition(e.camera.position.clone()).toArray(); }")
        assert math.dist(torch, [p[0], p[1] + EYE + ABOVE, p[2] + 0.1]) < 0.05, (torch, p)
        shot(page, "01-behind")

        # Walking, it follows.
        hold(page, "w", 1.0)
        c, p, _ = cam(page)
        log("walking:", round(c[2] - p[2], 2))
        assert near(c[2] - p[2], BACK, 0.15), (c, p)

        # Inside, turned to the door: the back wall (inner face Z - 3.75) is 1.75 m behind you, and
        # the camera stays inside, CLEAR from it.
        place(page, X - 2, 0.05, Z - 2.0, math.pi)
        settle(page, 2.0)
        c, p, st = cam(page)
        log("inside, the wall behind:", round(c[2] - Z, 2), "figure", st["myFigure"])
        assert Z - 3.75 < c[2] < Z - 2.0 and near(c[2], Z - 3.75 + CLEAR, 0.1), c
        assert st["myFigure"], st
        shot(page, "02-inside")

        # Your back against the wall: the camera can't get behind you, so your figure isn't drawn.
        place(page, X - 2, 0.05, Z - 3.75 + 0.32, math.pi)
        settle(page, 1.0)
        c, p, st = cam(page)
        log("against the wall:", round(c[2] - Z, 2), "figure", st["myFigure"])
        assert c[2] > Z - 3.75 and not st["myFigure"], (c, st["myFigure"])

        # The drone, from behind.
        page.keyboard.press("f")
        wait_for(lambda: state(page)["mode"] == "fly", "drone mode")
        place(page, X + 3, 2.0, Z + 9, 0)
        settle(page, 2.0)
        c, p, st = cam(page)
        log("drone from behind:", [round(c[i] - p[i], 2) for i in range(3)], "figure", st["myFigure"])
        assert near(c[2] - p[2], FLY_BACK, 0.08) and near(c[1] - p[1], FLY_ABOVE, 0.05) and st["myFigure"], (c, p)
        shot(page, "03-drone")

        # Turned away from the house, its front wall (outer face Z + 4) right behind: the camera
        # stops in front of it ...
        place(page, X + 3, 2.0, Z + 4.8, math.pi)
        settle(page, 1.5)
        c, p, _ = cam(page)
        log("drone, the wall behind:", round(c[2] - Z, 2))
        assert Z + 4.0 < c[2] < Z + 4.8, c
        # ... unless it is a ghost: then it goes through the wall too.
        page.keyboard.press("g")
        wait_for(lambda: state(page)["ghost"], "ghost on")
        settle(page, 2.0)
        c, p, _ = cam(page)
        log("ghost drone:", round(c[2] - Z, 2))
        assert near(c[2], Z + 4.8 - FLY_BACK, 0.1), c
        page.keyboard.press("g")

        # V again: your (drone's) eyes.
        page.keyboard.press("v")
        wait_for(lambda: state(page)["view"] == "eyes", "your eyes again")
        settle(page, 1.5)
        c, p, st = cam(page)
        assert math.dist(c, p) < 0.02 and not st["myFigure"], (c, p, st["myFigure"])
        page.keyboard.press("f")
        wait_for(lambda: state(page)["mode"] == "walk", "walking again")

        # The buttons, and the browser keeps the choice.
        page.click("#rm-behind")
        wait_for(lambda: state(page)["view"] == "behind", "Behind pressed")
        page.reload(wait_until="domcontentloaded")
        wait_world(page)
        st = state(page)
        assert st["view"] == "behind" and page.get_attribute("#rm-behind", "class").endswith("is-on"), st["view"]
        settle(page, 1.0)
        assert state(page)["myFigure"]
        page.click("#rm-eyes")
        wait_for(lambda: state(page)["view"] == "eyes", "Eyes pressed")

        # 繁體中文.
        page.click("#lang-toggle")
        wait_for(lambda: page.inner_text("#rm-behind") == "背後視角", "the buttons in Chinese")
        assert page.inner_text("#rm-eyes") == "眼睛視角"
        page.click("#lang-toggle")
        wait_for(lambda: page.inner_text("#rm-behind") == "Behind", "English again")
        browser.close()
    if errors:
        print("\n".join(errors))
        return 1
    log("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
