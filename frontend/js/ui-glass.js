/* Team Apex UI layer, additive only.
   Nachweis glass UI: theme toggle (dark default), language switch (English default, German optional),
   header menu, navigation regrouping (5 + More) with a sliding yellow indicator and swipe between tabs,
   chat and document enhancements, in-page confirm for "Send on", phone sheets, and a clean site plan whose
   labels appear only for the hovered or selected object.
   It only observes and extends the DOM rendered by js/app.js and js/site3d.js; it never changes API calls or backend behaviour.
   Spec: docs/ui/UI_STYLE.md */
(() => {
  "use strict";
  const q = (s, r = document) => r.querySelector(s);
  const qa = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch {} },
  };
  const LANG = store.get("nw-lang") === "de" ? "de" : "en";
  const DE = LANG === "de";
  const L = (en, de) => (DE ? de : en);
  const ST = DE ? { draft: "Entwurf", checked: "Geprüft", sent: "Weitergegeben" } : { draft: "Draft", checked: "Checked", sent: "Sent" };

  /* ------------------------------------------------------------------ icons */
  const svg = (inner, fill = false) =>
    `<svg viewBox="0 0 24 24" fill="${fill ? "currentColor" : "none"}" stroke="${fill ? "none" : "currentColor"}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`;
  const IC = {
    chat: svg('<path d="M4 5h16v11H9l-5 4z"/>'),
    doc: svg('<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/><path d="M10 13h6M10 17h6"/>'),
    dash: svg('<rect x="3" y="3" width="8" height="8" rx="2"/><rect x="13" y="3" width="8" height="5" rx="2"/><rect x="13" y="10" width="8" height="11" rx="2"/><rect x="3" y="13" width="8" height="8" rx="2"/>'),
    site: svg('<path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>'),
    camera: svg('<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>'),
    more: svg('<circle cx="5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="19" cy="12" r="1.7"/>', true),
    mic: svg('<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>'),
    clip: svg('<path d="M20 11.5l-8.2 8.2a5 5 0 0 1-7.1-7.1l8.5-8.5a3.3 3.3 0 0 1 4.7 4.7l-8.4 8.4a1.7 1.7 0 0 1-2.4-2.4l7.6-7.6"/>'),
    sun: svg('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
    moon: svg('<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>'),
  };

  /* ------------------------------------------------------------------ theme (dark default) + language */
  const root = document.documentElement;
  function applyTheme(t) {
    root.dataset.theme = t;
    const m = q('meta[name="theme-color"]'); if (m) m.content = t === "dark" ? "#14161c" : "#e9eef5";
    const b = q("#glTheme");
    if (b) { b.innerHTML = t === "dark" ? IC.sun : IC.moon; b.title = t === "dark" ? L("Light mode", "Helles Design") : L("Dark mode", "Dunkles Design"); b.setAttribute("aria-label", b.title); }
  }
  applyTheme(store.get("nw-theme") === "light" ? "light" : "dark");
  root.lang = LANG;
  const fav = q('link[rel="icon"]');
  if (fav) fav.href = "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><rect width="48" height="48" rx="12" fill="#ffcc00"/><text x="24" y="33" font-family="Arial,Helvetica,sans-serif" font-size="26" font-weight="700" text-anchor="middle" fill="#1b1b1b">N</text></svg>');
  if (DE) document.title = "Nachweis · KI-Assistent für die Bauleitung";

  /* ------------------------------------------------------------------ German labels */
  const EX = {
    // header + nav
    "Load demo data": "Demo laden", "Demo data loaded ✓": "Demo geladen ✓", "Reset demo": "Demo zurücksetzen",
    "Click again to reset": "Zum Bestätigen erneut klicken", "■ Stop": "■ Stopp",
    "Extraction: rules fallback": "Extraktion: Regeln", "Photos: mock mode": "Fotos: Testmodus",
    "Assistant": "Assistent", "Documents": "Dokumente", "Plan vs actual": "Plan & Ist", "Summaries": "Zusammenfassungen",
    "Photos": "Fotos", "Map": "Karte", "Live camera": "Live-Kamera", "Metrics": "Metriken",
    // chat
    "Send": "Senden", "Open draft": "Entwurf öffnen",
    "Drafts appear here. Every field shows where it came from. Nothing is sent without your click.":
      "Entwürfe erscheinen hier. Jedes Feld zeigt seine Quelle. Nichts wird ohne deinen Klick weitergegeben.",
    "Drafts appear here.": "Entwürfe erscheinen hier.",
    "Tell me what happened on site. Type, dictate with 🎤, or tap an example below.":
      "Erzähl mir, was auf der Baustelle passiert ist: tippen, mit dem Mikrofon diktieren oder unten ein Beispiel antippen.",
    "Try: rock at pile 7 → I draft a Mehrkostenanzeige and ask for what is missing.":
      "Probier: Fels an Pfahl 7 → ich entwerfe die passende Meldung und frage nach, was fehlt.",
    "Rock at pile 7": "Fels an Pfahl 7", "Excavator idle": "Bagger steht", "Defect": "Mangel", "Diary note": "Tagebuchnotiz",
    "Edit by chat": "Per Chat ändern", "File note": "Aktennotiz", "Daily report": "Tagesbericht",
    // documents
    "New": "Neu", "No documents yet.": "Noch keine Dokumente.", "Select a document.": "Dokument auswählen.",
    "Mark as checked": "Prüfen", "Approve & mark as sent": "Weitergeben",
    "No photos attached.": "Keine Fotos angehängt.", "Choose photos": "Fotos auswählen", "Save": "Speichern",
    "Edit log": "Änderungsprotokoll", "No edits yet.": "Noch keine Änderungen.", "Undo": "Rückgängig", "undone": "zurückgenommen",
    "Accept": "Übernehmen", "AI suggests:": "KI-Vorschlag:", "low confidence, please check": "unsicher, bitte prüfen",
    "proposal from alert": "Vorschlag aus Warnung", "extracted by nachweis_llm": "KI-Extraktion", "extracted by rules": "Regel-Extraktion",
    "missing, required": "fehlt (Pflichtfeld)", "empty": "leer", "Fill required fields first": "Erst Pflichtfelder ausfüllen",
    "Edited by you, AI will not overwrite": "Von dir geändert, die KI überschreibt das nicht", "critical field": "kritisches Feld",
    // plan
    "Weather service unreachable": "Wetterdienst nicht erreichbar", "No deviations.": "Keine Abweichungen.",
    'No schedule loaded. Click "Load demo data".': "Kein Bauzeitenplan geladen. Im Menü oben rechts „Demo laden“ wählen.",
    "Activity": "Vorgang", "Period": "Zeitraum", "Actual / planned": "Ist / Soll", "Progress": "Fortschritt", "Delay": "Verzug",
    "not started": "nicht begonnen", "on plan": "im Plan", "Report progress": "Fortschritt melden",
    "Quantity": "Menge", "Note (e.g. Pfahl 7)": "Notiz (z. B. Pfahl 7)", "Add": "Hinzufügen",
    // summaries
    "Minutes, diary or email": "Protokoll, Bautagebuch oder E-Mail",
    "Paste meeting minutes, site diary entries or an email": "Besprechungsprotokoll, Tagebucheinträge oder E-Mail einfügen",
    "Sample minutes": "Beispielprotokoll", "Sample email": "Beispiel-E-Mail", "Summarize": "Zusammenfassen",
    "E-mail addresses, phone numbers and IBANs are masked before any AI call.": "E-Mail-Adressen, Telefonnummern und IBANs werden vor jedem KI-Aufruf maskiert.",
    "Open items with owner and deadline appear here.": "Offene Punkte mit Verantwortlichem und Frist erscheinen hier.",
    "Working…": "Wird verarbeitet …", "Open items": "Offene Punkte", "Item": "Punkt", "Owner": "Verantwortlich", "Deadline": "Frist",
    "None found.": "Keine gefunden.", "Decisions": "Entscheidungen",
    "Possible Nachtrag (client instruction / changed work)": "Möglicher Nachtrag (Anordnung des Bauherrn / geänderte Leistung)",
    "Draft Nachtragsmeldung from this": "Daraus Nachtragsmeldung entwerfen",
    // photos, live, metrics
    "Upload photos": "Fotos hochladen", "Photo report (Word)": "Fotobericht (Word)", "No photos yet.": "Noch keine Fotos.",
    "please confirm category": "bitte Kategorie bestätigen", "Add photos": "Fotos hinzufügen",
    "Webcam frames go to the Roboflow model about once a second. Nothing is saved unless you press save.":
      "Kamerabilder gehen etwa einmal pro Sekunde an das Roboflow-Modell. Gespeichert wird nur, wenn du speicherst.",
    "Start camera": "Kamera starten", "Stop camera": "Kamera stoppen", "Save frame to inbox": "Bild speichern", "mock mode": "Testmodus",
    "Measured pipeline metrics": "Gemessene Pipeline-Metriken", "Refresh": "Aktualisieren",
    "One JSON line per stage (nachweis_llm MetricsRecorder). Only these measured numbers belong in the pitch.":
      "Eine JSON-Zeile pro Stufe (nachweis_llm MetricsRecorder). Nur diese gemessenen Zahlen gehören in den Pitch.",
    "Stage": "Stufe", "Runs": "Läufe", "Avg ms": "Ø ms", "Tokens in/out": "Tokens ein/aus", "Cost €": "Kosten €", "Model": "Modell",
    "No measurements yet. Use the assistant first.": "Noch keine Messungen. Erst den Assistenten nutzen.", "Last 20 entries": "Letzte 20 Einträge",
    // site twin
    "2D plan": "2D-Plan", "3D isometric": "3D-Ansicht", "AI detections": "KI-Erkennungen", "Labels": "Beschriftung", "Zones": "Zonen",
    "Min conf": "Min. Sicherheit", "▶ Tour": "▶ Rundgang", "Reset": "Zurücksetzen", "Layout": "Lageplan",
    "Loading site plan…": "Lageplan wird geladen …", "Object": "Objekt", "Plan position": "Planposition", "Location": "Standort",
    "Evidence": "Beleg", "Detection confidence": "Erkennungssicherheit", "Zone": "Zone", "Vision description": "Bildbeschreibung",
    "Used in": "Verwendet in", "Timestamp": "Zeitstempel", "Timeline": "Verlauf", "Taken": "Aufgenommen", "Site digital twin": "Digitaler Zwilling",
    "Set direction": "Richtung setzen", "Remove from plan": "Aus dem Plan entfernen", "Record": "Datensatz", "Position on plan": "Position im Plan",
    "Planned (dashed)": "Geplant (gestrichelt)", "Place": "Platzieren", "Pixel box": "Pixelbox", "Photo without GPS": "Foto ohne GPS",
    "Photo location": "Fotostandort", "On plan": "Im Plan", "None.": "Keine.", "No scheduled activity linked to this zone.": "Kein Vorgang mit dieser Zone verknüpft.",
    "No photos with detections in this zone.": "Keine Fotos mit Erkennungen in dieser Zone.", "No photos placed in this zone.": "Keine Fotos in dieser Zone platziert.",
    "No events yet.": "Noch keine Ereignisse.", "Models": "Modelle", "Linked activity": "Verknüpfter Vorgang", "Legend": "Legende",
    "How positioned": "Positionierung", "Evidence records": "Belege", "Evidence ID": "Beleg-ID", "Esc to cancel": "Esc zum Abbrechen",
    "Direction": "Richtung", "Detected machinery": "Erkannte Maschinen", "Count": "Anzahl", "Construction activity": "Bauvorgang",
    "Confidence": "Sicherheit", "Clear direction": "Richtung löschen", "Built (from progress log)": "Gebaut (laut Fortschritt)",
    "Best confidence": "Beste Sicherheit", "Not started – drawn dashed / translucent.": "Nicht begonnen – gestrichelt / transparent.",
    "Site plan could not be loaded": "Lageplan konnte nicht geladen werden", "Site twin could not start": "Baustellenansicht konnte nicht starten",
    "Construction site": "Baustelle", "Digital twin": "Digitaler Zwilling", "Photo evidence": "Fotobelege", "Early warning": "Frühwarnung",
    "Planned structure": "Geplantes Bauwerk", "Structure": "Bauwerk", "Excavator": "Bagger", "Dump truck": "Muldenkipper",
    "Bulldozer": "Planierraupe", "Tractor": "Traktor", "No objects detected.": "Keine Objekte erkannt.", "Place on plan": "Im Plan platzieren",
    "Move on plan": "Im Plan verschieben", "No scheduled activity": "Kein Vorgang", "Every marker traces back to evidence": "Jede Markierung führt zu einem Beleg",
    "Right-click / Esc to skip": "Rechtsklick / Esc zum Überspringen", "Detections": "Erkennungen",
    "PHOTOS WITHOUT GPS — select one, then “Place on plan”": "FOTOS OHNE GPS — eines wählen, dann „Im Plan platzieren“",
    "← Site overview": "← Baustellenübersicht",
    "Object detection:": "Objekterkennung:", "Vision description:": "Bildbeschreibung:", "In zone": "In Zone",
    "photos": "Fotos", "on plan": "im Plan", "detections": "Erkennungen", "zones": "Zonen", "no detections": "keine Erkennungen",
    "Drag to pan · scroll to zoom · click to inspect": "Ziehen zum Verschieben · Scrollen zum Zoomen · Klicken für Details",
    "Drag to rotate · right-drag to pan · scroll to zoom · click to inspect": "Ziehen zum Drehen · Rechts ziehen zum Verschieben · Scrollen zum Zoomen · Klicken für Details",
    "Not georeferenced: relative coordinates only. Place photos manually.": "Nicht georeferenziert: nur relative Koordinaten. Fotos bitte manuell platzieren.",
    "Click where the photo was taken.": "Klicke, wo das Foto aufgenommen wurde.", "Click in the direction the camera was pointing.": "Klicke in die Blickrichtung der Kamera.",
    "Uploaded in mock mode – detector was not configured.": "Im Testmodus hochgeladen – kein Detektor konfiguriert.",
    "No GPS in these photos. Place them on the plan and the detected machines appear in 3D.": "Diese Fotos haben kein GPS. Im Plan platzieren, dann erscheinen die erkannten Maschinen in 3D.",
    "These photos carry no EXIF GPS, so their position is unknown. Place each one where it was taken; optionally click a second time to set the viewing direction, which positions the detected objects.":
      "Diese Fotos haben kein EXIF-GPS, ihre Position ist unbekannt. Jedes Foto dort platzieren, wo es aufgenommen wurde; optional ein zweiter Klick für die Blickrichtung, damit die erkannten Objekte positioniert werden.",
    "Site layout (JSON)": "Lageplan (JSON)", "Reset to default": "Standard wiederherstellen", "Cancel": "Abbrechen", "Save layout": "Lageplan speichern",
    "Hide detections below this model confidence": "Erkennungen unter dieser Modellsicherheit ausblenden",
    "Automated camera tour of the site from the live data": "Automatischer Kamerarundgang über die Baustelle",
    // autopilot captions
    "Site assistant": "Baustellen-Assistent", "Speak it. It becomes a formal notice.": "Sprich es ein. Daraus wird eine formale Meldung.",
    "Chat or voice turns into Behinderungs- and Mehrkostenanzeigen. Every field cites its evidence.":
      "Chat oder Sprache wird zu Behinderungs- und Mehrkostenanzeigen. Jedes Feld nennt seinen Beleg.",
    "Draft → Checked → Sent, only by your click": "Entwurf → Geprüft → Weitergegeben, nur per Klick",
    "Early warning raised": "Frühwarnung ausgelöst", "Schedule on track": "Bauzeitenplan im Soll",
    "Upload site photos to detect machinery.": "Baustellenfotos hochladen, um Maschinen zu erkennen.",
    "Measured, not claimed": "Gemessen, nicht behauptet",
    "Every pipeline stage is timed and costed in llm_metrics.jsonl.": "Jede Pipeline-Stufe wird in llm_metrics.jsonl gemessen.",
    "Evidence in. Notices out. On time.": "Belege rein. Meldungen raus. Pünktlich.",
    "Autopilot finished — you have the controls.": "Autopilot beendet – du hast die Kontrolle.",
    "Paused — you have the controls": "Pausiert – du hast die Kontrolle",
    "Hands-free walkthrough of the app (any click or key stops it)": "Automatischer Rundgang durch die App (jeder Klick oder jede Taste stoppt ihn)",
    "Loads the fictional bridge schedule": "Lädt den fiktiven Bauzeitenplan der Brücke",
    "Clears chat, documents and notes. Photos stay.": "Löscht Chat, Dokumente und Notizen. Fotos bleiben.",
    "Dictate (Chrome speech recognition)": "Diktieren", "Dictation language": "Diktiersprache",
    "Type or dictate, e.g. „Bagger steht seit 10 Uhr an Widerlager Süd, weil Bewehrungspläne fehlen“":
      "Nachricht tippen oder diktieren, z. B. „Bagger steht seit 10 Uhr an Widerlager Süd, weil Bewehrungspläne fehlen“",
  };
  const CAT = { all: "Alle", progress: "Fortschritt", delivery: "Lieferung", defect: "Mangel", "Nachtrag evidence": "Nachtragsbeleg",
    obstruction: "Behinderung", safety: "Sicherheit", uncategorized: "ohne Kategorie" };
  const deDate = s => { const m = /^(\d{4})-(\d\d)-(\d\d)(?:[ T](\d\d:\d\d))?/.exec(s || ""); return m ? `${m[3]}.${m[2]}.${m[1]}${m[4] ? " " + m[4] : ""}` : s; };
  const num = s => String(s).replace(".", ",");
  const RX = [
    [/^Photos \((\d+)\)$/, (_, n) => `Fotos (${n})`],
    [/^Missing required: (.*)$/, (_, x) => `Fehlende Pflichtfelder: ${x}`],
    [/^reviewer: (\d+) finding\(s\)$/, (_, n) => `Prüfer: ${n} Hinweis(e)`],
    [/^conf (\d+)%$/, (_, n) => `${n} %`],
    [/^Reviewer \((.*?)\): /, (_, x) => `Prüfer (${x}): `],
    [/^status (\w+) → (\w+)(.*)$/, (_, a, b, r) => `Status ${ST[a] || a} → ${ST[b] || b}${r}`],
    [/^proposal for (.*)$/, (_, f) => `Vorschlag für ${f}`],
    [/^edit (\S+): /, (_, f) => `Änderung ${f}: `],
    [/^Draft created with AI assistance\. Formal completeness check only, no legal advice\.(.*)$/s, (_, rest) => {
      const c = /Checked by (.*?) (\d{4}-\d\d-\d\d \d\d:\d\d)\./.exec(rest), s = /Marked as sent (\d{4}-\d\d-\d\d \d\d:\d\d)\./.exec(rest);
      return `Entwurf mit KI-Unterstützung erstellt, geprüft von ${c ? `${c[1]} am ${deDate(c[2])}` : "… (noch nicht geprüft)"}.` +
        (s ? ` Weitergegeben am ${deDate(s[1])}.` : "") + " Nur formale Vollständigkeitsprüfung, keine Rechtsberatung.";
    }],
    [/^as of (.*)$/, (_, d) => `Stand ${deDate(d)}`],
    [/^Weather today: (.*?), (-?\d+) to (-?\d+) °C, rain (.*) mm$/, (_, t, a, b, r) => `Wetter heute: ${t}, ${a} bis ${b} °C, Regen ${num(r)} mm`],
    [/^Draft (\S+?)( \(winter measures\))?$/, (_, d, w) => `${d === "Bedenkenanzeige" ? "Bedenkenanmeldung" : d} entwerfen${w ? " (Wintermaßnahmen)" : ""}`],
    [/^of (\S+)$/, (_, n) => `von ${n}`],
    [/^(\d+(?:\.\d+)?) d$/, (_, n) => `${num(n)} AT`],
    [/^Plan vs actual $/, () => "Plan & Ist "],
    [/^Summary \((\w+)\)$/, (_, k) => `Zusammenfassung (${k === "email" ? "E-Mail" : k === "minutes" ? "Protokoll" : k})`],
    [/^Masked before AI: (.*)$/, (_, x) => `Vor KI-Aufruf maskiert: ${x}`],
    [/^(all|progress|delivery|defect|Nachtrag evidence|obstruction|safety|uncategorized) (\d+)$/, (_, c, n) => `${CAT[c]} ${n}`],
    [/^(set by you|vision LLM \d+%|detector \d+%) · (GPS from photo|site location)$/, (_, a, b) =>
      `${a.replace("set by you", "von dir gesetzt").replace("vision LLM", "Bild-KI").replace("detector", "Detektor").replace(/(\d)%/, "$1 %")} · ${b === "GPS from photo" ? "GPS aus Foto" : "Baustellenstandort"}`],
    [/^Site: (.*) \((.*)\)\. Orange = GPS from photo, grey = site location \(no GPS in photo\)\.$/, (_, n, c) =>
      `Baustelle: ${n} (${c}). Farbig = GPS aus Foto, grau = Baustellenstandort (kein GPS im Foto).`],
    [/^(\d+) detections$/, (_, n) => `${n} Erkennungen`],
    [/^Detections: (.*)$/, (_, x) => `Erkennungen: ${x.replace("mock mode", "Testmodus").replace(/^none$/, "keine")}`],
    [/^nachweis_llm: (.*?)( \+ reviewer)?$/, (_, m, r) => `KI: ${m}${r ? " + Prüfer" : ""}`],
    [/^(\S+) documents with evidence appendix, edit locks and undo\. Export to Word or PDF\.$/, (_, n) =>
      `${n === "Your" ? "Deine" : n} Dokumente mit Belegverzeichnis, Bearbeitungssperre und Rückgängig. Export als Word oder PDF.`],
    [/^(\d+) photos · (\d+) AI detections$/, (_, a, b) => `${a} Fotos · ${b} KI-Erkennungen`],
    [/^(\d+) photos? · (\d+) objects?$/, (_, a, b) => `${a} Foto${a === "1" ? "" : "s"} · ${b} Objekt${b === "1" ? "" : "e"}`],
    [/^(\d+) photos · (.*)$/, (_, a, m) => `${a} Fotos · ${m === "no machinery detected" ? "keine Maschinen erkannt" : m}`],
    [/^(\d+) detections? on plan$/, (_, n) => `${n} Erkennung${n === "1" ? "" : "en"} im Plan`],
    [/^Georeferenced: origin (.*?)(, plan rotated (.*)°)?\. Photos with real GPS are positioned automatically\.$/, (_, o, r, d) =>
      `Georeferenziert: Ursprung ${o}${r ? `, Plan um ${d}° gedreht` : ""}. Fotos mit echtem GPS werden automatisch platziert.`],
    [/^(\d+) zones · (\d+) photos · (\d+) AI detections · (\d+) photos on the plan$/, (_, z, p, d, pl) => `${z} Zonen · ${p} Fotos · ${d} KI-Erkennungen · ${pl} Fotos im Plan`],
    [/^(\d+) photos? waiting for a position$/, (_, n) => `${n} Foto(s) warten auf eine Position`],
    [/^Photos without GPS \((\d+)\)$/, (_, n) => `Fotos ohne GPS (${n})`],
    [/^\(confidence values from stored model output\)\.$/, () => "(Sicherheitswerte aus der gespeicherten Modellausgabe)."],
    [/^\(only where a description was stored at upload\)\.$/, () => "(nur wo beim Hochladen eine Beschreibung gespeichert wurde)."],
    [/^Object detection: /, () => "Objekterkennung: "], [/^Vision description: /, () => "Bildbeschreibung: "], [/^In zone /, () => "In Zone "],
    [/^(.*?)\s?· (\d{4}-\d\d-\d\d \d\d:\d\d)(?: · (\d+) missing)?$/, (_, l, d, n) => `${l ? l + " · " : ""}${deDate(d)}${n ? ` · ${n} ${n === "1" ? "Pflichtfeld fehlt" : "Pflichtfelder fehlen"}` : ""}`],
  ];
  const PHOTO_MSG = /^Added (\d+) photo\(s\): (.*)\. They will be attached to matching drafts and today's daily report\.$/s;

  function tr(s) {
    const t = s.trim(); if (!t || t.length > 400) return null;
    let out = EX[t];
    if (out === undefined) for (const [re, f] of RX) if (re.test(t)) { out = t.replace(re, f); break; }
    if (out === undefined || out === t) return null;
    return s.replace(t, () => out);
  }
  const SKIP_TAGS = new Set(["TEXTAREA", "SCRIPT", "STYLE", "CODE", "INPUT", "svg", "SVG"]);
  function trText(n) {
    const p = n.parentElement; if (!p) return;
    if (p.closest(".quote,.gl-noi18n,#twLayTxt")) return;
    let out = null;
    if (p.classList.contains("pill")) out = ST[n.data.trim()] || null;
    else if (p.classList.contains("m")) {                 // chat message body: user/assistant content stays as is
      const m = PHOTO_MSG.exec(n.data.trim());
      if (m) out = `${m[1]} Foto(s) hinzugefügt: ${m[2].replace(/\b(progress|delivery|defect|Nachtrag evidence|obstruction|safety|uncategorized)\b/g, c => CAT[c])}. Sie werden passenden Entwürfen und dem heutigen Bautagesbericht zugeordnet.`;
    } else if (p.closest(".log") && /^(ai|user)$/.test(n.data.trim())) out = n.data.trim() === "ai" ? "KI" : "Nutzer";
    else out = tr(n.data);
    if (out != null && out !== n.data) n.data = out;
  }
  function trAttrs(el) {
    for (const a of ["placeholder", "title", "aria-label"]) {
      const v = el.getAttribute?.(a); if (!v) continue;
      const o = tr(v); if (o != null && o !== v) el.setAttribute(a, o);
    }
    if (el.tagName === "OPTION" && el.parentElement?.matches("#grid select") && CAT[el.textContent]) {
      if (!el.hasAttribute("value")) el.value = el.textContent;     // keep the API value, translate only the label
      el.textContent = CAT[el.textContent];
    }
  }
  function walk(node) {
    if (node.nodeType === 3) return trText(node);
    if (node.nodeType !== 1 || SKIP_TAGS.has(node.tagName)) { if (node.nodeType === 1 && node.tagName !== "svg") trAttrs(node); return; }
    trAttrs(node);
    if (node.id === "ltT") return trCaption(node);
    for (let c = node.firstChild; c; c = c.nextSibling) walk(c);
  }
  function trCaption(el) {                                   // lower third title is split into word spans by fx.js
    const t = el.textContent.trim(), o = tr(t);
    if (o != null) el.textContent = o;
  }
  function enPills(node) {                                  // English UI: only the status pills get a readable label
    const el = node.nodeType === 3 ? node.parentElement : node;
    if (!el || el.nodeType !== 1) return;
    const list = el.classList?.contains("pill") ? [el] : qa(".pill", el);
    for (const p of list) { const k = p.textContent.trim(); if (ST[k] && p.textContent !== ST[k]) p.textContent = ST[k]; }
  }

  /* ------------------------------------------------------------------ header */
  function buildHeader() {
    const h = q("header"); if (!h) return;
    const brand = q(".brand", h);
    if (brand && !q(".gl-logo", brand)) brand.insertAdjacentHTML("afterbegin", '<span class="gl-logo" aria-hidden="true">N</span>');
    const auto = q("#autoBtn"), demo = q("#demoBtn"), reset = q("#resetBtn");
    const theme = document.createElement("button");
    theme.id = "glTheme"; theme.className = "gl-hbtn"; theme.type = "button";
    theme.onclick = () => {
      const t = root.dataset.theme === "dark" ? "light" : "dark";
      store.set("nw-theme", t);
      // one GPU cross-fade of the whole page instead of transitioning every element's colours
      const rm = matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (document.startViewTransition && !rm) document.startViewTransition(() => applyTheme(t)).ready?.catch(() => {});
      else applyTheme(t);
      theme.classList.remove("gl-flash"); void theme.offsetWidth; theme.classList.add("gl-flash");
    };
    theme.addEventListener("animationend", e => { if (e.animationName === "glThemePulse") theme.classList.remove("gl-flash"); });
    const menu = document.createElement("div");
    menu.className = "gl-menu";
    menu.innerHTML = `<button class="gl-hbtn" id="glMenuBtn" type="button" title="${L("More actions", "Weitere Aktionen")}" aria-label="${L("More actions", "Weitere Aktionen")}" aria-haspopup="true" aria-expanded="false">${IC.more}</button>
      <div class="gl-pop" id="glMenuPop" role="menu"><div class="gl-hint">Demo</div></div>`;
    h.insertBefore(theme, auto || null);
    h.appendChild(menu);
    const pop = q("#glMenuPop", menu);
    if (demo) pop.appendChild(demo);
    if (reset) { pop.appendChild(reset); pop.insertAdjacentHTML("beforeend", `<div class="gl-hint">${L("Reset clears chat, documents and notes. Photos stay.", "Zurücksetzen löscht Chat, Dokumente und Notizen. Fotos bleiben.")}</div>`); }
    pop.insertAdjacentHTML("beforeend", `<div class="gl-sep"></div><div class="gl-hint">${L("Language", "Sprache")}</div>
      <div class="gl-langs"><button type="button" data-lang="en" class="${DE ? "" : "on"}">English</button><button type="button" data-lang="de" class="${DE ? "on" : ""}">Deutsch</button></div>`);
    q(".gl-langs", pop).addEventListener("click", e => {
      const b = e.target.closest("[data-lang]"); if (!b || b.dataset.lang === LANG) return;
      store.set("nw-lang", b.dataset.lang); location.reload();
    });
    const mb = q("#glMenuBtn", menu);
    mb.onclick = e => { e.stopPropagation(); const on = pop.classList.toggle("on"); mb.setAttribute("aria-expanded", on); };
    pop.addEventListener("click", e => e.stopPropagation());
    document.addEventListener("click", () => { pop.classList.remove("on"); mb.setAttribute("aria-expanded", "false"); });
    applyTheme(root.dataset.theme);
  }

  /* ------------------------------------------------------------------ navigation: 5 primary + More, sliding yellow indicator */
  const PRIMARY = [["assist", L("Assistant", "Assistent"), IC.chat], ["docs", L("Documents", "Dokumente"), IC.doc], ["dash", "Dashboard", IC.dash],
    ["twin", L("Site", "Baustelle"), IC.site], ["photos", L("Photos", "Fotos"), IC.camera]];
  const MORE = [["plan", L("Plan vs actual", "Plan & Ist")], ["sum", L("Summaries", "Zusammenfassungen")], ["live", L("Live camera", "Live-Kamera")], ["metrics", L("Metrics", "Metriken")]];
  const HIDDEN = [["mapt", L("Map", "Karte")], ...MORE];
  let moreEl, morePop;
  function buildNav() {
    const nav = q("#nav"); if (!nav) return;
    const btn = t => q(`button[data-t="${t}"]`, nav);
    for (const [t, label, icon] of PRIMARY) {
      const b = btn(t); if (!b) continue;
      b.innerHTML = `<span class="gl-ic">${icon}</span><span>${label}</span>`;
      nav.appendChild(b);
    }
    for (const [t, label] of HIDDEN) { const b = btn(t); if (b) { b.textContent = label; b.classList.add("gl-hidden"); b.tabIndex = -1; nav.appendChild(b); } }
    moreEl = document.createElement("span");
    moreEl.className = "gl-more"; moreEl.setAttribute("role", "button"); moreEl.tabIndex = 0; moreEl.setAttribute("aria-haspopup", "true");
    moreEl.innerHTML = `<span class="gl-ic">${IC.more}</span><span>${L("More", "Mehr")}</span>`;
    nav.appendChild(moreEl);
    // the menu lives on <body>: the nav scrolls horizontally and its backdrop-filter would clip a fixed child
    morePop = document.createElement("div");
    morePop.className = "gl-pop"; morePop.setAttribute("role", "menu");
    morePop.innerHTML = MORE.map(([t, l]) => `<button type="button" data-gl-t="${t}" role="menuitem">${l}</button>`).join("");
    document.body.appendChild(morePop);
    const place = () => {
      const r = moreEl.getBoundingClientRect(), w = morePop.offsetWidth, hgt = morePop.offsetHeight;
      const up = r.top > innerHeight / 2;
      Object.assign(morePop.style, { position: "fixed", zIndex: 1300, right: "auto",
        left: Math.max(8, Math.min(r.right - w, innerWidth - w - 8)) + "px", top: (up ? r.top - hgt - 10 : r.bottom + 8) + "px" });
    };
    const toggle = e => { e.stopPropagation(); morePop.classList.toggle("on"); if (morePop.classList.contains("on")) place(); };
    moreEl.addEventListener("click", toggle);
    moreEl.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(e); } });
    morePop.addEventListener("click", e => { const b = e.target.closest("[data-gl-t]"); if (!b) return; e.stopPropagation(); morePop.classList.remove("on"); window.NW.TAB(b.dataset.glT); });
    document.addEventListener("click", () => morePop.classList.remove("on"));
    addEventListener("resize", () => morePop.classList.remove("on"));
    // segmented switch Site plan / Map inside "Site"
    for (const id of ["twin", "mapt"]) {
      const s = q("#" + id); if (!s || q(".gl-seg", s)) continue;
      s.insertAdjacentHTML("afterbegin", `<div class="gl-seg" role="tablist"><button type="button" data-gl-t="twin">${L("Site plan", "Baustellenplan")}</button><button type="button" data-gl-t="mapt">${L("Map", "Karte")}</button></div>`);
      q(".gl-seg", s).addEventListener("click", e => { const b = e.target.closest("[data-gl-t]"); if (b) window.NW.TAB(b.dataset.glT); });
    }
    addEventListener("resize", () => requestAnimationFrame(syncNav));     // runs after fx.js' own indicator update
    setTimeout(syncNav, 450);
    syncNav();
  }
  function activeTab() { return q("section.tab.on")?.id; }
  let lastTab;
  function syncNav() {
    const t = activeTab(); if (!t) return;
    const nav = q("#nav");
    const twinBtn = q('#nav button[data-t="twin"]');
    twinBtn?.classList.toggle("gl-on", t === "mapt");
    moreEl?.classList.toggle("on", MORE.some(([m]) => m === t));
    qa("[data-gl-t]", morePop || document).forEach(b => b.classList.toggle("on", b.dataset.glT === t));
    qa(".gl-seg button").forEach(b => b.classList.toggle("on", b.dataset.glT === t));
    // the yellow indicator sits on the visible owner of the active tab (Site for the map, More for its items)
    const vis = qa("#nav button.on").find(b => b.offsetWidth) || (t === "mapt" ? twinBtn : null) || (moreEl?.classList.contains("on") ? moreEl : null);
    const ind = q("#nav .ind");
    if (ind && vis) { ind.style.left = vis.offsetLeft + "px"; ind.style.width = vis.offsetWidth + "px"; }
    if (vis && nav && nav.scrollWidth > nav.clientWidth) vis.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
    if (t !== lastTab) { lastTab = t; document.body.classList.remove("gl-sheet", "gl-sheet-docs"); }
  }

  /* swipe left / right on the content to move between the primary tabs */
  const ORDER = PRIMARY.map(p => p[0]);
  function bindSwipe() {
    const main = q("main"); if (!main) return;
    let s = null;
    main.addEventListener("touchstart", e => {
      s = null;
      if (e.touches.length !== 1 || document.body.classList.contains("gl-sheet") || document.body.classList.contains("gl-sheet-docs")) return;
      if (e.target.closest("#twCanvas,.tw-stage,#mapbox,.leaflet-container,textarea,input,select,#demoChips,table,.gl-seg,dialog,video,canvas,.db-g-track,[data-no-swipe]")) return;
      const tch = e.touches[0]; s = { x: tch.clientX, y: tch.clientY, t: Date.now() };
    }, { passive: true });
    main.addEventListener("touchend", e => {
      if (!s) return;
      const tch = e.changedTouches[0], dx = tch.clientX - s.x, dy = tch.clientY - s.y, dt = Date.now() - s.t; s = null;
      if (Math.abs(dx) < 70 || Math.abs(dx) < Math.abs(dy) * 1.6 || dt > 700) return;
      const cur = activeTab() === "mapt" ? "twin" : activeTab(), i = ORDER.indexOf(cur); if (i < 0) return;
      const next = ORDER[i + (dx < 0 ? 1 : -1)]; if (!next) return;
      root.dataset.swipe = dx < 0 ? "next" : "prev";
      window.NW.TAB(next);
      setTimeout(() => delete root.dataset.swipe, 700);
    }, { passive: true });
  }

  /* ------------------------------------------------------------------ composer */
  function buildComposer() {
    const bar = q(".inbar"); if (!bar) return;
    const cam = qa("button", bar).find(b => /chatPhotos/.test(b.getAttribute("onclick") || ""));
    const input = q("#chatPhotos");
    if (cam) {
      cam.classList.add("gl-ico"); cam.innerHTML = IC.camera; cam.title = L("Take photo", "Foto aufnehmen"); cam.setAttribute("aria-label", cam.title);
      const clip = document.createElement("button");
      clip.className = "gl-ico"; clip.type = "button"; clip.innerHTML = IC.clip; clip.title = L("Attach photo or evidence", "Foto oder Beleg anhängen"); clip.setAttribute("aria-label", clip.title);
      clip.onclick = () => { input?.removeAttribute("capture"); input?.click(); };
      cam.after(clip);
      // the camera button opens the rear camera on phones; capture phase runs before its inline onclick
      bar.addEventListener("click", e => { if (e.target.closest("button") === cam) input?.setAttribute("capture", "environment"); }, true);
    }
    const mic = q("#mic");
    if (mic) { mic.innerHTML = IC.mic; mic.setAttribute("aria-label", L("Dictate", "Diktieren")); }
  }

  /* ------------------------------------------------------------------ document view (trust) */
  const SRC_DE = { "chat message": ["Chat-Nachricht", "message"], dictation: ["Diktat", "voice"], "your answer in chat": ["deine Antwort", "answer"],
    "edited by you": ["von dir", "user"], "message time": ["Nachrichtenzeit", "timestamp"], "weather service": ["Wetterdienst", "weather"],
    photos: ["Fotos", "photo"], schedule: ["Bauzeitenplan", "schedule"], "site diary": ["Bautagebuch", "diary"], notices: ["Meldungen", "documents"],
    "e-mail": ["E-Mail", "email"], minutes: ["Protokoll", "minutes"], "client document": ["Auftraggeber-Dokument", "document"],
    "project data": ["Projektdaten", "project"], calendar: ["Kalender", "calendar"] };
  const TYPE_ICON = { message: "🎙", voice: "🎙", answer: "💬", user: "✍️", timestamp: "🕒", weather: "🌦", photo: "📷", schedule: "📊",
    diary: "📓", documents: "📄", email: "✉️", minutes: "📝", document: "📄", project: "🏗", calendar: "📅" };
  function iconFor(eid, type) {
    const e = eid || "";
    if (/^msg-/.test(e)) return "🎙";
    if (/^photo-/.test(e)) return "📷";
    if (/^mail-/.test(e)) return "✉️";
    if (/^cal-/.test(e)) return "📅";
    if (/^sched-/.test(e)) return "📊";
    if (/^(gutachten-|lv-)/.test(e)) return "📄";
    if (/^crew-/.test(e)) return "👷";
    return TYPE_ICON[type] || "🔗";
  }
  window.NWGlass = { iconFor, ST, LANG, L };

  function enhanceDoc(el) {
    const dh = q(".dh", el); if (!dh) return;
    const pill = q(".pill", dh), st = pill ? ["draft", "checked", "sent"].find(s => pill.classList.contains(s)) : null;
    const title = q("h2", dh)?.textContent || L("Document", "Dokument");
    if (!q(".gl-sheetbar", el)) {
      el.insertAdjacentHTML("afterbegin", `<div class="gl-sheetbar"><button type="button" class="gl-close">‹ ${L("Back", "Zurück")}</button><b>${esc(title)}</b></div>`);
      q(".gl-close", el).onclick = () => document.body.classList.remove("gl-sheet", "gl-sheet-docs");
    }
    // the description line mixes English and German: keep the one for the current language
    const meta = q(":scope > span.mut", dh), types = (typeof cfg !== "undefined" && cfg?.doc_types) || {};
    if (meta && !meta.dataset.gl) {
      meta.dataset.gl = 1;
      for (const v of Object.values(types)) if (v.en && meta.textContent.startsWith(v.en)) { meta.textContent = DE ? meta.textContent.slice(v.en.length).trim() : v.en; break; }
    }
    qa(".badge", dh).forEach(b => { if (/being verified/.test(b.textContent)) { b.classList.add("gl-run"); b.innerHTML = `<span class="gl-spin"></span>${L("being verified", "wird geprüft")}`; } });
    if (st && !q(".gl-steps", el)) {
      const order = ["draft", "checked", "sent"], i = order.indexOf(st);
      dh.insertAdjacentHTML("afterend", `<div class="gl-steps" aria-label="Status">${order.map((s, k) =>
        `<span class="${k < i ? "done" : k === i ? "cur" : ""}" ${k === i ? 'aria-current="step"' : ""}>${ST[s]}</span>`).join("")}</div>`);
    }
    const first = q(".f", el);
    if (first && !q(".gl-section", el)) first.insertAdjacentHTML("beforebegin", `<div class="gl-section">${L("Fields and evidence", "Felder und Belege")}</div>`);
    qa(".f", el).forEach(f => {
      const lock = q('label span[title^="Edited by you"],label span[title^="Von dir geändert"]', f);
      if (lock && !q(".gl-lock", f)) { f.classList.add("gl-locked"); lock.insertAdjacentHTML("afterend", `<span class="gl-lock">${L("edited by you", "von dir geändert")}</span>`); }
      const a = q(".src a[data-q]", f);
      if (a && !a.classList.contains("gl-chip")) {
        const m = /^source: (.*?)(?: · (.*))?$/s.exec(a.textContent.trim()) || [];
        const [de, type] = SRC_DE[m[1]] || [m[1] || "Quelle", ""];
        const kind = DE ? de : (m[1] || "source");
        const eid = q(".src code", f)?.textContent || "";
        a.classList.add("gl-chip");
        a.title = `${L("Source", "Quelle")}: ${kind}${eid ? " · " + L("evidence", "Beleg") + " " + eid : ""} · ${L("tap for the quote", "antippen für den Wortlaut")}`;
        a.innerHTML = `<span aria-hidden="true">${iconFor(eid, type)}</span><span>${esc(m[2] || kind)}</span>`;
      }
      qa(".src span", f).forEach(s => {
        if (/unsicher|low confidence/.test(s.textContent)) s.classList.add("gl-low");
        else if (/%$/.test(s.textContent.trim())) { s.classList.add("gl-conf"); s.title = L("Extraction confidence", "Sicherheit der Extraktion"); }
      });
    });
  }

  /* in-page confirm for sending on (no window.confirm) */
  document.addEventListener("click", e => {
    const b = e.target.closest?.('[data-st="sent"]');
    if (!b || b._glOk) return;
    e.stopImmediatePropagation(); e.preventDefault();
    const row = b.closest(".row") || b.parentElement;
    if (row.nextElementSibling?.classList.contains("gl-confirm")) return;
    row.insertAdjacentHTML("afterend", `<div class="gl-confirm" role="alertdialog" aria-label="${L("Confirm", "Bestätigen")}">
      <b>${L("Mark this document as sent? It becomes read-only. Nothing is sent automatically.",
             "Wirklich weitergeben? Das Dokument wird als weitergegeben markiert und ist danach schreibgeschützt. Es wird nichts automatisch versendet.")}</b>
      <button type="button" class="gl-yes">${L("Yes, mark as sent", "Ja, weitergeben")}</button><button type="button" class="gl-no">${L("Cancel", "Abbrechen")}</button></div>`);
    const box = row.nextElementSibling;
    q(".gl-no", box).onclick = () => box.remove();
    q(".gl-yes", box).onclick = () => { box.remove(); b._glOk = true; b.click(); };
    q(".gl-yes", box).focus();
  }, true);

  /* phone: open the document as a full-screen sheet */
  document.addEventListener("click", e => {
    if (e.target.closest?.("#msgs [data-open], .gl-doccard")) document.body.classList.add("gl-sheet");
    if (e.target.closest?.("#docList li[data-id]")) document.body.classList.add("gl-sheet-docs");
  }, true);
  window.NWGlass.openSheet = which => document.body.classList.add(which === "docs" ? "gl-sheet-docs" : "gl-sheet");

  /* ------------------------------------------------------------------ chat: document cards + quick answers */
  let docCache = null, docFetch = null;
  function fetchDocs() {
    if (!window.NW?.api) return Promise.resolve([]);
    docFetch = docFetch || window.NW.api("/api/docs").then(d => (docCache = d)).catch(() => docCache || []).finally(() => setTimeout(() => (docFetch = null), 300));
    return docFetch;
  }
  function docCardHtml(d) {
    const req = d.meta?.fields?.filter(f => f.required) || [];
    const filled = req.filter(f => d.fields?.[f.key]?.value).length;
    const loc = d.fields?.location?.value || d.fields?.subject?.value || "";
    const pct = req.length ? Math.round(filled / req.length * 100) : 100, np = (d.photos || []).length;
    return `<div class="gl-dc-top"><b>${esc(d.title)}${loc ? " · " + esc(loc) : ""}</b><span class="pill ${esc(d.status)}">${ST[d.status] || esc(d.status)}</span></div>
      <div class="gl-progress" role="progressbar" aria-valuenow="${filled}" aria-valuemin="0" aria-valuemax="${req.length}"><i style="width:${pct}%"></i></div>
      <div class="gl-dc-sub">${L(`${filled} of ${req.length} required fields · ${np} photo${np === 1 ? "" : "s"}`, `${filled} von ${req.length} Pflichtfeldern · ${np} Foto${np === 1 ? "" : "s"}`)}</div>
      <div class="gl-dc-act"></div>`;
  }
  function fillCards(box) {
    const list = docCache || [];
    qa(".m.assistant [data-open]", box).forEach(b => {
      const m = b.closest(".m"), d = list.find(x => x.id === b.dataset.open);
      if (!d) return;
      let card = q(".gl-doccard", m);
      if (!card) { card = document.createElement("div"); card.className = "gl-doccard"; (q(".acts", m) || m).before(card); }
      if (card.dataset.sig === d.updated_at + d.status) return;
      card.dataset.sig = d.updated_at + d.status;
      card.innerHTML = docCardHtml(d);
      b.textContent = L("Open", "Öffnen");
      q(".gl-dc-act", card).appendChild(b);
    });
  }
  function enhanceMsgs() {
    const box = q("#msgs"); if (!box) return;
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    if (docCache) fillCards(box);
    if (q("#msgs [data-open]")) fetchDocs().then(() => { fillCards(box); if (nearBottom) box.scrollTop = 1e9; });
    const all = qa(".m", box), last = all[all.length - 1];
    if (last?.classList.contains("assistant") && !q(".gl-quick", last)) {
      const text = last.firstChild?.nodeType === 3 ? last.firstChild.data : "";
      const chips = [], ask = (text.match(/[^.!?]*\?/g) || []).pop() || "";   // only the question sentence
      if (/\b(Wann|Datum|Uhrzeit|Zeitpunkt|When|date|time)\b/i.test(ask)) {
        const n = new Date(), p = x => String(x).padStart(2, "0");
        const now = `${p(n.getDate())}.${p(n.getMonth() + 1)}.${n.getFullYear()} ${p(n.getHours())}:${p(n.getMinutes())}`;
        chips.push([`${L("Today", "Heute")}, ${now.slice(11)}`, now]);
      }
      if (ask && /„skip“|"skip"|\bskip\b/.test(text)) chips.push([L("Skip", "Überspringen"), "skip"]);
      if (chips.length) {
        last.insertAdjacentHTML("beforeend", `<div class="gl-quick">${chips.map(([l, v]) => `<button type="button" data-gl-say="${esc(v)}">${esc(l)}</button>`).join("")}</div>`);
        q(".gl-quick", last).addEventListener("click", e => {
          const b = e.target.closest("[data-gl-say]"); if (!b) return;
          q("#inp").value = b.dataset.glSay; q("#send").click();
        });
      }
    }
    if (nearBottom) box.scrollTop = 1e9;
  }

  /* ------------------------------------------------------------------ site plan: labels only for the hovered or selected object */
  let twinRaf = 0;
  function syncTwinLabels() {
    twinRaf = 0;
    const tip = q("#twTip"), stage = q(".tw-stage");
    const hover = tip && tip.style.display === "block" ? tip.textContent.trim() : "";
    const sel = q("#twSide h3")?.textContent.trim() || "";
    let tipMatched = false;
    for (const el of qa("#twCanvas .twl.zone, #twCanvas .twl.struct")) {
      const name = (q("b", el) || el).textContent.trim();
      const on = !!name && (name === hover || name === sel);
      if (on && name === hover) tipMatched = true;
      el.classList.toggle("gl-show", on);
    }
    const piles = /pfahl|pile/i.test(hover + " " + sel);
    qa("#twCanvas .twl.pile").forEach(el => el.classList.toggle("gl-show", piles));
    stage?.classList.toggle("gl-tip-label", tipMatched);
  }
  const twinSoon = () => { if (!twinRaf) twinRaf = requestAnimationFrame(syncTwinLabels); };
  function bindTwin() {
    const tip = q("#twTip"), side = q("#twSide");
    const o = new MutationObserver(twinSoon);
    if (tip) o.observe(tip, { attributes: true, attributeFilter: ["style"], childList: true, characterData: true, subtree: true });
    if (side) o.observe(side, { childList: true, subtree: true });
  }

  /* ------------------------------------------------------------------ observe + boot */
  let pendingDoc = new Set(), pendingMsgs = false, cardTimer = 0;
  const mo = new MutationObserver(recs => {
    for (const r of recs) {
      if (r.type === "attributes") {
        if (r.attributeName === "class" && r.target.classList?.contains("tab")) syncNav();
        else if (DE) trAttrs(r.target);
        continue;
      }
      const t = r.target.nodeType === 1 ? r.target : r.target.parentElement;
      const docEl = t?.closest?.("#assistDoc,#docView"); if (docEl) pendingDoc.add(docEl);
      if (t?.closest?.("#msgs")) pendingMsgs = true;
      if (t?.closest?.("#twCanvas")) twinSoon();
      if (DE && t?.closest?.("#ltT")) { trCaption(q("#ltT")); continue; }
      if (r.type === "characterData") { if (DE) trText(r.target); else enPills(r.target); }
      else r.addedNodes.forEach(n => (DE ? walk(n) : enPills(n)));
    }
    if (pendingDoc.size) {
      const s = pendingDoc; pendingDoc = new Set(); s.forEach(enhanceDoc);
      clearTimeout(cardTimer);                    // a status or field change in the document updates the chat cards
      cardTimer = setTimeout(() => { const box = q("#msgs"); if (box && q("[data-open]", box)) fetchDocs().then(() => fillCards(box)); }, 400);
    }
    if (pendingMsgs) { pendingMsgs = false; enhanceMsgs(); }
  });

  function boot() {
    buildHeader();
    buildNav();
    buildComposer();
    bindSwipe();
    bindTwin();
    if (DE) walk(document.body); else enPills(document.body);
    qa("#assistDoc,#docView").forEach(enhanceDoc);
    enhanceMsgs();
    mo.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["class", "placeholder", "title"] });
  }
  boot();
})();
