# synthetic_data – Testdaten für BauBuddy (BW 12 Mühlbach, fiktiv)

Alles hier ist erfunden. Es werden **keine Fotos und keine Audiodateien** erzeugt, nur Texte, Skripte und Shot-Listen. Die bestehenden Demo-Daten (`backend/data/demo`, `data/eval`, `data/seed`) bleiben unberührt. Dieser Ordner ergänzt sie um Grenz-, Fehler- und Angriffsfälle. Er wird von der App nicht automatisch geladen.

## Inhalt
| Pfad | Inhalt | Zweck |
|---|---|---|
| `commands/agent_commands.json` | 45 Befehle für `POST /api/agent` (DE/EN, Handoff, Edge, PII, Injection) mit gewünschter Route | Intent-Router `core/agent.py` |
| `emails/*.eml` (8) | PII, Zitatkette, nur Anhang, leer, Englisch, Prompt-Injection, Sonderzeichen, Newsletter | Outlook/Inbox, `sanitizer.py`, Summarize |
| `minutes/baubesprechung_2026-11-19.md` | Protokoll mit Fristen, Zahlen, einem Widerspruch | Summarize, Open Items, Aktennotiz |
| `audio/audio_scripts.md` | 21 Sprechskripte (normal, schwierig, Pipeline-Grenzen) mit erwartetem Ergebnis | `stt.py`, `/api/voice`, Extraktion |
| `photos/photo_shotlist.csv` | 27 Fotovorschläge mit Kategorie, Zone, erwarteter Detektion und Incident-Regel | `photos.py`, Detektor, Incident-Regeln |
| `scenarios/progress_*.json` | Fortschrittsvarianten (planmäßig, Verzug, Vorsprung, Überschuss, ungültig, leer) | `core/plan.py`, Frühwarnung |
| `scenarios/weather_frost_cases.json` | Frostschwelle und fehlende Wetterdaten | Warnlogik, Tagesbericht |
| `scenarios/layout_edge_cases.json` | 7 Site-Layouts (leer, ohne Origin, ungültig, lat/lon, doppelt, überlappend, riesig) | `site_twin.py`, `PUT /api/site/layout` |
| `scripts/check_routes.py` | Schreibgeschützt: vergleicht gewünschte mit tatsächlicher Route | schneller Regressions-Check |

Szenario wie im Rest der Demo: Bauvertrag 2026-117 (VOB/B), Pfahl 7 trifft am 17.11.2026 ab 4,0 m auf Fels. Aktivitäten-IDs (`W1_BP`, `W1_BET`, `A1_BP` …) und Zonen-IDs (`be`, `wls`, `a10`, `erd`, `wln`) stammen aus `backend/data/seed`.

## So wird es benutzt
1. Route-Check ohne Server: `python synthetic_data/scripts/check_routes.py` (Exit-Code 1 bei Abweichung).
2. Befehle: Server starten (`cd backend && uvicorn app:app --port 8000`), dann je Eintrag aus `agent_commands.json` an `/api/agent` senden oder im Tab „AI Manager" tippen.
3. E-Mails: im Tab Inbox hochladen oder in `backend/data/demo/outlook/mails/` kopieren (Kopie, nicht verschieben).
4. Fortschritt/Layout: per API einspielen (`PUT /api/site/layout`, Fortschritt über die Store-Funktionen). Achtung: `python -m core.demo reset` löscht alle Laufzeitdaten. Besser mit einer Kopie von `backend/data` arbeiten.
5. Audio und Fotos: nach `audio_scripts.md` und `photo_shotlist.csv` selbst aufnehmen oder beschaffen. Ablage in `synthetic_data/audio/recordings/` und `synthetic_data/photos/images/`, beide nicht einchecken.

## Audit: wie die App funktioniert (Kurzfassung)
- **Backend** FastAPI (`backend/app.py`), Router in `routes/` (agent, documents, inbox, metrics, photos, plan, replan, site, system, voice). JSON-Store in `backend/data` (`core/store.py`).
- **Dokument-Pipeline:** Chat/Voice/Mail → Intent (Registry-Keywords, dann LLM) → Extraktion nur mit Beleg-Ref und Konfidenz-Schwelle → abgeleitete Felder in Python → Reviewer (LLM B) → Word/PDF. Felder stehen in `registry/doc_types/*.yaml`. PII (E-Mail, IBAN, Telefon) wird vor jedem LLM-Aufruf maskiert (`core/sanitizer.py`).
- **AI Manager** (`core/agent.py`): regelbasierter Router über Regex-Intents → Tools (progress, safety, incidents, changes, zone, report). Sicherheitsregeln laufen deterministisch auf gespeicherten Detektionen (MIN_CONF 0.5).
- **Site-Twin** (`core/site_twin.py`, `frontend/js/site3d.js`): Layout + Fotos + Fortschritt zu 2D/3D.
- **Offene Punkte, nicht geprüft:** Ich habe Route-Logik und Demo-Daten gelesen und die Router-Regexes gegen die Befehle laufen lassen. LLM-Aufrufe, STT, Detektor und Frontend habe ich **nicht** ausgeführt. Alle „Erwartung"-Spalten sind Sollwerte, keine gemessenen Ergebnisse.

## Befunde aus dem Route-Check (behoben in `backend/core/agent.py`)
| Fall | Problem | Korrektur |
|---|---|---|
| c11 | „Explain what happened…" löste die Helm-Antwort aus, weil `ppe` in „hap**pe**ned" steckt | Helm/PSA-Regex mit Wortgrenzen |
| c26 | „Standsicherheit" löste safety + progress aus statt Bedenkenanmeldung | `NOTICE_RX` (Bedenken, Behinderungs-/Mehrkosten-/Mängelanzeige, Nachtragsmeldung, Aktennotiz) → immer Chat; `stand` nur als ganzes Wort |
| e18 | „Did anyone get injured today?" legte einen Vorfall an | `is_incident_report()`: Fragen sind keine Meldung; `injur`/`verletz` listen jetzt Vorfälle |
| e19 | „Kein Unfall heute" legte einen Vorfall an | `is_incident_report()`: Verneinung ist keine Meldung |

Bewusst unverändert: das Wort „incident" löst zusätzlich `incidents` aus (c07, c11), „Zeig" zusätzlich `focus` (e04, e11), und „delete all incidents" (e09) liest nur, löscht nichts. Tests: `backend/tests/test_agent_routes.py`.

## Nächste Schritte
1. Weitere Negationen/Fragen in anderen Sprachen ergänzen, falls gebraucht (`_NEGATION_RX`, `_QUESTION_RX`).
3. E-Mails 01–08 durch `outlook.py`/`summarize.py` laufen lassen, Ergebnisse mit den Erwartungen vergleichen (PII-Maske, leere Mail, Injection).
4. Audio (A/B/C) und Fotos (P01–P27) beschaffen. Mit Detektor und STT gegen die Erwartungen laufen lassen und Abweichungen hier dokumentieren.
5. Szenarien `scenarios/*.json` über die Plan-API einspielen und Warnungen prüfen.
