"""Acceptance checks for the cost model (COST_MODEL.md §8). No network: weather and the demo day are fixed here."""
import datetime as dt

import pytest
from docx import Document

from core import cost_model as cm
from core import docs, export, store

FROST = {f"2026-11-{d:02d}": -2.0 for d in range(10, 31)} | {f"2026-12-{d:02d}": -2.0 for d in range(1, 11)}


@pytest.fixture
def site(tmp_path, monkeypatch):
    from core import plan
    real_demo = store.DATA / "demo"                    # read-only demo sources (drilling list, schedule)
    monkeypatch.setattr(plan, "DEMO_DIR", real_demo)
    (tmp_path / "uploads").mkdir()
    for m in (store, export):
        monkeypatch.setattr(m, "DATA", tmp_path, raising=False)
    monkeypatch.setattr(cm, "_today", lambda: dt.date(2026, 11, 17))
    monkeypatch.setattr(cm, "weather", lambda: dict(FROST))
    monkeypatch.setattr(plan, "weather", lambda: None)
    for k in list(cm._DEFAULTS):
        monkeypatch.delenv(k, raising=False)
    plan.load_demo()                                   # schedule + progress from the demo drilling list
    return tmp_path


def _doc(dtype, values):
    d = docs.create(dtype)
    for k, v in values.items():
        if k in d["fields"]:
            docs.set_field(d, k, v, {"type": "message", "evidence_id": "msg:t1", "quote": v}, by="ai", confidence=0.9)
    docs.put(d)
    return d


def _ok(xs):
    return [x for x in xs if x["status"] == "ok"]


# 1 ---------------------------------------------------------------- Nachtrag exposure, pile 7
def test_pile7_measured_and_predicted(site):
    p7 = next(x for x in cm.nachtrag_exposure() if x.get("pile") == "P07")
    # by hand: P07 4.583 h (06:45 -> Stand 11:20) for 4.6 m; reference P01-P06 = 0.3333 h/m -> 1.533 h; extra 3.05 h
    assert p7["extra_hours"] == pytest.approx(3.05, abs=0.01)
    assert p7["rate_eur_h"] == 420 + 3 * 58
    assert p7["measured_eur"] == 1812
    # rock from 4 m: (4.583 - 4 x 0.3333) / 0.6 = 5.417 h/m; 7.4 m remaining
    assert p7["expected_eur"] == 24156 and p7["low_eur"] == 1812 and p7["high_eur"] == 28918
    assert p7["low_eur"] <= p7["expected_eur"] <= p7["high_eur"]
    assert p7["band"] == "medium" and p7["band_label"] == "mittel"
    assert "drill:P07" in p7["sources"] and "drill:P01" in p7["sources"]


# 2 ---------------------------------------------------------------- idle cost and reassignment
def test_breakdown_idle_cost_and_avoided(site):
    _doc("behinderungsanzeige", {"occurred_at": "17.11.2026, 10:00", "cause": "Hydraulikschaden Bagger, 4 Mann warten",
                                 "location": "Widerlager 1", "expected_duration": "2 Tage"})
    (x,) = _ok(cm.idle_cost())
    assert x["crew"] == 4 and x["repair_days"] == 2 and x["idle_hours"] == 18
    assert x["expected_eur"] == 18 * 150 + 4 * 18 * 58
    assert x["avoided_eur"] > 0 and x["with_reassignment_eur"] < x["expected_eur"]
    assert x["action"] == "Umsetzung annehmen" and x["accepted"] is False
    cm.decide(x["key"], True)
    assert _ok(cm.idle_cost())[0]["accepted"] is True


def test_breakdown_without_duration_uses_default_and_says_so(site):
    _doc("behinderungsanzeige", {"occurred_at": "17.11.2026, 10:00", "cause": "Bagger ausgefallen", "location": "Achse 2"})
    (x,) = _ok(cm.idle_cost())
    assert x["repair_days"] == 1 and any("Reparaturdauer ohne Angabe" in a for a in x["assumptions"])


# 3 ---------------------------------------------------------------- delay risk
def test_delay_widerlager1_and_frost_sensitivity(site, monkeypatch):
    w1 = next(x for x in _ok(cm.delay_risk()) if x["milestone"] == "W1_FERTIG")
    assert w1["slip_days"]["exp"] > 0 and w1["expected_eur"] > 0
    monkeypatch.setenv("COST_FROST_P_BELOW_0", "0.2")
    w1b = next(x for x in _ok(cm.delay_risk()) if x["milestone"] == "W1_FERTIG")
    assert w1b["expected_eur"] < w1["expected_eur"]


