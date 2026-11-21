# synthetic_data_en – English copy of the BauBuddy test data (BW 12 Mühlbach, fictitious)

English version of [`../synthetic_data/`](../synthetic_data/README.md) (German original). Everything is invented. **No photos or audio files are generated**, only text, scripts and shot lists. The app never loads this folder automatically.

## Contents
| Path | Content | Purpose |
|---|---|---|
| `commands/agent_commands.json` | 45 commands for `POST /api/agent` (same ids and intents as the German set) | Intent router `core/agent.py` |
| `emails/*.eml` (8) | PII, quoted chain, attachment only, empty, English, prompt injection, special characters, newsletter | Outlook/inbox, `sanitizer.py`, summarise |
| `minutes/site_meeting_2026-11-19.md` | Minutes with deadlines, numbers, one contradiction | Summarise, open items, file notes |
| `audio/audio_scripts.md` | 22 scripts (normal, difficult, pipeline edge cases) with expected results | `stt.py`, `/api/voice`, extraction |
| `photos/photo_shotlist.csv` | 27 photo suggestions with category, zone, expected detections and incident rule | `photos.py`, detector, incident rules |
| `scenarios/progress_*.json` | Progress variants (on track, behind, ahead, overshoot, invalid, empty) | `core/plan.py`, early warning |
| `scenarios/weather_frost_cases.json` | Frost threshold and missing weather data | Warning logic, daily report |
| `scenarios/layout_edge_cases.json` | 7 site layouts (empty, no origin, invalid, lat/lon, duplicate, overlapping, huge) | `site_twin.py`, `PUT /api/site/layout` |
| `scripts/check_routes.py` | Read-only: compares intended with actual routes | Quick regression check |

## Differences from the German set
- Texts, emails, scripts and notes are translated. Ids, file structure, activity ids (`W1_BP`, `W1_BET`, …) and zone ids (`be`, `wls`, `a10`, `erd`, `wln`) are unchanged.
- Layout zone and structure names are kept as in the seed layout (German), since they come from `backend/data/seed`.
- Audio: B02 (German dialect) became a strong English regional accent, and C10 (a question must not create an incident) was added.
- The document pipeline's prompts and registry are German (`backend/registry`). English input is a good test of how well the extraction copes with it. Expect some fields to differ from the German expectations, and note the differences.

## Usage
1. Route check without a server: `python synthetic_data_en/scripts/check_routes.py` (exit code 1 on a mismatch).
2. Router tests: `cd backend && python -m pytest tests/test_agent_routes.py -q` (runs both the German and English sets).
3. Other files: see the usage notes in the [German README](../synthetic_data/README.md). `python -m core.demo reset` wipes all runtime data, so work on a copy of `backend/data`.

Not run: LLM calls, speech-to-text, detector and frontend. All "Expected" columns are targets, not measured results.
