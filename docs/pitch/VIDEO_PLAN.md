# BauBuddy · Demo video (submission, max 2:00) · plan + script

> **Status 21.11.2026, 22:30: v1 rendered** (1:54) → `BauBuddy_Submission/1_demo_video/BauBuddy_Demo_v1.mp4`.
> Voiceover generated with Christo's ElevenLabs clone (not self-recorded); dictation WAV also from the clone, fed live
> into the app's Whisper. Final script = `video/script.json` (line 05 gained "That one, the exact seconds of the voice note").
> How to re-render: `video/README.md`.

Deadline: **Sun 22.11.2026, 12:00** (Tally). Only the video decides whether we reach the final 12.
Guideline checks: ≤ 2:00 · screen recording + voiceover · **live demo of the working prototype** · **explains the technical approach** · slides allowed.

## Why this structure
Same skeleton as the Erebos/Strascheg video (it worked): hook → solution → one complete live run → architecture → result.
What changes here is **how the demo is captured**: a *film autopilot*.

- The app's built-in ▶ Autopilot is a 45 s caption tour of the tabs. It never takes an input and produces a notice,
  which is the one thing the jury checks. So it's used only as the closing 3D beat, not as the demo.
- `video/director.js` drives the **real app** end to end with Playwright in your own Chrome: real German dictation
  (a WAV fed through Chrome's fake microphone → the app's own Whisper), real Claude Fable 5.2 extraction, real
  source chips, follow-up question, status click, Word export, AI Manager. Everything on screen is live; only
  waiting is cut, and each cut gets a visible "x s later" label.
- Because it's scripted, every take has the same timing: your voiceover can be recorded once and re-used across takes,
  and a re-take is one command.
- **No Blender.** It isn't installed and a render costs the night without adding proof. The hook uses your PowerPoint
  slides 2–4 (Morph + animations), exported to video by PowerPoint itself.

## Run of show (1:55) and voiceover script

Christo reads the voiceover (your own voice, best authenticity). ElevenLabs clone only as backup, test one line first.
**242 words** at ~2.3 words/s ≈ 105 s of speech in 115 s; the gaps are where the German dictation plays.

| Time | Picture | Voiceover |
|---|---|---|
| **0:00–0:12** Hook + problem | Deck slide 2 (pile 7 cross-section, 3 builds) | Eleven thirty on a bridge site. Pile seven hits rock at four metres. The soil report promised sand down to nine. That's a claim worth real money, if someone proves it today. |
| **0:12–0:25** Solution | Deck slide 3 → Morph → slide 4, then the app's BAUBUDDY splash | The proof sits in voice notes, photos and emails. It never reaches the office. BauBuddy changes that: talk on site, get the formal notice, with a source behind every field. |
| **0:25–0:37** Demo · dictation | Assistant tab, mic live, waveform + live captions. **German dictation audible**, EN subtitle | This is the live prototype. *(pause: dictation plays)* |
| **0:37–0:44** Demo · draft | *"3 s later"* → Nachtragsmeldung fills, badge "extracted by BauBuddy AI" | Local Whisper transcribes it. Claude extracts the fields and drafts the Nachtragsmeldung. |
| **0:44–0:54** Demo · proof | Zoom on a source line → quote opens: *Baugrundgutachten S. 14*, then *Diktat 00:04–00:11* | Every value cites its evidence. This one, page fourteen of the client's soil report. That one, seconds four to eleven of the voice note. |
| **0:54–1:03** Demo · gap | Empty required field → BauBuddy's question in chat → answer typed → field fills | Nothing is guessed. A required detail has no source, so the field stays empty and BauBuddy asks. One answer, and it's filled. |
| **1:03–1:11** Demo · human click | "Mark as checked" → pill turns *checked* → Word → document with evidence appendix | The site manager checks it. Only that click releases it, as a Word file with an evidence appendix for the office. |
| **1:11–1:20** Demo · whole site | AI Manager: "Check today's progress and safety" → workflow steps tick, plan vs actual; 3D twin flies to the pile row | And the AI site manager watches the whole site: which piles fall behind, where, and why, every finding linked to its source. |
| **1:20–1:45** Technical approach | Architecture diagram, builds in 4 beats (below) | Under the hood: voice, photos, emails and schedule rows become evidence chunks with stable IDs. Claude proposes each field, but code enforces the rules: no valid citation or low confidence means no value. Computed values come from Python, and personal data is masked before any model sees it. |
| **1:45–1:55** Result + team | 6 % tile (Rechnungshof BW) · logo · Team Apex · repo URL | On new builds, six percent of building cost runs through Nachträge. BauBuddy makes sure they're filed, with proof, on time. We're Team Apex. |

