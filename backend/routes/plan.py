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
    return summarize.samples()


@router.post("/demo/load")
def demo_load():
    plan.load_demo()
    return {"ok": True}


@router.post("/demo/full")
def demo_full():
    """Clean slate + project, schedule, site documents -> layout, geotagged photos with stored detections, incidents."""
    from core import demo
    return demo.load_full()


@router.post("/demo/reset")
def demo_reset():
    """Resets everything (chat, documents, notes, photos, schedule, site layout, uploads) to the empty fresh-start state."""
    from core import demo
    return demo.reset()


# ---------------------------------------------------------------- Geld & Zeit (core/cost_model.py, internal estimates only)
@router.get("/costs")
def costs():
    """All four money metrics, the top-3 ranking and the summary numbers. Labelled "Schätzung, intern"."""
    from core import cost_model
    return cost_model.summary()


@router.get("/costs/config")
def costs_config():
    from core import cost_model
    return cost_model.settings()


@router.post("/costs/decide")
def costs_decide(body: dict = Body(...)):
    """Human decision on a proposal (e.g. {"key": "idle:<doc>", "accepted": true}); nothing happens automatically."""
    from core import cost_model
    key = str(body.get("key") or "")
    if not key.startswith(("idle:", "nachtrag:", "delay:")):
        raise ApiError(400, "unknown key")
    return cost_model.decide(key, bool(body.get("accepted")))


@router.post("/costs/outcome")
def costs_outcome(body: dict = Body(...)):
    """Calibration hook: the real amount once known (approved Nachtrag, actual repair, actual milestone date)."""
    from core import cost_model
    try:
        return cost_model.record_outcome(str(body["key"]), float(body["actual_eur"]), str(body.get("note") or ""))
    except (KeyError, ValueError, TypeError):
        raise ApiError(400, "key and actual_eur required")


@router.get("/costs/calibration")
def costs_calibration():
    from core import cost_model
    return cost_model.calibration()
