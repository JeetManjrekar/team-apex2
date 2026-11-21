import dataclasses, json

import pytest

from core import llm_bridge, pricing
from core.llm_adapter import Usage


class _Resp:
    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d


def _fake_get(url, **kw):
    if "frankfurter" in url:
        return _Resp({"rates": {"EUR": 0.5}})
    return _Resp({"data": [{"id": "openai/gpt-oss-120b", "pricing": {"prompt": "0.0000002", "completion": "0.0000004"}},
                           {"id": "bad/model", "pricing": {"prompt": "x"}}]})


def _reset(monkeypatch, tmp_path):
    monkeypatch.setattr(pricing, "DATA", tmp_path)
    monkeypatch.setattr(pricing, "_state", {"rates": None, "fetched_at": 0.0, "busy": False})
    monkeypatch.setenv("LIVE_PRICING", "on")


def test_fetch_converts_usd_to_eur_per_million(monkeypatch, tmp_path):
    _reset(monkeypatch, tmp_path)
    monkeypatch.setattr(pricing.requests, "get", _fake_get)
    pricing._refresh()
    assert pricing.rates("openai/gpt-oss-120b") == pytest.approx((0.1, 0.2))      # 0.2 USD/1M * 0.5
    assert pricing.rates("gpt-oss-120b") == pytest.approx((0.1, 0.2))             # provider prefix added
    assert pricing.rates("bad/model") is None and pricing.rates("nope") is None
    assert json.loads((tmp_path / "pricing_cache.json").read_text())["rates"]


def test_network_failure_never_raises_and_disk_cache_is_used(monkeypatch, tmp_path):
    _reset(monkeypatch, tmp_path)
    monkeypatch.setattr(pricing.requests, "get", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    pricing._refresh()
    assert pricing._state["busy"] is False
    (tmp_path / "pricing_cache.json").write_text(json.dumps({"fetched_at": 9e12, "rates": {"m/x": [1.0, 2.0]}}))
    assert pricing.rates("m/x") == (1.0, 2.0)


def test_timed_uses_live_price_unless_env_override(monkeypatch, tmp_path):
    monkeypatch.setattr(llm_bridge.METRICS, "_path", tmp_path / "m.jsonl")
    monkeypatch.setattr(pricing, "rates", lambda m: (1.0, 2.0))
    u = Usage(input=1_000_000, output=500_000, model="m/x")
    with llm_bridge.timed("s", model="m/x") as t:
        t.add_usage(u)
    row = json.loads((tmp_path / "m.jsonl").read_text().splitlines()[-1])
    assert row["cost_eur"] == 2.0 and row["extra"]["price_src"] == "live"
    env = dataclasses.replace(llm_bridge.SETTINGS, input_cost_eur_per_1m=3.0)
    monkeypatch.setattr(llm_bridge, "SETTINGS", env)
    monkeypatch.setattr(llm_bridge.METRICS, "_settings", env)
    with llm_bridge.timed("s", model="m/x") as t:
        t.add_usage(u)
    row = json.loads((tmp_path / "m.jsonl").read_text().splitlines()[-1])
    assert row["cost_eur"] == 3.0 and "price_src" not in row.get("extra", {})
