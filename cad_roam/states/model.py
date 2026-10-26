"""One tab's side of a model's place (/room/<id>).

The 3D view does the walking and flying; this is what Reflex keeps for the tab: which model it is
at and who it is there (it enters the place in :mod:`cad_roam.presence`), the model's card (its
size, the size people chose, where else it opens), the list for switching to another model, and
commands for the 3D view (``command``: a new ``seq`` makes it act).
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import random
import secrets
import time
from datetime import datetime

import reflex as rx

from cad_roam import i18n, links, models, presence, settings, units
from cad_roam.call import sync_room
from cad_roam.presence import HUB
from cad_roam.states.lang import LangState, text
from cad_roam.states.room import ModelRoom, room_token

try:
    from reflex_ddns_auth import AuthState
    from reflex_ddns_auth.intent import Intent
    from reflex_ddns_auth.intent.registry import resolve_openers
except ImportError:  # runs without sign-in: everyone is a guest
    AuthState = None
    Intent = None
    resolve_openers = None

# Sizes offered for a model, metres per unit.
UNIT_CHOICES = ["0.001", "0.01", "0.1", "0.5", "1", "10"]


@dataclasses.dataclass
class Row:
    """A model in the switcher."""

    id: str = ""
    key: str = ""
    title: str = ""
    sub: str = ""
    thumb: str = ""
    built: bool = False


@dataclasses.dataclass
class Link:
    label: str = ""
    url: str = ""


def _when(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso).timestamp()
    except (TypeError, ValueError):
        return 0.0


def metres(value: float) -> str:
    """Whole metres from 10 m up, then tenths, then centimetres: "97", "3.2", "0.08"."""
    if value >= 10:
        return f"{value:.0f}"
    return f"{value:.1f}".rstrip("0").rstrip(".") if value >= 1 else f"{value:.2f}".rstrip("0").rstrip(".")


def measures(texts: dict, w: float, d: float, h: float) -> str:
    return texts["measures"].format(w=metres(w), d=metres(d), h=metres(h))


def _unit_value(m: float) -> str:
    for v in UNIT_CHOICES:
        if abs(float(v) - m) < 1e-9:
            return v
    return ""


class ModelState(rx.State):
    """A tab in CAD Roam: the model it is at and who it is there, and what is its own."""

    # The model on screen ("<owner>/<item>", "" on the list page), and whether there is none.
    model: str = ""
    title: str = ""
    gone: bool = False
    # It has an STL (it built in Codoc in CAD at least once).
    built: bool = True
    # Who this tab is: {"peer", "user", "name", "email", "avatar", "profile", "color"}; "profile"
    # is their name in Relack, whose profile is theirs ("" for a guest here).
    me: dict[str, str] = {}
    _peer: str = ""
    _guest: str = ""
    # The model's card: open or not, its words, and where else it opens.
    card_open: bool = False
    card: dict[str, str] = {}
    card_links: list[Link] = []
    # Switching to another model.
    switch_open: bool = False
    rows: list[Row] = []
    query: str = ""
    # Commands to the 3D view: {"seq", "type", ...}.
    command: dict[str, str] = {}
    _seq: int = 0
    mode: str = "walk"
    # Shadows or speed, kept in the browser.
    quality: str = rx.LocalStorage("high", name="cad_roam_quality", sync=True)

    @rx.var
    def room_id(self) -> str:
        """The model's id as in /room/<id> (what the AI's tools call its room)."""
        return self.model.split("/", 1)[1] if "/" in self.model else ""

    @rx.var
    def shown_rows(self) -> list[Row]:
        q = self.query.strip().lower()
        return [r for r in self.rows if q in r.title.lower()] if q else self.rows

    @rx.var
    def unit_choices(self) -> list[list[str]]:
        """[value, label] for the size menu ("" is "as its code says")."""
        return [[v, f"1 unit = {units.label(float(v))}"] for v in UNIT_CHOICES]

    # ------------------------------------------------------------ who and where

    async def _identify(self) -> None:
        """Who this tab is: the signed-in account (reflex_ddns_auth), else a guest."""
        email = name = avatar = profile = ""
        if AuthState is not None:
            try:
                auth = await self.get_state(AuthState)
                if not auth._auth_loaded:
                    await auth.load_auth()
                if auth.is_logged_in:
                    email, name, avatar = auth.user_email, auth.user_name or auth.user_email, auth.user_avatar
                    # Relack knows a Google account by its e-mail, a Relack guest by their nickname.
                    profile = email or auth.user_name
            except Exception:
                pass
        if not self._peer:
            self._peer = secrets.token_hex(6)
        if email:
            user = email
        else:
            if not self._guest:
                self._guest = str(random.randint(1000, 9999))
            # A Relack guest is signed in with a nickname but no email: keep the nickname.
            user, name = f"guest-{self._guest}", name or f"Guest {self._guest}"
        me = {"peer": self._peer, "user": user, "name": name, "email": email, "avatar": avatar, "profile": profile, "color": (self.me or {}).get("color", "")}
        if me != self.me:
            self.me = me

    def _enter(self) -> None:
        """Puts this tab among the people at its model."""
        me = self.me
        tab = presence.enter(self.model, self._peer, self.router.session.client_token, me["user"], me["name"], me.get("avatar", ""), me.get("profile", ""))
        if me.get("color") != tab.color:
            self.me = {**me, "color": tab.color}

    @rx.event
    async def on_load(self):
        """Opens the model in the URL (/room/<id>) and links this tab to its room."""
        parts = [p for p in str(self.router.url.path or "").split("/") if p]
        item_id = parts[1] if len(parts) >= 2 and parts[0] == "room" else ""
        key = await asyncio.to_thread(models.find, item_id)
        await self._identify()
        room = await self.get_state(ModelRoom)
        was_at = presence.where(self._peer)
        self.card_open = self.switch_open = False
        if not key:
            if was_at:
                presence.leave(self._peer)
                HUB.later(HUB.people_changed(was_at))
            self.model, self.gone = "", True
            try:
                return await room._unlink()
            except Exception:  # not linked
                return None
        self.model, self.gone = key, False
        self._enter()
        if was_at and was_at != key:
            HUB.later(HUB.people_changed(was_at))
        await self._refresh()
        room = await room._link_to(room_token(key))
        sync_room(room, key)
        return rx.call_script(f"document.title = {json.dumps(self.title + ' · CAD Roam')}")

    @rx.event
    async def leave(self):
        """Back to the list: the others stop seeing this tab."""
        left = presence.leave(self._peer) if self._peer else ""
        self.model, self.card_open, self.switch_open = "", False, False
        if left:
            HUB.later(HUB.people_changed(left))
        room = await self.get_state(ModelRoom)
        try:
            return await room._unlink()
        except Exception:  # not linked (e.g. after a server restart)
            return None

    @rx.event
    async def ping(self):
        """Still here: keeps this tab at its model (also without its 3D view), and shows the
        model's call as it is now."""
        if not self.model:
            return
        if not presence.touch(self.model, self._peer):
            await self._identify()
            self._enter()
        room = await self.get_state(ModelRoom)
        if room._linked_to == room_token(self.model):
            sync_room(room, self.model)

    # ------------------------------------------------------------ the model

    async def _refresh(self) -> None:
        """The title, whether it built, and the card, as the model is now."""
        try:
            world = await asyncio.to_thread(models.WORLDS.get, self.model)
        except KeyError:
            self.gone = True
            return
        self.title = world.get("title") or self.model
        things = world.get("things") or []
        self.built = bool(things)
        await self._fill_card(things[0] if things else None)

    async def _fill_card(self, thing: dict | None) -> None:
        lang_state = await self.get_state(LangState)
        lang, texts = lang_state.lang, lang_state.t
        it = models.item(self.model)
        updated = thing.get("updated") if thing else (it.updated_at if it else "")
        by = (thing.get("by") if thing else "") or ""
        when = i18n.ago(time.time() - _when(updated), lang) if updated else ""
        card = {
            "title": self.title,
            "kind": i18n.kind_title(it.kind if it else "", lang),
            "thumb": thing.get("thumb", "") if thing else (models.thumb_url(it) if it else ""),
            "changed": (texts["changed_by"].format(when=when, by=by) if by else texts["changed"].format(when=when)) if when else "",
            "measures": "",
            "size_note": "",
            "unit": "",
            "tris": "",
        }
        if thing:
            card["measures"] = measures(texts, thing["w"], thing["d"], thing["h"])
            size = units.label(thing["unit"])
            source = thing.get("unit_from")
            card["size_note"] = (
                texts["size_set"].format(size=size) if source == "set"
                else texts["size_code"].format(size=size) if source == "code"
                else texts["size_default"]
            )
            card["unit"] = _unit_value(thing["unit"]) if source == "set" else ""
            card["tris"] = texts["triangles"].format(n=f"{int(thing.get('tris') or 0):,}")
        out = []
        host = str(getattr(self.router.headers, "host", "") or "")
        if it is not None:
            room = links.model_room(it.owner, it.id, host)
            if room:
                out.append(Link(texts["open_in"].format(app=links.app_name(it.owner)), room))
            if resolve_openers is not None:
                me = os.environ.get("DDNS_APP_ID", "cad-roam")
                for o in await resolve_openers(it.kind):
                    url = links.opener_url(o["app"], o["action"], it.ref, host)
                    if url and o["app"] not in (me, it.owner):
                        out.append(Link(texts["open_in"].format(app=o.get("title") or links.app_name(o["app"])), url))
        self.card, self.card_links = card, out

    @rx.event
    def open_card(self):
        self.card_open, self.switch_open = True, False

    @rx.event
    def close_card(self):
        self.card_open = False

    @rx.event
    async def set_unit(self, value: str):
        """Metres per unit for this model, for everyone at it."""
        if not self.model:
            return None
        settings.set_unit(self.model, float(value) if value in UNIT_CHOICES else None)
        world = await asyncio.to_thread(models.WORLDS.get, self.model)
        await HUB.world_changed(self.model, world.get("rev", 0))
        await self._refresh()
        return rx.toast.success(await text(self, "size_changed"), position="bottom-center")

    # ------------------------------------------------------------ switching models

    @rx.event
    async def toggle_switch(self):
        self.switch_open = not self.switch_open
        if self.switch_open:
            self.card_open = False
            await self._load_rows()

    async def _load_rows(self) -> None:
        lang_state = await self.get_state(LangState)
        texts = lang_state.t
        rows = []
        for m in await asyncio.to_thread(models.models):
            sub = measures(texts, m.w, m.d, m.h) if m.built else texts["not_built"]
            rows.append(Row(id=m.id, key=m.key, title=m.title, sub=sub, thumb=m.thumb, built=m.built))
        self.rows = rows

    @rx.event
    def set_query(self, value: str):
        self.query = value

    # ------------------------------------------------------------ the 3D view

    def _command(self, kind: str, **fields: str) -> None:
        self._seq += 1
        self.command = {"seq": str(self._seq), "type": kind, **{k: str(v) for k, v in fields.items()}}

    @rx.event
    async def handle_js(self, e: dict):
        """What the 3D view says: {"type": ...}."""
        kind = str(e.get("type") or "")
        if kind == "select":
            self.card_open, self.switch_open = True, False
            return None
        if kind in ("world", "ready"):
            if self.model:
                await self._refresh()
            return None
        if kind == "gone":
            self.gone = True
            return None
        if kind == "mode":
            self.mode = "fly" if e.get("mode") == "fly" else "walk"
            return None
        if kind == "rejoin":
            if self.model:
                await self._identify()
                self._enter()
                self._command("rejoined")
            return None
        if kind == "profile":
            return await self._profile(str(e.get("peer") or ""))
        if kind == "error":
            return rx.toast.error(str(e.get("text") or ""), position="bottom-center")
        return None

    async def _profile(self, peer: str):
        """Someone's profile (Relack's), as a dialog over the page; by their tab here, so what
        opens is whom the place knows (and nobody's e-mail goes into a URL)."""
        tab = presence.tab(self.model, peer) if self.model and peer else None
        if Intent is None or tab is None or not tab.profile:
            return None
        return Intent.start("relack", "profile.view", private={"user": tab.profile}, label=await text(self, "profile"))

    @rx.event
    def to_entrance(self):
        """Back to where you arrive: in front of the model."""
        self._command("goto", key=self.model)

    @rx.event
    def set_mode(self, mode: str):
        self._command("mode", mode=mode)

    @rx.event
    def set_quality(self, value: str):
        self.quality = "low" if value == "low" else "high"


class OpenState(rx.State):
    """``/intent/cad-roam-open?ref=<ref>`` ("Open with" on re-ddns' storage page): to the model,
    standing in front of it."""

    @rx.event
    def open_ref(self, params: dict):
        key = links.read(str(params.get("ref") or ""))
        if not key:
            return rx.redirect("/")
        return rx.redirect(f"/room/{key.split('/', 1)[1]}")
