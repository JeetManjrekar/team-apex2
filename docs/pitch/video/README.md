# Demo video toolkit

Builds the 2-minute submission video from the **real running app**: a director script drives BauBuddy like a user
and records 1080p frames; slides and scenes are rendered separately; ffmpeg assembles everything with the voiceover,
"N s later" labels on cut waiting time, zooms and burned-in subtitles. Plan, script and claims check: [`../VIDEO_PLAN.md`](../VIDEO_PLAN.md).

## Files
| File | Role |
|---|---|
| `director.js` | Film autopilot (Playwright + installed Chrome). Resets the app, restores seed site data, plays the dictation WAV into Chrome's fake mic, opens sources, answers follow-up questions, clicks *Mark as checked*, shows the evidence appendix, AI Manager, 3D twin. Writes `raw/take_<time>/` (frames, `frames.ffconcat`, `markers.json`) |
| `director.config.json` | App data path, typed fallback text, source patterns, answers per missing field key, hold times |
| `export_slides.ps1` | PowerPoint renders deck slides 2–4 (Morph + timed builds) → `raw/slides_2-4.mp4` |
| `scenes.html`, `scenes.js` | Time-driven architecture (25 s) and closing (10 s) scenes → `raw/scene_*.mp4`. `preview.js arch:12` screenshots a moment |
| `script.json` | Voiceover lines (one WAV each in `vo/<id>.wav`) and the German dictation + subtitle |
| `vo/src/` | Voiceover MP3s from Christo's ElevenLabs clone (eleven_v4), one per line, plus `dictation_de.mp3`; `build_video.py` derives the WAVs |
| `build_video.py` | Cuts the take by its markers, pads beats to their voice line, labels cuts, zooms, mixes voice + dictation, subtitles, loudnorm −14 LUFS → `out/BauBuddy_Demo.mp4`, refuses > 115 s |
| `raw/`, `out/` | Generated, gitignored |

## Re-render (Windows, ~10 min)
Prerequisites: Node 18+, Python 3 (`py`), ffmpeg on PATH, Chrome, PowerPoint; the app running on :8000 with a working
`backend/.env` (see `BauBuddy_Submission/3_repo/README.md` for the settings used).
```
npm install
cd ../src && npm run assets && set DECK_FONT=Segoe UI&& node deck.js && py fx.py ../BauBuddy_Pitch.raw.pptx anim.json ../video/raw/deck_segoe.pptx && del ..\BauBuddy_Pitch.raw.pptx && cd ../video
powershell -File export_slides.ps1 -Durations 11.5,5.0,9.0 -StoryClicks 0.6,3.4,6.2
node scenes.js
node director.js raw/dictation.wav           # one live take (~2 min); check the header badge says claude-fable-5-2
py build_video.py --dictation raw/dictation.wav
```
- Rehearsal without audio: `node director.js --typed`. Pacing check without real voice: `py build_video.py --placeholder-vo` (Windows TTS).
- A take that shows "rules fallback" or a refused *Mark as checked* is not usable: re-run the director.
- `raw/dictation.wav` must be 16-bit PCM; the director reads its length from the RIFF `data` chunk. Make it from the MP3:
  `ffmpeg -i vo/src/dictation_de.mp3 -af "adelay=500,apad=pad_dur=0.6" -ar 48000 -ac 1 -c:a pcm_s16le raw/dictation.wav`
- Close the MP4 in any player before rebuilding (the builder writes a temp file and falls back to `BauBuddy_Demo_new.mp4` if the old one is locked).

## Honesty rules baked in
Only waiting time is cut, and every cut is labelled. The take is never edited otherwise. Lines claim only what the
prototype does today (see the claims table in `VIDEO_PLAN.md`); the reviewer LLM is off, so the voiceover doesn't mention it.
