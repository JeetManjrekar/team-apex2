# Claude Code Prompt · BauBuddy frontend and UI (paste everything below the line)

How to use: open Claude Code in `~/Projekte/team-apex2` (the repo cloned from `JeetManjrekar/team-apex2`), paste the prompt. The design files are already in `docs/ui/`.

---

You are the frontend and UI engineer for Team Apex at the TUM.ai Construction Hackathon (Challenge B). The product is **BauBuddy**: an AI assistant for construction site managers. They speak, type and take photos; the assistant drafts German construction documents (Nachtragsmeldung, Behinderungsanzeige, Mehrkostenanzeige, Bautagesbericht …) with a source for every field, asks follow-up questions for gaps, warns about schedule deviations, and exports Word/PDF. The site manager checks and decides; nothing is sent automatically.

## Repository
Work **only** in this repository: `~/Projekte/team-apex2` (clone of `JeetManjrekar/team-apex2`, branch `main`). Before anything else run `git status` and `git log --oneline -5` and show me the result. Create and work on a new local branch `ui-glass`. Do not push unless I explicitly say so.

## HARD RULE: additive only, existing code stays untouched
- **Do not modify, rename, move or delete any existing file or line** in the repo (backend, frontend, data, docs, config). Existing code belongs to the other workstreams.
- **Only add new files** for the new UI/design work, for example:
  - `frontend/css/glass.css` (design tokens + overrides, loaded after `app.css`)
  - `frontend/js/ui-glass.js` (theme toggle, German labels, navigation regrouping, field-state styling hooks)
  - `frontend/js/dashboard.js` (new Dashboard tab, reads existing APIs only)
  - more new files if needed, each with a header comment "Team Apex UI layer, additive only"
- **The single allowed exception:** append exactly the include lines for your new files at the end of `frontend/index.html` (one `<link rel="stylesheet" href="css/glass.css">` in `<head>` and the new `<script>` tags before `</body>`). Add lines only; change or remove nothing else. Show me the diff of `index.html` before committing it.
- Everything else is achieved by **overriding and extending at runtime**: CSS overrides (cascade, higher specificity, `:root` variable re-mapping), JS that adds elements, wraps or observes the DOM (e.g. `MutationObserver` to translate dynamically rendered English strings), and new event handlers. Never monkey-patch backend behaviour, never change API calls of existing code.
- **No new backend endpoints and no backend files.** The new UI reads the existing API only. Missing numbers show "––" with a hint, never fake values.
- If something truly cannot be done additively, **stop and ask me**; do not edit an existing file to get around it.
- Commit only new files plus the `index.html` include lines. Before every commit run `git diff --stat main` and confirm that no existing file except `frontend/index.html` appears, and that its diff contains only added lines.

## Read first (in this order)
1. `docs/ui/UI_STYLE.md` (binding design spec: tokens, rules, components, navigation, dashboard)
2. `docs/ui/reference/ui_concepts_glass.html` and `docs/ui/reference/dashboard_concept.html` (variant A "Frost" is the default) plus the PNG screenshots
3. `BUILD_PLAN.md` (sections 2 guardrails, 4 ownership, W3, 7 timeline) and `README.md`
4. `frontend/index.html`, `frontend/css/app.css`, `frontend/js/app.js` (read only, to learn the IDs, classes and render functions you must style or extend), then skim `js/tile.js`, `js/fx.js`, `js/site3d.js`, `js/voice.js`, `js/replan.js`, `js/inbox.js`

