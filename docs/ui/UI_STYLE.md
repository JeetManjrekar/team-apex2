# BauBuddy · UI Style (binding for W3)

Owner of design decisions: Christo. Implementation: W3 in `frontend/` (owner files per BUILD_PLAN §4).
Visual references: `reference/ui_concepts_glass.html` (variant A "Frost" = default), `reference/dashboard_concept.html`,
screenshots `reference/concept_A_frost.png`, `reference/dashboard_frost.png`.

## 1. Direction in one sentence
Clean, calm iOS glass: a professional work tool that construction people trust. Light by default, one accent colour,
documents look like paper, effects only where they carry meaning.

## 2. What changes from the current "cinematic command centre"
| Current | New |
|---|---|
| Dark only, orange #ff6a2b + cyan + violet | **Light "Frost" default**, dark "Graphite" as optional theme; **one accent: safety yellow** |
| Animated aurora, moving grid, flowing header line, splash screen | **Static** soft background gradient, no looping animation; splash off by default |
| English labels | **German labels** everywhere the user sees text |
| 9 top tabs | **5 primary tabs + "Mehr"** (section 6) |
| Documents rendered on glass | Document body on **opaque white paper**; glass only for chrome (header, nav, cards, chips) |

Keep: glass cards, rounded corners, Inter/system font, the 3D site twin (as a dark "map panel" inside the light UI is fine).

## 3. Design tokens (put in `:root`, dark theme under `[data-theme="dark"]`)
```css
:root{
  /* surface */
  --bg: linear-gradient(140deg,#e9eef5 0%,#dfe6ef 45%,#eef1f4 100%);
  --glass: rgba(255,255,255,.58);   --glass-strong: rgba(255,255,255,.74);
  --stroke: rgba(255,255,255,.80);  --hair: rgba(20,24,33,.08);
  --paper: #ffffff;                 --chip: rgba(255,255,255,.75);
  --blur: blur(24px) saturate(170%);
  --shadow: 0 10px 30px rgba(30,40,60,.10), inset 0 1px 0 rgba(255,255,255,.9);
  /* text */
  --ink: #16181d; --mut: #5d6575;
  /* accent + states */
  --acc: #ffcc00; --acc-ink: #1b1b1b; --acc-shadow: 0 6px 16px rgba(255,190,0,.32);
  --ok: #1f9d55; --warn: #d97706; --bad: #d93848;
  /* status */
  --st-draft-bg: rgba(120,128,140,.18);  --st-draft: #5d6575;   /* Entwurf */
  --st-checked-bg: rgba(31,157,85,.16);  --st-checked: #1f9d55; /* Geprüft */
  --st-sent-bg: #1d2027;                 --st-sent: #ffffff;    /* Weitergegeben */
  /* shape + type */
  --r: 20px; --r-sm: 14px; --r-pill: 999px;
  --font: "Inter",-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,sans-serif;
}
[data-theme="dark"]{
  --bg: radial-gradient(1300px 800px at 15% 0%,#2a2f3a,#14161c 55%,#0d0e12);
  --glass: rgba(40,44,54,.58); --glass-strong: rgba(52,57,69,.64);
  --stroke: rgba(255,255,255,.12); --hair: rgba(255,255,255,.09);
  --paper: #f7f7f5; --chip: rgba(255,255,255,.08);
  --shadow: 0 16px 40px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.08);
  --ink: #f2f4f8; --mut: #9aa3b3; --ok:#3ddc84; --warn:#ffb020; --bad:#ff5a6e;
  --st-sent-bg:#f2f4f8; --st-sent:#111;
}
```
Glass primitive: `background:var(--glass); backdrop-filter:var(--blur); border:1px solid var(--stroke); border-radius:var(--r); box-shadow:var(--shadow)`.
Theme switch: small toggle in the header, persisted in `localStorage` (wrap in try/catch). Respect `prefers-reduced-motion`.

