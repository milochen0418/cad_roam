"""CAD Roam: walk into a CAD model at its real size like in a game, or fly round it like a drone.

Pages: ``/`` lists the models of the shared collection ``cad-models`` (Codoc in CAD's models);
``/room/<id>`` is one of them as a place (the same id as its room in Codoc in CAD). Everyone at a
model sees the others walking or flying, and can call everyone. The 3D view is
``assets/roam/``; its data comes from the backend's own routes (:mod:`cad_roam.api`). An AI looks
at a model from inside through the AI Hub (:mod:`cad_roam.ai_tools`).
"""

import reflex as rx

try:
    from reflex_ddns_auth.intent import install_intent_host, intent
except ImportError:  # a standalone CAD Roam, without the DDNS libraries
    install_intent_host = intent = None
try:
    from cad_roam import ai_tools
except ImportError:  # a DDNS library without tools
    ai_tools = None

from cad_roam.api import api, lifespan
from cad_roam.components.home import home_page
from cad_roam.components.page import model_page
from cad_roam.components.together import call_keepalive
from cad_roam.states.home import HomeState
from cad_roam.states.lang import LangState
from cad_roam.states.model import AuthState, ModelState, OpenState

app = rx.App(
    head_components=[
        rx.el.link(rel="preconnect", href="https://fonts.googleapis.com"),
        rx.el.link(rel="preconnect", href="https://fonts.gstatic.com", cross_origin=""),
        rx.el.link(
            href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap",
            rel="stylesheet",
        ),
        rx.el.link(rel="stylesheet", href="/roam/roam.css"),
        rx.el.link(rel="icon", type="image/svg+xml", href="/favicon.svg"),
    ],
    # Our own backend routes (places, meshes, pictures, the people socket), next to Reflex's.
    api_transformer=api,
)
app.register_lifespan_task(lifespan)

# Dialogs of other apps (calls) live above every page, so a call goes on when you go back to
# the list.
if install_intent_host is not None:
    install_intent_host(app)
    app.extra_app_wraps[(8, "RoamCallKeepalive")] = lambda stateful: rx.fragment(call_keepalive())

_auth_on_load = [AuthState.load_auth] if AuthState is not None else []

app.add_page(
    home_page,
    route="/",
    title="CAD Roam",
    on_load=[*_auth_on_load, LangState.detect, ModelState.leave, HomeState.refresh],
)
app.add_page(
    model_page,
    route="/room/[model_id]",
    title="CAD Roam",
    on_load=[*_auth_on_load, LangState.detect, ModelState.on_load],
)

if intent is not None:

    @intent(app, action="cad-roam.open", on_open=OpenState.open_ref, accepts=("cad.build123d",), title="Walk in CAD Roam")
    def open_in_cad_roam():
        return rx.el.div("CAD Roam…", class_name="p-6 text-sm text-slate-500")

# An AI looks from inside a model (pictures taken by the pages open on it).
if ai_tools is not None:
    ai_tools.register(app)
