# BauBuddy – live demo script ("A day in the life of a site manager")

Runtime about 3 minutes. The assistant answers in two or three spoken words; details stay on screen. Everything on screen runs live against the real backend: speech to text, the LLM pipeline,
the photo detector output, the schedule maths, the weather alert and the PDF export.

## Before you go on stage (5 minutes)

1. Start the server: `cd backend && .venv/bin/uvicorn app:app --port 8000`
2. Open http://127.0.0.1:8000 in Chrome, full screen (Cmd+Ctrl+F), zoom 100 %.
3. Turn the laptop volume up: the voice note plays out loud and the assistant answers by voice.
4. Do one dry run: click **▶ Real Time Preview**, then **Start the day**. Let it finish once so Groq is warm.
5. Click **▶ Real Time Preview** again right before you present. It resets the site to a clean state each time.

Needs internet (Groq for the LLM and speech, Open-Meteo for weather). Roboflow is not needed for the story: the
stored detections are replayed.

## Phone finale: "try it yourself" (20–30 s, after the story)

Setup (before going on stage, server already running):
1. Second terminal: `cd backend && ./scripts/phone_tunnel.sh`. Wait for "Phone page: https://…".
2. Laptop: ⋯ menu → **📱 Phone app (QR)** shows the QR code. Keep it ready in a tab.
3. Optional: click **📍 Locate me** in the header. Right-click it to choose **Simulate on site** (the demo site is fictional).

On stage: show the QR. A judge scans it, taps **Share** (location) and holds the orange button:
"A dump truck tipped over near Achse 2". The laptop pops up the incident, the phone appears as "📱 Site phone"
in the 3D twin, and a photo taken on the phone lands on the site plan. Stop the tunnel with Ctrl+C afterwards:
anyone with the link can use the app while it runs.

Phones need HTTPS for the microphone and GPS, which is why the tunnel is required. iPhones may strip GPS from
browser photos; the page then uses the phone's live position instead.

## Controls while it runs

| Key | Action |
|---|---|
| Space | pause / resume (use it when a judge asks something) |
| → | skip to the next scene |
| Esc | stop |

## What to say, scene by scene

Speak over the chapter cards. Each card stays about 3 seconds; the scene's result then stays on screen about 7 seconds.

| Clock | On screen | Say |
|---|---|---|
| Start card | "A day in the life of a site manager" | "Site managers spend up to half their day on paperwork. This is Markus, site manager of a bridge rebuild. Here is his day with BauBuddy. Everything runs live." |
| 07:00 | AI Manager answers the morning briefing | "One question gives him the schedule status, a safety check of today's photos and the weather risk. Before, that was three phone calls." |
| 07:25 | Incident popup → 3D twin flies to the zone | "Our fine-tuned RF-DETR detector found an excavator parked in the site facilities area. GPS from the photo places it in the digital twin. A person confirms it; the AI never decides alone." |
| 10:05 | Typed sentence → delay notice, follow-up question | "The excavator breaks down. Markus types one sentence. BauBuddy drafts the formal Behinderungsanzeige, and asks for the one fact it can't know: how long. It never invents a value." |
| 11:20 | Voice note plays, transcript, change order | "Now he hits rock at pile 7, five metres higher than the soil report said. He's on the rig, so he speaks. The change order cites the soil report page, the foreman's drilling list, and the drilling time ratio is computed in Python, not guessed by the model." |
| 11:30 | Document with source chips | "Every field shows where it came from. No source, no value. If he edits a field, it is locked against the AI." |
| 13:10 | Email summary | "The client emails with a deadline. Personal data is masked before any model sees it. The deadline becomes an open item." |
| 14:30 | Frost alert → notice of concern | "BauBuddy compares plan and forecast: concreting on Monday at minus three degrees. It drafts the notice of concern proactively. It does not send it." |
| 15:30 | "Geld & Zeit" panel, top-3 ranking, "Umsetzung annehmen" clicked | "This is the money a site loses in silence. Pile 7: about 24 k€ of change-order potential, documented the same day. The breakdown: 3,900 € avoided by moving the crew. Widerlager 1: 17 k€ of delay risk, visible before it happens. Measured hours times internal rates, always with a range, and never in an outgoing letter." |
| 16:30 | Daily report | "The daily report normally takes 45 minutes at the end of the day. Here it is built from weather, progress, photos and today's notices." |
| 16:50 | Mark as checked → PDF | "Markus checks it and exports. The PDF carries an evidence appendix for every field and says it was drafted with AI and checked by him." |
| 16:53 | Big 3D flyover: whole site → Widerlager 1 → Achse 1 → site | "Everything you saw today is pinned to the site: every marker has a photo or a document behind it." |
| 16:55 | Animated phone + live QR code | "No install, no login: scan it, hold the button, talk. It shows up here live." (Press Space to keep the QR on screen while a judge scans.) |
| 17:00 | Finale with numbers | "Four documents, every field with a source, nothing sent without his click. About four hours of paperwork in roughly a minute of AI time. Markus goes home on time." |

Then: "Happy to show anything live: ask it a question, or upload a photo."

## If something goes wrong

| Problem | Do this |
|---|---|
| A scene shows "This step failed" | Press → and keep talking; the other scenes are independent. |
| No sound | Keep going; the transcript appears on screen. |
| Groq rate limit / no internet | Stop with Esc and use the tabs by hand: Documents already holds the drafts from the dry run if you skip the reset. |
| 3D twin blank | Chrome: Settings → System → "Use graphics acceleration" on. The 2D plan on the AI Manager tab still works. |

## Questions judges are likely to ask

- **"Is this legal advice?"** No. It drafts; the site manager reviews. No pricing, no entitlement assessment. The footer says so on every document.
- **"What if the AI hallucinates?"** A field is kept only if it cites a source that was in the request and its confidence is above the threshold (0.6). Otherwise it stays empty and becomes a follow-up question. Numbers like the drilling ratio are computed in code.
- **"Data privacy?"** Emails, phone numbers and IBANs are masked before every LLM call. Speech to text can run fully offline (faster-whisper).
- **"Does it work in German?"** Yes. Switch in the ⋯ menu; documents are German formal letters (VOB/B) either way.
- **"Where are the time figures from?"** The manual minutes are team estimates per document type and are labelled as such. The AI time is measured on each run and logged per pipeline stage (Metrics tab).
- **"What did you train?"** RF-DETR Small fine-tuned on construction equipment (excavator, dump truck, bulldozer, person, car), hosted on Roboflow.


## Pitch line with the measured demo numbers (COST_MODEL.md §10)

> "Today the site loses money in silence: rock nobody documents, machines nobody reassigns, delays nobody sees.
> With BauBuddy, pile 7 shows about **24 k€** of Nachtrag potential documented the same day (1.8 k€ already measured),
> the excavator breakdown costs **3.9 k€** less because the crew is reassigned, and the frost risk at Widerlager 1 is
> visible as **~17 k€** (+6.6 working days) before it happens. The paperwork took minutes instead of 90."

Numbers come from GET /api/costs and change with the data; the rates are assumptions until the partner confirms them
(`backend/.env`: COST_RIG_EUR_H, COST_CREW_EUR_H, COST_STANDBY_EUR_H, COST_SITE_OVERHEAD_EUR_DAY, …).
