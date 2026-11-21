from typing import List, Optional

from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel

from core import outlook
from core.errors import ApiError

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


@router.post("/import")
def import_inbox(files: List[UploadFile] = File(...)):
    """Import one or more Outlook .eml / .ics files.

    .eml -> mail- evidence, proposals on matching open drafts (or a new draft); .ics -> cal- reminders + chat notifications.
    Response: {created, drafts (with links), reminders, emails, notifications, skipped}.
    """
    named = [(f.filename or "", f.file.read(outlook.MAX_BYTES + 1)) for f in files]
    if not any(name for name, _ in named):
        raise ApiError(400, "no files uploaded")
    return outlook.import_files(named)


class SyncBody(BaseModel):
    ics_url: Optional[str] = None
    include_samples: bool = True


@router.post("/sync")
def sync_inbox(body: Optional[SyncBody] = None):
    """User-initiated one-click sync. Reads backend/data/inbox_samples/*.eml|*.ics (include_samples) and, only if given
    (ics_url or ICS_FEED_URL), one read-only iCal feed. Same pipeline and response as /import, plus `sources_synced`."""
    body = body or SyncBody()
    try:
        return outlook.sync(body.ics_url, body.include_samples)
    except outlook.SyncError as e:
        raise ApiError(e.status, e.detail)
