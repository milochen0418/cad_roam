"""A model over the server's triangle limit isn't loaded until you say so (server.env sets
CAD_ROAM_MAX_TRIANGLES to 100, so the chapel's GLB, 144 triangles, is one): a question says what
loading it costs (its triangles against the limit, the download, about how much memory). "Don't
load" leaves its outline, "not loaded" on it and a button at the top left that loads it after all,
in its colours. A new page asks again; "Load it" there also takes its next build without asking.
The house, an STL over the limit, is simplified on the server and loads without a question. The
question in 繁體中文."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

import fixtures  # noqa: E402
from common import BASE_URL, COLLECTIONS, launch, log, new_page, open_model, shot, state, thing, wait_for  # noqa: E402

ASKING = ".rm-hud.is-asking .rm-ask-box"


def ask(page, model_id: str) -> str:
    """Opens a model's page and waits for the question; its words."""
    page.goto(f"{BASE_URL}/room/{model_id}", wait_until="domcontentloaded")
    page.wait_for_function("() => window.__roam && window.__roam.ready", timeout=180000)
    page.wait_for_selector(ASKING, state="visible", timeout=60000)
    return page.inner_text(ASKING)


def status(page, key: str = "cad/chapel") -> str:
    return state(page)["things"].get(key, "")


def main() -> int:
    errors: list[str] = []
    meshes: list[str] = []
    with sync_playwright() as pw:
        browser = launch(pw)
        page = new_page(browser, errors, "A")
        page.on("request", lambda r: meshes.append(r.url) if "/_roam/mesh/cad/chapel" in r.url else None)

        words = ask(page, "chapel")
        log("asked:", words.replace("\n", " | "))
        assert "This model is big" in words, words
        assert "Chapel has 144 triangles, 1.4 times the suggested limit of 100." in words, words
        assert "Download" in words and "Memory" in words and "about 26 KB" in words, words
        assert status(page) == "waiting" and not meshes, (status(page), meshes)
        shot(page, "01-asked")

        # Don't load: its outline, "not loaded", and a button that loads it after all.
        page.click("#rm-big-skip")
        wait_for(lambda: status(page) == "skipped", "left unloaded")
        assert not page.is_visible(ASKING)
        wait_for(lambda: page.is_visible("#rm-big-later"), "the button that loads it after all")
        row = page.inner_text(".rm-loading")
        assert "Chapel" in row and "not loaded" in row and "Load it" in row, row
        assert "not loaded" in page.inner_text(".rm-label-sub")
        assert not meshes, meshes
        shot(page, "02-not-loaded")
        page.click("#rm-big-later")
        wait_for(lambda: status(page) == "ready", "loaded after all", 120)
        assert state(page)["looks"]["cad/chapel"] == {"parts": 4, "glass": 1}
        wait_for(lambda: page.inner_text(".rm-loading").strip() == "", "the row is gone")
        assert meshes, "its mesh was fetched"
        shot(page, "03-loaded")

        # A new page asks again. Load it: its next build comes in without a question.
        ask(page, "chapel")
        page.click("#rm-big-load")
        wait_for(lambda: status(page) == "ready", "loaded", 120)
        assert not page.is_visible(ASKING)
        rev, mesh = state(page)["rev"], thing(page, "cad/chapel")["mesh"]
        fixtures.rebuild_chapel(COLLECTIONS)
        wait_for(lambda: state(page)["rev"] > rev, "the place changed", 30)
        wait_for(lambda: thing(page, "cad/chapel")["mesh"] != mesh and status(page) == "ready", "its new build is in", 120)
        assert not page.is_visible(ASKING)
        assert page.evaluate("() => window.__roam.replacing.size") == 0
        log("rebuilt: loaded without a question")

        # An STL over the limit is simplified on the server: nothing to ask.
        st = open_model(page, "house")
        assert st["things"]["cad/house"] == "ready" and not page.is_visible(ASKING), st["things"]
        assert thing(page, "cad/house")["big"] is None

        zh = new_page(browser, errors, "B", locale="zh-TW")
        ask(zh, "chapel")
        wait_for(lambda: "這個模型很大" in zh.inner_text(ASKING), "the question in 繁體中文")
        words = zh.inner_text(ASKING)
        log("zh:", words.replace("\n", " | "))
        assert "Chapel 有 144 個三角形，是建議上限 100 的 1.4 倍。" in words, words
        assert "約 26 KB" in words and "不載入" in words, words
        shot(zh, "04-zh")
        browser.close()
    if errors:
        print("\n".join(errors))
        return 1
    log("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
