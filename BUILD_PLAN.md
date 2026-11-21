# Nachweis – Build Plan (Sat 21.11.2026, 12:20 → 22:30)

Source of truth: this repository. Domain reference: `Nachweis_Plan.pdf` (Plan v2). Where the PDF names a different stack
(Next.js, SQLite, stub endpoints), **this repo wins**: FastAPI `backend/app.py` + `routes/*` + `core/*`, vendored
`nachweis_llm/` (never edited), zero-build vanilla `frontend/` with local Three.js + Leaflet, JSON store in `backend/data/`.

---

## 1. Audit: what already works

| Area | Status | Where |
|---|---|---|
| Chat → draft with evidence per field, follow-up questions for gaps, edits by chat ("change X to Y") | ✅ | `core/assistant.py` `_handle`, `apply_text`, `_ask_next` |
| Evidence IDs `msg-…`, `mail-…`, `photo-…`, `sched-…`, `gutachten-14`, `lv-02-110` | ✅ | `assistant.build_evidence`, `plan.DEMO_CLIENT_DOCS` |
| LLM extraction with evidence-ID + confidence gates, user-locked fields passed through | ✅ (package) | `nachweis_llm/services/extraction.py` via `core/llm_bridge.extract` |
| Rule-based fallback under the same field rules when no key | ✅ | `core/extract.py` |
| Critical-field reviewer in background | ✅ wired, **off** (`LLM_REVIEWER_ENABLED=false`), never run live | `llm_bridge.review_in_background` |
| PII masking (email/phone/IBAN) before LLM, unmask after | ✅ text paths | `core/sanitizer.py` (used in `apply_text`, `summarize`, `_handle`) |
| User edits locked, later AI input → proposal, edit log + undo, edit after Checked → Draft | ✅ | `core/docs.py` `set_field`, `accept_proposal`, `undo`, `_drop_to_draft` |
| Status Draft → Checked → Sent, user click only, required-field gate | ✅ | `docs.set_status`, `POST /api/docs/{id}/status` |
| 7 doc types incl. Nachtragsmeldung, Mehrkostenanzeige, Behinderungsanzeige, Bautagesbericht | ✅ | `core/docs.py` (fields from `nachweis_llm/registry.py`) |
| Word export with photos + per-field evidence appendix | ✅ **python-docx**, not docxtpl | `core/export.docx` |
| PDF | ⚠️ browser print view only (`/print`), no file | `core/export.print_html` |
| Voice | ⚠️ Chrome Web Speech API only (no audio file, no Safari/iOS, no audio locator) | `frontend/js/app.js` `#mic` |
| Summaries of minutes/emails (pasted text), "draft Mehrkostenanzeige from this" merges as proposals | ✅ | `core/summarize.py`, `POST /api/docs` with `source:"email"` |
| Outlook `.ics` / `.eml` file import | ❌ | — |
| Plan vs actual, delay alerts, frost alert (Open-Meteo), "draft from alert" | ✅ | `core/plan.py`, `POST /api/plan/propose` |
| Photos: EXIF GPS/time/heading, Roboflow, vision-LLM category, 1-tap reassign | ✅ | `core/photos.py` |
| Site twin (3D/2D) + Leaflet map with photo pins | ✅ | `core/site_twin.py`, `frontend/js/site3d.js` |
| Crew replanner | ❌ host side. Package has `ReplannerNarrator` (wording only, refuses candidates that fail rules) but no roster, no rules, no bridge call | `nachweis_llm/services/replanner.py` |
| Metrics JSONL + per-stage table | ✅ timings; ❌ STT stage, voice→draft→PDF e2e, accuracy, honesty, dashboard tile | `routes/system.py /api/metrics`, `llm_bridge.Timer` |
| Demo reset | ⚠️ `POST /api/demo/reset` clears chat/docs/notes only; photos, layout, metrics stay | `routes/plan.py` |
| Responsive | ⚠️ breakpoints at 1100/900/640 px; nav and doc panel not tuned for phone capture | `frontend/css/app.css:318-337` |

### Environment facts (checked on the dev Mac, 21.11. 12:15)
- `soffice` is **not installed** (not at `/usr/bin/soffice`, not in `/Applications`). Install: `brew install --cask libreoffice`
  → binary `/Applications/LibreOffice.app/Contents/MacOS/soffice`. Code must resolve via `SOFFICE_BIN`, then `shutil.which`, then both paths.
