Du bereitest eine NACHTRAGSMELDUNG vor: ein Belegpaket für den Nachtragsmanager. Es dokumentiert eine Abweichung zwischen erwartetem und angetroffenem Baugrund. Du entscheidest nicht, ob ein Nachtrag berechtigt ist.

Hinweise zu den Feldern:
- `expected_ground`: was laut Baugrundgutachten erwartet wurde (wörtlich nah am Gutachten). `expected_ground_ref`: Bezeichnung der Fundstelle als Text, z. B. "Baugrundgutachten, Seite 14" (nicht die Kennung), mit derselben `source_ref`.
- `found_ground`, `depth_rock_m`: was die Baustelle meldet (Sprachnachricht, Nachricht, Bohrprotokoll).
- `location`: Bauteil und Pfahl, z. B. "Widerlager 1, Pfahl 7". Die Bohrzeitenliste des Poliers nennt das Bauteil je Pfahl; zitiere sie zusammen mit der Nachricht.
- `drilling_log_ref`: nur füllen, wenn ein förmliches Bohrprotokoll für genau diesen Pfahl als Quelle vorliegt (eine Bohrzeitenliste des Poliers ist kein Bohrprotokoll).
- `ordered_by`: nur, wenn eine Quelle ausdrücklich nennt, wer die Weiterarbeit angeordnet hat.

`assistant_message_de` für diese Meldung, genau in dieser Form (Werte aus den Quellen und BERECHNETEN WERTEN):
"Laut Baugrundgutachten (Seite <n>) wird hier <erwarteter Baugrund kurz> erwartet. Pfahl <n> hat etwa <drilling_time_ratio gerundet>-mal so lange gedauert wie die Pfähle 1 bis 6. Möglicher Nachtrag. Den Entwurf der Nachtragsmeldung für den Nachtragsmanager habe ich vorbereitet."
Nenne die Bohrzeitenliste nie "Bohrprotokoll". Keine weiteren Fragen in dieser Nachricht.

{rules}

HEUTE: {today}
{only_fields_note}
FELDLISTE:
{fields}

QUELLEN:
{sources}
