from fastapi import APIRouter

from core import metrics

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("")
def metrics_all():
    return metrics.aggregate()


@router.get("/summary")
def metrics_summary():
    return metrics.summary()
