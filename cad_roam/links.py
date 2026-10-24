"""Links between CAD Roam and the other apps: reading a pasted link back to a model, the model's
room in Codoc in CAD, and the apps that say they open CAD models (DDNS Intent "Open with").

On re-ddns every app lives at ``https://<subdomain>.<zone>``, and a model's owner is the
subdomain of the app that made it: Codoc in CAD's model ``cad/<id>`` is edited at
``https://cad.<zone>/room/<id>`` and walked in at ``https://cad-roam.<zone>/room/<id>``.
"""

from __future__ import annotations

import os
import re
from urllib.parse import parse_qs, quote, urlparse

from reflex_ddns_auth.collections.refs import valid_item_id

from cad_roam import models

APP_NAMES = {"cad": "Codoc in CAD", "_user": "the storage page"}
_HOST = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")


def zone(host: str) -> str:
    """The DNS zone apps live in: ``SERVICE_ZONE``, else this page's host without its first
    label (``cad-roam.reflex-ddns.com`` -> ``reflex-ddns.com``); "" for localhost or an address."""
    configured = os.environ.get("SERVICE_ZONE", "").strip().lower()
    if configured:
        return configured
    host = (host or "").split(":")[0].strip().lower()
    if not _HOST.match(host) or host.replace(".", "").isdigit() or host.endswith("localhost"):
        return ""
    parts = host.split(".")
    return ".".join(parts[1:]) if len(parts) > 2 else ""


def app_name(subdomain: str) -> str:
    return APP_NAMES.get(subdomain, subdomain)


def model_room(owner: str, item_id: str, host: str) -> str:
    """The model's room in the app that made it, when that app is Codoc in CAD ("" otherwise)."""
    z = zone(host)
    if not z or owner.startswith("_"):
        return ""
    return f"https://{owner}.{z}/room/{quote(item_id)}"


def opener_url(app: str, action: str, ref: str, host: str) -> str:
    z = zone(host)
    if not z:
        return ""
    return f"https://{app}.{z}/intent/{action.replace('.', '-')}?ref={quote(ref, safe='')}"


def read(link: str) -> str:
    """The key of the model a pasted text points to ("" when CAD Roam has no such model):
    ``https://cad.<zone>/room/<id>`` (or this app's own room link), a ref
    ``cad-models:<owner>/<id>``, ``<owner>/<id>``, or just the id."""
    text = (link or "").strip()
    if not text:
        return ""
    if "://" not in text and ":" in text:
        collection, _, key = text.partition(":")
        return key if collection == models.COLLECTION and models.item(key) is not None else ""
    if "://" not in text and "/" in text and "." not in text.split("/")[0]:
        return text if models.item(text) is not None else ""
    if "://" not in text and "/" not in text:
        return models.find(text) if valid_item_id(text) else ""
    url = urlparse(text if "://" in text else "https://" + text)
    parts = [p for p in url.path.split("/") if p]
    query = parse_qs(url.query)
    if parts[:1] == ["intent"]:
        return read((query.get("ref") or [""])[0])
    if len(parts) >= 3 and parts[0] == "room":
        key = f"{parts[1]}/{parts[2]}"
        return key if models.item(key) is not None else ""
    if parts:
        return models.find(parts[-1])
    return ""
