# BauBuddy · Pitch deck plan (Challenge B, 3 min + Q&A)

Format facts (challenge handoff §4b): 2–3 min pitch, ~2 min Q&A. Jury = construction people + organisers who asked for metrics.
The live demo is the product proof, so the slides only do three jobs: **who we are, why it hurts, what we built**. Then demo, then a Q&A slide that stays on screen.

## Run of show (3:00)

Decided order: **story first (cold open), team as the handover right before the demo.**

| # | Slide | Time | One-line message | Visual / effect |
|---|---|---|---|---|
| 1 | **Title** (holding) | before the timer | BauBuddy. Your buddy on site. | Big orange tile logo, blueprint grid, orange glow. Morph → logo flies to the corner on slide 2 |
| 2 | **11:30 · Pfahl 7** (story) | 0:00–0:20 | The partner's own case: the pile hits rock at 4 m, the Gutachten said sand and gravel to 9 m. | Ground cross-section built from shapes; drill pile grows down on click, red impact at 4 m, "Gutachten S. 14" callout |
| 3 | **The gap** | 0:20–0:30 | The site produces the evidence. It never reaches the Nachtragsmanager. No documentation, no Nachtrag, money lost. | Site (photos, voice, daily reports) ← broken dashed line → Office (Nachtragsmanager). Morph → the broken line becomes a solid orange bridge on slide 4 |
| 4 | **BauBuddy** (solution) | 0:30–0:43 | Speak or snap on site. A draft notice with a source on every field. You check, nothing leaves without your click. | Bridge line with logo in the middle, 3 steps, abstract evidence-chain graphic (no screenshot) |
| 5 | **Team Apex** | 0:43–0:50 | Christo Teresof, Jeet Manjrekar, Karim Keraani, Aaditya Salunke. | "Team Apex" in orange, 4 cards with initials + name only |
| 6 | **Live demo** | 0:50–0:55, demo to 2:25 | (talk over the app) | "LIVE" with a red dot and three short cards: source, question, your click |
| 7 | **Value** | 2:25–2:45 | What BauBuddy brings back per 10 M€ contract. | Native column chart (30 / 60 / 120 k€ scenario) + 3 sourced stat tiles: 6 % Nachträge, 30 % reporting time, 48 % rework from poor data |
| 8 | **Q&A** (closing) | 2:45–3:00 → Q&A | The ask: a pilot site. | Logo, 3 trust chips, "Questions?". Stays up during Q&A |

## Backup slides (after the Q&A slide, only shown when a question needs them)

| # | Slide | Answers the question |
|---|---|---|
| A1 | How it works | "What happens under the hood?" capture → evidence IDs + confidence gate → follow-up → review → Word/PDF |
| A2 | Trust by design | "Does the AI make things up? Legal? Data protection?" |
| A3 | Beyond notices | "What else does it do?" plan vs actual + frost warning, dashboard, site twin (3 screenshots) |
| A4 | Measured, not claimed | "How fast / what does it cost?" numbers from `/api/metrics/summary` only, `[MEASURED: …]` until feature freeze |
| A5 | Roadmap & ask | "What's next?" only ❌/⚠️ items from BUILD_PLAN §1 |

## Rules applied
- No invented numbers. Value slide: audited/sourced figures only; the lost-Nachtrag share (5/10/20 %) is a labelled scenario. Prototype metrics are placeholders `[MEASURED · …]` (backup slide 12).
- German document names stay German with an English gloss on first use.
- Voice: Chrome speech today; local Whisper is the planned default (roadmap), cloud STT opt-in.
- PDF: currently the browser print view; LibreOffice PDF file is on the roadmap unless W1 lands it.
- Theme: dark Graphite + safety orange `#ff7a00`, glass cards, 20 px radius. Font: Helvetica Neue (on every Mac, closest system match to Inter).

## Text rule
As little text on the slides as possible: no roles, headings only, the spoken script carries the detail.
