"""The 3D view: a local React component (``assets/roam/world.jsx``) wrapped for Reflex.

The JS files are plain assets (Reflex copies ``assets/`` into the frontend), imported by
``importable_path`` as Cellora's notebook and ReflexGrid's grid are; the modules next to
world.jsx are imported relatively. three.js and three-mesh-bvh are npm packages bundled by Vite
(``lib_dependencies``), so the page needs nothing from a CDN at run time.
"""

import reflex as rx

_JS = rx.asset("roam/world.jsx")
for _name in ("engine.js", "eyes.js", "input.js", "look.js", "player.js", "view.js", "things.js", "people.js", "hud.js", "roam.css"):
    rx.asset(f"roam/{_name}")

LIBS = ["three@0.186.1", "three-mesh-bvh@0.9.15"]


class RoamWorld(rx.Component):
    library = _JS.importable_path
    tag = "RoamWorld"
    lib_dependencies: list[str] = LIBS

    # The model whose place this is: "<owner>/<item>".
    model: rx.Var[str]
    # Any URL of the backend: the view's own routes (/_roam/...) are resolved against it.
    backend: rx.Var[str]
    # This tab: {"peer", "name", "color", ...}.
    me: rx.Var[dict]
    # The thing to arrive at ("<owner>/<item>"), else the newest one.
    spawn: rx.Var[str]
    # Commands from the page: {"seq", "type": "goto" | "follow" | "mode" | "play" | ..., ...}.
    command: rx.Var[dict]
    labels: rx.Var[dict]
    quality: rx.Var[str]
    on_event: rx.EventHandler[lambda e: [e]]


world_view = RoamWorld.create
