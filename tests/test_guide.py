"""The AI's guide to CAD Roam (roam.guide), read by the AI Hub's assistant before the other tools."""

import asyncio

from cad_roam import ai_tools
from reflex_ddns_auth.tools import ToolContext


def test_guide_tells_the_ai_how_to_see_what_a_person_sees():
    text = asyncio.run(ai_tools.guide(ToolContext(user="Claude Code", caller="ai-hub")))
    assert "roam.view" in text and "heading" in text and "/room/<id>" in text
    assert "1.62 m" in text and "Codoc in CAD" in text
