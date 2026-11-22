"""The Real Time Preview / "Load demo data" loads the demo in the request language: English duplicates (*_en files next to
the German originals) for en, the untouched German files for de. No network: weather and the demo day are fixed."""
import datetime as dt
from pathlib import Path

import pytest

from core import cost_model as cm
from core import demo, layout_suggest, photos, plan, site_twin, store, summarize
from core.i18n import set_lang

REPO = Path(__file__).resolve().parents[2]
DEMO = store.DATA / "demo"


@pytest.fixture
def site(tmp_path, monkeypatch):
    (tmp_path / "uploads").mkdir()
    for m in (store, site_twin, demo):
        monkeypatch.setattr(m, "DATA", tmp_path, raising=False)
    for m in (store, photos, demo):
        monkeypatch.setattr(m, "UPLOADS", tmp_path / "uploads", raising=False)
    monkeypatch.setattr(plan, "DEMO_DIR", DEMO)
    monkeypatch.setattr(demo, "ROOT", REPO, raising=False)
    monkeypatch.setattr(plan, "weather", lambda: None)
    monkeypatch.setattr(cm, "weather", lambda: {})
    monkeypatch.setattr(cm, "_today", lambda: dt.date(2026, 11, 17))
    # demo.load_full reads the seed photo list from DATA/seed: point it at the real one
    (tmp_path / "seed").mkdir()
    (tmp_path / "seed" / "photos.json").write_text((DEMO.parent / "seed" / "photos.json").read_text(encoding="utf-8"), encoding="utf-8")
    from core import llm_bridge
    monkeypatch.setattr(llm_bridge, "classify_photo", lambda *a, **k: None)
    return tmp_path


def _zone_names():
    return sorted(z["name"] for z in site_twin.get_layout()["zones"])


def test_english_demo(site):
    set_lang("en")
    demo.load_full()
    assert store.SITE["name"] == "Replacement road bridge BW 12 over the Mühlbach"
    assert _zone_names() == ["Abutment 1", "Abutment 2", "Axis 1", "Axis 2", "Site facilities"]
    names = {a["id"]: a["name"] for a in store.load("schedule", [])}
    assert names["W1_BP"] == "Bored piles Abutment 1 (8 × 12 m)" and names["A1_BET"] == "Concreting Axis 1"
    assert any("rock from 4 m (as of 11:20)" in p["note"] for p in store.load("progress", []))
    assert store.load("client_docs", [])[0]["locator"].startswith("Geotechnical report BW 12")
    assert summarize.samples()["email"].startswith("From:") and "Monday, 23.11.2026" in summarize.samples()["email"]


def test_german_demo_unchanged(site):
    set_lang("de")
    demo.load_full()
    assert store.SITE["name"] == "Ersatzneubau Straßenbrücke BW 12 über den Mühlbach"
    assert _zone_names() == ["Achse 1", "Achse 2", "Baustelleneinrichtung", "Widerlager 1", "Widerlager 2"]
    names = {a["id"]: a["name"] for a in store.load("schedule", [])}
    assert names["W1_BP"] == "Bohrpfähle Widerlager 1 (8 × 12 m)"
    assert any("ab 4 m Fels (Stand 11:20)" in p["note"] for p in store.load("progress", []))
    assert summarize.samples()["email"] == summarize.SAMPLE_EMAIL


def test_cost_numbers_identical_in_both_languages(site):
    out = {}
    for lang in ("de", "en"):
        set_lang(lang)
        p7 = next(x for x in cm.nachtrag_exposure() if x.get("pile") == "P07")
        out[lang] = (p7["measured_eur"], p7["expected_eur"], p7["low_eur"], p7["high_eur"])
    assert out["de"] == out["en"] == (1812, 24156, 1812, 28918)


def test_english_summary_sample_finds_open_items(site):
    set_lang("en")
    en = summarize.rules(summarize.samples()["minutes"])
    de = summarize.rules(summarize.SAMPLE_MINUTES)
    assert len(en["open_items"]) == len(de["open_items"]) and len(en["decisions"]) == len(de["decisions"])
    assert sum(1 for i in en["open_items"] if i["owner"] and i["deadline"]) == 4


def test_every_loaded_german_file_has_an_english_partner():
    german = [DEMO / "project.json", DEMO / "schedule" / "bauzeitenplan.csv", DEMO / "schedule" / "bauzeitenplan.xlsx",
              DEMO / "drilling" / "drilling_times.csv", DEMO / "source_documents" / "baugrundgutachten_auszug.md",
              DEMO / "source_documents" / "baugrundgutachten_auszug.pdf", DEMO / "site_plan" / "zones.json"]
    german += [REPO / "site_documents" / "upload" / n for n in demo.LAYOUT_FILES]
    for g in german:
        assert g.with_name(g.stem + "_en" + g.suffix).exists(), g
    assert (DEMO / "samples" / "sample_email_en.txt").exists() and (DEMO / "samples" / "sample_minutes_en.md").exists()
