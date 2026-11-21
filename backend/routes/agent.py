from fastapi import APIRouter, Body

from core import agent
from core.errors import ApiError

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/greeting")
def greeting(lang: str = "en"):
    return agent.greeting(lang)


@router.post("")
def command(body: dict = Body(...)):
    text = (body.get("text") or "").strip()
    if not text:
        raise ApiError(400, "text is required")
    return agent.run(text, body.get("ctx") or {}, body.get("lang"))


@router.get("/events")
def events(since: str | None = None):
    return {"incidents": agent.events(since), "now": agent.now()}


@router.get("/incidents")
def incidents(all: bool = False):
    agent.scan()
    return agent.incidents(open_only=not all)


@router.post("/incidents/{iid}/status")
def incident_status(iid: str, body: dict = Body(...)):
    if body.get("status") not in ("open", "resolved", "dismissed"):
        raise ApiError(400, "status must be open, resolved or dismissed")
    row = agent.set_status(iid, body["status"])
    if not row:
        raise ApiError(404, "incident not found")
    return row


@router.post("/report")
def report(body: dict = Body(default={})):
    return agent.report(body.get("scope") or "site", body.get("incident"), body.get("snapshot"), body.get("lang") or "en", body.get("note"),
                        body.get("plan_snapshot"))
