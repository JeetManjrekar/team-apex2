# BauBuddy – test pack

Ready-made inputs with the result each one should produce. Every case below was run on the demo data before writing
this; the "Expected" column is what the system produced, not a wish.

## Setup (once, then before each group)

1. Server running, open http://127.0.0.1:8000, language **English** (⋯ menu).
2. ⋯ menu → **Reset demo**, then ⋯ menu → **Load demo data** (clean site: 6 photos, 5 zones, 1 safety finding).
3. Go to **AI Manager**. Type into "Ask or command…", or attach audio with **📎 Files** and press Send.

Audio files are in `test_inputs/audio/`. `00_…` is a real human voice; the others were generated with the Mac's
built-in voices, so they are a little robotic but understandable.

**Language:** ⋯ menu → English or Deutsch, then Reset demo + Load demo data (or start ▶ Real Time Preview). The demo
loads in that language: English uses the `_en` duplicates of the demo files (place names **Abutment 1/2, Axis 1/2, Site
facilities**, project "Replacement road bridge BW 12 over the Mühlbach"); German uses the original files (**Widerlager 1/2,
Achse 1/2, Baustelleneinrichtung**). In English the inputs below can use either name ("Abutment 1" or "Widerlager 1").

**What may differ between runs:** the AI's wording and the exact number of filled fields (±2). The structure,
document type, key values and the money numbers in group E must match. The delay risk (E3) uses the live weather
forecast and can change from day to day.

---

## A. Notices from a few words (typed or spoken)

| ID | Input | Expected | Pass if |
|---|---|---|---|
| A1 | Type: `Excavator idle since 10 am due to hydraulic failure at Widerlager 1, crew of 4 waiting` | "✓ Draft ready: Delay / obstruction notice", chime + green pill. Fields: start **2026-11-17, 10 am**, location **Abutment 1** (German: Widerlager 1), cause **hydraulic failure**, client **State Building Authority**, contract **Construction contract no. 2026-117**. Asks **"How long will the obstruction presumably last?"** | Delay notice created, duration is asked, not invented |
| A1b | Answer: `about 2 days` | "✓ Expected duration. All filled in. Please review and approve." | Duration = "about 2 days", no new question |
| A2 | Audio: `00_real_voice_rock_pile7_en.m4a` | Transcript "…pile 7 at abutment 1, hit rock at 4 meters depth…". "✓ Draft ready: Change order notice". Fields: **rock depth 4**, **drilling time pile 4.6 h**, **reference piles 4 h**, **ratio 3**, crew hours 13.8, expected ground **Ground investigation report, page 14**. Asks **"Is there a drilling log for pile 7?"** | Change order notice; 4.6 / 4 / 3 come from the drilling list (computed, not guessed) |
| A3 | Audio: `01_excavator_breakdown_en.m4a` | Same as A1 (delay notice, Abutment 1, 10 am, asks duration) | Voice gives the same result as typing |
| A4 | Audio: `06_bagger_ausfall_de.m4a` (switch to **Deutsch** first) | "✓ Entwurf fertig: Behinderungsanzeige", Ort **Widerlager 1**, Beginn **17.11.2026, 10 Uhr**, asks "Wie lange wird die Behinderung voraussichtlich dauern?" | Whole answer in German |
| A5 | Audio: `04_defect_en.m4a` | "✓ Draft ready: Defect notice", location **Axis 1** (the voice says "Achse 1"), description "crack in the concrete wall…". Asks which company is responsible and the deadline | Defect notice with Achse 1 |
| A6 | Type: `I have concerns about concreting Achse 1 on Monday, the forecast says minus 3 degrees` | "✓ Draft ready: Notice of concern", location **Achse 1**. Asks when the concerns were identified | Notice of concern |
| A7 | Type: `Concrete delivery of 20 cubic metres arrived at 9:30` | "Noted in the site diary; it goes into the daily report." | **No** document created, only a diary note |
| A8 | Type: `Create today's daily report` | "Daily site report draft for 2026-11-17…". Fields: weather (rain showers, 12.5 mm), temperature **6 / 14 °C**, equipment (excavator, dump truck on 6 photos), work done **Bohrpfähle Widerlager 1… 4.6 m (P07: ab 4 m Fels)**, progress **76.6 / 96 m**. Asks which companies were on site | Daily report from data, staff left open |

## B. Questions to the AI Manager

