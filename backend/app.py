"""BauBuddy – AI Site Manager Assistant: FastAPI backend.

Run (from this folder):
    uvicorn app:app --reload --port 8000     # http://127.0.0.1:8000  (also serves ../frontend)
    python app.py                            # same, without auto-reload
API docs: http://127.0.0.1:8000/docs
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parent
load_dotenv(BACKEND / ".env", override=False)   # before core.* reads the environment

from fastapi import FastAPI, Request                               # noqa: E402
from fastapi.middleware.cors import CORSMiddleware                 # noqa: E402
from fastapi.responses import JSONResponse, PlainTextResponse      # noqa: E402
from fastapi.staticfiles import StaticFiles                        # noqa: E402

from core.errors import ApiError                                   # noqa: E402
from core.store import DATA                                        # noqa: E402
from routes import agent, documents, inbox, metrics, photos, plan, replan, site, system, voice          # noqa: E402

FRONTEND = Path(os.environ.get("FRONTEND_DIR", BACKEND.parent / "frontend")).resolve()
# Origins allowed to call the API when the frontend is hosted separately ("*" = any; fine for a local demo).
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGIN", "*").split(",")]

app = FastAPI(title="BauBuddy – AI Site Manager Assistant")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

for r in (system.router, photos.router, documents.router, plan.router, site.router,
          voice.router, inbox.router, replan.router, metrics.router, agent.router):
    app.include_router(r)


@app.exception_handler(ApiError)
def api_error(request: Request, e: ApiError):
    # same shape as FastAPI's HTTPException: {"detail": ...} (the frontend reads .detail)
    return JSONResponse({"detail": e.detail}, status_code=e.status)


@app.middleware("http")
async def no_stale_frontend(request: Request, call_next):
    """The frontend changes often during the hackathon: never let the browser run a cached HTML / JS / CSS."""
    resp = await call_next(request)
    p = request.url.path
    if p == "/" or (p.endswith((".html", ".js", ".css")) and not p.startswith("/vendor/")):
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp


@app.get("/config.js", include_in_schema=False)
def frontend_config():
    # served by the backend = same origin; overrides frontend/config.js (which targets a separately hosted frontend)
    return PlainTextResponse('window.API_BASE = window.API_BASE ?? "";\n', media_type="text/javascript")


# uploaded photos, generated reports
app.mount("/data", StaticFiles(directory=DATA), name="data")
# frontend (optional: it can also be served by any static server, see frontend/config.js). Mounted last.
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
