"""AI Site Manager orchestrator (core/agent.py): routing, evidence-backed incident rules, context, report."""
import pytest

from core import agent, store


def _photo(pid, dets, zone=None, caption="", category="progress"):
    return {"id": pid, "evidence_id": f"photo:{pid}", "file": f"uploads/{pid}.jpg", "ann_file": None, "original_name": f"{pid}.jpg",
            "category": category, "taken_at": "2026-11-17T10:00:00", "zone": zone, "plan_xy": None, "caption": caption,
            "detector": {"name": "RF-DETR Small"}, "detections": dets}


def _det(c, x, y, w=100, h=100, conf=0.9):
    return {"class": c, "confidence": conf, "x": x, "y": y, "width": w, "height": h}


LAYOUT = {"name": "BW 12", "boundary": [[0, 0], [100, 0], [100, 50], [0, 50]],
          "zones": [{"id": "erd", "name": "Erdbau / Aushub Ost", "kind": "earthworks", "polygon": [[50, 0], [100, 0], [100, 50], [50, 50]], "activities": []},
                    {"id": "wln", "name": "Widerlager Nord", "kind": "future", "polygon": [[0, 0], [50, 0], [50, 50], [0, 50]], "activities": ["W1_BP"]}]}
ACT = {"id": "W1_BP", "name": "Bohrpfähle W1", "unit": "m", "total": 96.0, "planned": 96.0, "actual": 76.6, "delay_days": 1.2, "light": "yellow"}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    monkeypatch.setattr(agent, "DATA", tmp_path)
    photos = [_photo("p1", [_det("person", 100, 100), _det("excavator", 150, 120)], zone="erd"),          # person in the machine's box
              _photo("p2", [_det("person", 10, 10, 20, 40), _det("excavator", 600, 400)], zone="erd"),   # far apart: no finding
              _photo("p3", [_det("dump_truck", 300, 300)], zone="wln"),                                  # machine in a future zone
              _photo("p4", [_det("excavator", 300, 300, conf=0.3), _det("person", 300, 300, conf=0.3)])]  # below MIN_CONF
    twin = {"layout": LAYOUT, "photos": photos, "zones": [{"id": "erd", "photos": ["p1", "p2"], "activities": [], "machinery": []},
                                                          {"id": "wln", "photos": ["p3"], "activities": [ACT], "machinery": []}],
            "models": {"detector": "RF-DETR Small", "vision": None}}
    monkeypatch.setattr(agent.site_twin, "twin", lambda: twin)
    monkeypatch.setattr(agent.plan, "status", lambda **kw: {"as_of": "2026-11-17", "activities": [ACT], "alerts": [], "weather_today": None})
    yield tmp_path


def test_rules_cite_real_detections_only():
    found = {(f["rule"], f["photo"]) for f in agent.detect_incidents()}
    assert found == {("person_near_machine", "p1"), ("machine_in_restricted_zone", "p3")}
    inc = next(f for f in agent.detect_incidents() if f["rule"] == "person_near_machine")
    assert inc["severity"] == "high" and inc["evidence"] == ["photo:p1", "zone:erd"] and inc["confidence"] == 0.9


def test_scan_is_idempotent_and_reports_new_only():
    assert len(agent.scan()) == 2
    assert agent.scan() == []
    assert len(agent.incidents()) == 2


def test_routing_hands_drafting_to_chat():
    assert agent.run("Bohrpfahl 7: bei 4 m auf Fels gestoßen")["handoff"] == "chat"
    assert agent.run("Betonlieferung um 7:30 angeliefert")["handoff"] == "chat"
    assert "handoff" not in agent.run("Check today's progress and safety")


def test_progress_and_safety_produce_cards_and_twin_actions():
    r = agent.run("Check today's construction progress and tell me if there are any safety issues")
    kinds = [c["kind"] for c in r["cards"]]
    assert {"progress", "incidents", "photos"} <= set(kinds)
    hl = next(a for a in r["actions"] if a["type"] == "twin.highlight")["zones"]
    assert {"id": "erd", "level": "red"} in hl and {"id": "wln", "level": "amber"} in hl
    assert any(a["type"] == "incident.open" for a in r["actions"])
    assert r["lang"] == "en" and "behind plan" in r["speech"]


def test_helmet_question_is_not_guessed():
    r = agent.run("Are there any workers without safety helmets?")
    assert "can't verify helmets" in r["speech"]


def test_verbal_incident_and_follow_up_report_use_context(tmp_path):
    r = agent.run("A dump truck fell into the excavation pit")
    assert r["intents"] == ["reported"] and r["ctx"]["zone"] == "erd"
    inc = agent.incidents()[0]
    assert inc["rule"] == "verbal_report" and inc["evidence"][0].startswith("msg:")
    r2 = agent.run("Generate a report for it", r["ctx"])
    rep = next(a for a in r2["actions"] if a["type"] == "report.generate")
    assert rep == {"type": "report.generate", "scope": "incident", "incident": inc["id"]}
    out = agent.report("incident", inc["id"], lang="en")
    page = (tmp_path / "reports" / out["url"].rsplit("/", 1)[1]).read_text()
    assert "Incident report" in page and "fell into the excavation pit" in page and "AI recommendation, not verified" in page
