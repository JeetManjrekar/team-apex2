# Handoff prompt · BauBuddy pitch deck (paste everything below the line into a new Claude Code session)

---

You are building the **pitch deck (PowerPoint, .pptx)** for **BauBuddy**, Team Apex's entry in the **TUM.ai Construction
Hackathon, Challenge B**. Work in the repo at `/Users/Christo/Projekte/team-apex2`. **The UI the team demos is the orange glass UI on branch
`w3_frontend`** (worktree `.claude/worktrees/intelligent-engelbart-0b588a`, served on port 8000). The old orange
"command-centre" look on `main` is superseded, so don't take visuals from it. Plan first, then build.
Use the `pptx` skill to produce the file. Output: `docs/pitch/BauBuddy_Pitch.pptx`, plus `docs/pitch/SPEAKER_NOTES.md`.

## 1. Read before planning (source of truth, in this order)
1. `README.md`: features, architecture, "Human in control", the demo script ("a day in the life").
2. `BUILD_PLAN.md`: §1 audit (what really works ✅ vs ⚠️/❌), §2 guardrails, gates and timeline.
3. `docs/ui/UI_STYLE.md` and `frontend/css/glass.css` on `w3_frontend`: visual language of the app (the deck should feel like
   the same product).
4. Logo files on `w3_frontend` in `frontend/img/`: `logo.svg` (orange app tile), `logo-mark.svg` (icon only, orange
   lines), `logo-wordmark-dark.svg` / `logo-wordmark-light.svg` (tile + name, for dark / light backgrounds). Use these
   files, don't redraw them.
5. If the backend is running (`http://127.0.0.1:8000`), read `GET /api/metrics` and `GET /api/metrics/summary`. **These
   are the only numbers allowed in the deck.** If an endpoint is missing or empty, put a clearly marked placeholder
   `[MEASURED: …]` in the slide. Never invent or estimate a number.

## 2. The product in one breath
BauBuddy is an AI assistant for German construction site managers (Bauleiter / Polier). They speak, type, or take photos
on site. BauBuddy drafts the formal documents they owe the client (Nachtragsmeldung, Mehrkostenanzeige,
Behinderungsanzeige, Bautagesbericht and others, 7 types). **Every field carries a source**: a chat or voice quote, an
email, a photo, a schedule row, or a page in the client's geotechnical report. A field with no source stays empty and
BauBuddy asks a follow-up question. It also watches plan vs actual and warns early (delays, frost from the weather
forecast), summarises minutes and emails, detects objects in site photos (Roboflow) with GPS, and shows everything on a 3D
site twin. The site manager checks and decides. Nothing is sent automatically. Export to Word / PDF with photos and an
evidence appendix.

Positioning line (keep or improve): **"Your buddy on site. Evidence in, notices out, on time."**
The old working name was "Nachweis" (proof). Keep that idea: proof for every claim is the differentiator.

## 3. Brand
- Name is always written **BauBuddy** (capital B twice, one word).
- Logo: a hard hat sitting on a speech bubble with a check mark. That's site + assistant + verified evidence. In the app
  it sits as dark lines on an orange rounded tile.
- Colours (from `frontend/css/glass.css`): accent safety orange `#ff7a00`, like hi-vis vests and hard hats (text on orange is `#1b1b1b`; darker
  orange `#c2410c` for orange text on light backgrounds), dark "Graphite"
  surface `#14161c` / `#2a2f3a` with frosted glass cards, light "Frost" surface `#e9eef5` / `#ffffff` with text
  `#16181d`, muted `#9aa3b3` / `#5d6575`, status green `#3ddc84`, warning `#ffb020`, red `#ff5a6e`. Orange is for
  emphasis and primary actions only. Warning amber `#ffb020` is a status colour, not the brand colour.
- Pick one theme for the deck (dark Graphite recommended for a stage screen) and stay with it. Rounded corners (20 px
  cards), soft shadows, glass panels.
