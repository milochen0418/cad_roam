"""Where CAD Roam keeps its own files: the meshes it makes from models (a cache) and the sizes
people chose for models.

``CAD_ROAM_HOME`` moves it; the default is ``~/Library/Application Support/cad_roam`` on macOS and
``~/.local/share/cad_roam`` elsewhere (in the App Store container: the volume
``smart-app-cad-roam-data``). It lies outside the project folder, so writing it never triggers a
Reflex hot reload.

The models themselves are read where re-ddns mounts the ``cad-models`` collection
(``DDNS_COLLECTIONS_ROOT``), or, run on a Mac without re-ddns, in the shared folder all local apps
use (see ``reflex_ddns_auth.collections.paths``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _default_home() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "cad_roam"


def home() -> Path:
    return Path(os.environ.get("CAD_ROAM_HOME") or _default_home())


def mesh_cache() -> Path:
    return home() / "meshes"


def units_file() -> Path:
    return home() / "units.json"
