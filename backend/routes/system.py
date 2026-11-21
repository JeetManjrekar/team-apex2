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


@router.post("/system/reset")
def system_reset(body: dict | None = None):
    """Reset all runtime state to empty (core/demo.reset). Body: {"keep_metrics": true}."""
    from core import demo
    return demo.reset(keep_metrics=(body or {}).get("keep_metrics", True))
