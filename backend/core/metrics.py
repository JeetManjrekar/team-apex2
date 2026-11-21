"""Metrics aggregation (W4) over the llm_metrics.jsonl written by llm_bridge / nachweis_llm."""
import json

from . import llm_bridge


def aggregate() -> dict:
    """Per-stage stats; shape of the former GET /api/metrics kept: {"file", "stages": [...], "recent": [...]}."""
    path = llm_bridge.SETTINGS.metrics_file
    rows = []
    if path.exists():
        for line in path.read_text().splitlines()[-5000:]:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    agg = {}
    for r in rows:
        a = agg.setdefault(r["stage"], {"stage": r["stage"], "count": 0, "ms": [], "tokens_in": 0, "tokens_out": 0, "cost_eur": 0.0, "model": r.get("model")})
        a["count"] += 1
        a["ms"].append(r["duration_ms"])
        a["tokens_in"] += r.get("tokens_in", 0)
        a["tokens_out"] += r.get("tokens_out", 0)
        a["cost_eur"] += r.get("cost_eur", 0)
    out = []
    for a in agg.values():
        ms = sorted(a.pop("ms"))
        out.append(dict(a, avg_ms=round(sum(ms) / len(ms), 1), p50_ms=ms[len(ms) // 2], max_ms=max(ms), cost_eur=round(a["cost_eur"], 5)))
    return {"file": str(path), "stages": sorted(out, key=lambda x: x["stage"]), "recent": rows[-20:][::-1]}


def summary() -> dict:
    """Compact numbers for the dashboard tile (e2e, cost per document, accuracy, honesty). Stub: empty."""
    return {}
