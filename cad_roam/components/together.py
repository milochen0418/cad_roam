"""What shows that a model is shared (as on a Cellora notebook): the link to share, the account,
Call everyone, an incoming call, and the page's heartbeat. Who is here and where is drawn by the
3D view itself (its people chips and figures)."""

from __future__ import annotations

import reflex as rx

from cad_roam.call import CALLS_ENABLED, CallState
from cad_roam.states.lang import LangState
from cad_roam.states.room import ModelRoom
from cad_roam.states.model import AuthState, Intent, ModelState

T = LangState.t

TOP_BTN = "flex items-center gap-1.5 h-8 px-2.5 rounded-lg text-[13px] font-medium text-slate-200 hover:bg-white/10 whitespace-nowrap shrink-0"


def share_button() -> rx.Component:
    return rx.el.button(
        rx.icon("link", class_name="h-4 w-4"),
        rx.el.span(T["share"], class_name="hidden md:inline"),
        on_click=[
            rx.call_script("navigator.clipboard && navigator.clipboard.writeText(window.location.href)"),
            rx.toast.success(T["link_copied"], position="bottom-center"),
        ],
        id="share-link",
        title=T["share_title"],
        type="button",
        class_name=TOP_BTN,
    )


def identity() -> rx.Component:
    """Who you are here (signed in, a click opens your profile), and signing in or out (with
    reflex_ddns_auth)."""
    link = "text-xs whitespace-nowrap hover:underline"
    look = "text-xs font-medium text-slate-100 whitespace-nowrap max-w-[8rem] truncate"
    underline = {"borderBottom": "2px solid " + ModelState.me["color"].to(str)}
    name = rx.el.span(ModelState.me["name"], id="me-name", class_name=look, style=underline)
    if Intent is not None:
        # Your profile is Relack's (a dialog over the page); a guest here has none.
        name = rx.cond(
            ModelState.me["profile"],
            rx.el.button(
                ModelState.me["name"],
                on_click=Intent.start("relack", "profile.view", private={"user": ModelState.me["profile"]}, label=T["profile"]),
                id="me-name",
                type="button",
                title=T["your_profile"],
                class_name=f"{look} cursor-pointer hover:text-white",
                style=underline,
            ),
            name,
        )
    if AuthState is None:
        return rx.el.div(name, class_name="hidden sm:flex items-center gap-2")
    return rx.el.div(
        name,
        rx.cond(
            AuthState.is_logged_in,
            rx.el.a(T["sign_out"], href=AuthState.logout_url, class_name=f"{link} text-slate-400"),
            rx.el.a(T["sign_in"], href=AuthState.login_url, class_name=f"{link} text-teal-300"),
        ),
        class_name="hidden sm:flex items-center gap-2",
    )


def lang_toggle(then: list | None = None) -> rx.Component:
    return rx.el.button(
        rx.cond(LangState.lang == "en", "中文", "EN"),
        on_click=[LangState.pick(rx.cond(LangState.lang == "en", "zh-TW", "en")), *(then or [])],
        type="button",
        id="lang-toggle",
        title=T["language"],
        class_name="px-2 py-1 rounded-md text-xs font-medium text-slate-300 hover:bg-white/10 whitespace-nowrap shrink-0",
    )


def call_button() -> rx.Component:
    """Call everyone at the model, or join its call while one is in progress."""
    if not CALLS_ENABLED:
        return rx.fragment()
    return rx.cond(
        ModelRoom.call_count > 0,
        rx.el.button(
            rx.icon("phone-call", class_name="h-4 w-4"),
            rx.el.span(T["join_call"], " · ", ModelRoom.call_count, class_name="whitespace-nowrap"),
            on_click=CallState.join_call,
            id="call-join",
            title=T["join_call_title"],
            type="button",
            class_name=f"{TOP_BTN} !bg-emerald-600 !text-white hover:!bg-emerald-500",
        ),
        rx.el.button(
            rx.icon("phone", class_name="h-4 w-4"),
            rx.el.span(T["call_everyone"], class_name="hidden lg:inline whitespace-nowrap"),
            on_click=CallState.join_call,
            id="call-everyone",
            title=T["call_everyone_title"],
            aria_label="Call everyone",
            type="button",
            class_name=TOP_BTN,
        ),
    )


