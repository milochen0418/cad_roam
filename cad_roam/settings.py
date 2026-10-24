"""The sizes people chose for models, kept in ``CAD_ROAM_HOME/units.json``:

    {"<owner>/<item>": 0.5, ...}     metres per model unit

A model nobody chose a size for is as big as its code says (:mod:`cad_roam.units`).
Plain Python; writes are atomic, and one lock covers reading-changing-writing.
"""

from __future__ import annotations

import json
import os
import threading

from cad_roam import paths

_lock = threading.RLock()


def _load() -> dict:
    try:
        data = json.loads(paths.units_file().read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def mtime() -> int:
    try:
        return paths.units_file().stat().st_mtime_ns
    except OSError:
        return 0


def unit(key: str) -> float | None:
    value = _load().get(key)
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def set_unit(key: str, metres: float | None) -> None:
    """Metres per unit for one model; None goes back to what its code says."""
    path = paths.units_file()
    with _lock:
        data = _load()
        if metres is None:
            data.pop(key, None)
        else:
            data[key] = float(metres)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, path)