- Font: Inter (fallback: system sans). Large type, few words per slide, no bullet walls.

## 4. Proposed storyline (adjust after reading, ~10 slides, 3–5 min talk + live demo)
1. **Title**: logo, "BauBuddy · AI Site Manager", team, Challenge B.
2. **Problem**: site managers lose evenings to paperwork. Missed or late notices (Behinderungs-/Mehrkostenanzeige) cost
   real money because of deadlines and burden of proof. Use the partner's framing if the challenge brief has one.
   Don't put a statistic in without a source.
3. **Insight**: the hard part isn't writing text, it's *proving* it. Every claim needs evidence.
4. **Solution**: one sentence, with an app screenshot (header with logo, assistant + draft side by side).
5. **How it works**: capture (voice / chat / photo / email) → extraction with evidence ID and confidence gates →
   follow-up for gaps → human review (Draft → Checked → Sent) → Word / PDF. Draw it as a simple flow diagram.
6. **Trust by design**: evidence or empty, user edits are locked (AI input becomes a proposal), PII masked before any LLM,
   human-only status changes, no legal/pricing advice. This is the slide the judges remember.
7. **Beyond notices**: plan vs actual early warning, daily report from photos + notes + schedule + weather, site twin
   with geotagged photo detections. One screenshot each, at most three.
8. **Live demo**: the hero flow (see §5). A slide with a QR/URL and a 3-step outline, as a fallback if the demo fails.
9. **Measured, not claimed**: numbers from `/api/metrics/summary` only (per-stage latency p50/p95, voice→draft→PDF end to
   end, cost per document, extraction accuracy if `data/eval/report.json` exists). Label assumptions.
10. **Roadmap and ask**: what's next (only items marked ❌/⚠️ in BUILD_PLAN §1, framed honestly), and what we want from the
    partner (pilot site, document templates, feedback).

## 5. Demo to support (from README / BUILD_PLAN gate 14:30)
Voice "Pfahl 7 Fels bei 4 m …" + 2 photos → Nachtragsmeldung draft with Gutachten p.14 citation → one follow-up
answered → tap "source" on a field to show the quote → Checked → Word + PDF with photos and evidence appendix. Optional:
plan vs actual red piles → "Draft Behinderungsanzeige". The in-app **Autopilot** button runs a hands-free walkthrough,
which is the backup if live input fails.

## 6. Screenshots
Take them yourself with the browser tool from the running app (`http://127.0.0.1:8000`, click "Load demo data" first).
Port 8000 serves the `w3_frontend` worktree (orange glass UI); that's the one to screenshot. It has a theme toggle
in the header, so take screenshots in the theme the deck uses. Check that the header shows the **BauBuddy** tile
logo, not "Nachweis" or an "N" tile. Save screenshots to `docs/pitch/img/`.

## 7. Rules
- Only claim features marked ✅ in BUILD_PLAN §1 (or verified working in the app now). ⚠️ items need a caveat.
  ❌ items go on the roadmap only.
- No invented numbers, no invented customer quotes, no competitor claims you can't source.
- Cloud STT can't mask audio. If voice is shown, say local STT is the default (BUILD_PLAN guardrail 3).
- German document names stay German (Mehrkostenanzeige etc.), with a short English gloss the first time.
- Keep the deck editable: real text boxes, no slides that are just one flattened image.

## 8. Workflow
1. Read §1 sources, then write the plan (slide list with title, one-line message, visual, and data source) into
   `docs/pitch/DECK_PLAN.md`. Show it to the user and wait for an OK.
2. Collect screenshots and metrics.
3. Build the .pptx with the pptx skill, then render each slide to an image and check it visually (overflow, contrast,
   logo crispness).
4. Write speaker notes with timing per slide (total ≤ 5 min including a 90 s demo).
5. Report what's done, which numbers are still placeholders, and which screenshots need retakes after feature freeze.
