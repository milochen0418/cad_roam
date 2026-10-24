"""The model page (/room/<id>): the 3D view filling the window, a thin bar over it, the model's card,
and a list for switching to another model."""

from __future__ import annotations

import reflex as rx

from cad_roam.components.together import TOP_BTN, call_button, identity, incoming_call, lang_toggle, page_hooks, share_button
from cad_roam.components.world_view import world_view
from cad_roam.states.lang import LangState
from cad_roam.states.model import Link, ModelState, Row

T = LangState.t
GLASS = "bg-slate-900/90 backdrop-blur-md border border-white/10 shadow-2xl"


def backend_url(path) -> rx.Var:
    """A backend route (``/_roam/...``) as the browser must ask for it: on the backend's port
    in a local run, on the page's own host behind re-ddns (the upload URL, then ``..``)."""
    return rx.get_upload_url(".." + path)


def thumb(src, size: str = "h-10 w-10") -> rx.Component:
    return rx.cond(
        src != "",
        rx.image(src=backend_url(src), alt="", class_name=f"{size} rounded-md object-cover bg-white shrink-0"),
        rx.el.div(rx.icon("box", class_name="h-5 w-5 text-teal-300"), class_name=f"{size} rounded-md bg-slate-800 flex items-center justify-center shrink-0"),
    )


def top_bar() -> rx.Component:
    return rx.el.header(
        rx.el.div(
            rx.el.a(
                rx.icon("arrow-left", class_name="h-4 w-4"),
                rx.el.span(T["back"], class_name="hidden sm:inline"),
                href="/",
                id="back-home",
                class_name=TOP_BTN,
            ),
            rx.el.span(ModelState.title, id="model-title", class_name="text-[15px] font-semibold text-white truncate"),
            rx.el.button(
                rx.icon("chevrons-up-down", class_name="h-4 w-4"),
                rx.el.span(T["switch"], class_name="hidden md:inline"),
                on_click=ModelState.toggle_switch,
                id="switch-toggle",
                title=T["switch"],
                type="button",
                class_name=rx.cond(ModelState.switch_open, f"{TOP_BTN} bg-white/15", TOP_BTN),
            ),
            rx.el.button(
                rx.icon("info", class_name="h-4 w-4"),
                rx.el.span(T["details"], class_name="hidden md:inline"),
                on_click=rx.cond(ModelState.card_open, ModelState.close_card, ModelState.open_card),
                id="details-toggle",
                title=T["details"],
                type="button",
                class_name=rx.cond(ModelState.card_open, f"{TOP_BTN} bg-white/15", TOP_BTN),
            ),
            class_name="flex items-center gap-1.5 min-w-0",
        ),
        rx.el.div(
            share_button(),
            call_button(),
            rx.el.select(
                rx.el.option(T["graphics_high"], value="high"),
                rx.el.option(T["graphics_low"], value="low"),
                value=ModelState.quality,
                on_change=ModelState.set_quality,
                title=T["graphics"],
                id="quality",
                class_name="hidden md:block h-8 rounded-lg bg-transparent text-[12px] text-slate-300 border border-white/15 px-1.5 hover:bg-white/10",
            ),
            lang_toggle(),
            identity(),
            class_name="flex items-center gap-1.5",
        ),
        class_name=f"absolute top-0 inset-x-0 z-20 h-12 px-2 sm:px-3 flex items-center justify-between gap-2 {GLASS} !border-x-0 !border-t-0 !shadow-none",
    )


def switch_row(r: Row) -> rx.Component:
    here = r.key == ModelState.model
    return rx.el.a(
        thumb(r.thumb),
        rx.el.div(
            rx.el.span(r.title, class_name="text-[13px] font-medium text-slate-100 truncate"),
            rx.el.span(r.sub, class_name="text-[11px] text-slate-400 truncate"),
            class_name="flex flex-col min-w-0 text-left",
        ),
        href="/room/" + r.id,
        custom_attrs={"data-key": r.key},
        class_name=rx.cond(
            here,
            "rm-model w-full flex items-center gap-3 p-2 rounded-lg bg-white/10 ring-1 ring-teal-400/60",
            "rm-model w-full flex items-center gap-3 p-2 rounded-lg hover:bg-white/10",
        ),
    )


def switcher() -> rx.Component:
    return rx.cond(
        ModelState.switch_open,
        rx.el.aside(
            rx.el.input(
                value=ModelState.query,
                on_change=ModelState.set_query,
                placeholder=T["find"],
                id="find",
                class_name="w-full h-9 px-3 rounded-lg bg-slate-800/80 text-sm text-slate-100 placeholder:text-slate-500 border border-white/10 outline-none focus:border-teal-400",
            ),
            rx.el.div(
                rx.foreach(ModelState.shown_rows, switch_row),
                class_name="flex-1 min-h-0 overflow-y-auto flex flex-col gap-0.5 -mx-1 px-1",
            ),
            id="switcher",
            class_name=f"absolute left-3 top-14 bottom-3 z-20 w-[min(18rem,calc(100vw-1.5rem))] flex flex-col gap-2 p-3 rounded-2xl {GLASS}",
        ),
    )


