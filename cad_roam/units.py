"""How big a model is: how many metres one unit of its coordinates is.

A CAD model has no size of its own, only numbers. build123d's unit is the millimetre, but people
modelling buildings often work in metres and say so in a comment, as the models in the
``cad-models`` collection do::

    # Taj Mahal - v8 with a walk-in interior (scale: 1 unit = 0.5 m)
    # 單位：1 = 1 公尺；榮耀立面朝 -Y

:func:`from_code` finds such a comment. Without one the model is in millimetres; people can
change it in Roam (it is kept per world, see :mod:`cad_roam.settings`).

Plain Python.
"""

from __future__ import annotations

import io
import re
import tokenize

MILLIMETRE = 0.001
DEFAULT = MILLIMETRE

# Unit words -> metres.
_UNITS = {
    "mm": 0.001, "millimeter": 0.001, "millimeters": 0.001, "millimetre": 0.001, "millimetres": 0.001,
    "毫米": 0.001, "公釐": 0.001, "公厘": 0.001, "釐米": 0.01,
    "cm": 0.01, "centimeter": 0.01, "centimeters": 0.01, "centimetre": 0.01, "centimetres": 0.01,
    "公分": 0.01, "厘米": 0.01,
    "dm": 0.1, "decimeter": 0.1, "decimeters": 0.1, "decimetre": 0.1, "decimetres": 0.1,
    "m": 1.0, "meter": 1.0, "meters": 1.0, "metre": 1.0, "metres": 1.0, "公尺": 1.0, "米": 1.0,
    "km": 1000.0, "kilometer": 1000.0, "kilometers": 1000.0, "kilometre": 1000.0, "kilometres": 1000.0, "公里": 1000.0,
    "in": 0.0254, "inch": 0.0254, "inches": 0.0254, "英寸": 0.0254, "吋": 0.0254,
    "ft": 0.3048, "foot": 0.3048, "feet": 0.3048, "英尺": 0.3048, "呎": 0.3048,
}
# Longest first, so "mm" wins over "m" and "meters" over "meter".
_WORDS = "|".join(sorted((re.escape(w) for w in _UNITS), key=len, reverse=True))
# After a unit word: not another letter (so "1 = 5 m" but not "1 = 5 mins"); CJK words end anyway.
_END = r"(?![A-Za-z])"
_NUM = r"(\d+(?:\.\d+)?|\.\d+)"

# "1 unit = 0.5 m", "1 = 1 公尺", "1 單位 = 0.5 公尺", "1 u = 10 cm"
_ONE_IS = re.compile(
    rf"(?<![\d.])1(?:\.0+)?\s*(?:units?|u|單位|单位|格)?\s*(?:=|:|：|is|equals|代表|等於|等于)\s*{_NUM}\s*({_WORDS}){_END}",
    re.IGNORECASE,
)
# "units: m", "unit = mm", "單位：公尺", "单位: 米", "in metres", "(meters)"
_UNITS_ARE = re.compile(rf"(?:units?|單位|单位)\s*(?:=|:|：|are|is|in)?\s*({_WORDS}){_END}", re.IGNORECASE)
_IN_UNIT = re.compile(rf"\b(?:in|all in|dimensions in|sizes in)\s+({_WORDS}){_END}", re.IGNORECASE)


def _comments(code: str) -> list[str]:
    """The comments and the string-only statements (docstrings) of Python code, in order.

    Code that doesn't tokenize (half typed) falls back to the text after each ``#``.
    """
    out: list[str] = []
    try:
        prev = None
        for tok in tokenize.generate_tokens(io.StringIO(code).readline):
            if tok.type == tokenize.COMMENT:
                out.append(tok.string.lstrip("#").strip())
            elif tok.type == tokenize.STRING and (prev is None or prev.type in (tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.DEDENT)):
                out.append(tok.string.strip("\"'rbuRBU").strip())
            if tok.type not in (tokenize.NL, tokenize.COMMENT):
                prev = tok
    except (tokenize.TokenError, IndentationError, SyntaxError):
        out = [line.split("#", 1)[1].strip() for line in code.splitlines() if "#" in line]
    return out


def from_text(text: str) -> float | None:
    """Metres per unit stated in one comment, or None."""
    m = _ONE_IS.search(text)
    if m:
        value = float(m.group(1)) * _UNITS[m.group(2).lower()]
        return value if value > 0 else None
    for pattern in (_UNITS_ARE, _IN_UNIT):
        m = pattern.search(text)
        if m:
            return _UNITS[m.group(1).lower()]
    return None


def from_code(code: str) -> float | None:
    """Metres per unit a model's code says it uses (the first comment that says), or None."""
    for text in _comments(code[:200_000]):
        found = from_text(text)
        if found is not None:
            return found
    return None


def label(metres: float) -> str:
    """``0.5`` -> ``"0.5 m"``, ``0.001`` -> ``"1 mm"``, ``0.025`` -> ``"2.5 cm"``."""
    for word, size, above in (("km", 1000.0, 1000.0), ("m", 1.0, 0.1), ("cm", 0.01, 0.01), ("mm", 0.001, 0.0)):
        if metres >= above:
            text = f"{metres / size:.4f}".rstrip("0").rstrip(".")
            return f"{text} {word}"
    return f"{metres} m"
