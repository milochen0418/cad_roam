# E2E testcases

Playwright end-to-end suites, one per folder:

- `testcases/<suite_name>/run_test.py`
- `testcases/<suite_name>/output/` (screenshots and logs, ignored by git)

Each `run_test.py` exits `0` on success and non-zero on failure, and writes its screenshots into
`OUTPUT_DIR` (provided by the runner). Shared helpers (a browser with software WebGL, opening a
model's page and waiting for it to load, holding a key for some of the 3D view's own time,
reading the engine's state through `window.__roam`) are in `common.py`.

Every run builds its own small `cad-models` collection with `fixtures.py` in
`OUTPUT_DIR/collections` (a 10 x 8 m house with a door and steps up to a platform, a 30 m tower in
millimetres, a 6 cm part with no size in its code, a model that never built, an 8 x 12 m chapel
in its colours, with a GLB beside its STL and a blue glass window in its east wall) and points
`DDNS_COLLECTIONS_ROOT` and `CAD_ROAM_HOME` there: your models are never touched.

## Suites

| Suite | What it checks |
|-------|----------------|
| `smoke_home` | The models with their real sizes and the one not built yet; a pasted Codoc in CAD link lands in front of that model; a link CAD Roam can't find says so; 繁體中文; a card opens its model; a model that never built and one that doesn't exist each say so. |
| `walk_fly` | In through the house's door until the back wall stops you; the front wall stops you outside; up the steps onto the platform; a jump; the drone climbs, bumps into the house and, as a ghost (G), flies through its wall; Details shows "10 × 8 m, 3.2 m high" with the size its code says, and Back to the entrance; at the part, a size chosen in Details makes it bigger for everyone; Other models takes you to the tower. |
| `together` | Two people at the house see each other (figure, chip, name); one takes off and the other sees where; a click on the chip flies there; a closed tab is seen leaving; someone at the tower is not seen. |
| `live_update` | The house rebuilt in its collection (as Codoc in CAD does on Run) is swapped in while you are there; a model that never built appears the moment it builds, with you in front of it. |
| `colours` | The chapel is drawn from its GLB (4 colours, 1 of them glass), with shadows on; by day no blue light inside, in the morning sun (T, through the evening) the floor and the wall in front of its window turn blue (counted in the drawn pixels); the house, with only an STL, is one colour. |

## Running

```bash
poetry run ./run_test_suite.sh smoke_home
poetry run ./run_test_suite.sh walk_fly
poetry run ./run_test_suite.sh together
poetry run ./run_test_suite.sh live_update
poetry run ./run_test_suite.sh colours
```

If ports 3000/8000 belong to another app, use others: `FRONTEND_PORT=3150 BACKEND_PORT=8150`.
The suites expect the fixture's models, so they are meant for local runs, not for the live app.

Optional env vars:
- `BASE_URL` (default `http://127.0.0.1:3000`) and `BACKEND_URL`
- `HEADLESS=0` to watch the browser
- `PW_SLOWMO_MS=100` to slow actions down
- `PW_TIMEOUT_MS=60000` to change Playwright timeouts
