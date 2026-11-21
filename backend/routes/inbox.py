from typing import List

from fastapi import APIRouter, UploadFile, File

from core.errors import ApiError

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


@router.post("/import")
def import_inbox(files: List[UploadFile] = File(...)):
    """W1: .eml / .ics files -> core.outlook.import_files."""
    raise ApiError(501, "not implemented yet (W1)")
