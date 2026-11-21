"""Deterministic crew replanner (W4). Rules choose candidates; the LLM only phrases them (llm_bridge.phrase_replan).
Proposals are never applied automatically: a human accepts or rejects (data/replan.json)."""


def actions_for(doc: dict) -> list:
    """Chat actions (proposal cards) triggered by a newly created doc, e.g. a Behinderungsanzeige. Stub: no actions."""
    return []


def accepted_for(day: str) -> list:
    """Accepted reassignments for an ISO day, for the Bautagesbericht. Stub: none."""
    return []


def get_proposals() -> list:
    """All replan proposals (open + decided)."""
    return []


def decide(proposal_id: str, accept: bool) -> dict:
    """Accept or reject a proposal; nothing is moved automatically."""
    raise NotImplementedError("W4: implement core/replanner.decide")
