from fastapi import APIRouter, Body

from core import site_twin
from core.errors import ApiError

router = APIRouter(prefix="/api/site", tags=["site twin"])


@router.get("/twin")
def twin():
    try:
        return site_twin.twin()
    except ValueError as e:
        raise ApiError(400, f"site layout invalid: {e}")


@router.get("/layout")
def get_layout():
    return site_twin.get_layout()


@router.put("/layout")
def put_layout(body: dict = Body(...)):
    try:
        return site_twin.save_layout(body)
    except (ValueError, KeyError, TypeError, IndexError) as e:
        raise ApiError(400, f"site layout invalid: {e}")


@router.post("/layout/reset")
def reset_layout():
    return site_twin.save_layout(site_twin.default_layout())
