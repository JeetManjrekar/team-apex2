from fastapi import APIRouter, Body
from fastapi.responses import FileResponse, HTMLResponse

from core import assistant, docs, export, llm_bridge
from core.errors import ApiError
from core.store import SITE, load

router = APIRouter(prefix="/api", tags=["assistant & documents"])


@router.get("/messages")
def messages():
    return {"messages": load("messages", []), "active": load("chat_state", {}).get("active")}


@router.post("/chat")
def chat(body: dict = Body(...)):
    text = (body.get("text") or "").strip()
    if not text:
        raise ApiError(400, "empty message")
    return assistant.handle(text, voice=bool(body.get("voice")))


def _doc(doc_id):
    d = docs.get(doc_id)
    if not d:
        raise ApiError(404, "document not found")
    return d


@router.get("/docs")
def list_docs():
    return [docs.public(d) for d in sorted(docs.all_docs(), key=lambda d: d["updated_at"], reverse=True)]


@router.get("/docs/{doc_id}")
def get_doc(doc_id: str):
    return docs.public(_doc(doc_id))


@router.post("/docs")
def create_doc(body: dict = Body(...)):
    if body.get("type") not in docs.DOC_TYPES:
        raise ApiError(400, "bad type")
    if body.get("text"):
        kind = "email" if body.get("source") == "email" else "text"
        d, *_ = assistant.apply_text(body["type"], body["text"], kind, body.get("ref"), origin=body.get("source", "chat"))
    else:
        d = docs.create(body["type"], origin="manual")
    return docs.public(d)


@router.patch("/docs/{doc_id}/fields/{key}")
def edit_field(doc_id: str, key: str, body: dict = Body(...)):
    d = _doc(doc_id)
    if key not in d["fields"]:
        raise ApiError(400, "bad field")
    if d["status"] == "sent":
        raise ApiError(409, "Document was already sent")
    docs.set_field(d, key, body.get("value", ""), {"type": "user", "quote": "manual edit"}, by="user")
    return docs.public(docs.put(d))


@router.post("/docs/{doc_id}/fields/{key}/accept")
def accept(doc_id: str, key: str):
    return docs.public(docs.put(docs.accept_proposal(_doc(doc_id), key)))


@router.post("/docs/{doc_id}/undo/{index}")
def undo(doc_id: str, index: int):
    return docs.public(docs.put(docs.undo(_doc(doc_id), index)))


@router.post("/docs/{doc_id}/status")
def status(doc_id: str, body: dict = Body(...)):
    d = _doc(doc_id)
    try:
        docs.set_status(d, body.get("status"), body.get("user") or SITE["manager"])
    except ValueError as e:
        raise ApiError(400, str(e))
    return docs.public(docs.put(d))


@router.post("/docs/{doc_id}/photos")
def doc_photos(doc_id: str, body: dict = Body(...)):
    d = _doc(doc_id)
    d["photos"] = [p for p in body.get("photos", []) if isinstance(p, str)]
    assistant._host_fields(d)
    return docs.public(docs.put(d))


def _download_name(d, ext):
    return f"{d['title'].split(' /')[0].replace(' ', '_')}_{d['id']}.{ext}"


@router.get("/docs/{doc_id}/docx")
def doc_docx(doc_id: str):
    d = _doc(doc_id)
    return FileResponse(export.docx(d), filename=_download_name(d, "docx"))


@router.get("/docs/{doc_id}/pdf")
def doc_pdf(doc_id: str):
    """PDF via headless LibreOffice. 503 if it is unavailable: the client then falls back to GET /api/docs/{id}/print."""
    d = _doc(doc_id)
    try:
        path = export.pdf(d)
    except export.PdfUnavailable as e:
        raise ApiError(503, f"PDF export unavailable ({e}). Use the print view instead: /api/docs/{doc_id}/print")
    return FileResponse(path, media_type="application/pdf", filename=_download_name(d, "pdf"))


@router.get("/docs/{doc_id}/print", response_class=HTMLResponse)
def doc_print(doc_id: str):
    d = _doc(doc_id)
    with llm_bridge.Timer("export_pdf_view", d["id"], document_type=d["type"]):
        return export.print_html(d)


@router.post("/reports/daily")
def daily(body: dict = Body(default={})):
    return docs.public(assistant.daily_report(body.get("date")))
