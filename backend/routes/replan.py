from fastapi import APIRouter

from core import replanner

router = APIRouter(prefix="/api/replan", tags=["replan"])


@router.get("/proposals")
def proposals():
    return {"proposals": replanner.get_proposals()}


@router.post("/{proposal_id}/accept")
def accept(proposal_id: str):
    return replanner.decide(proposal_id, True)


@router.post("/{proposal_id}/reject")
def reject(proposal_id: str):
    return replanner.decide(proposal_id, False)