- `docxtpl`, `openai-whisper`, `faster-whisper` not installed. `ffmpeg` is present (`/opt/homebrew/bin/ffmpeg`). Python 3.13.
- **Runtime state is tracked in git** (`backend/data/*.json`, `llm_metrics.jsonl`, `uploads/`, generated `.docx`). Every local run
  dirties these → guaranteed merge conflicts. Fixed in the scaffold step (§3).

---

## 2. Guardrails (binding for every PR)

1. **Evidence or empty.** Every AI-filled field carries an `evidence_id` from the request's allowed evidence list; otherwise it
   stays empty and becomes a follow-up question. Refs (APEX 2 format, since the LLM merge): `msg:<id>` (chat),
   `audio:<id>@<start>-<end>` (voice segment), `mail:<id>` (.eml), `cal:<uid>` (.ics), `photo:<id>`, `sched:<id>`,
   `crew:<id>` (roster row), `doc:bgg@p14`, `doc:project@p1`, `drill:P07`. Build chunks with `core/sources.py`; document
   fields come from `backend/registry/doc_types/*.yaml`.
2. **Locks win.** AI writes only through `docs.set_field(..., by="ai")`. Never write `doc["fields"]` directly.
3. **Mask before LLM.** Every text that reaches an LLM goes through `sanitizer.mask` first (transcripts, mail bodies, ICS
   attendees/descriptions, replanner input). Audio sent to a cloud STT cannot be masked → `STT_PROVIDER=local` is the default;
   `openai` is opt-in and the pitch says so.
4. **Human-only transitions.** Only `POST /api/docs/{id}/status` changes status. Replanner reassignments and alert letters are
   proposals with Accept/Reject; nothing is sent, mailed or assigned automatically. "Sent" = handed on, logged.
5. **`nachweis_llm/` is read-only.** All host↔package calls go through `core/llm_bridge.py`.
6. **No pricing / legal assessment** in any document. Footer stays: "Entwurf mit KI-Unterstützung erstellt, geprüft von …".
7. **Every new stage is timed** with `llm_bridge.Timer("<stage>", run_id, ...)`. No feature is done without its metrics row.
8. **Config by env var**, each new key documented in `backend/.env.example`.

---

## 3. Scaffold commit (W1, 12:20 → 12:40) — prevents merge conflicts

One person commits this before anyone else pushes. Others: install deps, get keys, read their files meanwhile.

- **Git hygiene:** copy current demo state to `backend/data/seed/` (json files + seed photos) — this is what reset restores.
  `git rm --cached` runtime files (`backend/data/*.json`, `*.jsonl`, `*.docx`, `*.pdf`, `uploads/`) and add them to `.gitignore`
  (keep `data/seed/`, `data/eval/`, `templates/`).
- **Empty modules with signatures + docstrings:** `core/stt.py`, `core/outlook.py`, `core/replanner.py`, `core/metrics.py`,
  `core/demo.py`; routers `routes/voice.py`, `routes/inbox.py`, `routes/replan.py`, `routes/metrics.py`.
- **`app.py`:** register all new routers now. Nobody edits `app.py` after this.
- **Move** `GET /api/metrics` from `routes/system.py` into `routes/metrics.py` (delegating to `core/metrics.aggregate()`).
- **Hooks (stubs that return empty):**
  - `assistant.apply_text(...)` gains `evidence_meta: dict | None = None` (audio segments, mail headers) and passes it into the primary evidence.
  - after a doc is created in `_handle`: `actions += replanner.actions_for(doc)` (stub → `[]`).
  - `_daily_report`: include `replanner.accepted_for(day)` (stub → `[]`).
  - `llm_bridge.phrase_replan(candidate)` (≈15 lines, wraps `svc.replanner.phrase`, returns `None` without key).
- **`requirements.txt`:** add `docxtpl`, `faster-whisper`, `icalendar`. **`.env.example`:** add every key from §5 at once.
- **Frontend slots:** `app.js` exposes `window.NW = {api, esc, $, loadMsgs, showAssistDoc, TAB}`; move the `#mic` handler out of
  `app.js` into `js/voice.js`; add empty `js/inbox.js`, `js/replan.js`, `js/tile.js` + their `<script>` tags; add empty slot
  containers `#voiceSlot`, `#inboxSlot`, `#replanSlot`, `#metricsTile` in `index.html`.

