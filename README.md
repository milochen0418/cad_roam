# CAD Roam 🧭

Walk **into** your CAD models. Pick a model made in [Codoc in CAD](https://github.com/milochen0418/codoc_in_cad) and it stands in front of you at its **real size**, in its colours: walk in like in a first-person game (in through the Taj Mahal's gate, up to its tomb chamber), or fly round it like a drone (over the Sagrada Família's towers). Its glass is glass: in the morning sun the Sagrada Família's blue and green windows glow and throw their colours on the floor and the pillars, in the evening its red and orange ones. Everyone who opens the same model sees each other there, walking or flying, and can call everyone.

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
- **L** lights a torch for dark insides, **T** jumps the sun to the morning, the day or the evening (the ☀ slider under Walk / Drone moves it through the day), **E** (or a click while looking) opens the model's details, **H** shows the keys again. Phones and tablets get a stick and up/down buttons; a gamepad works too (sticks, A up, B down, Y switches).

**In its colours**
- A model built in Codoc in CAD since it has colours shows each part in its colour: the build writes a GLB beside the STL, and CAD Roam draws that. Models built before, and STL files imported on the storage page, are drawn in one stone colour (press Run in Codoc in CAD to get the colours).
- See-through parts (a colour with an alpha, like `("#2f6fd6", 0.55)`) are glass. From inside, a stained-glass window shows the sky in its colour and glows when the sun is behind it; the sunlight that comes through it falls in its colour on whatever it reaches, its pattern cut by the stone round it.
- **Big models ask first.** A model in its colours with more triangles than `CAD_ROAM_MAX_TRIANGLES` (3 million) loads only once you say so: a question tells how many triangles it has (and how many times the limit), how much it downloads and about how much memory it takes (the Sagrada Família at 4.7 million: 9.3 MB, about 850 MB). **Load it** draws it in its colours; **Don't load** leaves its outline, with **Load it** at the top left for later. The answer holds while the page is open, for the model's next builds too; a new page asks again.
- **The sun's time**: drag the ☀ slider under Walk / Drone from 6:30 to 17:30, and the sun crosses the sky as it does on a spring or autumn day at Barcelona's latitude: up in the east, 49° high in the south at noon, down in the west, warmer and with a dimmer sky when it is low. **T** jumps to 7:30, 10:30 and 16:30. 10:30 is where you arrive: the sun behind you, a little to the east (+X is east, the front of a model faces south). Your browser keeps the time you leave it at. The Sagrada Família's Nativity side (+X) has the cool windows, lit in the morning, its Passion side the warm ones, lit in the afternoon, as in the real church.
- Under a roof, less of the sky's light gets in, so insides are dimmer than outside and their windows' light shows. These lights need *Best (shadows)*; *Fast* shows the colours and the glass only.

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
  │  things.js  the model            │                                   │   mesh, or the GLB (gz)    │
  │  look.js    colours, glass, sun  │                                   │                            │
  │  people.js  the others           │ ◀──── WS /_roam/ws/<owner>/<id> ▶ │ presence.py: who, where    │
  │  hud.js     keys, map, chips     │   poses ~10/s, "model changed"    │ api.py: watches the models │
  └──────────────────────────────────┘                                   └─────────────┬──────────────┘
        Reflex pages around it: the list, the switcher, the details, calls             │ reads (read-only)
                                                                                        ▼
                                          /data/collections/cad-models/by-app/cad/<id>/   (re-ddns mounts)
```

- **Meshes.** A model is drawn from the GLB its build wrote beside the STL (Codoc in CAD's `model.glb`, each part in its colour), sent gzipped as it is (the Sagrada Família's: 50 MB, 6.4 MB gzipped, 2.3 million triangles); three.js reads it and makes one mesh per colour. Without a GLB, from the STL, which writes every corner of every triangle out (70 MB for an older Sagrada Família, 1.4 million triangles): `cad_roam/meshes.py` sends each corner once and the triangles as indices, gzipped (9 MB). Either is made once per build and cached in `CAD_ROAM_HOME` under the file's size and time, so a rebuilt model gets a new URL and browsers cache the rest for good. STLs over `CAD_ROAM_MAX_TRIANGLES` (3 million) are simplified first; a GLB over it is sent as it is once the person agrees (the place says `big`: the limit and the gzipped size, so the browser can ask), and one that needs a glTF extension isn't used (the STL is).
- **Glass and light** (`assets/roam/look.js`). A part whose colour has an alpha is drawn twice after the rest: once multiplying what is behind it by its colour, once adding its reflections and the sun shining through it. Each frame the glass is also drawn from the sun into a small picture of its colours and depth; surfaces look it up next to their shadow, and those behind glass from the sun get its colour. A picture of the model from straight above, made when it loads, tells which surfaces are under a roof: they get half the sky's light.
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
| `CAD_ROAM_MAX_TRIANGLES` | `3000000` | A model in its colours with more triangles asks before it loads; a bigger STL is simplified to this many |
| `CAD_ROAM_CALL_APP` | (chosen when calling) | The call app every call uses |
| `DDNS_COLLECTIONS_ROOT` | set by re-ddns | Where the collections are |

## 🧪 Tests

```bash
poetry run pytest                              # 34 unit tests: units, meshes and GLBs, models, links, presence, routes
poetry run ./run_test_suite.sh smoke_home      # E2E (Playwright), see testcases/README.md
```

The E2E suites build their own small `cad-models` collection (`testcases/fixtures.py`: a house with a door and stairs, a tower, a small part, a model that never built, a chapel in its colours with a blue window) and never see your models.

## 🩺 Troubleshooting

- **A model is tiny or huge.** Details says what size CAD Roam uses and why; choose one, or add `# 1 unit = 1 m` to its code.
- **"Not built yet".** The model has no STL: open it in Codoc in CAD and press Run.
- **All one colour.** It was last built before Codoc in CAD wrote colours: press Run there once.
- **Only an outline, "not loaded".** The model is big and you chose *Don't load*: press **Load it** at the top left, or open the page again.
- **No light through the windows.** Move the sun (the ☀ slider, or T) to where the windows face: the east ones in the morning, the west ones in the afternoon. At 10:30 it is high in the south-east. And choose *Best (shadows)*.
- **Slow.** Pick *Fast (no shadows)* in the top bar. Browsers without a GPU draw 3D in software.
- **The mouse doesn't turn the view.** Click the view once (Esc gives the mouse back), or drag.

## 📄 License

MIT
