from typing import List

from fastapi import APIRouter, Body, File, UploadFile

from core import layout_suggest, site_twin
from core.errors import ApiError

router = APIRouter(prefix="/api/site", tags=["site twin"])
MAX_SOURCE_BYTES = 20 * 1024 * 1024


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


# ---- layout suggestion from accumulated site documents + photo GPS
@router.get("/sources")
def list_sources():
    """Accumulated site documents and the coordinates read from them."""
    return {"files": [{k: s[k] for k in ("file", "hash", "added_at", "points", "skipped", "meta", "activities")} for s in layout_suggest.sources()]}


@router.post("/sources")
def add_sources(files: List[UploadFile] = File(...)):
    """Upload csv / xlsx / docx / pdf / geojson / json files with coordinates. Re-uploading the same file is a no-op."""
    named = []
    for f in files:
        raw = f.file.read(MAX_SOURCE_BYTES + 1)
        if len(raw) > MAX_SOURCE_BYTES:
            raise ApiError(413, f"{f.filename}: larger than {MAX_SOURCE_BYTES // (1024 * 1024)} MB")
        named.append((f.filename or "upload", raw))
    if not named:
        raise ApiError(400, "no files uploaded")
    return layout_suggest.add_sources(named)


@router.delete("/sources")
def clear_sources():
    layout_suggest.clear_sources()
    return {"ok": True}


@router.post("/layout/suggest")
def suggest_layout(save: bool = False):
    """Draft layout + report. Not saved unless ?save=true."""
    try:
        res = layout_suggest.suggest()
    except ValueError as e:
        raise ApiError(400, f"could not build a layout: {e}")
    if save:
        site_twin.save_layout(res["layout"])
        res["saved"] = True
    return res