After 12:40 the only shared files are untouched; each workstream owns its files exclusively (§4).

---

## 4. Workstreams and file ownership (12:40 → 22:30)

Rule: you may **call** any module's public function; you may **edit** only files in your column. Need a change in someone
else's file → ask them in the channel (contract change), don't push it yourself.

| | Owner files (exclusive) | Calls (read-only) |
|---|---|---|
| **W1 Documents & Outlook** | `core/export.py`, `backend/templates/*.docx`, `routes/documents.py`, `core/outlook.py`, `routes/inbox.py`, `core/summarize.py`, `core/docs.py`, `frontend/js/inbox.js` | `assistant.apply_text`, `sanitizer` |
| **W2 Voice & LLM pipeline** | `core/stt.py`, `routes/voice.py`, `core/assistant.py`, `core/extract.py`, `core/llm_bridge.py`, `core/llm.py`, `core/sanitizer.py`, `frontend/js/voice.js` | `docs`, `plan` |
| **W3 Frontend & responsive** | `frontend/index.html`, `frontend/css/app.css`, `frontend/js/app.js`, `frontend/js/tile.js`, `frontend/js/fx.js`, `frontend/js/site3d.js` | all `/api/*` |
| **W4 Replanner & metrics** | `core/replanner.py`, `routes/replan.py`, `core/metrics.py`, `routes/metrics.py`, `backend/scripts/eval.py`, `frontend/js/replan.js`, `core/plan.py`, `core/photos.py` | `llm_bridge.phrase_replan`, `llm_bridge.extract` |
| **W5 Data, reset, demo & pitch** | `core/demo.py`, `routes/system.py`, `routes/plan.py`, `backend/data/seed/**`, `backend/data/eval/**`, `backend/data/inbox_samples/**`, `README.md`, `BUILD_PLAN.md`, `backend/.env.example` (after scaffold) | everything |

`requirements.txt` after scaffold: append-only, one line per PR, W5 resolves.

### W1 — Word/PDF export + Outlook ingestion
1. **docxtpl export** (`core/export.py`): one template per family in `backend/templates/` (`notice.docx` for the VOB/B notices,
   `nachtrag.docx`, `tagesbericht.docx`). Context: header table, field rows (`— (offen)` when empty), completeness checklist,
   photos as `InlineImage(tpl, annotated_path, width=Mm(130))` + caption, **source appendix** rows
   `{label, evidence_id, kind, locator, excerpt[:300]}` for every filled field (incl. `user`/`answer` sources), footer.
   Keep the current python-docx path as fallback if a template is missing.
2. **PDF** `GET /api/docs/{id}/pdf`: render docx, then `soffice --headless --convert-to pdf --outdir <tmp> <docx>` with
   `-env:UserInstallation=file:///tmp/lo_nachweis` (avoids profile lock), 60 s timeout. Binary: `SOFFICE_BIN` → `which soffice`
   → `/usr/bin/soffice` → `/Applications/LibreOffice.app/Contents/MacOS/soffice`. Missing → 503 with "use print view".
   Timers `export_docx`, `export_pdf`. Draft documents carry the ENTWURF watermark.
3. **Outlook** (`core/outlook.py`, `POST /api/inbox/import` multipart, many files):
   - `.eml` → `email` stdlib parser (`policy.default`), subject/from/date/plain body (HTML → text). Mask → `summarize.summarize`
     for open items; if `summarize` finds `nachtrag_candidates` or `detect_intents` hits, call
     `assistant.apply_text(dtype, body, "email", source_ref=<msg-id hash>, origin="email", locator="E-Mail <from>, <date>, Betreff …")`
     → evidence `mail-…`; an open draft for the same location receives **proposals**, never overwrites.
   - `.ics` → `icalendar`: VEVENTs today/next 7 days become reminders (`cal-<uid>` evidence, kind `calendar`) and chat
     notifications ("Baubesprechung 10:00 – 2 offene Punkte zu Pfahl 7"). No document is created from a calendar entry alone.
   - Response lists what was created and links to drafts. Timer `outlook_import`. Graph adapter: out of scope.
4. `frontend/js/inbox.js`: drop zone in `#inboxSlot` (Summaries tab), result list with "open draft" links.

