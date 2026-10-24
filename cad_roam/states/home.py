"""The list page: the CAD models to walk into (their picture, real size, who is in them), and going
straight to the model a pasted link points to."""

from __future__ import annotations

import asyncio
import dataclasses
import time

import reflex as rx

from cad_roam import i18n, links, models, presence
from cad_roam.states.lang import LangState, text
from cad_roam.states.model import _when, measures


@dataclasses.dataclass
class Card:
    id: str = ""
    key: str = ""
    title: str = ""
    thumb: str = ""
    built: bool = False
    size: str = ""  # "250 × 220 m, 181 m high"
    changed: str = ""  # "Milo Chen · 2 hours ago"
    inside: int = 0
    inside_names: str = ""


class HomeState(rx.State):
    cards: list[Card] = []
    loaded: bool = False
    link: str = ""
    link_error: str = ""

    @rx.event
    async def refresh(self):
        lang_state = await self.get_state(LangState)
        lang, texts = lang_state.lang, lang_state.t
        visitors = presence.visitors()
        cards = []
        for m in await asyncio.to_thread(models.models):
            people = visitors.get(m.key, [])
            when = i18n.ago(time.time() - _when(m.updated), lang) if m.updated else ""
            cards.append(
                Card(
                    id=m.id,
                    key=m.key,
                    title=m.title,
                    thumb=m.thumb,
                    built=m.built,
                    size=measures(texts, m.w, m.d, m.h) if m.built else texts["not_built"],
                    changed=" · ".join(x for x in (m.by, when.strip()) if x),
                    inside=len(people),
                    inside_names=", ".join(p["name"] for p in people[:4]),
                )
            )
        self.cards, self.loaded = cards, True

    @rx.event
    def set_link(self, value: str):
        self.link = value
        self.link_error = ""

    @rx.event
    async def go_link(self, value: str = ""):
        """To the model a pasted link points to. ``value`` is the box's text as it is now (the
        box tells the server about typing a moment late, so a quick click would miss it)."""
        self.link = value or self.link
        key = await asyncio.to_thread(links.read, self.link)
        if not key:
            self.link_error = await text(self, "paste_unknown")
            return None
        self.link, self.link_error = "", ""
        return rx.redirect(f"/room/{key.split('/', 1)[1]}")
