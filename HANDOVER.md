# Handover: LLM + voice merge (BauBuddy)

This covers the work done on the LLM pipeline, the voice input (speech to text) and chat. It sits on top of `BUILD_PLAN.md`, which still sets the workstreams and guardrails.
The work went in with commit `6994957` and is merged into `integrate-all`.

Status on 2026-11-21: on `integrate-all`, `python -m pytest tests -q` reports **58 passed, 1 skipped**. Run `pip install -r requirements.txt` first, because `docxtpl` and `icalendar` are needed.

---

## 1. What was done

| # | Task | Result |
|---|------|--------|
| 1 | Audit repo + `Nachweis_Plan.pdf` | `BUILD_PLAN.md`: 5 workstreams, checkpoints 14:30 / 18:30 / 21:00, stack lock (no Next.js, no SQLite, no stub endpoint trees) |
| 2 | Merge the APEX 2 LLM pipeline with the voice work | Ported into `backend/`. APEX 2 is no longer used and is gitignored. |
| 3 | The 3 open decisions | Decided and implemented (see §3) |
| 4 | Env setup | All keys and settings in `backend/.env` (gitignored). `.env.example` has empty keys. |
| 5 | Chat answered as diary | Off-topic questions ("what is 2 plus 1?") now get a chat answer instead of being filed as diary notes |
| 6 | Photo attach rule | Recent photos that couldn't be categorized are attached to the incident draft, marked "Kategorie nicht geprüft" |

## 2. Architecture (new modules)

All LLM calls go through `core/llm_bridge.py`, which also writes metrics (time, tokens and cost) as JSONL.

| Module | Role |
|--------|------|
| `registry/doc_types/*.yaml`, `registry/prompts/*.md` | **Single source of document fields** (required/critical/derived, follow-up questions, intent keywords). 7 types, including the new `bedenkenanmeldung` and `aktennotiz`. Prompts are cached, so **restart the server after editing them**. |
| `core/llm_settings.py` | Reads the env config (`CFG`) and provides `today()`, which follows `DEMO_TODAY=2026-11-17` |
| `core/llm_adapter.py` | Talks to openai, anthropic or groq. Retries once on bad JSON, waits and retries on 429 rate limits (not on exhausted credits), and has a record/replay cache (`LLM_CACHE_MODE`) |
| `core/sources.py` | Turns every piece of evidence into a chunk with a stable ref (see §4) |
| `core/llm_extract.py` | Intent routing (registry keywords first, then the LLM), extraction (LLM A) and chat replies (`converse`, prompt `chat.md`) |
| `core/review.py` | Reviewer (LLM B) for critical fields. Runs as `single` or `double_judge` in the background, guarded by field lock + version |
| `core/registry.py` | Loads the YAML registry |
| `core/stt.py` | Speech to text: local faster-whisper, openai, groq or elevenlabs. If a cloud provider fails, it **falls back to the local model**. Each Whisper segment becomes its own chunk. |
| `core/extract.py` | Rule-based fallback when no LLM key is set, using the same field keys |

## 3. Guardrails enforced in code (not trusted to the model)

- **Citations:** a field value is kept only if it cites a ref that was in this request. Otherwise the field stays empty and the user gets a follow-up question.
- **Confidence:** values below `CONFIDENCE_THRESHOLD` are dropped and become follow-up questions.
- **Computed fields:** `derived` fields (drilling times, ratio, crew and rig hours) are calculated in Python, never by the LLM.
- **PII masking:** e-mails, phone numbers and IBANs are masked before every LLM call, with one shared mapping per prompt. `ENABLE_PII_MASKING` turns it on or off.
- **User edits win:** a field the user edited is locked. A per-field `version` stops the reviewer from overwriting a field that changed during review.
- **Status changes:** Draft → Checked → Sent happens only when the user clicks.

**The 3 decisions**
1. **Field names:** the YAML registry replaces the hard-coded field list. Old docs are backfilled by `_normalize`.
2. **Ref format:** the APEX 2 format (§4), so audio refs point to an exact segment.
3. **Demo day:** one dataset, BW 12 Mühlbach (`backend/data/demo`). Dates resolve to `DEMO_TODAY` and drafts carry the demo date.

## 4. Evidence refs

`msg:<id>` chat · `audio:<id>@<start>-<end>` voice segment · `mail:<id>` · `cal:<uid>` · `photo:<id>` · `doc:project@p1` · `doc:bgg@p14` (Baugrundgutachten page) · `drill:P07` · `sched:<activity>` · `dr:<date>#personal`

If a model shortens an audio ref to `audio:<id>`, `_resolve` expands it to that recording's segment refs.