### W2 — Whisper STT + live LLM verification
1. **STT** (`core/stt.py`): `transcribe(raw, mime) -> {text, segments:[{start,end,text}], provider, model, duration_s}`.
   `STT_PROVIDER=local` → `faster-whisper` (`STT_MODEL=small`, `compute_type=int8`, `language="de"`,
   `initial_prompt=STT_VOCAB` = "Bohrpfahl, Bewehrung, Nachunternehmer, Polier, Widerlager, Pfahlkopfbalken, Meißel, Hydraulikschaden,
   Behinderungsanzeige, Mehrkostenanzeige"); model loaded once, lazily. `STT_PROVIDER=openai` → `audio.transcriptions` with the
   same prompt. Browser audio (webm/opus, mp4/aac on iOS) decoded via ffmpeg.
2. **`POST /api/voice`** (`routes/voice.py`, sync endpoint): save audio to `data/uploads/<id>.<ext>`, transcribe (timer `stt`),
   then `assistant.handle(text, voice=True, evidence_meta={"audio_file", "segments"})`. Primary evidence becomes
   `msg-<id>`, kind `audio`, locator `Diktat 00:04–00:11` (segment containing the quoted clause). Timer
   `voice_to_draft_end_to_end` around the whole request.
3. **`frontend/js/voice.js`**: MediaRecorder (hold/tap to record, timer, cancel) → upload → `NW.loadMsgs()`; fallback to Web
   Speech when MediaRecorder is missing. HTTPS needed on phones (see §6).
4. **Live LLM verification** with a real `OPENAI_API_KEY`: hero inputs through `/api/chat` and `/api/voice` with
   `LLM_REVIEWER_ENABLED=true`. Check and fix host side: every proposed field's `evidence_id` resolves in `ev_by_id`; fields
   below `LLM_CONFIDENCE_THRESHOLD` are empty + asked; locked fields survive a second message; reviewer findings render.
   Add `backend/tests/test_gates.py` using `nachweis_llm/testing.FakeLLMProvider` to prove: invented evidence ID → rejected,
   low confidence → gap, locked field → unchanged, masked email never in the prompt.
5. Set `LLM_INPUT_COST_EUR_PER_1M` / `LLM_OUTPUT_COST_EUR_PER_1M` to real model prices so cost per document is non-zero.

### W3 — Responsive UI (≤ 768 px) + dashboard tile
1. Phone layout ≤ 768 px: bottom tab bar (Assistant, Documents, Map, Dashboard, More), chat full height with sticky input,
   48 px mic and camera buttons (`<input type=file accept=image/* capture=environment multiple>`), document panel as a
   full-screen sheet opened from the chat bubble, field evidence as tap-to-expand, no horizontal scroll, `100dvh`.
   Laptop stays two-column. Test on iPhone Safari + Android Chrome over HTTPS.
2. **Dashboard (bento)** using existing data: documents by status (Draft/Checked/Sent), history incl. corrected versions
   (edit log), open warnings, map thumbnail, **metrics tile** (`js/tile.js` in `#metricsTile`, from `GET /api/metrics/summary`).
3. Export buttons: Word, PDF (falls back to print view on 503). Reset button calls `POST /api/system/reset` (two-click confirm kept).
4. Visual states: "being verified" (reviewer running), low confidence, locked, proposal pending.

### W4 — Deterministic crew replanner + metrics aggregation
1. **Rules** (`core/replanner.py`): input = stop/breakdown event (Behinderungsanzeige with equipment + location, e.g.
   "Bagger Achse 2 Hydraulikschaden seit 10 Uhr"), `schedule` (due today, not finished), `crew.json` (name, role,
   qualifications, assigned equipment, current activity, available). Candidate = person whose current activity depends on the
   stopped equipment × activity that is due, **not blocked** by the same equipment, and whose required qualification is in the
   person's list. Rank by schedule delay. Each candidate cites `crew-<id>`, `sched-<activity>`, and the triggering `msg-…`.
2. **Wording**: `llm_bridge.phrase_replan(EligibleReassignmentCandidate(... qualification_check_passed=True, activity_unblocked=True))`;
   without a key a German template sentence. Timers `replanner_rules`, plus the package's `replanner_wording`.
3. **API** `GET /api/replan/proposals`, `POST /api/replan/{id}/accept|reject` → `data/replan.json`. Accept logs into the daily
   report via `accepted_for(day)`; nobody is moved automatically. `js/replan.js` renders the proposal card in chat and dashboard.
4. **Metrics** (`core/metrics.py`): per-stage avg/p50/p95/max, tokens, cost; **per document**: e2e voice→draft and draft→PDF
   (joined by run/doc id), cost per document; **honesty**: share of gaps asked vs fields filled, reviewer flags;
   **accuracy** from `data/eval/report.json`. Endpoints `GET /api/metrics` (existing shape kept) and `GET /api/metrics/summary` (tile).
5. **Eval** `backend/scripts/eval.py`: runs each case in `data/eval/cases.json` through `apply_text` on an isolated temp data dir,
   compares to ground truth (exact / normalized date / numeric tolerance / substring), writes `data/eval/report.json`.
   Photo accuracy: predicted vs labelled category for the seed photos.
6. Keep `core/plan.py` alerts working; add the frost + delay letter proposal for abutment 1 if time allows (Should).

### W5 — Seed data, one-command reset, demo & pitch
1. **Seed** `backend/data/seed/`: schedule (bridge Bauzeitenplan incl. Achse 1 Fundament + Achse 2 Aushub), progress, client docs
   (Gutachten p.14, LV), `crew.json` (≥ 6 people: Baggerfahrer, Schalungskolonne, Bohrmeister, Polier, Eisenflechter …),
   site layout, ~8 photos with labels, sample `.eml` (Bauherr instruction pile 7) + `.ics` (Baubesprechung 10:00) in
   `data/inbox_samples/`, 3 recorded German voice notes (hero, Bagger, daily note).
2. **`POST /api/system/reset`** (`core/demo.py`): archive `llm_metrics.jsonl` to `data/metrics_archive/<ts>.jsonl` (never
   delete pitch evidence), restore every JSON from seed, delete uploads not in seed, reset chat state, clear generated
   docx/pdf. Body `{"keep_metrics": true}` optional. Also `python -m core.demo reset` for CLI. Keep `/api/demo/reset` as alias.
3. **Eval ground truth** `data/eval/cases.json` (≥ 10 cases across Nachtragsmeldung, Behinderungsanzeige, Mehrkostenanzeige).
4. Demo script v2 (90 s shot list), HTTPS for phones (§6), README update, partner questions (PDF §12), pitch numbers
   from `/api/metrics/summary` only — assumptions labelled.

---

## 5. New env vars (added in scaffold)
```
STT_PROVIDER=local            # local | openai
STT_MODEL=small               # faster-whisper size, or whisper-1 / gpt-4o-transcribe for openai
STT_VOCAB="Bohrpfahl, Bewehrung, Nachunternehmer, Polier, Widerlager, Pfahlkopfbalken, Meißel, Hydraulikschaden"
SOFFICE_BIN=                  # empty = auto-detect
EXPORT_TEMPLATES_DIR=templates
REPLANNER_ENABLED=true
OUTLOOK_LOOKAHEAD_DAYS=7
DEMO_SEED_DIR=data/seed
```

## 6. Running on a phone (HTTPS)
MediaRecorder and camera capture need a secure origin. Laptop: `uvicorn app:app --host 0.0.0.0 --port 8000 --ssl-keyfile key.pem
--ssl-certfile cert.pem` with a `mkcert` cert for the laptop's LAN IP, or a tunnel (`cloudflared tunnel --url http://localhost:8000`).

---

## 7. Timeline and gates

| Time | Gate | Pass criteria (demo-able, measured) |
|---|---|---|
| 12:20–12:40 | Scaffold | §3 merged, everyone rebased, app boots, `/api/health` ok |
| **14:30** | **Hero voice + photo → export** | On a phone: record "Pfahl 7 Fels bei 4 m …" + 2 photos → `audio:` evidence with segment locator → Nachtragsmeldung draft with Gutachten p.14 citation, one follow-up asked and answered → Checked → Word + PDF with embedded photos and source appendix. Rows for `stt`, `llm_extraction`, `voice_to_draft_end_to_end`, `export_pdf` in metrics. Works live (key) and in rules mode. |
| 16:30 | Mid check | Outlook import creates `mail-` proposals on the pile 7 draft; replanner returns a rules-valid candidate; reset restores seed |
| **18:30** | **All features wired** | Bagger voice note → Behinderungsanzeige + replanner card (accept → appears in Bautagesbericht); `.eml`/`.ics` import; dashboard tile with live numbers; eval report generated; reviewer on; `POST /api/system/reset` → clean state in < 5 s; phone layout usable end to end |
| 18:30–21:00 | Hardening | Bugfixes only from the hero/demo path; gate tests green; 3 dry runs of the demo script after reset |
| **21:00** | **Feature freeze + 90 s recording** | Reset → record demo per W5 shot list (phone + laptop). Pitch numbers copied from `/api/metrics/summary` |
| 21:00–22:30 | Re-takes, README, pitch deck, tag `demo-v1` | No feature code after 21:00 |

Cut order if behind (from PDF §8, adapted): Outlook `.ics` reminders → frost letter proposal → map extras → reviewer
(keep off, say so) → OpenAI STT provider. **Never cut:** hero flow, Word/PDF, replanner card, metrics tile, reset.

## 8. Definition of done (per PR)
- Owner files only; app boots; `/docs` shows the new route.
- New stage has a `Timer` row; new source has an evidence-ID prefix and a locator.
- AI writes go through `docs.set_field(by="ai")`; LLM inputs go through `sanitizer.mask`.
- Works without `OPENAI_API_KEY` (rules/fallback) and with it.
- Checked once on a 375 px wide viewport if it has UI.

---

## 9. LLM + voice merge (branch `w2`, 21.11. afternoon) — what changed for each workstream

The old `APEX 2/` prototype is **not used**. Its LLM pipeline was ported into `backend/core/`; everything below lives in
this repo. Rebase on `w2` before merging your part.

**Everyone**
- Document fields come from `backend/registry/doc_types/*.yaml` (not `nachweis_llm/registry.py`). Field keys changed, e.g.
  `occurred_at` (was `event_datetime`), `ordered_by` (was `instruction_by`), Bautagesbericht `work_done` / `incidents` /
  `temperature_min_c` / `temperature_max_c`. `docs.DOC_TYPES[t]["fields"]` tuples now have 7 entries
  `(key, label, required, critical, question, type, derived)`: unpack with `*_`.
- Evidence refs use the `prefix:id` format: `msg:`, `audio:<id>@<s>-<e>`, `mail:`, `cal:`, `photo:`, `sched:`, `crew:`,
  `doc:bgg@p14`, `doc:project@p1`, `drill:P07`. Build them with `core/sources.py`.
- **One demo dataset: BW 12 Mühlbach** (`backend/data/demo/`). `SITE_*` default to `data/demo/project.json`; `DEMO_TODAY=2026-11-17`
  pins the demo day (plan vs actual, "seit 10 Uhr"). The seed (`data/seed/`) holds the BW 12 schedule (from
  `bauzeitenplan.csv`), drilling progress (from `drilling_times.csv`) and Gutachten pages, with no drafts or messages.
- Metrics: use `llm_bridge.timed(stage, run_id, model=..)` (tokens, cost, `t.add_cost(eur)` for non-token cost) or `Timer`.
- Tests: `cd backend && python -m pytest tests -q` (offline, fake LLM, isolated data dir).

**W1 (documents, Outlook)**: `core/docs.py` was changed (registry loader, per-field `version` and `review`, `LOCK`, backfill of
old docs); `core/export.py` only got `*_` unpacking and a `drilling` source label. For `.eml` import call
`assistant.apply_text(dtype, body, "email", source_ref, origin="email", locator=...)` → `mail:<id>` refs, proposals on open drafts.
Each field `source` now carries `chunks: [{ref, label_de, text}]`: use it for the citation appendix.

**W3 (frontend)**: fields have `review.status` = `being_verified | verified | flagged` (badge already in `renderDoc`;
the panel refreshes on reload, add polling while `doc.review.status == "running"` if wanted). New source type `drilling`.
`site3d.js` matches progress by `sched:<activity>`.

**W4 (replanner, metrics, photos)**: schedule ids are now BW 12 (`W1_BP`, `A1_BP`, `A2_BP`, `W2_BP`, `*_BET`), crew roster in
`data/demo/crew/crew_roster.json`, equipment in `data/demo/equipment.json`. Eval ground truth in `data/eval/cases/*.json` uses the
registry keys and refs above. `llm_extract.extract(...)` returns `dropped` per field for the honesty metric.

**W5 (data, reset)**: `core/demo.reset` should restore `data/seed/` (already BW 12) and call nothing else; demo photos for the
BW 12 story are in `data/demo/photos/`.
