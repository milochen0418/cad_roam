"""An AI's pictures from inside a model (roam.view, roam.tour, roam.where through the AI Hub's tool
endpoint): with someone at the chapel, a picture from inside it, looking at the floor in front of
its blue window, is blue in the morning sun and not in the evening's, as that person's own view
would be; their view, their time of day and where they stand don't change (the sun goes back to
their time a moment later), and a note says an AI took a picture. roam.where finds them at the
entrance; roam.tour takes two smaller pictures. With the page drawing nothing (as a tab in the
background: no animation frames, timers held back for minutes), the chapel rebuilt meanwhile, a
picture is still taken, of the new build, with its light worked out. With nobody at the model, the
answer says which page to open."""

from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from reflex_ddns_auth.tools import IMAGE_KEY, call_token  # noqa: E402

import fixtures  # noqa: E402
from common import BACKEND_URL, COLLECTIONS, OUTPUT_DIR, launch, log, new_page, open_model, place, settle, shot, state, wait_for, wait_light  # noqa: E402

# Inside the chapel, 1 m east of its middle, looking down to the west, at the floor and the wall the
# morning sun lights through the window (as the colours suite stands).
FLOOR = {"room": "chapel", "at": [1.0, 0.0, 1.62], "heading": 291.2, "pitch": -28.6}

# The share of clearly blue pixels in a JPEG (decoded by the page).
BLUE = """async (b64) => {
  const img = new Image();
  img.src = "data:image/jpeg;base64," + b64;
  await img.decode();
  const c = document.createElement("canvas");
  c.width = img.width;
  c.height = img.height;
  const g = c.getContext("2d");
  g.drawImage(img, 0, 0);
  const px = g.getImageData(0, 0, c.width, c.height).data;
  let blue = 0;
  for (let i = 0; i < px.length; i += 4) if (px[i + 2] > px[i] + 25 && px[i + 2] > px[i + 1] + 8) blue++;
  return { w: c.width, h: c.height, blue: blue / (px.length / 4) };
}"""

# The share of clearly blue pixels in a frame of the page's own view (as the colours suite counts).
OWN_BLUE = """() => {
  const e = window.__roam, r = e.renderer;
  e.look.frame();
  r.render(e.scene, e.camera);
  const gl = r.getContext(), w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
  const px = new Uint8Array(w * h * 4);
  gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
  let blue = 0;
  for (let i = 0; i < px.length; i += 4) if (px[i + 2] > px[i] + 25 && px[i + 2] > px[i + 1] + 8) blue++;
  return blue / (px.length / 4);
}"""

# A tab in the background: no frames, and every timer held back for two minutes.
BACKGROUND = """() => {
  const e = window.__roam;
  cancelAnimationFrame(e._raf);
  window.requestAnimationFrame = () => 0;
  const later = window.setTimeout;
  window.setTimeout = (f, ms, ...args) => later(f, Math.max(ms || 0, 120000), ...args);
}"""


def call(name: str, args: dict, timeout: float = 120.0) -> dict:
    """A tool call as the AI Hub makes one."""
    started = time.time()
    r = httpx.post(
        f"{BACKEND_URL}/_ddns_tool/call/{name}",
        json={"args": args},
        headers={"Authorization": f"Bearer {call_token(os.environ.get('DDNS_APP_ID', 'cad-roam'), 'Claude Code')}"},
        timeout=timeout,
    )
    body = r.json()
    log(f"{name}: {'ok' if body.get('ok') else body.get('error')} ({time.time() - started:.1f} s)")
    return body


