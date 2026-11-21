from typing import List, Optional

from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel

from core import layout_suggest, outlook
from core.errors import ApiError

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


GEO_ONLY = ("geojson", "json")                 # site plans / reference points: layout store only, not the document inbox
GEO_TOO = ("pdf", "docx", "xlsx", "csv")       # office documents: inbox AND scanned for coordinates


def _ext(name):
    return name.lower().rsplit(".", 1)[-1] if "." in name else ""


@router.post("/import")
def import_inbox(files: List[UploadFile] = File(...)):
    """Import Outlook .eml / .ics files, client documents (.pdf .docx .xlsx .csv) and site plans (.geojson .json).

    .eml -> mail- evidence, proposals on matching open drafts (or a new draft); .ics -> cal- reminders + chat notifications;
    documents/tables -> cited proposals (PDF page, sheet/row) on matching open drafts only.
    Documents, tables and GeoJSON are also scanned for coordinates (site layout sources, see /api/site/sources).
    Response: {created, drafts (with links), reminders, emails, documents, notifications, skipped, site}.
    """
    named = [(f.filename or "", f.file.read(outlook.MAX_BYTES + 1)) for f in files]
    if not any(name for name, _ in named):
        raise ApiError(400, "no files uploaded")
    inbox = [(n, r) for n, r in named if _ext(n) not in GEO_ONLY]
    out = outlook.import_files(inbox) if inbox else {"created": [], "drafts": [], "reminders": [], "emails": [], "documents": [],
                                                     "notifications": [], "skipped": []}
    geo_files = [(n, r) for n, r in named if _ext(n) in GEO_ONLY + GEO_TOO and len(r) <= outlook.MAX_BYTES]
    added = layout_suggest.add_sources([(n, r) for n, r in geo_files if _ext(n) in GEO_TOO], keep_empty=False) if geo_files else None
    plans = layout_suggest.add_sources([(n, r) for n, r in geo_files if _ext(n) in GEO_ONLY]) if any(_ext(n) in GEO_ONLY for n, _ in geo_files) else None
    for res in (added, plans):
        if res:
            out["skipped"] += res["skipped"]
    out["site"] = {**layout_suggest.summary(),
                   "new_files": [a["file"] for res in (added, plans) if res for a in res["added"] if a["points"] or a["meta"]],
                   "known_files": [d for res in (added, plans) if res for d in res["duplicates"]]}
    return out


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
