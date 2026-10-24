"""Calls on a model, carried out by a call app through the DDNS Intent ``call.join`` (as in
Cellora, ReflexGrid and Codoc in CAD).

CAD Roam keeps who is in each model's call and rings the people in the model; the call itself runs
in the call app, opened in the intent dialog:

    Intent.start(<call app>, "call.join", private={"room": <call id>}, keep_alive=True,
                 single=True, title=..., user=..., name=...)

- Anyone in a model can call everyone in it: the others there get an incoming call (Accept /
  Decline) for RING_SECONDS.
- While the call is on, everyone in the model (also people who come later) sees "Join call"
  with the number of people in it.
- The call dialog is keep-alive (other dialogs minimize it to the tray) and single (joining
  another call closes it), so you keep walking around while you talk.

Whoever starts a call chooses its app among the installed apps that provide ``call.join``
(``Intent.choose_app`` asks only when there are several); everyone who answers or joins later
opens the same app. ``CAD_ROAM_CALL_APP`` names the app for every call instead. The call id is
private: anyone holding it can join the call, so it stays out of the iframe URL and the room.

The members and the call id live in this process's memory (``CallStore``); what everyone in the
model must see goes to the model's ``ModelRoom``.
"""

from __future__ import annotations

import os
import secrets
import time
from typing import Dict, List, Optional, TypedDict

import reflex as rx

from cad_roam import presence
from cad_roam.states.room import ModelRoom

try:
    from reflex_ddns_auth.intent import Intent, IntentState

    CALLS_ENABLED = True
except ImportError:  # the app runs without reflex_ddns_auth: no calls
    CALLS_ENABLED = False

CALL_APP = os.environ.get("CAD_ROAM_CALL_APP") or None
CALL_ACTION = "call.join"
# How long a new call rings the people in the model.
RING_SECONDS = 45
# A tab in a call refreshes its entry this often...
TOUCH_SECONDS = 15
# ...and is dropped after this long without a heartbeat (closed tab, lost network).
# Generous because background tabs get their timers throttled.
STALE_SECONDS = 150
# The dialog opens one event after join_call; don't mistake that gap for a closed dialog.
OPENING_GRACE_SECONDS = 10


class Member(TypedDict):
    id: str
    name: str


class ModelCall(TypedDict):
    call_id: str
    # The call app chosen by whoever started the call: everyone joins through it.
    app: str
    started_by_name: str
    started_at: float
    ringing: bool
    # Client token -> who; a person may be in the call from several tabs.
    members: Dict[str, Member]
    last_seen: Dict[str, float]
    # User ids who joined or declined: they are not rung (again).
    responded: List[str]
    # User ids in the model when the call started: the people it rings (not those who come later).
    invited: List[str]


class CallStore:
    """The call of each model, at most one."""

    calls: Dict[str, ModelCall] = {}

    @classmethod
    def cleanup(cls, model: str, now: float) -> None:
        """Drop members gone silent, stop ringing after RING_SECONDS, end an empty call."""
        call = cls.calls.get(model)
        if call is None:
            return
        for token, seen in list(call["last_seen"].items()):
            if now - seen > STALE_SECONDS:
                call["members"].pop(token, None)
                call["last_seen"].pop(token, None)
        if call["ringing"] and now - call["started_at"] > RING_SECONDS:
            call["ringing"] = False
        if not call["members"]:
            del cls.calls[model]

    @classmethod
    def join(cls, model: str, token: str, member: Member, now: float, app: str, call_id: str = "", invited: Optional[List[str]] = None) -> ModelCall:
        """Join the model's call, starting it in ``app`` (ringing ``invited``) if there is none."""
        call = cls.calls.get(model)
        if call is None:
            call = ModelCall(
                call_id=call_id or secrets.token_urlsafe(12),
                app=app,
                started_by_name=member["name"],
                started_at=now,
                # A call put back after being dropped (call_id given) doesn't ring again.
                ringing=not call_id,
                members={},
                last_seen={},
                responded=[],
                invited=list(invited or []),
            )
            cls.calls[model] = call
        call["members"][token] = member
        call["last_seen"][token] = now
        if member["id"] not in call["responded"]:
            call["responded"].append(member["id"])
        return call

    @classmethod
    def leave(cls, model: str, token: str) -> None:
        """Take a tab out of the model's call; the call ends with its last member."""
        call = cls.calls.get(model)
        if call is None:
            return
        call["members"].pop(token, None)
        call["last_seen"].pop(token, None)
        if not call["members"]:
            del cls.calls[model]

    @classmethod
    def decline(cls, model: str, user_id: str) -> None:
        call = cls.calls.get(model)
        if call is not None and user_id not in call["responded"]:
            call["responded"].append(user_id)


def sync_room(room: ModelRoom, model: str) -> None:
    """Shows the model's call as it is now to everyone in it (only what changed)."""
    CallStore.cleanup(model, time.time())
    call = CallStore.calls.get(model)
    count = len(call["members"]) if call else 0
    ringing_from = call["started_by_name"] if call and call["ringing"] else ""
    responded = list(call["responded"]) if call else []
    invited = list(call["invited"]) if call and call["ringing"] else []
    if room.call_count != count:
        room.call_count = count
    if room.call_ringing_from != ringing_from:
        room.call_ringing_from = ringing_from
    if list(room.call_responded) != responded:
        room.call_responded = responded
    if list(room.call_invited) != invited:
        room.call_invited = invited