## Constraints carried over
1. Keep every existing feature working: chat, mic, photo upload, document list/view, field edit/lock/undo/proposal accept, status change, Word export, print view, plan alerts, summaries, photos, site twin, map, live camera, metrics table, demo load/reset, autopilot.
2. Do not rely on renaming IDs; target existing IDs/classes (`#msgs`, `#inp`, `#send`, `#mic`, `#assistDoc`, `#docList`, `#docView`, `#voiceSlot`, `#inboxSlot`, `#replanSlot`, `#metricsTile`, `#twCanvas`, `.pill.draft|checked|sent`, `data-t`, `window.NW` …).
3. Guardrails stay visible: source per field, status only by user click, in-page confirm for "Weitergeben", footer "Entwurf mit KI-Unterstützung erstellt, geprüft von …", no prices or legal assessment.
4. German UI text, English code. Display mapping only (draft → Entwurf, checked → Geprüft, sent → Weitergegeben); API values unchanged.
5. Zero build: vanilla CSS/JS, no framework, no npm, local assets only.

## Work plan (show me a short plan first and wait for my OK)
1. **Baseline**: run the app (`cd backend && uvicorn app:app --reload --port 8000`, open http://127.0.0.1:8000, "Load demo data"). Screenshots at 1440 px and 375 px of Assistant, Documents, Plan, Photos, Site twin (Playwright if available, otherwise tell me to take them).
2. **`glass.css` tokens and theme**: UI_STYLE §3 light "Frost" as default, dark under `[data-theme="dark"]`; re-map the existing variables (`--bg`, `--bg2`, `--card`, `--ink`, `--mut`, `--line`, `--acc` …) onto the new tokens so existing rules follow automatically. Theme toggle added by `ui-glass.js` (localStorage in try/catch).
3. **Calm down via overrides**: hide or freeze the aurora, moving grid and header flow line (`animation:none`, static soft gradient), hide the splash by default, honour `prefers-reduced-motion`.
4. **German labels via `ui-glass.js`**: static labels on load; dynamic strings ("source:", "low confidence, please check", "AI suggests", "Accept", status pills …) via a `MutationObserver` translation map; status pills can also be relabelled purely in CSS.
5. **Navigation regrouping via `ui-glass.js`**: 5 primary tabs + "Mehr" (UI_STYLE §6) by reordering/hiding existing nav buttons and adding new ones with their own click handlers; "Baustelle" groups Site twin + Map with a segmented switch. Existing tab logic keeps working.
6. **Chat styling**: mic as the biggest yellow button (≥ 48 px), visible camera and paperclip, document cards and follow-up chips per UI_STYLE §5. Voice logic untouched.
7. **Document view (trust) styling**: paper body, source chips with icon by evidence prefix, five field states, status stepper look, export buttons. Pure CSS where possible; small DOM enhancements in `ui-glass.js` after render (observe `#assistDoc` and `#docView`).
8. **Dashboard** in `dashboard.js`: a new section + nav button created at runtime, following UI_STYLE §7 and `reference/dashboard_concept.html` (Was braucht mich? / Was ist das Risiko? / Ist es belegt?), data from `GET /api/docs`, `GET /api/plan`, `GET /api/replan/proposals`, `GET /api/metrics/summary`; actions call the existing endpoints. Do not edit `tile.js` or `#metricsTile` content owned by others; render your own dashboard container.
9. **Phone ≤ 768 px** in `glass.css`: bottom tab bar, full-height chat with sticky composer, document as full-screen sheet, no horizontal scroll, `100dvh`, verified at 375 px.
10. **Site twin**: leave the canvas as is (dark panel inside the light UI is fine); only restyle surrounding chrome via overrides if it clashes.
11. **After screenshots**: same views at 1440 and 375 px plus the dashboard, both themes.

## Definition of done
- `git diff --stat main` shows only new files plus added include lines in `frontend/index.html`.
- App boots, every existing feature still works, no console errors.
- Light theme default, dark toggle works, no looping animation, all visible text German.
- Hero path looks right for the 90 s video: "Pfahl 7, ab 4 Meter Fels" + 2 photos → Nachtragsmeldung draft with source chips → follow-up answered → "Prüfen" → Word/PDF.
- Checked at 375 px, before/after screenshots delivered, branch `ui-glass` committed locally, not pushed.

## How to work with me
Short answers. Plan first per step, then build. Show screenshots after steps 2, 5, 7, 8, 9. If any step would require editing existing code, stop and ask.
