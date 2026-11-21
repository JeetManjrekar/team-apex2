# Pitch deck · handoff for the next session (state 21.11.2026, evening)

Paste into a new Claude Code session: *"Read docs/pitch/HANDOFF.md and continue the BauBuddy pitch deck from there."*

## What exists
| File | What it is |
|---|---|
| `BauBuddy_Pitch.pptx` | The deck: 13 slides (8 pitch + 5 backup), dark Graphite + safety orange, Morph transitions, entrance animations |
| `BauBuddy_Pitch_backup.pdf` | Static fallback (no animations), e.g. for a Windows laptop |
| `SPEAKER_NOTES.md` | The timed 3:00 script, demo click-list, value-slide sources, Q&A answers. The same text is in each slide's presenter notes |
| `DECK_PLAN.md` | Slide plan, timings, rules applied |
| `src/` | Build: `assets.js` (icons, glow, background, logo → `src/assets/`), `deck.js` (pptxgenjs, all slide content + notes), `fx.py` (injects Morph + animations into the slide XML), `apply_theme.js`, `brand/` (logo SVGs) |
| `img/` | App screenshots (dark theme), reference only; the deck does not use them on purpose |

## Rebuild
```
cd docs/pitch/src
npm install          # once (pptxgenjs, sharp, react-icons …, exact versions pinned)
npm run build        # assets + deck → ../BauBuddy_Pitch.pptx
```
Needs Node ≥ 18 and python3 (stdlib only). Close the .pptx in PowerPoint before rebuilding.
Visual check (optional): LibreOffice → PDF. On macOS, Homebrew LibreOffice can't see the system fonts, so point fontconfig at
`/System/Library/Fonts` (`FONTCONFIG_FILE` with a `<dir>` entry). Otherwise text renders as serif. Validate with the pptx skill's `validate.py`.

## Decisions already made (don't re-litigate)
- **Order:** Title (holding, before the timer) → Story "Pile 7 hits rock at 4 m" (cold open, 3 clicks) → Gap → Solution (broken line morphs into the orange bridge) → Team → LIVE → *demo* → Value → Q&A. Backup slides 9–13: How it works, Trust, Beyond notices, Measured, Roadmap & ask.
- **Timing:** slides 1:30 in total (0:55 before the demo, 0:35 after), demo 1:30 (0:55–2:25).
- **The deck complements the demo, it never replicates it:** no app screenshots, no step-by-step demo route on the slides.
- **As little text as possible:** headings only, no roles. The spoken script carries the detail.
- **Team:** "Team Apex" in orange; Christo Teresof, Jeet Manjrekar, Karim Keraani, Aaditya Salunke (initials + names only).
- **Value slide (7):** column chart of 30 / 60 / 120 k€ recovered per 10 M€ contract = 10 M€ × 6 % Nachträge × 5/10/20 % lost. The 6 % is sourced; the lost share is a **labelled assumption** that the pilot measures. Stat tiles: 6 % (Rechnungshof BW Denkschrift 2020, new builds), 30 % (IW-Kurzbericht 94/2025, managers' reporting time), 48 % (FMI/PlanGrid 2018, rework from poor data). Full links in SPEAKER_NOTES.md.
- **Rule:** never invent numbers. Prototype metrics come only from `GET /api/metrics/summary` (live LLM mode, after the freeze).
- **Font:** Helvetica Neue (on every Mac). Present from a Mac in PowerPoint 2019/365 for Morph. On Windows, use the PDF or switch the font in `deck.js` (`const F`).

## Open items
1. **Demo driver:** pick a name and replace `[name]` in `SPEAKER_NOTES.md` and `src/deck.js` (notes of slides 5, 6 and 8), then rebuild.
2. **Backup slide 12:** replace the four `[MEASURED · …]` with real numbers from `/api/metrics/summary` after the freeze.
3. **Backup slide 13:** if Whisper STT, Outlook import, the PDF file export or the crew replanner landed, move them off the roadmap.
4. **Check once in real PowerPoint:** Morph transitions and animations were validated structurally but not watched in PowerPoint yet.
5. Dry run with a stopwatch, with the demo running on the app (`w3_frontend` branch, port 8000, "Load demo data").

## Submission (state 21.11.2026, 22:30) · deadline Sun 22.11. 12:00, Tally
The written submission is separate from the live deck. Everything ready to send sits in
`D:\projects\Hackathon\TUM.ai construction\BauBuddy_Submission\` (see its `SUBMISSION.md`).
- **Demo video v1 done** (1:54): built by the toolkit in `docs/pitch/video/` (README there), plan + script + claims check in `VIDEO_PLAN.md`.
  Voiceover = Christo's ElevenLabs clone; demo = live run of `integrate-all-3` with Claude Fable 5.2. Waiting for team feedback.
- **7-slide PDF**: outline in `BauBuddy_Submission/2_pitch_deck_pdf/README.md`, not built yet.
- **Repo**: needs the patch in `BauBuddy_Submission/3_repo/` (Fable 5.2 request params, UTF-8 JSON on Windows), must be public, then frozen.
- `src/deck.js` now reads `DECK_FONT` (default unchanged: Helvetica Neue); the video uses a Segoe UI render.

## Context sources
- `docs/pitch/PITCH_DECK_HANDOFF.md`: original brief for the deck.
- Challenge brief and partner transcripts: `challenge2_handoff_prompt.md` (was in ~/Downloads on the MacBook; copy it into the repo or the vault if needed).
- `README.md`, `BUILD_PLAN.md` (§1 audit of what really works), `docs/ui/UI_STYLE.md`.