def incoming_call() -> rx.Component:
    """Someone called everyone at the model: accept or decline."""
    if not CALLS_ENABLED:
        return rx.fragment()
    me = ModelState.me["user"]
    rung = (
        (ModelRoom.call_ringing_from != "")
        & ModelRoom.call_invited.contains(me)
        & ~ModelRoom.call_responded.contains(me)
        & (ModelState.model != "")
    )
    round_button = "p-2.5 rounded-full flex cursor-pointer border-0"
    # Above the intent dialog (z-index 1000), so a call can be answered from inside another.
    return rx.cond(
        rung,
        rx.el.div(
            rx.el.div(
                rx.icon("phone-incoming", class_name="h-5 w-5 text-white"),
                class_name="h-10 w-10 rounded-full bg-emerald-500 flex items-center justify-center shrink-0 animate-pulse",
            ),
            rx.el.div(
                rx.el.span(T["incoming_call"], class_name="text-[11px] font-semibold uppercase tracking-wider text-emerald-600"),
                rx.el.span(ModelRoom.call_ringing_from, class_name="text-sm font-bold text-slate-900 truncate"),
                rx.el.span(T["is_calling_everyone"], class_name="text-xs text-slate-500"),
                class_name="flex flex-col min-w-0 flex-1",
            ),
            rx.el.button(
                rx.icon("phone-off", class_name="h-4 w-4"),
                on_click=CallState.decline_call,
                title=T["decline"],
                aria_label="Decline",
                class_name=f"{round_button} bg-red-50 text-red-600 hover:bg-red-100",
            ),
            rx.el.button(
                rx.icon("phone", class_name="h-4 w-4"),
                on_click=CallState.join_call,
                title=T["accept"],
                aria_label="Accept",
                class_name=f"{round_button} bg-emerald-600 text-white hover:bg-emerald-500",
            ),
            role="alertdialog",
            aria_label="Incoming call",
            class_name="fixed bottom-24 right-4 sm:right-6 z-[1001] w-[min(21rem,calc(100vw-2rem))] flex items-center gap-3 p-3 rounded-2xl bg-white border border-slate-200 shadow-2xl",
        ),
    )


_CALL_HEARTBEAT_JS = """
if (window.__rmCallHb) clearInterval(window.__rmCallHb);
window.__rmCallHb = setInterval(function () {
    var el = document.getElementById('call-heartbeat-trigger');
    if (!el) { clearInterval(window.__rmCallHb); window.__rmCallHb = null; return; }
    el.click();
}, 3000);
"""


@rx.memo
def call_keepalive() -> rx.Component:
    """While in a call, keep its heartbeat going on every page (the call runs in the app-wide
    intent dialogs, so it outlives the model page)."""
    return rx.cond(
        CallState.current_model != "",
        rx.el.button(
            id="call-heartbeat-trigger",
            on_click=CallState.heartbeat,
            on_mount=rx.call_script(_CALL_HEARTBEAT_JS),
            tab_index=-1,
            aria_hidden="true",
            class_name="sr-only",
        ),
    )


_PING_JS = """
if (window.__rmPing) clearInterval(window.__rmPing);
window.__rmPing = setInterval(function () {
    var el = document.getElementById('rm-ping');
    if (!el) { clearInterval(window.__rmPing); window.__rmPing = null; return; }
    el.click();
}, 5000);
"""


def page_hooks() -> rx.Component:
    """Still here: a ping every 5 s keeps this tab at its model and its call shown as it is.
    (Leaving is the 3D view's socket closing: the others see it at once.)"""
    return rx.el.button(
        id="rm-ping",
        on_click=ModelState.ping,
        on_mount=rx.call_script(_PING_JS),
        tab_index=-1,
        aria_hidden="true",
        class_name="sr-only",
    )