class CallState(rx.State):
    """This tab's side of model calls."""

    # The model whose call this tab is in ("" when in no call).
    current_model: str = ""
    _call_id: str = ""
    # The call's app, to put the call back as it was.
    _call_app: str = ""
    _joined_at: float = 0.0
    # The model of the call this tab starts, while its caller chooses the call app.
    _starting_model: str = ""

    async def _me(self) -> tuple[str, str, str]:
        """(model on screen, user id, display name) of this tab."""
        from cad_roam.states.model import ModelState

        m = await self.get_state(ModelState)
        me = m.me or {}
        return m.model, me.get("user", ""), me.get("name", "")

    async def _room(self, model: str) -> None:
        """Pushes the call of ``model`` to its room, when that is the model on screen."""
        on_screen, _, _ = await self._me()
        if model and on_screen == model:
            sync_room(await self.get_state(ModelRoom), model)

    @rx.event
    async def join_call(self):
        """Call everyone in the model, or join its call, and open it in the dialog."""
        return await self._join(CALL_APP or "")

    @rx.event
    async def start_call(self, data: dict):
        """The caller chose the call app: call everyone in the model with it."""
        model, self._starting_model = self._starting_model, ""
        on_screen, _, _ = await self._me()
        if model and model == on_screen and data.get("app"):
            # Joins instead if someone called everyone in the model meanwhile.
            return await self._join(data["app"])

    async def _join(self, app: str):
        """Join the model's call in its app, or start the call in ``app``.

        Without ``app``, a new call first lets the caller choose it (``start_call`` comes back
        here with it).
        """
        if not CALLS_ENABLED:
            return
        model, user_id, name = await self._me()
        if not model or not user_id:
            return
        dialog = await self.get_state(IntentState)
        if self.current_model == model and CALL_ACTION in dialog.open_actions:
            # Already in this call (maybe minimized): bring it back rather than rejoin.
            return Intent.show(CALL_ACTION)
        if model not in CallStore.calls and not app:
            # Everyone who joins later opens the app chosen now: other apps can't reach the call.
            self._starting_model = model
            return Intent.choose_app(CALL_ACTION, on_result=CallState.start_call)

        now = time.time()
        token = self.router.session.client_token
        if self.current_model and self.current_model != model:
            # Switching calls: the old dialog's on_cancel comes too late to know which one.
            CallStore.leave(self.current_model, token)
        call = CallStore.join(model, token, Member(id=user_id, name=name), now, app, invited=presence.users_in(model))
        self.current_model = model
        self._call_id = call["call_id"]
        self._call_app = call["app"]
        self._joined_at = now
        await self._room(model)

        from cad_roam.states.model import ModelState

        title = (await self.get_state(ModelState)).title or "CAD Roam"
        return Intent.start(
            call["app"],
            CALL_ACTION,
            on_result=CallState.call_closed,
            on_cancel=CallState.call_closed,
            private={"room": call["call_id"]},
            keep_alive=True,
            single=True,
            label=f"Call · {title}",
            title=title,
            user=user_id,
            name=name,
        )

    @rx.event
    async def decline_call(self):
        model, user_id, _ = await self._me()
        CallStore.decline(model, user_id)
        await self._room(model)

    @rx.event
    async def call_closed(self, data: dict):
        """The call dialog closed (hung up or closed): leave the call.

        Other dialogs only minimize it (keep-alive), so being replaced means another call took
        its place (single): join_call already moved us.
        """
        if data.get("reason") == "replaced" and data.get("by") == CALL_ACTION:
            return
        model = self.current_model
        self.current_model = ""
        self._call_id = ""
        if model:
            CallStore.leave(model, self.router.session.client_token)
            await self._room(model)

    @rx.event
    async def heartbeat(self):
        """Keep this tab in its call while the call dialog runs (in front or minimized)."""
        if not CALLS_ENABLED or not self.current_model:
            return
        now = time.time()
        token = self.router.session.client_token
        model = self.current_model
        dialog = await self.get_state(IntentState)
        if CALL_ACTION not in dialog.open_actions and now - self._joined_at > OPENING_GRACE_SECONDS:
            # The dialog went away without telling us: we are not in the call.
            CallStore.leave(model, token)
            self.current_model = ""
            self._call_id = ""
            await self._room(model)
            return

        CallStore.cleanup(model, now)
        call = CallStore.calls.get(model)
        if call is not None and call["call_id"] != self._call_id:
            # Another call took this model's place while ours was dropped.
            self.current_model = ""
            self._call_id = ""
            return
        if call is None or token not in call["members"] or now - call["last_seen"][token] > TOUCH_SECONDS:
            # Touch our entry, or put the call back if it was dropped (e.g. this tab slept past
            # STALE_SECONDS) while the dialog still runs it.
            _, user_id, name = await self._me()
            CallStore.join(model, token, Member(id=user_id, name=name), now, self._call_app, call_id=self._call_id)
            if call is None:
                await self._room(model)
