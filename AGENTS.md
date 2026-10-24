# AGENTS.md

This file describes how an AI coding agent (and humans) should work in this repository.

## 0) Always read the docs first

Before making changes or running commands, **read all README.md files in this repo** and follow them.

- Repo overview & dev workflow: `README.md`
- E2E test runner conventions: `testcases/README.md`

If you already read them earlier in the session, **re-check** when unsure.

## 1) Python / Poetry requirements (strict)

This project targets **Python 3.11** (the range allows up to 3.14: CAD Roam uses numpy, whose
line for 3.11 has no 3.15 wheels).

- Prefer Poetry-managed environments.
- If Poetry selected another Python, switch it:

```bash
poetry env use python3.11
poetry env info
poetry install
```

If `python3.11` is not available on PATH, use an absolute path to the 3.11 executable.

## 2) Default rule: use `poetry run` for scripts

When running any repo scripts, prefer:

- `poetry run <command>`

This ensures the correct virtualenv + dependencies are used.

## 3) Running the app: prefer `reflex_rerun.sh`

When you need to start/restart the Reflex app during development, **prefer the repo helper script**.

Typical usage:

```bash
poetry run ./reflex_rerun.sh
```

Notes:
- Prefer `poetry run ./reflex_rerun.sh` over `poetry run reflex run`.
- It runs on the expected ports: frontend `3000`, backend `8000` (it kills whatever holds them).
- Other apps on this machine may own 3000/8000. Then run on other ports and point the frontend at the backend: `REFLEX_API_URL=http://localhost:8150 poetry run reflex run --frontend-port 3150 --backend-port 8150`.
- Run on a Mac, CAD Roam reads the real shared `cad-models` collection (`/Users/Shared/re-ddns/collections`), read-only. Set `CAD_ROAM_HOME` to a scratch folder when trying things, so sizes you try don't land in your real settings; `DDNS_COLLECTIONS_ROOT=<folder>` shows another collections tree (e.g. one made by `testcases/fixtures.py`).

## 4) Running E2E suites: prefer `run_test_suite.sh`

E2E suites live under `testcases/<suite_name>/run_test.py`.

Do **not** run Playwright suites by starting/stopping the server manually unless you have to.
Use the repo runner, which starts/stops the Reflex server, sets `OUTPUT_DIR`, builds a fresh test collections tree (`DDNS_COLLECTIONS_ROOT`) and `CAD_ROAM_HOME` in it, and collects artifacts:

```bash
poetry run ./run_test_suite.sh smoke_home
```

Optional environment variables (see `testcases/README.md`): `BASE_URL`, `BACKEND_URL`,
`FRONTEND_PORT` / `BACKEND_PORT`, `HEADLESS=0`.

Unit tests: `poetry run pytest`.

## 4.5) How CAD Roam is put together

- **One model per page**: `/` lists the models of the `cad-models` collection, `/room/<id>` is one of them as a place (the same id as in Codoc in CAD; the key is `<owner>/<id>`, `models.find` picks the owner, `cad` first).
- **The 3D view is plain assets** (`assets/roam/*.js`, imported by `importable_path`; three.js and three-mesh-bvh via `lib_dependencies` in `cad_roam/components/world_view.py`): `engine.js` (scene, the sun and its times of day, loading the place, commands), `player.js` (walk/drone physics, collisions, step-up), `things.js` (the model from its GLB or STL mesh, its paving and pedestal), `look.js` (colours, glass, the sunlight through glass and the dimmer sky under roofs: it patches three.js' `lights_fragment_begin` chunk, so check it after upgrading three), `people.js` (the socket and the others' figures), `hud.js` (what is drawn over the view), `input.js`. Check them with `node --input-type=module --check < file.js` after editing: a syntax error only shows as a page that never gets ready.
- **The place comes from the backend** (`cad_roam/api.py`, all under `/_roam/`): `models.py` turns an item into the model's place (its JSON layout is described at the top of `models.py`; `things.js` reads the same fields, so change both together; `models.look` picks the GLB beside the STL when it can be drawn; `models.big` marks one over `CAD_ROAM_MAX_TRIANGLES`, and `engine.js` asks the person before loading it), `meshes.py` turns STL files into cached indexed meshes and passes GLBs on (reading only their size), `units.py` reads a model's scale from its code's comments, `settings.py` keeps the sizes people chose (`CAD_ROAM_HOME/units.json`).
- **Model coordinates**: Z up, front = -Y. In the view: metres, Y up, the front faces +Z (where you arrive). `things.js` `placeModel` does the conversion.
- **People** (`presence.py`): a tab enters a model's place from `ModelState.on_load` (trusted identity), its 3D view then says hello on `WS /_roam/ws/<owner>/<id>` with its peer id and Reflex token. Calls: `call.py` + `ModelRoom` (`rx.SharedState`), ported from Cellora.
- Words of the UI: `cad_roam/i18n.py` (English, 繁體中文); the 3D view gets the same dict as `labels`.
- `backend-paths.txt` sends `/_roam/` to the backend behind re-ddns nginx (container restart after changing it).

## 4.6) The re-ddns dev-mode install

- `smart-app-cad-roam` bind-mounts this checkout and hot-reloads on **any** file change in it (`.png` under `docs/` or `testcases/` too). A reload restarts the backend: everyone's model socket reconnects. Keep test output outside the checkout (`OUTPUT_DIR=...`) when testing against `https://cad-roam.reflex-ddns.com`.
- `pyproject.toml`, `rxconfig.py`, `poetry.lock` are copied into the container at start: changes to them need `docker restart smart-app-cad-roam`.
- The `cad-models` collection is mounted read-only; CAD Roam's own data is the volume `smart-app-cad-roam-data` (`/root/.local/share/cad_roam`).
- Diagnose with `docker logs smart-app-cad-roam`.

## 5) Expectations when acting as an agent

- Prefer the smallest, focused change set.
- After code changes, run the closest relevant check (at minimum the related suite via `run_test_suite.sh`).
- Report outcomes: what you ran, pass/fail, and where artifacts/logs were written.

## 6) Smart way to help the Agent to debug

```
poetry run ./reflex_rerun.sh --loglevel debug
```

In the browser console, `window.__roam.state()` tells where you are, the mode, whether the model loaded and who is here; `window.__roam.player.place(x, y, z, yaw, pitch)` puts you somewhere.
