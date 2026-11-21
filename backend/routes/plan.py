from fastapi import APIRouter, Body

from core import assistant, docs, plan, summarize
from core.errors import ApiError
from core.store import save

router = APIRouter(prefix="/api", tags=["plan & summaries"])


@router.get("/plan")
def get_plan(as_of: str | None = None):
    return plan.status(as_of)


@router.post("/progress")
def progress(body: dict = Body(...)):
    try:
        plan.add_progress(body["date"], body["activity"], body["qty"], body.get("note", ""))
    except KeyError as e:
        raise ApiError(400, f"missing field {e}")
    return plan.status()


@router.post("/plan/propose")
def propose(body: dict = Body(...)):
    try:
        return docs.public(assistant.propose_from_alert(body))
    except ValueError as e:
        raise ApiError(400, str(e))


@router.post("/summarize")
def summarize_ep(body: dict = Body(...)):
    return summarize.summarize(body.get("text", ""))


@router.get("/demo/samples")
def samples():
    return {"minutes": summarize.SAMPLE_MINUTES, "email": summarize.SAMPLE_EMAIL}


@router.post("/demo/load")
def demo_load():
    plan.load_demo()
    return {"ok": True}


@router.post("/demo/reset")
def demo_reset():
    """Resets everything (chat, documents, notes, photos, schedule, site layout, uploads) to the empty fresh-start state."""
    from core import demo
    return demo.reset()
