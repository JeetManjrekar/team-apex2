# BauBuddy · Pitch script (3:00)

**Budget:** slides 1:30 in total (0:55 before the demo + 0:35 after) · live demo 1:30.
Speaking pace is about 2.5 words per second, and every block is cut to fit its time. Read it out loud with a stopwatch once.
**[name]** = demo driver. Pick one person and write the name in.

---

## Slides · 0:00–0:55 (Christo)

**Slide 1 · Title** (holding slide, up before the timer starts). Say nothing. When the timer starts, click.

**Slide 2 · Pile 7 · 0:00–0:20 · 3 clicks**
> 11:30 on a bridge site. Pile 7 hits rock at four metres.
> *[click]* The client's soil report promised sand and gravel down to nine.
> *[click]* So every pile takes hours longer. That's extra work the company can claim back.
> *[click]* But only with proof, written down today. Nobody has time. No proof, no Nachtrag, money lost.

**Slide 3 · The gap · 0:20–0:30**
> That's Challenge B: the site has the evidence, photos, voice notes, reports. It never reaches the Nachtragsmanager, the one who turns it into money.

**Slide 4 · Solution · 0:30–0:43**
> BauBuddy closes that gap. Speak or snap a photo on site, and BauBuddy drafts the formal notice. Every field shows its source. No source? It asks instead of guessing. And nothing leaves without your click.

**Slide 5 · Team · 0:43–0:50**
> We're Team Apex: Christo, Jeet, Karim and Aaditya. [name], show them.

*([name] is already at the laptop.)*

**Slide 6 · Live · 0:50–0:55 ([name])**
> Three things to watch: the source, the question, the click.

→ switch to the app.

---

## Live demo · 0:55–2:25 ([name], talks while clicking)

| Time | Click | Say |
|---|---|---|
| 0:55–1:18 | **Speak** → say *"Pfahl 7, ab 4 Meter Fels, Bohrgerät kommt kaum runter"* → add 2 photos | "I talk like I would on site, in German. BauBuddy spots a possible Nachtrag and pulls in page 14 of the client's soil report." |
| 1:18–1:40 | Answer the follow-up → tap a **source chip** | "One detail is missing, so it asks me. It doesn't invent. And every value: one tap, and there's the exact quote." |
| 1:40–1:55 | **Mark as checked** → **Word** | "I check it, I decide. Word export with the photos and an evidence appendix, for the Nachtragsmanager. Same day, instead of never." |
| 1:55–2:20 | **Plan vs actual** → red piles + frost → **Draft Behinderungsanzeige** | "It also watches the schedule: piles three days behind, frost before the pour. One click drafts the Behinderungsanzeige. We see the delay on day one, not in month two." |
| 2:20–2:25 | Switch back to the deck → **slide 7** | (no talking, Christo takes over) |

**If you're running late:** at 1:55 skip the plan-vs-actual step and go straight back to the deck.
**If the mic or network fails:** type the sentence instead, or press **▶ Autopilot** in the header and narrate over it.

---

## Value · 2:25–2:45 (Christo, slide 7)
> What's it worth? On new builds, about six percent of building cost runs through Nachträge, according to the state audit office. If just ten percent of those get lost for missing proof, that's sixty thousand euros per ten million of contract. And managers spend about thirty percent of their week on reporting.

## Close · 2:45–3:00 (Christo, slide 8)
> Our ask: one live pilot site, so we measure the real number together. Thank you. Questions?

Slide 8 stays up for the whole Q&A.

### Where the value numbers come from (say this if asked)
| Number | Source |
|---|---|
| 6 % Nachträge on new builds (17 % on renovations) | Rechnungshof Baden-Württemberg, [Denkschrift 2020, Beitrag 17](https://rechnungshof.baden-wuerttemberg.de/fileadmin/Denkschriften/Denkschrift_2020_-_Beitrag_Nr._17.pdf): Landesbau projects, relative to approved total cost |
| ~30 % of a manager's working time on reporting and documentation | [IW-Kurzbericht 94/2025](https://www.iwkoeln.de/studien/andrea-hammermann-klaus-heiner-roehl-ein-tag-pro-woche-fuer-buerokratie.html): survey across all industries (managers ~30 %, employees ~23 %) |
| 48 % of rework from miscommunication and poor project data | [FMI/PlanGrid "Construction Disconnected" 2018](https://www.autodesk.com/blogs/construction/construction-disconnected-fmi-report/): US survey of 599 leaders, vendor-sponsored |
| 5 / 10 / 20 % of Nachträge lost for missing proof | **Assumption**, not a measurement. The chart is a scenario: 10 M€ × 6 % × lost share. The pilot measures the real share. |

Be upfront about the scenario: "The six percent is audited. How much of it gets lost is exactly what the pilot measures."

---

## Q&A · backup slides (type the number + Enter)
| Question | Slide | Two-sentence answer |
|---|---|---|
| Where's the money number from? | 7 | Six percent is the audited Nachtrag share on new builds. The lost share is a scenario; the pilot measures it. |
| Under the hood? | 9 | Our own LLM package extracts each field only with a valid evidence ID and enough confidence. Without a key, a rule-based fallback runs under the same rules. |
| Does the AI make things up? | 10 | No source, no value: the field stays empty and BauBuddy asks. Your own edits are locked and can't be overwritten. |
| Legal advice? | 10 | No. We check formal completeness against the template; the site manager and the Nachtragsmanager decide. |
| Data protection? | 10 | Emails, phone numbers and IBANs are masked before any text reaches an LLM. Voice runs on Chrome speech recognition today; local Whisper is next. |
| What else does it do? | 11 | Plan vs actual with weather warnings, daily reports from photos and notes, and a site twin with geotagged photos. |
| How fast, what does it cost? | 12 | We time every stage on the prototype; the numbers are on the slide. (Fill them in after the freeze.) |
| What's next? | 13 | A pilot on a live site, measured by Nachträge filed and writing time saved. |

Split: Christo answers domain and business questions, [name] answers tech.

## Before going on stage
- Fill in: `[name]` (demo driver) and the `[MEASURED · …]` values (slide 12).
- In the app: Reset → "Load demo data" → Assistant tab open, mic permission granted, dark theme.
- Present the .pptx in PowerPoint (Morph and the animations). Backup: `BauBuddy_Pitch_backup.pdf`.
- One full dry run with a stopwatch. If the demo runs long, cut plan vs actual, never the value slide.