## 5. Behaviour changes worth knowing

- **Chat routing (`core/assistant.py`):** messages are routed to a document type, a diary note, or chat. `_is_chat` and `chat_reply` catch questions and off-topic text. If a follow-up question is open and the user chats, the bot answers and then repeats the open question.
- **Photo attach rule (`attach_photos`):**
  1. Today's photos whose category fits the document type are attached. "Today" means the real date or the demo day.
  2. **New:** `uncategorized` photos are attached too, if they were uploaded in the last `PHOTO_ATTACH_WINDOW_MIN` minutes (default 120) and are not already on another open draft. They show "Kategorie nicht geprüft" in the draft, and "bitte bestätigen" in the Word caption.
  3. Demo tip: **send the photo first, then the message.**
- **Daily report:** uses the demo day by default and the registry fields (`work_done`, `incidents`, `temperature_min_c/max_c`, `reassignments`, `photos`).
- **Rules fallback fix:** the word "Hydraulikschaden" no longer triggers a Mängelanzeige (defect notice).
- **UI:** the reviewer badges show being verified / verified / flagged.

## 6. Configuration (`backend/.env`)

| Key | Notes |
|-----|-------|
| `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` | Groq is the default. Also accepts `OPENAI_API_KEY` / `GROQ_API_KEY`. |
| `OPENAI_API_KEY` | Used for photo classification (`nachweis_llm` is pinned to OpenAI) and OpenAI STT |
| `STT_PROVIDER`, `STT_FALLBACK_LOCAL`, `STT_LOCAL_MODEL` | With OpenAI, the STT model must be `whisper-1`/`gpt-*`; any other name falls back to `whisper-1` |
| `REVIEW_MODE` | `single` or `double_judge` |
| `CONFIDENCE_THRESHOLD`, `DEMO_TODAY`, `PHOTO_ATTACH_WINDOW_MIN`, `LLM_RATE_LIMIT_MAX_WAIT_S` | |

**Put comments on their own line.** With `KEY=   # comment`, python-dotenv reads the comment as the value. The code now ignores values that start with "#", but keep the lines clean anyway.

## 7. Verified live

- Text + voice for rock at pile 7 → Nachtragsmeldung with 14 cited fields and drilling ratio 3.0
- Voice note about the excavator breakdown → Behinderungsanzeige, 17.11.2026 10:00, cites `sched:A2_AUSHUB`
- Chat answers in English and German. Diary notes are still filed.
- Word export, including the embedded photo and the unverified-category caption
- A photo did not spread to a second open draft

## 8. Open items / known gaps

| Item | Owner / note |
|------|--------------|
| **OpenAI credits exhausted** (429 `insufficient_quota`) | Photo classification fails until credits are added. STT works through the local fallback. |
| **Groq free tier: 8k tokens/min** vs ~4.6k per extraction | A rate-limit retry is in place. Use a paid tier for the live demo, or `LLM_CACHE_MODE=replay`. |
| **Groq key was shared in chat** | Rotate it. Never put keys in `.env.example` or commits. |
| Document upload in chat (needed for the Bohrprotokoll follow-up) | Not built |
| Most fixed bot replies are German-only | Could follow the user's language |
| `core/demo.reset` is still a stub | Reset by hand: `cp backend/data/seed/*.json backend/data/` |
| `soffice` not installed on every machine | The PDF button falls back to the print view |

## 9. Run and test

```
cd backend
pip install -r requirements.txt
cp .env.example .env            # fill in keys
uvicorn app:app --reload --port 8000
python -m pytest tests -q       # 58 passed, 1 skipped
```

`tests/test_llm_merge.py` (17 tests) covers the merge. It uses a fake LLM and an isolated temporary data directory, so it needs no keys.

## 10. AI Site Manager layer (added 2026-11-21)

The default view is now an assistant-first command centre, documented in README "AI Site Manager".
New files: `backend/core/agent.py`, `backend/routes/agent.py`, `backend/tests/test_agent.py` (6 tests), `frontend/js/command.js`, `frontend/css/command.css`.
Small hooks in existing files:
- `site3d.js`: the AI control API.
- `app.js`: dispatches the live-detection event.
- `routes/photos.py`: scans uploads for incidents.
- `routes/plan.py`: demo reset also clears incidents.
- `index.html`, `.gitignore`.

Limits, stated in the UI and the report rather than faked:
- PPE (helmets, vests) can't be checked, because the detector has no such class.
- Zone-based rules need the photo placed on the plan, and all 7 demo photos are still unplaced.
- The PDF comes from the browser's print dialog, because `soffice` isn't installed here.
