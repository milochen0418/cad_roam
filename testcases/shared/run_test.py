"""What people at one model share: Ann and Ben, signed in (their sign-in cookies made with the
server's secret, see server.env), and a guest, at the fixture's chapel.

- Profiles: beside Ben's chip, Ann has a button for his profile, which opens Relack's User Profile
  in a dialog, asked for Ben (privately: his e-mail isn't in its address); Ann's own name opens
  hers. The guest has none: no button beside their chip, their name not a button.
- The sun: Ann drags it to 16:30 and Ben's is there too, with a note that Ann moved it; Ben's T
  moves Ann's; dragged by both at the same moment, both end at the same time; the guest, who comes
  with another time of their own, gets the chapel's.
- Torches: Ben lights his torch (L) inside the chapel, and Ann (with shadows) sees its lamp on his
  head and its light on the wall he looks at. From outside, behind the wall he shines at, she sees
  none of it on the grass beyond (the wall stops it), while out in the open his torch lights the
  grass. Off again, it is gone from her page too.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from common import launch, log, model_place, new_page, open_model, settle, shot, sign_in, state, wait_for, wait_light  # noqa: E402

CHAPEL = "cad/chapel"

# Where someone's torch shines, on the page: from its lamp along its middle to the first surface
# (or, with `ground`, to where that line meets the ground, walls or not), and how bright the page
# draws a 40 px square there (0 to 255, a frame drawn for it, with the eyes as used to that place as
# they get: they take a while to, which in software WebGL is many seconds).
SPOT = """([peer, ground]) => {
  const e = window.__roam, f = e.people.figures.get(peer), V = e.camera.position.constructor;
  const at = f.lamp.at.getWorldPosition(new V()), dir = f.direction(new V());
  const far = ground ? -at.y / dir.y : e.people.reach(at, dir, 60);
  const p = at.clone().addScaledVector(dir, far).project(e.camera);
  const r = e.renderer;
  e.look.frame();
  r.toneMappingExposure = e.exposure * e.look.light.eyeAt(e.camera.position).brightness;
  r.render(e.scene, e.camera);
  const gl = r.getContext(), w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
  const x = Math.round(((p.x + 1) / 2) * w), y = Math.round(((p.y + 1) / 2) * h);
  const px = new Uint8Array(40 * 40 * 4);
  gl.readPixels(x - 20, y - 20, 40, 40, gl.RGBA, gl.UNSIGNED_BYTE, px);
  let s = 0;
  for (let i = 0; i < px.length; i += 4) s += 0.2126 * px[i] + 0.7152 * px[i + 1] + 0.0722 * px[i + 2];
  return { x, y, far: Math.round(far * 100) / 100, lum: Math.round(s / 16) / 100 };
}"""

# Someone's figure is where they are and looks where they look (it is eased in).
ARRIVED = """([peer, p, yaw, pitch]) => {
  const f = window.__roam.people.figures.get(peer);
  if (!f) return false;
  const at = f.pos.clone().fromArray(p), turn = Math.atan2(Math.sin(yaw - f.yaw), Math.cos(yaw - f.yaw));
  return f.pos.distanceTo(at) < 0.01 && Math.abs(turn) < 0.003 && Math.abs(pitch - f.pitch) < 0.003;
}"""


def arrived(page, other, peer: str) -> bool:
    """`other` (their tab is `peer`) is on `page` where they are on their own page."""
    s = state(other)
    return page.evaluate(ARRIVED, [peer, s["position"], s["yaw"], s["pitch"]])


def drag_sun(page, hours: float) -> None:
    """Drags the ☀ slider to `hours` (as a person does: input events), and lets go of it (the keys
    go back to the view)."""
    page.evaluate(
        """(v) => {
          const r = document.querySelector(".rm-sun-range");
          r.value = String(v);
          r.dispatchEvent(new Event("input", { bubbles: true }));
          r.blur();
        }""",
        hours,
    )


def profile_asked(page) -> str:
    """Whose profile the dialog in front asks Relack for ("" when none is open)."""
    return page.evaluate(
        """() => {
          const frame = document.querySelector('iframe[data-intent-action="profile.view"]');
          if (!frame) return "";
          const asked = (window.__ddnsIntentPending || {})[frame.dataset.intentId];
          return (asked && asked.data && asked.data.user) || "?";
        }"""
    )


def close_dialog(page) -> None:
    page.locator('[data-intent-front="1"] [aria-label="Close"]').click()
    wait_for(lambda: page.locator('iframe[data-intent-action="profile.view"]').count() == 0, "the dialog closed", 15)


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = launch(pw)
        # Ann draws with shadows (a torch's light is stopped by walls only with them).
        ann = new_page(browser, errors, "Ann", width=1000, height=700, quality="high")
        ben = new_page(browser, errors, "Ben", width=800, height=560)
        sign_in(ann, "ann@example.com", "Ann")
        sign_in(ben, "ben@example.com", "Ben")
        open_model(ann, "chapel")
        open_model(ben, "chapel")
        wait_for(lambda: len(state(ann)["people"]) == 2 and len(state(ben)["people"]) == 2, "Ann and Ben see each other")
        peer_ben = ben.evaluate("() => window.__roam.opts.me.peer")
        # Both came in at the same place: Ben steps aside (else he looks out of Ann's head).
        model_place(ben, CHAPEL, 2.5, -9.0, 0.0, 0.0, 0.0)

        # Profiles: Ben's from the button beside his chip, Ann's own from her name.
        button = ann.locator(f'.rm-chip-profile[data-peer="{peer_ben}"]')
        wait_for(lambda: button.count() == 1, "a button for Ben's profile beside his chip")
        assert button.get_attribute("title") == "Ben's profile", button.get_attribute("title")
        button.click()
        wait_for(lambda: profile_asked(ann) == "ben@example.com", "Ben's profile opens in a dialog")
        src = ann.get_attribute('iframe[data-intent-action="profile.view"]', "src")
        assert src.startswith("http://127.0.0.1:9/intent/profile-view?") and "example.com" not in src, src
        shot(ann, "01-ben-profile")
        close_dialog(ann)
        ann.click("#me-name")
        wait_for(lambda: profile_asked(ann) == "ann@example.com", "Ann's name opens her own profile")
        close_dialog(ann)
        log("profiles: Ben's from his chip, Ann's from her name")

        # The sun: anyone moves it for everyone.
        drag_sun(ann, 16.5)
        wait_for(lambda: state(ben)["time"] == 16.5, "Ben's sun at 16:30 too", 20)
        wait_for(lambda: ben.inner_text(".rm-notice") == "Ann moved the sun to 16:30", "Ben is told who moved it", 10)
        shot(ben, "02-ben-told")
        ben.keyboard.press("t")
        wait_for(lambda: state(ben)["time"] == 7.5 and state(ann)["time"] == 7.5, "Ben's T moves Ann's sun", 20)
        # Both drag it at the same moment: they end at the same time.
        for i in range(6):
            drag_sun(ann, 9 + i * 0.25)
            drag_sun(ben, 15 - i * 0.25)
        wait_for(lambda: state(ann)["time"] == state(ben)["time"] in (10.25, 13.75), "Ann and Ben end at the same time", 20)
        settle(ann, 1.0)
        both = state(ann)["time"]
        assert state(ben)["time"] == both, (both, state(ben)["time"])
        log("dragged by both at once, both at", both)

        # A guest comes with a time of their own and gets the chapel's; they have no profile.
        guest = new_page(browser, errors, "guest", width=800, height=560)
        guest.context.add_init_script("try { localStorage.setItem('cad_roam_sun_time', '12') } catch (e) {}")
        open_model(guest, "chapel")
        wait_for(lambda: state(guest)["time"] == both, "the guest gets the chapel's sun", 20)
        peer_guest = guest.evaluate("() => window.__roam.opts.me.peer")
        wait_for(lambda: ann.locator(f'.rm-chip[data-peer="{peer_guest}"]').count() == 1, "the guest's chip")
        assert ann.locator(f'.rm-chip-profile[data-peer="{peer_guest}"]').count() == 0, "a guest has no profile"
        assert guest.eval_on_selector("#me-name", "e => e.tagName") == "SPAN", "a guest's name opens nothing"
        guest.context.close()
        log("the guest got", both, "and has no profile")

        # Ben's torch, inside: Ann sees its lamp on his head and its light on the back wall.
        drag_sun(ann, 10.5)
        wait_for(lambda: state(ann)["time"] == state(ben)["time"] == 10.5, "the sun back at 10:30", 20)
        wait_light(ann)
        model_place(ben, CHAPEL, 2.0, 0.0, 0.0, 0.3, -0.1)
        model_place(ann, CHAPEL, -2.5, -4.5, 0.0, 0.0, 0.05)
        wait_for(lambda: arrived(ann, ben, peer_ben), "Ben where he stands, on Ann's page")
        dark = ann.evaluate(SPOT, [peer_ben, False])
        ben.keyboard.press("l")
        wait_for(lambda: state(ann)["torches"] == [{"id": peer_ben, "lit": True}], "Ann's page lights Ben's torch", 15)
        assert ann.evaluate("(p) => window.__roam.people.figures.get(p).lamp.pivot.visible", peer_ben), "the lamp on his head"
        settle(ann, 0.5)
        lit = ann.evaluate(SPOT, [peer_ben, False])
        log("where Ben's torch shines, on Ann's page: off", dark, "on", lit)
        assert lit["lum"] > dark["lum"] + 25, (dark, lit)
        shot(ann, "03-ben-torch-inside")

        # From outside, behind the wall he shines at: none of it on the grass beyond the wall.
        model_place(ben, CHAPEL, 0.0, 3.0, 0.0, 0.0, -0.3)
        model_place(ann, CHAPEL, 0.0, 18.0, 0.0, math.pi, -0.3)
        wait_for(lambda: arrived(ann, ben, peer_ben), "Ben by the back wall, on Ann's page")
        settle(ann, 0.5)
        on = ann.evaluate(SPOT, [peer_ben, True])
        shot(ann, "04-behind-the-wall")
        ben.keyboard.press("l")
        wait_for(lambda: state(ann)["torches"] == [], "Ben's torch off on Ann's page", 15)
        assert not ann.evaluate("(p) => window.__roam.people.figures.get(p).lamp.pivot.visible", peer_ben)
        settle(ann, 0.5)
        off = ann.evaluate(SPOT, [peer_ben, True])
        log("on the grass behind the wall: torch on", on, "off", off)
        assert abs(on["lum"] - off["lum"]) < 3, (on, off)

        # Out in the open, the same torch lights the grass.
        model_place(ben, CHAPEL, 0.0, 7.0, 0.0, 0.0, -0.3)
        wait_for(lambda: arrived(ann, ben, peer_ben), "Ben behind the chapel, on Ann's page")
        settle(ann, 0.5)
        off = ann.evaluate(SPOT, [peer_ben, True])
        ben.keyboard.press("l")
        wait_for(lambda: state(ann)["torches"] == [{"id": peer_ben, "lit": True}], "Ben's torch on again", 15)
        settle(ann, 0.5)
        on = ann.evaluate(SPOT, [peer_ben, True])
        log("on the grass in the open: torch off", off, "on", on)
        assert on["lum"] > off["lum"] + 8, (off, on)
        shot(ann, "05-in-the-open")

        # Ben goes: his torch's light is free again.
        ben.context.close()
        wait_for(lambda: not state(ann)["torches"] and not state(ann)["figures"], "Ben's figure and torch gone", 15)
        browser.close()
    if errors:
        print("\n".join(errors))
        return 1
    log("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
