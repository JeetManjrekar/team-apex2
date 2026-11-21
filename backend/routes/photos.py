from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from core import photos as pipeline
from core.report import build_report
from core.store import DATA, SITE, load

router = APIRouter(prefix="/api", tags=["photos"])


@router.get("/photos")
def list_photos():
    return load("photos", [])


@router.post("/photos")
def upload(files: list[UploadFile] = File(...)):
    # sync endpoint: runs in the threadpool, so Roboflow / vision calls don't block the event loop
    return pipeline.ingest((f.filename, f.content_type, f.file.read()) for f in files)


@router.patch("/photos/{pid}")
def patch_photo(pid: str, body: dict = Body(...)):
    return pipeline.patch(pid, body)


@router.post("/infer")
def infer(file: UploadFile = File(...)):
    dets = pipeline.detect(file.file.read())
    return {"mock": dets is None, "detections": dets or []}


@router.get("/report")
def photo_report():
    path = build_report(load("photos", []), SITE, DATA / "report.docx", DATA)
    return FileResponse(path, filename="Fotobericht.docx")
