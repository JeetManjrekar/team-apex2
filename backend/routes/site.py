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


@router.post("/snapshot")
def twin_snapshot(body: dict = Body(...)):
    """3D twin overview from the browser (data URL), embedded in Word/PDF exports for a few hours (core/report_visuals)."""
    import base64, io
    from PIL import Image
    from core import report_visuals
    data = (body or {}).get("image") or ""
    if not data.startswith("data:image/"):
        raise ApiError(400, "image must be a data URL")
    try:
        raw = base64.b64decode(data.split(",", 1)[1])
        if len(raw) > 12 * 1024 * 1024:
            raise ApiError(413, "snapshot too large")
        Image.open(io.BytesIO(raw)).convert("RGB").save(report_visuals.snapshot_path())
    except ApiError:
        raise
    except Exception as e:
        raise ApiError(400, f"not a valid image: {e}")
    return {"ok": True}


# ---------------------------------------------------------------- live location ("You" in the twin and on the map)
@router.post("/presence")
def presence_update(body: dict = Body(...)):
    from core import presence
    try:
        return presence.update(body)
    except ValueError as e:
        raise ApiError(400, str(e))


@router.get("/presence")
def presence_list():
    from core import presence
    return presence.active()


@router.delete("/presence/{device}")
def presence_remove(device: str):
    from core import presence
    presence.remove(device)
    return {"ok": True}


# ---------------------------------------------------------------- phone capture page (/m.html) link + QR code
@router.get("/phone")
def phone_link():
    """Public HTTPS link of the phone page (written by scripts/phone_tunnel.sh) and a QR code for it."""
    import base64, io, os
    from core.store import DATA
    url = os.environ.get("PUBLIC_URL", "").strip()
    f = DATA / "public_url.txt"
    if not url and f.exists():
        url = f.read_text(encoding="utf-8").strip()
    if not url:
        return {"url": None, "qr": None}
    page = url.rstrip("/") + "/m.html"
    try:
        import qrcode
        img = qrcode.make(page, box_size=10, border=2)
        buf = io.BytesIO(); img.save(buf, format="PNG")
        qr = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        qr = None
    return {"url": page, "qr": qr}

