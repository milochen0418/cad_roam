"""The fixture's chapel in its colours (testcases/fixtures.py: a GLB beside its STL, as Codoc in CAD
builds write them): each part in its colour, its window as glass; by day the sun doesn't come in,
in the morning (T) it shines through the blue window and the floor and the wall in front of it
turn blue; T goes on to the evening and back to the day. The house, which has only an STL, is
drawn in one colour."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from common import launch, log, new_page, open_model, place, settle, shot, state, wait_for  # noqa: E402

# Draws a frame and counts, in the lower half of the view (the floor and the foot of the wall), the
# pixels that are clearly blue.
BLUE_SHARE = """() => {
  const e = window.__roam, r = e.renderer;
  e.look.frame();
  r.render(e.scene, e.camera);
  const gl = r.getContext(), w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
  const px = new Uint8Array(w * h * 4);
  gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
  let blue = 0, n = 0;
  for (let y = 0; y < h / 2; y += 2) {
    for (let x = 0; x < w; x += 2) {
      const i = (y * w + x) * 4;
      n++;
      if (px[i + 2] > px[i] + 40 && px[i + 2] > px[i + 1] + 15) blue++;
    }
  }
  return blue / n;
}"""


def flags(page) -> str:
    return page.inner_text(".rm-flags")


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = launch(pw)
        # Shadows on: the sun through glass needs them (slow in software WebGL, the chapel is small).
        page = new_page(browser, errors, "A", quality="high")
        st = open_model(page, "chapel")
        looks = st["looks"]["cad/chapel"]
        log("chapel:", looks)
        assert looks == {"parts": 4, "glass": 1}, looks

        # Inside, by the window, looking west and down at the floor in front of it.
        place(page, 1.0, 0, 0, 1.5708, -0.5)
        settle(page, 1.0)
        day = page.evaluate(BLUE_SHARE)
        log("blue by day:", round(day, 3))
        shot(page, "01-day")

        page.keyboard.press("t")
        wait_for(lambda: "Evening sun" in flags(page), "the evening sun")
        page.keyboard.press("t")
        wait_for(lambda: "Morning sun" in flags(page), "the morning sun")
        settle(page, 1.0)
        morning = page.evaluate(BLUE_SHARE)
        log("blue in the morning:", round(morning, 3))
        shot(page, "02-morning")
        assert day < 0.02, day
        assert morning > 0.08 and morning > 5 * day, (day, morning)

        # Its window from inside, the sun behind it.
        place(page, -2.0, 0, 0, -1.5708, 0.25)
        settle(page, 0.5)
        shot(page, "03-window")
        page.keyboard.press("t")
        wait_for(lambda: flags(page) == "", "the day again")

        # The house has no colours: one part, no glass.
        st = open_model(page, "house")
        log("house:", st["looks"]["cad/house"])
        assert st["looks"]["cad/house"] == {"parts": 1, "glass": 0}
        browser.close()
    if errors:
        print("\n".join(errors))
        return 1
    log("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
