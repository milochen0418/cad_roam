"""Helpers shared by the Playwright suites (imported by each run_test.py)."""

from __future__ import annotations

import os
import time
from pathlib import Path

from playwright.sync_api import Browser, Page, Playwright

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:3000").rstrip("/")
BACKEND_URL = os.environ.get("BACKEND_URL", BASE_URL).rstrip("/")
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parent / "output"))
COLLECTIONS = Path(os.environ.get("DDNS_COLLECTIONS_ROOT", OUTPUT_DIR / "collections"))
HEADLESS = os.environ.get("HEADLESS", "1").strip().lower() not in {"0", "false", "no", "off"}
SLOWMO = int(os.environ.get("PW_SLOWMO_MS", "0") or 0)
TIMEOUT = int(os.environ.get("PW_TIMEOUT_MS", "60000") or 60000)
_T0 = time.time()


def log(*args) -> None:
    print(f"[{time.time() - _T0:6.2f}]", *args, flush=True)


def launch(pw: Playwright) -> Browser:
    # Software WebGL: the same pictures on any machine (and in CI) as with a GPU, only slower.
    args = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
    if BASE_URL.startswith("https://") and ".reflex-ddns.com" in BASE_URL:
        # A Mac may resolve *.reflex-ddns.com to the Docker-internal IP.
        args.append("--host-resolver-rules=MAP *.reflex-ddns.com 127.0.0.1")
    return pw.chromium.launch(headless=HEADLESS, slow_mo=SLOWMO, args=args)


def new_page(browser: Browser, errors: list[str], who: str, *, locale: str = "en-US", width: int = 1280, height: int = 800, quality: str = "low") -> Page:
    ctx = browser.new_context(viewport={"width": width, "height": height}, locale=locale, ignore_https_errors=True)
    # Shadows cost too much in software WebGL.
    ctx.add_init_script(f"try {{ localStorage.setItem('cad_roam_quality', '{quality}') }} catch (e) {{}}")
    page = ctx.new_page()
    page.set_default_timeout(TIMEOUT)

    def on_console(msg) -> None:  # noqa: ANN001
        if msg.type == "error" and "Outdated Optimize Dep" not in msg.text and "Failed to load resource" not in msg.text:
            errors.append(f"[{who}] console: {msg.text}")

    def on_error(err) -> None:  # noqa: ANN001
        if "at window.onerror" in (getattr(err, "stack", "") or ""):
            return
        errors.append(f"[{who}] pageerror: {err}")

    page.on("console", on_console)
    page.on("pageerror", on_error)
    return page


def shot(page: Page, name: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUTPUT_DIR / f"{name}.png"))


def wait_for(fn, what: str, timeout: float = 60.0) -> None:
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            if fn():
                return
        except Exception as e:  # noqa: BLE001 - keep trying until the deadline
            last = e
        time.sleep(0.25)
    raise AssertionError(f"timed out: {what}" + (f" (last error: {last})" if last else ""))


def state(page: Page) -> dict:
    return page.evaluate("() => window.__roam ? window.__roam.state() : null")


def wait_world(page: Page) -> dict:
    """Waits until the 3D view on the page is there and its model is loaded."""
    page.wait_for_function("() => window.__roam && window.__roam.ready", timeout=180000)
    wait_for(lambda: all(s in ("ready", "failed") for s in state(page)["things"].values()), "models loaded", 180)
    return state(page)


def open_model(page: Page, model_id: str) -> dict:
    """Opens a model's page (standing in front of it) and waits until it is loaded."""
    page.goto(f"{BASE_URL}/room/{model_id}", wait_until="domcontentloaded")
    return wait_world(page)


def thing(page: Page, key: str) -> dict:
    return page.evaluate("(k) => { const t = window.__roam.things.get(k); return t ? t.data : null }", key)


def place(page: Page, x: float, y: float, z: float, yaw: float = 0.0, pitch: float = 0.0) -> None:
    page.evaluate("([x, y, z, yaw, pitch]) => window.__roam.player.place(x, y, z, yaw, pitch)", [x, y, z, yaw, pitch])


def sim_time(page: Page) -> float:
    return page.evaluate("() => window.__roam._t")


def hold(page: Page, key: str, seconds: float) -> None:
    """Holds a key for ``seconds`` of the world's own time (slow software WebGL draws few frames
    a second, and each frame moves the world at most 1/20 s)."""
    start = sim_time(page)
    page.keyboard.down(key)
    try:
        wait_for(lambda: sim_time(page) - start >= seconds, f"{seconds}s holding {key}", timeout=seconds * 60 + 30)
    finally:
        page.keyboard.up(key)


def settle(page: Page, seconds: float = 1.0) -> None:
    start = sim_time(page)
    wait_for(lambda: sim_time(page) - start >= seconds, "the world to settle", timeout=seconds * 60 + 30)