**German dictation** (recorded separately, ~8 s, a real voice):
> *Pfahl sieben: um elf Uhr dreißig bei vier Meter auf Fels gestoßen, laut Baugrundgutachten erst ab neun Meter erwartet. Bohrzeit sechs Stunden statt zwei.*
Subtitle: *Pile 7: hit rock at 4 m at 11:30, the soil report expected it only from 9 m. Drilling took 6 hours instead of 2.*
(Tested live with Fable 5.2 on 21.11.: this wording fills the time; "heute 11:30" did not.)

The time is in the sentence on purpose: then the one thing BauBuddy has to ask is the drilling log
("Is there a formal drilling log for pile 7? So far there's only the Polier's list."), which is the best on-camera
proof that it asks instead of guessing. The answer typed on screen: *"Bohrprotokoll Nr. 7 vom 17.11.2026 liegt vor."* (the field wants a reference to a document;
a plain "yes, it exists" was rejected in a test, which is the guardrail working).

### Claims check (only what the prototype does today)
| Claim in the VO | Where it's true |
|---|---|
| Local Whisper transcribes | `core/stt.py`, `STT_PROVIDER=local` (faster-whisper) |
| Claude extracts the fields | `LLM_PROVIDER=anthropic`, `claude-fable-5-2` (hackathon tokens) via `core/llm_adapter.py` |
| Source down to page / voice seconds | refs `doc:bgg@p14`, `audio:<id>@4-11` (README "Evidence refs") |
| Empty + question instead of a guess | citation + `CONFIDENCE_THRESHOLD` gates in `core/llm_extract.py` |
| Only the click releases it | `POST /api/docs/{id}/status`, user click only |
| Word file with evidence appendix | `GET /api/docs/{id}/docx` |
| Which piles fall behind | live plan alerts (e.g. "Bohrpfähle Achse 1: 2.0 Arbeitstage Verzug" on 21.11.). Delays come from today's date and the live weather, so the VO names no number |
| Computed values in Python, PII masked | `derived` fields, `sanitizer.mask` before every LLM call |
| 6 % of building cost via Nachträge | Rechnungshof BW, Denkschrift 2020, Beitrag 17 (new builds) |
The reviewer (second model) is **off** (`ENABLE_REVIEWER_LLM=false`), so the VO doesn't mention it.

### Architecture scene (1:20–1:45), 4 beats synced to the VO
```
CAPTURE                    EVIDENCE                     CLAUDE + RULES IN CODE              HUMAN            OUTPUT
voice → Whisper (local)  ┐                              Claude proposes fields               check, lock,     Word / PDF
photos → RF-DETR         ├→ chunks with stable IDs ──→  ✓ cites an ID from this request ──→  click        ──→ + evidence appendix
emails .eml / .ics       │   audio:id@4-11              ✓ confidence ≥ 0.6
schedule, Gutachten PDF  ┘   doc:bgg@p14 · drill:P07    ✓ derived values in Python · PII masked
```
Stack strip: FastAPI · Python · YAML document registry · Claude Fable 5.2 · faster-whisper · RF-DETR · vanilla JS · Three.js · Leaflet · python-docx

## Workflow (who does what)

| # | Step | Who | Tool | Status |
|---|---|---|---|---|
| 1 | Paste the hackathon Anthropic key into `Baubuddy-app/backend/.env` (`LLM_API_KEY=`) | Christo | editor | **blocking** |
| 2 | Record the German dictation, ~8 s, quiet room → WAV | Christo (or a teammate) | phone / any mic | **blocking** |
| 3 | Dry run of the director with the key; tune the follow-up answer to the question Fable actually asks | Claude | `director.js` | after 1+2 |
| 4 | Record 2–3 takes (headless, no voice, 30 fps frames) | Claude | `npm run record` | after 3 |
| 5 | Export deck slides 2–4 to MP4 with Morph | Claude | PowerPoint `CreateVideo` | ready to do |
| 6 | Build architecture + close scenes, same design as the deck | Claude | `scenes.html` → frames | ready to do |
| 7 | Read the voiceover, **one WAV per scene** (10 files), 2 takes each | Christo | Audacity / phone | after script lock |
| 8 | Assemble: slides + demo + VO + dictation + "x s later" labels + zooms + burned subtitles, length check | Claude | `build_video.py` (ffmpeg, ffprobe) | after 4–7 |
| 9 | Watch, one fix round, export `BauBuddy_Demo.mp4` (1080p30, −14 LUFS) | both | | Sun morning |
| 10 | Script becomes the base of the 3 min final pitch + Q&A list | Claude | `SPEAKER_NOTES.md` | after submission |

## Before every take (the director does most of this)
- Demo reset → "Load demo data" → no old chat messages, no stale drafts.
- Badge in the header reads **LLM**, not "rules fallback".
- Nothing private on screen: no `.env`, no keys, no e-mail addresses, no OS taskbar (headless capture has none).
