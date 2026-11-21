"""Router regression tests driven by synthetic_data/commands/agent_commands.json (no server, no LLM, no store)."""
import json
from pathlib import Path

import pytest

from core import agent

ROOT = Path(__file__).resolve().parents[2]
CASES = []
for _d in ("synthetic_data", "synthetic_data_en"):           # German original + English copy
    for _c in json.loads((ROOT / _d / "commands/agent_commands.json").read_text())["cases"]:
        CASES.append({**_c, "id": f"{_d.removeprefix('synthetic_data').lstrip('_') or 'de'}-{_c['id']}"})


def _got(text):
    return ["reported"] if agent.is_incident_report(text) else agent.route(text)


@pytest.mark.parametrize("c", CASES, ids=[c["id"] for c in CASES])
def test_command_routes(c):
    want = ["reported"] if "verbal_report" in c["tags"] else c["intended"]
    assert set(_got(c["text"])) == set(want), c["text"]


@pytest.mark.parametrize("c", [c for c in CASES if "no-verbal-report" in c["tags"]], ids=lambda c: c["id"])
def test_question_or_negation_is_not_an_incident_report(c):
    assert not agent.is_incident_report(c["text"])


def test_helmet_needs_a_whole_word():
    assert "helmet" not in agent.route("Explain what happened at the last incident")
    assert "helmet" in agent.route("Are workers wearing helmets?")
    assert "helmet" in agent.route("Tragen alle ihre Schutzausrüstung?")


def test_notice_names_win_over_safety_and_progress_words():
    assert agent.route("Bedenken gegen die Schalung, Standsicherheit fraglich") == ["chat"]
    assert "progress" not in agent.route("Standsicherheit prüfen")      # 'stand' only as a whole word
    assert "progress" in agent.route("Wie ist der Stand?")


def test_real_incident_statements_still_report():
    for t in ("A truck fell into the pit near the excavation", "Ein Bagger ist umgekippt, eine Person ist verletzt"):
        assert agent.is_incident_report(t)
