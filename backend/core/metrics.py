"""Metrics aggregation (W4) over the llm_metrics.jsonl written by llm_bridge / nachweis_llm."""
import json
import statistics

from . import llm_bridge, pricing

EVAL_REPORT = llm_bridge.SETTINGS.metrics_file.parent / "eval" / "report.json"


def _rows() -> list[dict]:
    path = llm_bridge.SETTINGS.metrics_file
    rows = []
    if path.exists():
        for line in path.read_text().splitlines()[-5000:]:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def _ok(r: dict) -> bool:
    return (r.get("extra") or {}).get("ok") is not False


def aggregate() -> dict:
    """Per-stage stats; shape of the former GET /api/metrics kept: {"file", "stages": [...], "recent": [...]}.
    Failed rows (extra.ok == false) are counted in `errors` but excluded from latency, tokens and cost."""
    rows = _rows()
    agg = {}
    for r in rows:
        a = agg.setdefault(r["stage"], {"stage": r["stage"], "count": 0, "errors": 0, "ms": [], "tokens_in": 0, "tokens_out": 0,
                                        "cost_eur": 0.0, "models": set()})
        if not _ok(r):
            a["errors"] += 1
            continue
        a["count"] += 1
        a["ms"].append(r["duration_ms"])
        a["tokens_in"] += r.get("tokens_in", 0)
        a["tokens_out"] += r.get("tokens_out", 0)
        a["cost_eur"] += r.get("cost_eur", 0)
        if r.get("model"):
            a["models"].add(r["model"])
    out = []
    for a in agg.values():
        ms, models = a.pop("ms"), a.pop("models")
        total = a["count"] + a["errors"]
        out.append(dict(a, model=", ".join(sorted(models)) or None, error_rate=round(a["errors"] / total, 3),
                        avg_ms=round(sum(ms) / len(ms), 1) if ms else 0, p50_ms=statistics.median(ms) if ms else 0,
                        max_ms=max(ms) if ms else 0, cost_eur=round(a["cost_eur"], 5)))
    return {"file": str(llm_bridge.SETTINGS.metrics_file), "stages": sorted(out, key=lambda x: x["stage"]), "recent": rows[-20:][::-1]}


def summary() -> dict:
    """Compact numbers for the dashboard tile. Keys are omitted (not faked as 0) when there is no data behind them."""
    rows = [r for r in _rows() if _ok(r)]
    out: dict = {}
    e2e = [r["duration_ms"] for r in rows if r["stage"] == "voice_to_draft_end_to_end"]
    if e2e:
        out["e2e_voice_to_draft_p50_ms"] = statistics.median(e2e)
    per_run: dict[str, float] = {}
    for r in rows:
        if r.get("run_id") not in ("host", "chat", "stt", None) and r.get("cost_eur"):
            per_run[r["run_id"]] = per_run.get(r["run_id"], 0) + r["cost_eur"]
    if per_run:
        out["cost_per_document_eur"] = round(sum(per_run.values()) / len(per_run), 5)
    if per_run:
        out["pricing"] = pricing.info()
    try:
        rep = json.loads(EVAL_REPORT.read_text())
        if isinstance(rep.get("accuracy"), (int, float)):
            out["extraction_accuracy"] = rep["accuracy"]
    except Exception:
        pass
    return out