# 4 ---------------------------------------------------------------- every result explains itself
def test_every_result_is_labelled_explained_and_sourced(site):
    _doc("behinderungsanzeige", {"occurred_at": "10:00", "cause": "Bagger steht, Hydraulik", "expected_duration": "1 Tag"})
    s = cm.summary()
    results = [x for xs in s["items"].values() for x in xs if x["status"] == "ok"]
    assert results
    for x in results:
        assert x["label"] == "Schätzung, intern"
        assert len(x["explanation"]) > 20 and "€" in x["explanation"]
        assert x["sources"] and x["assumptions"]
        assert x["low_eur"] <= x["expected_eur"] <= x["high_eur"]


# 5 ---------------------------------------------------------------- export guard: no money in outgoing documents
@pytest.mark.parametrize("dtype,values", [
    ("nachtragsmeldung", {"location": "Widerlager 1, Pfahl 7", "description": "Fels bei 4 m", "found_ground": "Fels"}),
    ("behinderungsanzeige", {"occurred_at": "17.11.2026, 10:00", "cause": "Hydraulikschaden Bagger", "expected_duration": "2 Tage"}),
    ("bautagesbericht", {"date": "2026-11-17", "work_done": "Bohrpfähle W1"}),
])
def test_no_euro_in_exports(site, dtype, values):
    d = _doc(dtype, values)
    cm.summary()                                       # the cost model has run and stored its estimates
    w = Document(str(export.docx(docs.get(d["id"]))))
    text = "\n".join([p.text for p in w.paragraphs] + [c.text for t in w.tables for r in t.rows for c in r.cells]
                     + [p.text for s in w.sections for p in s.header.paragraphs + s.footer.paragraphs])
    html = export.print_html(docs.get(d["id"]))
    for out in (text, html):
        assert "€" not in out and "EUR" not in out and "Euro" not in out


# 6 ---------------------------------------------------------------- missing input -> no number
def test_missing_input_gives_no_number(site):
    rows = [r for r in cm.drilling_rows()]
    for r in rows:
        if r["pile"] == "P07":
            r["crew"] = None
    p7 = next(x for x in cm.nachtrag_exposure(rows=rows) if x.get("key") == "nachtrag:P07")
    assert p7["status"] == "no_data" and p7["status_text"] == "nicht genug Daten" and p7["expected_eur"] is None and p7["reason"]
    no_ref = [r for r in cm.drilling_rows() if not r["done"]]
    assert all(x["status"] == "no_data" for x in cm.nachtrag_exposure(rows=no_ref))


# 7 ---------------------------------------------------------------- rates scale the result
def test_rate_change_is_proportional(site, monkeypatch):
    a = next(x for x in cm.nachtrag_exposure() if x.get("pile") == "P07")
    monkeypatch.setenv("COST_RIG_EUR_H", "840")
    monkeypatch.setenv("COST_CREW_EUR_H", "116")
    b = next(x for x in cm.nachtrag_exposure() if x.get("pile") == "P07")
    assert b["measured_eur"] == pytest.approx(2 * a["measured_eur"], abs=1)
    assert b["expected_eur"] == pytest.approx(2 * a["expected_eur"], abs=2)
    assert "gesetzt in der Konfiguration" in cm.settings()["COST_RIG_EUR_H"]["source"]


# 8 ---------------------------------------------------------------- summary has real numbers
def test_summary_after_demo_and_one_document(site):
    _doc("nachtragsmeldung", {"location": "Widerlager 1, Pfahl 7", "description": "Pfahl 7: ab 4 m Fels"})
    s = cm.summary()
    assert s["nachtrag_documented"]["expected_eur"] > 0 and s["nachtrag_documented"]["count"] == 1
    assert s["delay_open"] and s["delay_open"]["expected_eur"] > 0
    assert s["documentation"]["docs"] == 1 and s["documentation"]["manual_min"] == 90
    assert s["top"] and s["top"][0]["expected_eur"] >= s["top"][-1]["expected_eur"]
    assert s["footer"].startswith("Schätzung, intern")
    assert store.load("cost_estimates", {})            # calibration hook: estimates stored with their inputs


def test_calibration_reports_error(site):
    cm.summary()
    cm.record_outcome("nachtrag:P07", 20000)
    c = cm.calibration()
    assert c["pairs"] and c["pairs"][0]["key"] == "nachtrag:P07" and c["mean_abs_error_pct"] is not None


def test_english_by_language(site):
    from core.i18n import set_lang
    set_lang("en")
    p7 = next(x for x in cm.nachtrag_exposure() if x.get("pile") == "P07")
    assert p7["label"] == "Estimate, internal" and p7["band_label"] == "medium"
    assert "extra hours" in p7["explanation"] and "1,812 €" in p7["explanation"] and "Mehrstunden" not in p7["explanation"]
    assert p7["title"].startswith("Change order")
