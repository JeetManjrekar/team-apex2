# BauBuddy – AI Site Manager Assistant

BauBuddy is a Python FastAPI backend with a vanilla JS, Leaflet and Three.js frontend (served by the backend), a JSON-file store, an LLM generator and judge pair for report drafting, speech-to-text via faster-whisper, Groq, OpenAI or ElevenLabs, and an RF-DETR vision model served through Roboflow.

## 1. Run

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env        # add keys (Roboflow, LLM, STT); without keys a rule-based fallback runs
uvicorn app:app --reload --port 8000
```

Open http://127.0.0.1:8000 (the backend serves the frontend; Swagger at `/docs`), then click **Load demo data**.

Optional: `backend/scripts/phone_tunnel.sh` (cloudflared, needed for the phone QR), LibreOffice `soffice` (PDF export), `python -m pytest tests -q` (tests).

## 2. General Layout

```
backend/
  app.py              FastAPI entry point, serves API, frontend and /data
  routes/             thin API routers (photos, documents, plan, site, voice, inbox, agent, replan, metrics, system)
  core/               business logic: agent, assistant (chat/follow-ups), extraction, review, STT, photos, layout, cost model, export, store
  nachweis_llm/       LLM package for photo captions and replanner wording
  registry/           YAML document types and German prompts (single source of report fields)
  templates/          Word templates for exported reports
  data/               demo, seed, eval and runtime data (JSON store, uploads)
  scripts/            model download, phone tunnel, eval runner, sample data generators
  tests/              pytest suite (fake LLM, no keys needed)
frontend/
  index.html          desktop app (AI manager, documents, plan, photos, 3D twin, map, metrics)
  m.html              phone page opened via QR (PWA)
  js/                 UI modules (app, command/voice, dashboard/costs, site3d, presence, story demo)
  vendor/             Leaflet and Three.js
model_file/           Colab notebook fine-tuning the construction vision model
site_documents/       sample site-layout inputs (Baugrundgutachten, Bauzeitenplan, GeoJSON, GPS photos) and ground truth
synthetic_data(_en)/  generated test scenarios, audio, mails and minutes
test_inputs/          manual test pack with voice commands and expected results
docs/, DEMO.md, HANDOVER.md, schema.md   pitch material, demo script, handover notes, photo record schema
```

## 3. Main features

- **Transcription:** voice commands and live dictation (faster-whisper, Groq, OpenAI or ElevenLabs, live captions over WebSocket).
- **Text extraction:** from emails, calendar files, PDF, DOCX, XLSX, CSV and photo metadata, every field cited to its source.
- **Fill out reports:** Nachtragsmeldung, Mehrkostenanzeige, Behinderungsanzeige, Mängelanzeige, Bedenkenanmeldung, Aktennotiz, Bautagesbericht, plus an AI site and incident report; export to Word and PDF.
- **Follow-up questions:** the assistant asks for missing required fields and answers general questions in chat.
- **Automatic detection** from photos, reports, mails, Baugrundgutachten, drilling lists, Bauzeitenpläne and weather:
  - Nachtrag / claim potential (for example drilling much slower than reference piles) with an estimated amount
  - delay, which triggers a Behinderungsanzeige draft
  - frost on concrete work, which triggers a Bedenkenanmeldung draft
  - idle cost (breakdowns) and missing documentation (for example a missing drilling log)
  - safety incidents: person near machine, machine in a restricted zone, reported incident, flagged safety photo, verbal incident report
- **Site layout generation:** built from photo GPS metadata, coordinates in documents, GeoJSON and schedule ids. Areas are classified into zones (work, facilities, future), and photos are attached to the live map and 3D twin by GPS position.
- **Worker contribution via QR code:** the QR code opens a phone page where workers add photos, voice or text notes and share their live location.

## 4. More technical details

- **Generator + judge LLM workflow:** one LLM extracts and drafts report fields, and a second reviewer LLM (optional double-judge mode, unanimity required) checks that each critical field is supported by its cited evidence and flags unsupported ones. It is a single verification pass, not an iterative loop.
- **Custom vision model:** RF-DETR Small fine-tuned on construction machinery (excavator, bulldozer, dump truck, car, person) and served via Roboflow. Fine-tuning and benchmarks: https://colab.research.google.com/drive/1MTrQJe-x7pI0KGVeU3ZJV1TV2TQBRSOZ?usp=sharing
- **Claim cost estimation:** a Qwen3-14B model on an OpenAI-compatible endpoint gives a claim estimate with range and rationale, next to a transparent rule-based cost model (Nachtrag exposure, idle cost, delay risk, time saved).
- **Guardrails:** every value needs a source reference and a confidence threshold, numbers are computed in Python, PII is masked before LLM calls, user edits lock fields, and nothing is sent automatically (Draft, Checked, Sent by user click).
- **Other:** JSON-file persistence, record/replay LLM cache for offline demos, live LLM cost metrics, DE/EN support, offline rule-based fallback, FastAPI backend, vanilla JS frontend with Three.js and Leaflet.
