from cad_roam import units

TAJ = '''import build123d as bd

# Taj Mahal - v8 with a walk-in interior (scale: 1 unit = 0.5 m)
# Plinth 95 m square x 7 m; mausoleum 55 m chamfered square;
result = bd.Box(1, 1, 1)
'''

SAGRADA = '''import build123d as bd
import math

# 聖家堂 v25：街道加上路燈
# 單位：1 = 1 公尺；榮耀立面朝 -Y，誕生立面朝 +X
A = 1
'''

BRACKET = '''import build123d as bd

# Simple L-Bracket
length, width, thickness = 80, 50, 8
result = None
'''


def test_the_models_say_their_scale():
    assert units.from_code(TAJ) == 0.5
    assert units.from_code(SAGRADA) == 1.0
    assert units.from_code(BRACKET) is None


def test_ways_of_saying_it():
    assert units.from_text("1 unit = 10 cm") == 0.1
    assert units.from_text("1 = 1 m") == 1.0
    assert units.from_text("1 單位 = 0.5 公尺") == 0.5
    assert units.from_text("单位：米") == 1.0
    assert units.from_text("units: mm") == 0.001
    assert units.from_text("all sizes in metres") == 1.0
    assert units.from_text("1 unit is 1 foot") == 0.3048


def test_not_a_scale():
    assert units.from_text("Plinth 95 m square x 7 m") is None
    assert units.from_text("walk in mausoleum") is None
    assert units.from_text("11 = 5 m") is None
    assert units.from_text("1 = 5 minutes") is None


def test_only_comments_and_docstrings_count():
    assert units.from_code('label = "1 unit = 1 m"\nresult = 1\n') is None
    assert units.from_code('"""Bridge. Units: m"""\nresult = 1\n') == 1.0
    # Half-typed code still reads its comments.
    assert units.from_code("# 1 unit = 2 m\nx = (\n") == 2.0


def test_label():
    assert units.label(0.5) == "0.5 m"
    assert units.label(1.0) == "1 m"
    assert units.label(0.001) == "1 mm"
    assert units.label(0.025) == "2.5 cm"
