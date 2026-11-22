"""Claim potential: location -> plan position, estimate normalisation, debounced background store. No network."""
import json
import time
from pathlib import Path

import pytest

from core import claim_potential as cp, docs, llm_adapter, site_twin, store
from core.llm_settings import CFG

SEED = Path(__file__).resolve().parents[1] / "data" / "seed"
LAYOUT = site_twin.normalise(json.loads((SEED / "site_layout.json").read_text()))
SQUARE = [[0, 0], [10, 0], [10, 10], [0, 10]]


def test_resolve_pile_in_pile_row():
    xy, how = site_twin.resolve_location("Bohrpfahl 7", LAYOUT)
    assert how == "pile" and xy == pytest.approx([19.29, 0.0], abs=0.01)   # 7th of 8 piles from -27 to 27


def test_resolve_marker_zone_photo_and_nothing():
    lay = {"structures": [{"id": "bp7", "kind": "marker", "name": "BP 07", "x": 5, "y": 6}],
           "zones": [{"id": "p01", "name": "Pfeiler 1", "polygon": SQUARE}]}
    assert site_twin.resolve_location("Bohrpfahl 7", lay) == ([5, 6], "structure")
    assert site_twin.resolve_location("Pfeiler 1, Nordseite", lay) == ([5.0, 5.0], "zone")
    assert site_twin.resolve_location("Pier 3", lay, [[1, 1], [3, 3]]) == ([2.0, 2.0], "photo")
    assert site_twin.resolve_location("Pier 3", lay) == (None, None)
    assert site_twin.resolve_location("Bohrpfahl 7", site_twin.empty_layout()) == (None, None)


def test_claim_spots_need_an_amount():
    d = {"id": "a", "type": "nachtragsmeldung", "status": "draft", "title": "N", "photos": [],
         "fields": {"location": {"value": "Bohrpfahl 7"}}}
    assert site_twin.claim_spots(LAYOUT, [d], []) == []
    d["claim_potential"] = {"amount_eur": 12400}
    [s] = site_twin.claim_spots(LAYOUT, [d], [])
    assert s["amount_eur"] == 12400 and s["matched_by"] == "pile" and s["status"] == "draft"


@pytest.fixture
def tmpdata(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    monkeypatch.setattr(cp, "DEBOUNCE_S", 0.05)
    new = {"claim_model": "qwen3-14b", "claim_base_url": "http://x/v1"}    # CFG is a frozen dataclass
    old = {k: getattr(CFG, k) for k in new}
    for k, v in new.items():
        object.__setattr__(CFG, k, v)
    yield tmp_path
    for k, v in old.items():
        object.__setattr__(CFG, k, v)


def _wait(pred, t=3.0):
    end = time.time() + t
    while time.time() < end and not pred():
        time.sleep(0.02)
    return pred()


def test_estimate_stored_in_background_and_not_repeated(tmpdata, monkeypatch):
    calls = []

    def fake(prompt, schema, model, **kw):
        calls.append(kw["provider"])
        assert "Bohrpfahl 7" in prompt and "/no_think" in kw["system"]
        return schema(amount_eur=12400.4, low_eur=20000, high_eur=9000, confidence=0.6, rationale_de="ok", basis=["5 m × 2480 €"]), None
    monkeypatch.setattr(llm_adapter, "complete_json", fake)
    d = docs.create("nachtragsmeldung", origin="manual")
    docs.set_field(d, "location", "Bohrpfahl 7", by="user")
    docs.put(d)
    assert _wait(lambda: (docs.get(d["id"]).get("claim_potential") or {}).get("amount_eur"))
    got = docs.get(d["id"])["claim_potential"]
    assert (got["amount_eur"], got["low_eur"], got["high_eur"]) == (12400, 12400, 12400) and calls == ["qwen"]
    docs.put(d)                                    # stale copy without the estimate: kept, and no new call
    time.sleep(0.2)
    assert docs.get(d["id"])["claim_potential"]["amount_eur"] == 12400 and calls == ["qwen"]


def test_model_failure_stores_nothing(tmpdata, monkeypatch):
    def boom(*a, **k):
        raise llm_adapter.LLMError("connection refused")
    monkeypatch.setattr(llm_adapter, "complete_json", boom)
    d = docs.create("mehrkostenanzeige", origin="manual")
    docs.set_field(d, "cause", "Fels statt Kies", by="user")
    docs.put(d)
    time.sleep(0.3)
    assert "claim_potential" not in docs.get(d["id"])
