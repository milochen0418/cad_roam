"""The fixture's chapel in its colours (testcases/fixtures.py: a GLB beside its STL, as Codoc in CAD
builds write them): each part in its colour, its window as glass, its lamp glowing. At 10:30 the
sun doesn't come in; T jumps on to 16:30 and 7:30, and in the morning sun the floor and the wall in
front of its blue east window turn blue; dragged to 16:30 (the sun in the west), the blue is gone
again, while the lamp, seen from under it, is bright in its warm colour, far brighter than the roof
round it (which it lights: the light suite); the time is still there after a reload. The house,
which has only an STL, is drawn in one colour."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from common import launch, log, new_page, open_model, place, settle, shot, state, wait_for, wait_world  # noqa: E402

# Draws a frame and counts the pixels that are clearly blue (looking away from the window, the blue
# can only be its light, on the floor and the wall).
BLUE_SHARE = """() => {
  const e = window.__roam, r = e.renderer;
  e.look.frame();
  r.render(e.scene, e.camera);
  const gl = r.getContext(), w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
  const px = new Uint8Array(w * h * 4);
  gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
  let blue = 0, n = 0;
  for (let y = 0; y < h; y += 2) {
    for (let x = 0; x < w; x += 2) {
      const i = (y * w + x) * 4;
      n++;
      if (px[i + 2] > px[i] + 25 && px[i + 2] > px[i + 1] + 8) blue++;
    }
  }
  return blue / n;
}"""

# Draws a frame and the mean colour of a 20 px square in the middle (the lamp, from under it) and
# of one further out (the roof round it).
LAMP_AND_ROOF = """() => {
  const e = window.__roam, r = e.renderer;
  e.look.frame();
  r.render(e.scene, e.camera);
  const gl = r.getContext(), w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
  const mean = (cx, cy) => {
    const px = new Uint8Array(20 * 20 * 4);
    gl.readPixels(Math.round(cx - 10), Math.round(cy - 10), 20, 20, gl.RGBA, gl.UNSIGNED_BYTE, px);
    const s = [0, 0, 0];
    for (let i = 0; i < px.length; i += 4) for (let k = 0; k < 3; k++) s[k] += px[i + k];
    return s.map((v) => Math.round(v / 400));
  };
  return [mean(w / 2, h / 2), mean(w * 0.15, h / 2)];
}"""


def sun(page) -> tuple[float, str]:
    return state(page)["time"], page.inner_text(".rm-sun-time")


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = launch(pw)
        # Shadows on: the sun through glass needs them (slow in software WebGL, the chapel is small).
        page = new_page(browser, errors, "A", quality="high")
        st = open_model(page, "chapel")
        looks = st["looks"]["cad/chapel"]
        log("chapel:", looks)
        assert looks == {"parts": 5, "glass": 1, "glow": 1}, looks

        # Inside, by the window, looking west-north-west and down, where the morning sun through it
        # falls on the floor.
        assert sun(page) == (10.5, "10:30"), sun(page)
        place(page, 1.0, 0, 0, 1.2, -0.5)
        settle(page, 1.0)
        day = page.evaluate(BLUE_SHARE)
        log("blue at 10:30:", round(day, 3))
        shot(page, "01-day")

        page.keyboard.press("t")
        wait_for(lambda: sun(page) == (16.5, "16:30"), "T: the evening")
        page.keyboard.press("t")
        wait_for(lambda: sun(page) == (7.5, "07:30"), "T: the morning")
        settle(page, 1.0)
        morning = page.evaluate(BLUE_SHARE)
        log("blue at 07:30:", round(morning, 3))
        shot(page, "02-morning")
        assert day < 0.02, day
        assert morning > 0.08 and morning > 5 * day, (day, morning)

        # The slider: the sun in the west, behind the chapel's back, lights no blue.
        page.fill(".rm-sun-range", "16.5")
        wait_for(lambda: sun(page) == (16.5, "16:30"), "dragged to 16:30")
        settle(page, 0.5)
        evening = page.evaluate(BLUE_SHARE)
        log("blue at 16:30:", round(evening, 3))
        assert evening < morning / 5, (morning, evening)

        # The lamp gives light: from under it, in the evening, it is bright in its warm colour, far
        # brighter than the roof round it.
        place(page, 0.0, 0, 0, 0.0, 1.57)
        settle(page, 0.5)
        lamp, roof = page.evaluate(LAMP_AND_ROOF)
        log("lamp:", lamp, "roof:", roof)
        shot(page, "03-lamp")
        # Its own colour as it is (fixtures.LAMP in sRGB), in the dark.
        assert all(abs(a - b) <= 12 for a, b in zip(lamp, (255, 196, 118))), lamp
        assert sum(roof) < 0.5 * sum(lamp), (lamp, roof)

        # Its window from inside, the morning sun behind it.
        page.fill(".rm-sun-range", "7.5")
        wait_for(lambda: sun(page) == (7.5, "07:30"), "dragged to 07:30")
        place(page, -2.0, 0, 0, -1.5708, 0.25)
        settle(page, 0.5)
        shot(page, "04-window")

        # The browser keeps the time.
        page.reload(wait_until="domcontentloaded")
        wait_world(page)
        assert sun(page) == (7.5, "07:30"), sun(page)

        # The house has no colours: one part, no glass.
        st = open_model(page, "house")
        log("house:", st["looks"]["cad/house"])
        assert st["looks"]["cad/house"] == {"parts": 1, "glass": 0, "glow": 0}
        browser.close()
    if errors:
        print("\n".join(errors))
        return 1
    log("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