def _link(l: Link) -> rx.Component:
    return rx.el.a(
        rx.icon("external-link", class_name="h-4 w-4"),
        l.label,
        href=l.url,
        target="_blank",
        rel="noopener",
        class_name="flex items-center gap-2 h-9 px-3 rounded-lg bg-white/10 text-[13px] text-slate-100 hover:bg-white/20",
    )


def card() -> rx.Component:
    c = ModelState.card
    return rx.cond(
        ModelState.card_open,
        rx.el.aside(
            rx.el.div(
                rx.el.div(
                    rx.el.span(c["kind"], class_name="text-[11px] uppercase tracking-wider text-teal-300 font-semibold"),
                    rx.el.h2(c["title"], id="card-title", class_name="text-[17px] font-semibold text-white leading-snug"),
                    rx.el.span(c["changed"], class_name="text-xs text-slate-400"),
                    class_name="flex flex-col gap-0.5 min-w-0",
                ),
                rx.el.button(
                    rx.icon("x", class_name="h-4 w-4"),
                    on_click=ModelState.close_card,
                    title=T["close"],
                    type="button",
                    id="card-close",
                    class_name="p-1.5 rounded-md text-slate-400 hover:bg-white/10 hover:text-white shrink-0",
                ),
                class_name="flex items-start justify-between gap-2",
            ),
            rx.cond(
                c["thumb"] != "",
                rx.image(src=backend_url(c["thumb"]), alt="", class_name="w-full max-h-44 object-contain rounded-lg bg-white"),
            ),
            rx.cond(
                ModelState.built,
                rx.el.div(
                    rx.el.span(c["measures"], id="card-measures", class_name="text-sm text-slate-200"),
                    rx.el.label(T["size"], html_for="card-unit", class_name="text-[11px] uppercase tracking-wider text-slate-400 mt-1"),
                    rx.el.select(
                        rx.el.option(T["size_auto"], value=""),
                        rx.foreach(ModelState.unit_choices, lambda u: rx.el.option(u[1], value=u[0])),
                        value=c["unit"],
                        on_change=ModelState.set_unit,
                        id="card-unit",
                        class_name="h-9 rounded-lg bg-slate-800 text-sm text-slate-100 border border-white/10 px-2",
                    ),
                    rx.el.span(c["size_note"], id="card-size-note", class_name="text-xs text-slate-400"),
                    rx.el.span(c["tris"], class_name="text-xs text-slate-500"),
                    class_name="flex flex-col gap-1",
                ),
            ),
            rx.el.button(
                rx.icon("door-open", class_name="h-4 w-4"),
                T["entrance"],
                on_click=ModelState.to_entrance,
                type="button",
                id="card-entrance",
                class_name="flex items-center justify-center gap-2 h-9 rounded-lg bg-teal-500 text-slate-950 text-sm font-semibold hover:bg-teal-400",
            ),
            rx.foreach(ModelState.card_links, _link),
            id="card",
            class_name=f"absolute right-3 top-14 z-20 w-[min(20rem,calc(100vw-1.5rem))] max-h-[calc(100%-4.5rem)] overflow-y-auto flex flex-col gap-3 p-4 rounded-2xl {GLASS}",
        ),
    )


def notice(title, body) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.p(title, class_name="text-[15px] font-semibold text-white"),
            body,
            class_name=f"flex flex-col items-center gap-2 max-w-sm text-center p-5 rounded-2xl {GLASS}",
        ),
        class_name="absolute inset-0 z-10 flex items-center justify-center pointer-events-none [&>*]:pointer-events-auto px-4",
    )


def model_page() -> rx.Component:
    room_link = rx.foreach(ModelState.card_links, _link)
    return rx.el.div(
        rx.cond(
            ModelState.model != "",
            world_view(
                model=ModelState.model,
                backend=rx.get_upload_url(""),
                me=ModelState.me,
                spawn=ModelState.model,
                command=ModelState.command,
                labels=T,
                quality=ModelState.quality,
                on_event=ModelState.handle_js,
            ),
        ),
        rx.cond(
            ModelState.gone,
            notice(T["no_such_model"], rx.el.a(T["back"], href="/", class_name="text-teal-300 hover:underline")),
            rx.cond(
                (ModelState.model != "") & ~ModelState.built,
                notice(T["not_built_title"], rx.el.div(rx.el.p(T["not_built_body"], class_name="text-sm text-slate-300"), room_link, class_name="flex flex-col gap-3")),
            ),
        ),
        top_bar(),
        switcher(),
        card(),
        incoming_call(),
        page_hooks(),
        class_name="fixed inset-0 overflow-hidden bg-slate-950 text-slate-100",
    )
