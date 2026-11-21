# BauBuddy – AI Site Manager Assistant (TUM.ai Construction Hackathon, Challenge B)

<img src="frontend/img/logo-wordmark-light.svg" alt="BauBuddy" height="44">

*Formerly "Nachweis". The internal LLM package keeps its name `nachweis_llm`.*

Chat and voice capture → notices with evidence per field → review → Word / PDF. Plus plan vs actual with early warnings,
daily report from photos/notes/schedule/weather, summaries of minutes and emails, Roboflow photo detection with geotags.

## Project layout
```
backend/                 FastAPI (Python)
  app.py                 entry point: routers, JSON errors, CORS, serves ../frontend and /data
  routes/                one APIRouter per area: system, photos, documents, plan, site
  core/                  host logic: store, docs, assistant, plan, summarize, export, photos, site_twin, llm_bridge …
  nachweis_llm/          the team's LLM package (vendored unmodified)
  data/                  JSON store, uploads/, generated reports
  requirements.txt, .env(.example)
frontend/                static UI, no build step
  index.html, config.js, css/app.css, js/app.js, js/site3d.js
  vendor/                three.js 0.160 and Leaflet 1.9.4 (local: the demo works without CDN access)
```

## Run
```
cd backend
pip install -r requirements.txt
cp .env.example .env        # fill in keys (loaded automatically by app.py)
uvicorn app:app --reload --port 8000   # http://127.0.0.1:8000 – API + frontend, API docs at /docs
```
Open http://127.0.0.1:8000, click "Load demo data" once.

Frontend hosted separately (optional): `cd frontend && python -m http.server 5500`, open http://127.0.0.1:5500.
It calls the API at `http://127.0.0.1:8000` (change in `frontend/config.js`; restrict `CORS_ORIGIN` in `.env` if needed).

## Architecture
- `backend/registry/` – **single source of document fields**: `doc_types/*.yaml` (fields, types, required/critical/derived,
  follow-up questions, intent keywords, checklist) and `prompts/*.md` (German extraction / intent / reviewer prompts). Merged from APEX 2.
- LLM pipeline (merged from APEX 2), all behind `backend/core/llm_bridge.py`:
  - `core/llm_extract.py` – intent routing (registry keywords first, LLM second) and extraction (LLM A). In code: a value survives
    only if it cites a ref from the request and passes `CONFIDENCE_THRESHOLD`; `derived` fields (drilling times, ratio, crew/rig
    hours) are computed in Python; PII is masked in every chunk before the prompt.
  - `core/review.py` – critical-field reviewer (LLM B), single or double judge, background, guarded by field lock + version.
  - `core/llm_adapter.py` – openai | anthropic | groq, JSON repair retry, record/replay cache (`LLM_CACHE_MODE`).
  - `core/sources.py` – evidence chunks; `core/llm_settings.py` – env config; `core/registry.py` – YAML loader.
- `core/stt.py` – speech to text: local faster-whisper (default) | openai | groq | elevenlabs. Each Whisper segment becomes its own
  evidence chunk, so a field extracted from a voice note cites the exact moment (`Diktat 00:04–00:11`).
- `backend/nachweis_llm/` – vendored unmodified; still used for photo classification and replanner wording.
- `backend/core/` – host: chat, persistence, edit locks, status flow, schedule maths, weather, export, rule fallback.
- `backend/data/demo/` – APEX 2 demo dataset the LLM cites (project, Baugrundgutachten pages, drilling list, Bauzeitenplan, daily
  reports); `backend/data/eval/` – ground truth cases. Tests: `cd backend && python -m pytest tests -q`.
- Evidence refs: `msg:<id>` (chat), `audio:<id>@<start>-<end>` (dictation segment), `mail:<id>`, `cal:<uid>`, `photo:<id>`,
  `doc:project@p1`, `doc:bgg@p14` (Baugrundgutachten page), `drill:P07`, `sched:<activity>`, `dr:<date>#personal`.

## Site twin (2D plan / 3D isometric)
Tab "Site twin": a Three.js engineering site plan (`frontend/js/site3d.js`, layout + data from `backend/core/site_twin.py`).
- Layout in `backend/data/site_layout.json` (edit via "Layout"): boundary, zones (linked to schedule activities), roads, gates,
  structures. Metres relative to `origin`; points may also be given as `{lat, lon}`. `origin: null` = relative coordinates only.
- Photos with EXIF/user GPS are positioned automatically. Photos without GPS sit in a "no GPS" strip until placed by click;
  a second click sets the camera direction. The site-default GPS fallback is never shown as a real position.
- Detected objects: confidences from the stored detector output. Their plan position is estimated (pinhole model from
  box column/height + camera direction) or drawn next to the camera when no direction is known; the UI says which.
- Structures show progress from the progress log (piles done/current, abutment height, cap beam length).
- API: `GET /api/site/twin`, `GET|PUT /api/site/layout`, `POST /api/site/layout/reset`, `PATCH /api/photos/{id}` with `site_xy`, `heading`, `zone`.

## Human in control
- Every field has a source (message quote, answer, photo, schedule, weather) or stays empty and triggers a follow-up question.
- Status Draft → Checked → Sent only by the user's click. Editing after Checked drops back to Draft.
- User edits are locked; later AI input appears as a proposal. Edit log with undo.
- E-mails, phone numbers and IBANs are masked before any LLM call.
- Formal completeness checklist only, no legal advice.

## Demo script ("a day in the life")
1. Assistant: tap "Rock at pile 7" → Mehrkostenanzeige draft, answer the follow-up question, "Also draft Behinderungsanzeige".
2. Tap a field's "source" to show the quote. Edit a field, show lock + edit log + undo.
3. Summaries: sample email → masked contact data, open item, "Draft Mehrkostenanzeige from this" merges into the pile 7 draft as proposals.
4. Plan vs actual: piles red (3 days) → "Draft Behinderungsanzeige"; frost warning if the forecast is cold.
5. Diary note, then "daily report" → Bautagesbericht with weather, plan status, photos, notices.
6. Mark as checked → Word / PDF export with photos and evidence appendix.
