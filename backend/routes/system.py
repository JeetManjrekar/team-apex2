import json

from fastapi import APIRouter

from core import docs, llm, llm_bridge
from core.photos import CATEGORIES
from core.store import SITE, env

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/config")
def config():
    return {"categories": CATEGORIES, "site": SITE, "mock_mode": not (env("ROBOFLOW_API_KEY") and env("ROBOFLOW_MODEL")),
            "llm": llm_bridge.status(), "summary_llm": llm.provider(),
            "doc_types": {k: {"title": v["title"], "en": v["en"]} for k, v in docs.DOC_TYPES.items()}}


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/metrics")
def metrics():
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
