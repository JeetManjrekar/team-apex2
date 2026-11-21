from fastapi import APIRouter, UploadFile, File

from core.errors import ApiError

router = APIRouter(prefix="/api", tags=["voice"])


@router.post("/voice")
def voice(audio: UploadFile = File(...)):
    """W2: audio -> core.stt.transcribe -> assistant.handle(voice=True, evidence_meta=...)."""
    raise ApiError(501, "not implemented yet (W2)")