| ID | Input | Expected | Pass if |
|---|---|---|---|
| B1 | Audio: `05_progress_question_en.m4a` (or type `Check today's progress and safety`) | "Bohrpfähle Widerlager 1 (8 × 12 m) is **1.2 days behind plan**. **1 safety issue**: Heavy equipment in a non-work zone (Baustelleneinrichtung)." Voice says only "One delay, 1 issue." | Short voice, details on screen |
| B2 | Type: `Are there any workers without safety helmets?` | "I can't verify helmets: the detector (RF-DETR Small) has no helmet or safety-vest class…" | Honest "cannot verify", no invented answer |

## C. Incidents in your own words

| ID | Input | Expected | Pass if |
|---|---|---|---|
| C1 | Audio: `03_incident_truck_en.m4a` | "Incident recorded as **high severity in Achse 2**…", red alert popup, alert sound, 3D flies to **Achse 2** | Incident with the right zone |
| C2 | Then type: `generate a report for it` | "I'm compiling the incident report." Report card with **PDF** and **Word**; PDF opens: incident card, site plan with orange ring on Achse 2, photos from that zone | PDF + Word exist and show Achse 2 |
| C3 | Audio: `07_unfall_de.m4a` (Deutsch) | "Vorfall mit hoher Priorität erfasst im Bereich **Widerlager 2**…" | German incident, zone Widerlager 2 |
| C4 | Audio: `08_no_incident_en.m4a` | Shows the existing safety finding; **no new incident** in the Incident feed | Not treated as an incident |
| C5 | Type: `A dump truck tipped over near axis 2, nobody hurt` | Incident in **Achse 2** ("axis" is understood as Achse) | English word for the zone works |

## D. Email summary

| ID | Input | Expected | Pass if |
|---|---|---|---|
| D1 | More → Summaries → **Sample email** → **Summarize** | English: "Pile 7 – next steps", **2 open items**, deadline **Monday** (German: "Pfahl 7 – weiteres Vorgehen", Montag), "Masked before AI: EMAIL_1, EMAIL_2, PHONE_1", box "Possible change order" | Contact data masked, deadline found |

## E. Money (Dashboard → "Money & time")

Do A1, A1b and then type `Pile 7 at Widerlager 1 hit rock at 4 m, drilling takes three times as long`, then open **Dashboard**.

| ID | Where | Expected | Pass if |
|---|---|---|---|
| E1 | Change order potential | **24 k€** (24,156 €), range **1,812 – 28,918 €**, top item "Change order P07 (W1)" with action **Request drilling log**. ⓘ shows "3.1 extra hours until 11:20 … × 594 €/h … = 1,812 € measured" | Exactly these numbers |
| E2 | Idle cost | "Idle cost avoidable **3,944 €**", "stoppage costs about **6,876 €**" (18 h × 150 €/h + 4 people × 18 h × 58 €/h). Click **Accept reassignment** → becomes "Idle cost avoided" | Numbers + the click changes the label |
| E3 | Delay risk | about **16.5 k€**, **+6.6 working days** for Widerlager 1, action "Check moving the concreting" (depends on the live forecast) | Positive delay risk with reasons |
| E4 | Paperwork time | e.g. "7 instead of 120 min", 2 docs | Shows minutes saved |
| E5 | Export guard | Open the delay notice → **PDF** and **Word** | **No € amount anywhere** in the files |

## F. Other features

| ID | How | Expected |
|---|---|---|
| F1 | Site → **✏️ Edit layout** → ＋ Add zone → drag a rectangle → name it "Material storage", type Storage → **Save layout** | "Layout saved"; new zone in the 3D twin and the zone list |
| F2 | Documents → delay notice → **Mark as checked** → **PDF** | Badge "CHECKED", site plan + plan-vs-actual chart in the PDF, evidence appendix |
| F3 | Header **📍 Locate me** (allow location) | "You · xx km SW ↙" at the edge of the 3D site; on the Map tab a pulsing blue dot. Right-click → Simulate on site |
| F4 | ⋯ menu → **Deutsch** | Whole interface German, including Dashboard money panel and AI answers |
| F5 | **▶ Real Time Preview** → Start the day | Runs about 3 minutes and ends with the summary screen |
| F6 | Phone: `cd backend && ./scripts/phone_tunnel.sh`, ⋯ → Phone app (QR), scan, hold the button and say "excavator broken at Achse 1" | Phone shows "✓ Draft ready", laptop chat updates |

## Automated tests

`cd backend && .venv/bin/python -m pytest tests -q` → **281 passed** (includes the cost model checks, the export guard
and the voice/location fixes).
