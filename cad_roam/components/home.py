"""The list page (/): the CAD models to walk into, and a box for a link to one."""

from __future__ import annotations

import reflex as rx

from cad_roam.components.page import backend_url
from cad_roam.components.together import lang_toggle
from cad_roam.states.home import Card, HomeState
from cad_roam.states.lang import LangState
from cad_roam.states.model import AuthState

T = LangState.t

# The paste box's text right now.
_PASTED = rx.Var("((document.getElementById('paste') || {}).value || '')", _var_type=str)


def logo(size: str = "h-9 w-9") -> rx.Component:
    return rx.image(src="/roam/logo.svg", alt="CAD Roam", class_name=size)


def account() -> rx.Component:
    if AuthState is None:
        return rx.fragment()
    link = "text-xs whitespace-nowrap hover:underline"
    return rx.cond(
        AuthState.is_logged_in,
        rx.el.div(
            rx.el.span(AuthState.user_name, class_name="text-xs text-slate-300 max-w-[10rem] truncate"),
            rx.el.a(T["sign_out"], href=AuthState.logout_url, class_name=f"{link} text-slate-400"),
            class_name="hidden sm:flex items-center gap-2",
        ),
        rx.el.a(T["sign_in"], href=AuthState.login_url, class_name=f"{link} text-teal-300"),
    )


def model_card(card: Card) -> rx.Component:
    picture = rx.cond(
        card.thumb != "",
        rx.image(src=backend_url(card.thumb), alt="", class_name="w-full h-44 object-contain bg-white rounded-t-2xl"),
        rx.el.div(
            rx.icon("box", class_name="h-10 w-10 text-slate-500"),
            class_name="h-44 flex items-center justify-center rounded-t-2xl bg-gradient-to-br from-slate-800 to-slate-900",
        ),
    )
    return rx.el.a(
        picture,
        rx.el.div(
            rx.el.h3(card.title, class_name="text-[16px] font-semibold text-white truncate"),
            rx.el.span(card.size, class_name=rx.cond(card.built, "text-[13px] text-slate-200", "text-[13px] text-amber-300")),
            rx.el.span(card.changed, class_name="text-[12px] text-slate-500 truncate"),
            rx.el.div(
                rx.cond(
                    card.inside > 0,
                    rx.el.span(
                        rx.el.span(class_name="inline-block h-2 w-2 rounded-full bg-emerald-400 mr-1.5 animate-pulse"),
                        card.inside, " ", T["inside_now"], " · ", card.inside_names,
                        class_name="text-[12px] text-emerald-300 truncate",
                    ),
                    rx.el.span(),
                ),
                rx.el.span(
                    T["walk_in"], rx.icon("arrow-right", class_name="h-4 w-4"),
                    class_name="flex items-center gap-1 text-[13px] font-semibold text-teal-300 shrink-0",
                ),
                class_name="flex items-center justify-between gap-2 mt-1",
            ),
            class_name="flex flex-col gap-1 p-4",
        ),
        href="/room/" + card.id,
        custom_attrs={"data-key": card.key},
        class_name="rm-card block rounded-2xl bg-slate-900 border border-white/10 hover:border-teal-400/60 hover:-translate-y-0.5 transition-all shadow-lg overflow-hidden",
    )


def paste_box() -> rx.Component:
    return rx.el.div(
        rx.el.label(T["paste_label"], html_for="paste", class_name="text-[13px] text-slate-300"),
        rx.el.div(
            rx.el.input(
                value=HomeState.link,
                on_change=HomeState.set_link,
                on_key_down=lambda key: rx.cond(key == "Enter", HomeState.go_link(_PASTED), rx.noop()),
                placeholder=T["paste_placeholder"],
                id="paste",
                class_name="flex-1 min-w-0 h-11 px-4 rounded-xl bg-slate-900 border border-white/15 text-sm text-slate-100 placeholder:text-slate-500 outline-none focus:border-teal-400",
            ),
            rx.el.button(T["go"], on_click=HomeState.go_link(_PASTED), type="button", id="paste-go", class_name="h-11 px-5 rounded-xl bg-teal-500 text-slate-950 text-sm font-semibold hover:bg-teal-400"),
            class_name="flex gap-2",
        ),
        rx.cond(HomeState.link_error != "", rx.el.span(HomeState.link_error, id="paste-error", class_name="text-[13px] text-rose-300")),
        class_name="flex flex-col gap-2 w-full max-w-2xl",
    )


def how_to() -> rx.Component:
    row = "flex gap-3 items-start text-[13px] text-slate-300"
    return rx.el.section(
        rx.el.h2(T["how_title"], class_name="text-sm font-semibold text-slate-200"),
        rx.el.div(
            rx.el.div(rx.icon("footprints", class_name="h-5 w-5 text-teal-300 shrink-0"), rx.el.span(T["how_walk"]), class_name=row),
            rx.el.div(rx.icon("plane", class_name="h-5 w-5 text-sky-300 shrink-0"), rx.el.span(T["how_fly"]), class_name=row),
            rx.el.div(rx.icon("mouse-pointer-click", class_name="h-5 w-5 text-amber-300 shrink-0"), rx.el.span(T["how_open"]), class_name=row),
            class_name="grid sm:grid-cols-3 gap-4",
        ),
        class_name="flex flex-col gap-3 p-5 rounded-2xl bg-slate-900/60 border border-white/10",
    )


def home_page() -> rx.Component:
    return rx.el.div(
        rx.el.header(
            rx.el.div(logo(), rx.el.span("CAD Roam", class_name="text-lg font-bold tracking-tight text-white"), class_name="flex items-center gap-2.5"),
            rx.el.div(lang_toggle([HomeState.refresh]), account(), class_name="flex items-center gap-3"),
            class_name="flex items-center justify-between max-w-6xl mx-auto w-full px-4 sm:px-6 h-16",
        ),
        rx.el.main(
            rx.el.section(
                rx.el.h1(T["tagline"], class_name="text-3xl sm:text-5xl font-bold tracking-tight text-white"),
                rx.el.p(T["intro"], class_name="text-[15px] sm:text-base text-slate-300 max-w-2xl leading-relaxed"),
                paste_box(),
                class_name="flex flex-col gap-5 py-6 sm:py-10",
            ),
            rx.el.h2(T["models"], class_name="text-sm font-semibold uppercase tracking-wider text-slate-400"),
            rx.cond(
                HomeState.loaded & (HomeState.cards.length() == 0),
                rx.el.p(T["no_models"], class_name="text-slate-400 text-sm"),
            ),
            rx.el.div(
                rx.foreach(HomeState.cards, model_card),
                id="models",
                class_name="grid gap-4 sm:grid-cols-2 lg:grid-cols-3",
            ),
            how_to(),
            class_name="flex flex-col gap-5 max-w-6xl mx-auto w-full px-4 sm:px-6 pb-16",
        ),
        class_name="min-h-screen bg-gradient-to-b from-slate-950 via-slate-950 to-[#08201f] text-slate-100",
    )
