"""What everybody at a model sees at once through Reflex: its call.

``ModelRoom`` is a Reflex ``SharedState``: every tab on /room/<id> links its room to the model
(``room_token``). Where people are and what they do in the 3D view travels over the model's own
socket (:mod:`cad_roam.presence`), not through here.
"""

from __future__ import annotations

import hashlib

import reflex as rx


def room_token(key: str) -> str:
    """The shared-state token of a model (link tokens can't hold ``_``, item ids can)."""
    return "model-" + hashlib.sha1(key.encode()).hexdigest()[:16]


class ModelRoom(rx.SharedState):
    # The model's call: how many are in it, who is ringing everyone (while it rings), the people it
    # rings (those at the model when it started), and those who joined or declined.
    call_count: int = 0
    call_ringing_from: str = ""
    call_invited: list[str] = []
    call_responded: list[str] = []
