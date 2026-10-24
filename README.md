# CAD Roam 🧭

Walk **into** your CAD models. Pick a model made in [Codoc in CAD](https://github.com/milochen0418/codoc_in_cad) and it stands in front of you at its **real size**: walk in like in a first-person game (in through the Taj Mahal's gate, up to its tomb chamber), or fly round it like a drone (over the Sagrada Família's towers). Everyone who opens the same model sees each other there, walking or flying, and can call everyone.

Built with [Reflex](https://reflex.dev/) and [three.js](https://threejs.org/) for the [re-ddns](https://github.com/milochen0418/re_ddns) Agentic App Store: install it there and open `https://cad-roam.reflex-ddns.com`. A model's address is the same as in Codoc in CAD, with another app name: `https://cad.reflex-ddns.com/room/e5172e80e3` is edited there and walked in at `https://cad-roam.reflex-ddns.com/room/e5172e80e3`. It also runs on its own.

## 📸 Interface Preview

| The models, at their real size | Arriving at a model |
|:---:|:---:|
| ![Models](docs/images/home.png) | ![In front of the Taj Mahal](docs/images/arrive.png) |

| Flying the drone | Walking inside |
|:---:|:---:|
| ![Drone](docs/images/drone.png) | ![Inside](docs/images/inside.png) |

| The model's details (its real size) | Others at the model, walking and flying |
|:---:|:---:|
| ![Details](docs/images/card.png) | ![Together](docs/images/together.png) |

## 🌟 Features

**Pick a model, go in**
- The first page lists the models of the shared collection `cad-models` (Codoc in CAD's models, and STL files imported on the App Store's storage page): the picture of each one's last build, its real size, who changed it and when, and who is in it now. A model that never built says so.
- **Paste a link** to start right in front of a model: its room in Codoc in CAD (`https://cad.reflex-ddns.com/room/<id>`), a CAD Roam link, a ref (`cad-models:cad/<id>`) or just the id.
- **Other models** in the top bar switches without going back; the App Store's storage page offers **Open with → Walk in CAD Roam** for every CAD model.

**Two ways to move** (press **F** to switch)
- **Walk** like in a game: W A S D (or the arrows) to move, the mouse to look (click the view; Esc frees the mouse, or drag to look without it), Space to jump, Shift to run. Walls stop you, stairs and kerbs are stepped up (up to 36 cm), and you fall off ledges.
- **Drone**: Space up, Shift (or Q) down, the wheel sets its top speed (1 to 160 m/s). It drifts a little and leans into turns like a real drone, bumps into the model, and with **G** flies through walls (ghost). It shows its height above whatever is below it, its speed and its heading.
- **L** lights a torch for dark insides, **E** (or a click while looking) opens the model's details, **H** shows the keys again. Phones and tablets get a stick and up/down buttons; a gamepad works too (sticks, A up, B down, Y switches).

**Real size**
- A model's code says what one unit is, in a comment CAD Roam reads: `# 1 unit = 0.5 m`, `# 單位：1 = 1 公尺`, `# units: mm`. Without one it is in millimetres (build123d's unit). **Details** shows its size in metres and where that size comes from, and lets anyone choose another unit for everyone. Models under 1.5 m stand on a pedestal.

**Live**
- When someone presses Run in Codoc in CAD, everyone at the model sees the new build within a couple of seconds. The rebuilt model swaps in once its new mesh has loaded, so you can stand inside a building while it is being changed. A model that had never built appears the moment it does, with you in front of it.

**Together** (the same rules as the other apps)
- Everyone at a model sees the others: a figure in their colour when they walk, a little drone with their colours when they fly, their name over them, a chip for each at the top right (a click takes you to them) and their dot on the map.
- **Call everyone** rings everyone at the model through an installed call app (DDNS Intent `call.join`), as on a Codoc in CAD model.
- Signed in (the platform's account), you show as yourself; otherwise as a guest.

## 📐 How it works

```
  browser                                            CAD Roam's backend (Reflex + Starlette)
  ┌──────────────────────────────────┐   GET  /_roam/world/<owner>/<id> ┌────────────────────────────┐
  │ assets/roam/  (three.js)         │ ──────────────────────────────▶ │ models.py: the model, its  │
  │  engine.js  scene, sky, loading  │   GET  /_roam/mesh/…?v=…         │   real size, revisions     │
  │  player.js  walk / drone physics │ ──────────────────────────────▶ │ meshes.py: STL → indexed   │
  │  things.js  the model            │                                   │   mesh (gz), cached        │
  │  people.js  the others           │ ◀──── WS /_roam/ws/<owner>/<id> ▶ │ presence.py: who, where    │
  │  hud.js     keys, map, chips     │   poses ~10/s, "model changed"    │ api.py: watches the models │
  └──────────────────────────────────┘                                   └─────────────┬──────────────┘
        Reflex pages around it: the list, the switcher, the details, calls             │ reads (read-only)
                                                                                        ▼
                                          /data/collections/cad-models/by-app/cad/<id>/   (re-ddns mounts)
```

- **Meshes.** An STL writes every corner of every triangle out (70 MB for the Sagrada Família model, 1.4 million triangles). `cad_roam/meshes.py` sends each corner once and the triangles as indices, gzipped: 9 MB, made in about a second once per build and cached in `CAD_ROAM_HOME` under the STL's size and time, so a rebuilt model gets a new URL and browsers cache the rest for good. Models over `CAD_ROAM_MAX_TRIANGLES` (3 million) are simplified first.
- **Collisions** use [three-mesh-bvh](https://github.com/gkjohnson/three-mesh-bvh): the model gets a bounding-volume tree when it loads; the walker is a capsule, the drone a sphere. three.js and three-mesh-bvh are npm packages bundled by Reflex's Vite (`lib_dependencies`), so nothing comes from a CDN at run time.
- **Coordinates.** A model's Z is up and its front is -Y (Codoc in CAD's "Front" view); you arrive facing its front, and it stands on the ground at its own z = 0, scaled by its unit.
- **Presence.** A tab enters a model's place from its Reflex page (so the person comes from the sign-in, not from the browser), then its 3D view opens the model's socket with the tab's id and Reflex token; poses go out about ten times a second while you move. A closed tab leaves at once.
- **Watching.** Every 2 s the backend stats the manifests of the models people are in; a change rebuilds the place and tells everyone in it to fetch it again. The place's version changes only when something that shows changed, so typing in Codoc in CAD (which saves the code every 1.5 s) doesn't make anyone reload.

## 🚀 Install on re-ddns (Agentic App Store)

CAD Roam is in the App Store catalog as `cad-roam`. Its entry gives it **read** access to the collection `cad-models`, mounted read-only: CAD Roam never writes a model. Its own data (meshes, the sizes people chose) is in the volume `smart-app-cad-roam-data`. `backend-paths.txt` sends `/_roam/` to the backend.

## 💻 Run locally

```bash
poetry env use python3.11
poetry install
poetry run ./reflex_rerun.sh
```

Open `http://localhost:3000`. On a Mac it reads the same shared folder the local apps write (`/Users/Shared/re-ddns/collections`); `DDNS_COLLECTIONS_ROOT` points it elsewhere. If ports 3000/8000 are taken: `REFLEX_API_URL=http://localhost:8150 poetry run reflex run --frontend-port 3150 --backend-port 8150`.

## ⚙️ Configuration (all optional)

| Variable | Default | Meaning |
|---|---|---|
| `CAD_ROAM_HOME` | `~/Library/Application Support/cad_roam` (macOS), `~/.local/share/cad_roam` | Meshes made from models, and the sizes people chose |
| `CAD_ROAM_MAX_TRIANGLES` | `3000000` | Bigger models are simplified to this many triangles |
| `CAD_ROAM_CALL_APP` | (chosen when calling) | The call app every call uses |
| `DDNS_COLLECTIONS_ROOT` | set by re-ddns | Where the collections are |

## 🧪 Tests

```bash
poetry run pytest                              # 27 unit tests: units, meshes, models, links, presence, routes
poetry run ./run_test_suite.sh smoke_home      # E2E (Playwright), see testcases/README.md
```

The E2E suites build their own small `cad-models` collection (`testcases/fixtures.py`: a house with a door and stairs, a tower, a small part, a model that never built) and never see your models.

## 🩺 Troubleshooting

- **A model is tiny or huge.** Details says what size CAD Roam uses and why; choose one, or add `# 1 unit = 1 m` to its code.
- **"Not built yet".** The model has no STL: open it in Codoc in CAD and press Run.
- **Slow.** Pick *Fast (no shadows)* in the top bar. Browsers without a GPU draw 3D in software.
- **The mouse doesn't turn the view.** Click the view once (Esc gives the mouse back), or drag.

## 📄 License

MIT