def picture(page, result: dict, name: str) -> dict:
    """The picture in a tool's result: saved, and its size and blue share."""
    pic = result["picture"]
    assert pic[IMAGE_KEY] and pic["mime"] == "image/jpeg", pic.keys()
    data = base64.b64decode(pic["data"])
    assert data[:2] == b"\xff\xd8"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"{name}.jpg").write_bytes(data)
    seen = page.evaluate(BLUE, pic["data"])
    log(name, {k: v for k, v in result.items() if k != "picture"}, "blue", round(seen["blue"], 3))
    return seen


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = launch(pw)
        page = new_page(browser, errors, "A", quality="high")
        open_model(page, "chapel")
        wait_light(page)
        before = state(page)
        log("A stands at", [round(v, 2) for v in before["position"]], "at", before["time"])

        # The morning: blue light on the floor; with what the page measured.
        body = call("roam.view", {**FLOOR, "time": "7:30"})
        assert body["ok"], body
        out = body["result"]
        seen = picture(page, out, "01-morning")
        assert (seen["w"], seen["h"]) == (1280, 800), seen
        morning = seen["blue"]
        assert morning > 0.08, seen
        assert out["time"] == "7:30" and out["at"] == [1.0, 0.0, 1.62] and abs(out["heading"] - 291.2) < 0.2, out
        assert out["drawn_with"] == "shadows and the light inside", out
        assert out["light_here"] is not None and 0 < out["light_here"] < 1 and out["eyes"] >= 1, out
        assert out["ahead_m"] is not None and 1 < out["ahead_m"] < 6, out
        assert 0 < out["picture_brightness"]["mean"] < 255, out
        assert out["sun"]["bearing"] < 120, out  # in the east

        # A's view is A's: where they stand and look, their time; the sun goes back a moment later.
        after = state(page)
        assert after["position"] == before["position"] and after["yaw"] == before["yaw"] and after["pitch"] == before["pitch"]
        assert after["time"] == before["time"] and after["pictures"] == 1
        wait_for(lambda: state(page)["sunTime"] == before["time"], "the sun back at A's time", 60)
        wait_for(lambda: "took a picture inside" in page.inner_text(".rm-notice"), "the note")
        assert "AI · Claude Code" in page.inner_text(".rm-notice")
        shot(page, "02-A-after")

        # The evening: the sun in the west lights no blue.
        body = call("roam.view", {**FLOOR, "time": 16.5})
        assert body["ok"], body
        seen = picture(page, body["result"], "03-evening")
        assert seen["blue"] < morning / 5, (morning, seen)

        # Where A is: at the entrance, in front of the chapel (its front is -Y), at 10:30.
        body = call("roam.where", {"room": "chapel"})
        assert body["ok"], body
        where = body["result"]
        log("where:", where)
        (a,) = where["people"]
        assert a["mode"] == "walking" and a["time"] == "10:30" and a["at"][1] < -6 and abs(a["at"][2] - 1.62) < 0.05, a
        assert where["unit_m"] == 1 and where["pages"] == 1, where

        # A tour: the lamp from under it, the window from inside.
        stops = [
            {"name": "under the lamp", "at": [0, 0, 1.62], "look_at": [0, 0, 4.15]},
            {"name": "the window", "at": [-2, 0, 1.62], "look_at": [3.9, 0, 2.75]},
        ]
        body = call("roam.tour", {"room": "chapel", "stops": stops, "time": "16:30"})
        assert body["ok"], body
        tour = body["result"]
        assert [s["name"] for s in tour["stops"]] == ["under the lamp", "the window"] and "not_taken" not in tour, tour
        for i, s in enumerate(tour["stops"]):
            seen = picture(page, s, f"04-tour-{i + 1}")
            assert (seen["w"], seen["h"]) == (1024, 640), seen
        assert tour["stops"][0]["pitch"] > 80, tour["stops"][0]

        # A at that place in the morning, in their own view: about as blue as the picture.
        place(page, 1.0, 0, 0, 1.2, -0.5)
        page.fill(".rm-sun-range", "7.5")
        wait_for(lambda: state(page)["sunTime"] == 7.5, "A's sun at 7:30")
        settle(page, 1.5)
        wait_light(page)
        own = page.evaluate(OWN_BLUE)
        log("A's own view at 7:30: blue", round(own, 3), "the picture's", round(morning, 3))
        assert abs(own - morning) < 0.06, (own, morning)
        shot(page, "05-A-morning")

        # In the background (nothing drawn, timers held back), the chapel rebuilt: the picture is of
        # the new build, its light worked out.
        page.evaluate(BACKGROUND)
        rev = state(page)["rev"]
        fixtures.rebuild_chapel(COLLECTIONS)
        body = call("roam.view", {**FLOOR, "time": "7:30"})
        assert body["ok"], body
        seen = picture(page, body["result"], "06-background-rebuilt")
        assert seen["blue"] > 0.08, seen
        now = state(page)
        assert now["rev"] > rev and now["things"]["cad/chapel"] == "ready" and now["light"]["done"], now

        # Nobody at the model: which page to open.
        page.context.close()
        started = time.time()
        body = call("roam.view", {**FLOOR})
        assert not body["ok"] and "Nobody has this model open" in body["error"] and "/room/chapel" in body["error"], body
        assert time.time() - started < 10
        browser.close()
    if errors:
        print("\n".join(errors))
        return 1
    log("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