## 4. Rules
1. **Yellow only for**: the primary action per screen (Senden, Prüfen, Übernehmen), the mic button, the user's own chat bubbles, progress bars. Never for warnings (warnings = amber/red).
2. **Text sizes**: body ≥ 15 px laptop, ≥ 16 px phone; card titles 15 to 18 px; KPI numbers 30 to 36 px. Readable in a 1080p screen recording.
3. **Contrast**: text on glass must stay WCAG AA (check light theme especially on the blurred gradient).
4. **Motion**: only short transitions (150 to 250 ms) on hover, tab switch, card appear. No infinite animations.
5. **Status labels** always German: draft → **Entwurf**, checked → **Geprüft**, sent → **Weitergegeben** (map in the frontend; API values stay English).
6. **Icons by evidence kind**: chat/voice 🎙 (`msg-`), photo 📷 (`photo-`), mail ✉ (`mail-`), calendar 📅 (`cal-`), schedule 📊 (`sched-`), client document 📄 (`gutachten-`, `lv-`), crew 👷 (`crew-`).

## 5. Components
- **Chat bubble**: user = yellow, assistant = glass. Assistant can contain: document card (title, status pill, completeness bar "7/8 Pflichtfelder", "Öffnen"), follow-up question with quick-answer chips, proposal card (Übernehmen / Verwerfen), small timing badge "verarbeitet in 6,2 s" if available.
- **Composer**: camera button, paperclip, text field, **mic as the biggest button (≥ 48 px, yellow)**.
- **Field row** (document view): label + value + **source chip** (icon + locator, e.g. "📄 Gutachten S. 14", "🎙 0:02") → tap shows quote/excerpt. States: low confidence = amber outline + "unsicher, bitte prüfen"; missing required = red outline + "fehlt · Rückfrage offen"; locked = 🔒 "von dir geändert"; proposal pending = inline card "KI-Vorschlag: … [Übernehmen]"; reviewer running = spinner "wird geprüft".
- **Status bar**: segmented stepper Entwurf → Geprüft → Weitergegeben; buttons "Prüfen" (primary), "Weitergeben" (in-page confirm, no `window.confirm`), "Word", "PDF".
- **Document paper**: white, subtle shadow, footer "Entwurf mit KI-Unterstützung erstellt, geprüft von …".
- **Tiles**: glass cards in a CSS grid, title row (15 px, semibold) + optional hint right.

## 6. Navigation
Primary (laptop top nav, phone bottom tab bar ≤ 768 px):
1. **Assistent** (chat + current draft side by side on laptop)
2. **Dokumente**
3. **Dashboard** (new, section 7)
4. **Baustelle** (Site twin and Karte as a segmented switch inside)
5. **Fotos**
6. **Mehr** → Zusammenfassungen, Live-Kamera, Metriken (detail table), Plan & Ist (detail table)

Header: logo + "BauBuddy", project name, LLM/Roboflow badges (smaller), theme toggle, "Demo laden" / "Zurücksetzen" moved into a small overflow menu (still reachable for the demo). Autopilot stays but secondary.

## 7. Dashboard (structure from `reference/dashboard_concept.html`, data from THIS repo's API)
Read top to bottom as three questions:
1. **Was braucht mich?**
   - KPI strip (4): "Warten auf dich" (drafts + open proposals), "Nachträge in Vorbereitung" (Nachtragsmeldung drafts + completeness), "Größter Verzug" (max delay from plan), "Schreibzeit gespart" (metrics, labelled as assumption if baseline is an assumption).
   - **Heute zu entscheiden**: one list merged in the frontend from `GET /api/docs` (status draft), `GET /api/replan/proposals`, plan alerts from `GET /api/plan`; each row has its action inline.
2. **Was ist das Risiko?**
   - Wichtigste Warnung: top alert from `GET /api/plan` incl. weather/frost, "Brief übernehmen" via `POST /api/plan/propose`.
   - Bauzeitenplan: critical activities with delay from `GET /api/plan`.
   - Optional: map thumbnail linking to Baustelle.
3. **Ist es belegt?**
   - Nachtrag Belege: evidence checklist of the open Nachtragsmeldung (`GET /api/docs/{id}`).
   - KI-Leistung: `#metricsTile` via `GET /api/metrics/summary` (end to end, per stage, accuracy, cost per document; assumptions labelled).
   - Verlauf: documents incl. corrected versions (edit log).
No new backend endpoints. If a number is not available yet, show "––" with a hint, never a fake value.

## 8. Phone (≤ 768 px)
Bottom tab bar, chat full height with sticky composer, document view as full-screen sheet, field source as tap-to-expand, no horizontal scroll, `100dvh`, test at 375 px.
