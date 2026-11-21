import json
from pathlib import Path

from core import demo, site_twin, store

SEED = Path(__file__).resolve().parent.parent / "data" / "seed"


def test_fresh_start_is_empty_and_reads_do_not_write(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path); monkeypatch.setattr(store, "UPLOADS", tmp_path / "uploads")
    lay = site_twin.get_layout()
    assert lay["boundary"] == lay["zones"] == lay["roads"] == lay["gates"] == lay["structures"] == [] and lay["origin"] is None
    site_twin.normalise(lay)
    assert not (tmp_path / "site_layout.json").exists()


def test_reset_leaves_layout_empty(tmp_path, monkeypatch):
    for m in (store, demo):
        monkeypatch.setattr(m, "DATA", tmp_path); monkeypatch.setattr(m, "UPLOADS", tmp_path / "uploads")
    monkeypatch.setattr(site_twin, "DATA", tmp_path, raising=False)
    store.save("site_layout", json.loads((SEED / "site_layout.json").read_text()))
    assert site_twin.get_layout()["structures"]
    demo.reset()
    assert not (tmp_path / "site_layout.json").exists()
    assert site_twin.get_layout()["structures"] == []


def test_seed_layout_fixture_is_valid():
    assert site_twin.normalise(json.loads((SEED / "site_layout.json").read_text()))["zones"]


def test_no_project_references_when_blank(tmp_path, monkeypatch):
    from core import agent, sources, plan
    for m in (store, demo):
        monkeypatch.setattr(m, "DATA", tmp_path); monkeypatch.setattr(m, "UPLOADS", tmp_path / "uploads")
    monkeypatch.setattr(plan, "DATA", tmp_path); monkeypatch.setattr(agent, "DATA", tmp_path)
    assert store.SITE["name"] == "" and sources.project() == {} and sources.context_chunks(__import__("datetime").date.today()) == []
    assert "Straßenbrücke" not in agent.greeting("de")["text"] and "BW 12" not in agent.greeting("en")["text"]
    plan.load_demo()
    assert "Straßenbrücke" in store.SITE["name"]
    demo.reset()
    assert store.SITE["name"] == "" and sources.project() == {}
