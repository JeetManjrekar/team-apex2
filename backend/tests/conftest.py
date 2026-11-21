import pytest

from core import i18n


@pytest.fixture(autouse=True)
def _german_by_default():
    """Existing tests assert German text; language tests set it explicitly (i18n.set_lang)."""
    i18n.set_lang("de")
    yield
    i18n.set_lang("de")


@pytest.fixture(autouse=True)
def _metrics_to_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("LIVE_PRICING", "off")      # tests never touch the network
    """Never let tests append rows to the real data/llm_metrics.jsonl (it feeds the dashboard)."""
    from core import llm_bridge
    monkeypatch.setattr(llm_bridge.METRICS, "_path", tmp_path / "llm_metrics.jsonl")
