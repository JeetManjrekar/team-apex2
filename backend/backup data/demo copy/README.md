# Demo-Daten BW 12 Mühlbach

**Fiktives Projekt. Alle Namen, Daten und Sätze erfunden.** Erzeugt mit `python scripts/generate_fixtures.py`.

## Annahmen (keine belegten Fakten)
| Thema | Annahme | Quelle |
|---|---|---|
| Bohrleistung Pfähle | 24 m je Arbeitstag (2 Pfähle à 12 m), P01–P06 im Mittel 4,0 h je Pfahl | Annahme, Team |
| Dauern im Bauzeitenplan | in Arbeitstagen (Mo–Fr), keine Feiertage im Demo-Fenster | Annahme, Team |
| Frostgrenze Betonieren | Prognose-Minimum unter 5 °C löst Warnung aus (Terminannahme, keine Materialaussage) | Annahme, mit Fachperson zu klären |
| Kostensätze | Bohrgerät 420 €/h, Personal 58 €/h, Stillstand 150 €/h (fiktive interne Sätze) | Annahme, `.env.example` |
| Basiszeiten manuell | Nachtragsmeldung 90 min, Bautagesbericht 45 min, Behinderungsanzeige 30 min | Annahme, Bestätigung durch Partnerin offen |
| Wetter | festes Fixture 13.–21.11.2026, Do 19.11. min −4 °C | erfunden |
| Koordinaten | `SITE_LAT`/`SITE_LON`, fiktiver Ort, nur für Wetter | Annahme |

## Hinweise
* Mailzeilen (`mail:mail_NN#L<n>`) zählen ab Zeile 1 des Mail-Textes.
* `daily_reports/*.json` enthalten zusätzlich `output_by_activity` und `completed_activity_ids` (kumulativ) für die Terminberechnung.
* Fotos sind Platzhalter mit echten EXIF-Daten (17.11.2026, GPS nahe Baustelle). Audio muss das Team aufnehmen (`audio/scripts.md`).
* `inbox/pfahl7_bohrprotokoll.pdf` wird **nicht** geseedet, sondern im Chat hochgeladen.
* `stubs/_index.json` ordnet Endpunkte den Stub-Dateien zu; alle Zahlen dort sind Beispielwerte, keine Messungen.
