"""Request language (de | en) + message catalog. The frontend sends `X-Lang` on every call (app.py middleware sets it);
background threads and tests see the default. Backend text goes through T("key"); registry text through registry.tr()."""
from contextvars import ContextVar

LANGS = ("de", "en")
_lang: ContextVar[str] = ContextVar("lang", default="de")


def get_lang() -> str:
    return _lang.get()


def set_lang(lang) -> str:
    lang = lang if lang in LANGS else "en"
    _lang.set(lang)
    return lang


CATALOG: dict[str, dict[str, str]] = {}


def add(entries: dict[str, tuple[str, str]]):
    """entries: key -> (de, en)"""
    for k, (de, en) in entries.items():
        CATALOG[k] = {"de": de, "en": en}


def T(key: str, lang: str | None = None, **kw) -> str:
    e = CATALOG[key]
    s = e.get(lang or get_lang()) or e["de"]
    return s.format(**kw) if kw else s


add({
    "generic_q": ("Bitte ergänzen: ", "Please add: "),
    "err_fieldname": ("Feldname fehlt oder ist zu lang", "Field name is missing or too long"),
    "err_only_custom": ("Nur selbst hinzugefügte Felder können entfernt werden", "Only fields you added yourself can be removed"),
})


def fmt_date(d, with_time=False) -> str:
    """dd.mm.yyyy (de) / yyyy-mm-dd (en); `d` is a date/datetime."""
    if get_lang() == "de":
        return d.strftime("%d.%m.%Y %H:%M" if with_time else "%d.%m.%Y")
    return d.strftime("%Y-%m-%d %H:%M" if with_time else "%Y-%m-%d")


add({
    "src_voice": ("Diktat", "Dictation"), "src_project": ("Projektstammdaten", "Project master data"), "src_document": ("Unterlage", "Document"),
    "src_calendar": ("Kalender", "Calendar"), "src_message": ("Chat-Nachricht", "Chat message"), "src_answer": ("Antwort im Chat", "Chat answer"),
    "src_user": ("manuell bearbeitet", "edited manually"), "src_timestamp": ("Zeitstempel", "Timestamp"),
    "src_weather": ("Wetterdienst (Open-Meteo)", "Weather service (Open-Meteo)"), "src_photo": ("Fotos", "Photos"),
    "src_schedule": ("Bauzeitenplan", "Construction schedule"), "src_diary": ("Bautagebuch", "Site diary"), "src_documents": ("Anzeigen", "Notices"),
    "src_email": ("E-Mail", "Email"), "src_minutes": ("Protokoll", "Minutes"), "src_drilling": ("Bohrzeitenliste Polier", "Foreman drilling-time list"),
    "src_unknown": ("unbekannt", "unknown"),
    "ex_gps": ("GPS aus Foto", "GPS from photo"), "ex_site_loc": ("Standort Baustelle (kein GPS im Foto)", "Site location (no GPS in photo)"),
    "ex_none": ("keine", "none"), "ex_unverified": (" · Kategorie nicht geprüft, bitte bestätigen", " · category not verified, please confirm"),
    "ex_detection": ("Erkennung", "Detection"),
    "ex_footer_checked": ("Entwurf mit KI-Unterstützung erstellt, geprüft von {by} am {at}.", "Draft created with AI assistance, checked by {by} on {at}."),
    "ex_footer_draft": ("ENTWURF – mit KI-Unterstützung erstellt, noch nicht geprüft. Keine Rechtsberatung.", "DRAFT – created with AI assistance, not yet checked. Not legal advice."),
    "ex_project": ("Bauvorhaben", "Project"), "ex_recipient": ("Empfänger", "Recipient"), "ex_sender": ("Absender", "Sender"), "ex_date": ("Datum", "Date"),
    "ex_docno": ("Dokument-Nr.", "Document no."), "ex_open": ("— (offen)", "— (open)"), "ex_missing": ("☐ fehlt", "☐ missing"),
    "ex_checklist_note": ("Hinweis: Nur formale Prüfung der Angaben, keine rechtliche Bewertung von Anspruch oder Höhe.",
                          "Note: formal check of the information only, no legal assessment of entitlement or amount."),
    "ex_draft": ("ENTWURF", "DRAFT"), "ex_completeness": ("Formale Vollständigkeit", "Formal completeness"),
    "ex_photodoc": ("Fotodokumentation", "Photo documentation"), "ex_sources_title": ("Quellenanhang – Nachweise je Feld", "Source appendix – evidence per field"),
    "ex_evidence": ("Nachweise je Feld", "Evidence per field"), "ex_case": ("Angaben zum Vorgang", "Case details"),
    "ex_day": ("Angaben zum Berichtstag", "Report-day details"), "ex_col_field": ("Feld", "Field"), "ex_col_id": ("Beleg-ID", "Evidence ID"),
    "ex_col_where": ("Quelle, Fundstelle", "Source, location"), "ex_col_excerpt": ("Auszug", "Excerpt"),
    "ex_signature": ("Unterschrift Bauleitung", "Signature site management"), "ex_print": ("Save as PDF / Print", "Save as PDF / Print"),
    "ex_formal_only": ("Nur formale Prüfung, keine rechtliche Bewertung.", "Formal check only, no legal assessment."),
})

add({
    # sources / locators (stored with the field, written in the language active when the field is filled)
    "loc_report_time": ("Zeitpunkt der Meldung", "Time of report"), "loc_chat_answer": ("Antwort im Chat {t}", "Chat answer {t}"),
    "loc_chat_value": ("Angabe im Chat {t}", "Chat entry {t}"), "loc_chat_edit": ("Änderung im Chat", "Change in chat"),
    "loc_chat_msg": ("Chat-Nachricht {t}", "Chat message {t}"), "loc_dictation": ("Diktat {a}–{b}", "Dictation {a}–{b}"),
    "loc_photo": ("Foto {name}", "Photo {name}"), "loc_report_day": ("Berichtstag", "Report day"),
    "loc_detection": ("Objekterkennung (Roboflow)", "Object detection (Roboflow)"), "q_detection": ("Erkennung auf Fotos von heute", "Detections on today's photos"),
    "loc_replanner": ("Bestätigte Umplanungen (Replanner)", "Confirmed re-plannings (replanner)"), "q_moves": ("{n} Umsetzung(en)", "{n} reassignment(s)"),
    "loc_diary_sched": ("Bautagebuch und Bauzeitenplan", "Site diary and construction schedule"),
    "q_diary_sched": ("Einträge und Leistungsmeldungen von heute", "Entries and progress reports from today"),
    "loc_photos_cat": ("Fotos Kategorie delivery", "Photos category delivery"),
    "loc_notices_day": ("Anzeigen von heute und Soll-Ist-Vergleich", "Notices from today and plan-vs-actual comparison"),
    "q_notices_day": ("{n} Anzeige(n), {m} Warnung(en)", "{n} notice(s), {m} warning(s)"),
    "loc_photo_store": ("Fotoablage", "Photo store"), "q_photos_today": ("{n} Fotos von heute", "{n} photos from today"),
    "loc_schedule": ("Bauzeitenplan: {name}", "Construction schedule: {name}"),
    "q_schedule": ("{name}: Soll {p:g}, Ist {a:g} {unit} (Stand {asof})", "{name}: planned {p:g}, actual {a:g} {unit} (as of {asof})"),
    "loc_forecast": ("Open-Meteo Prognose", "Open-Meteo forecast"), "loc_progress_report": ("Leistungsmeldung", "Progress report"),
    # generated daily-report / alert values
    "v_weather": ("{text}, Niederschlag {rain:.1f} mm, Wind bis {wind:.0f} km/h", "{text}, precipitation {rain:.1f} mm, wind up to {wind:.0f} km/h"),
    "v_weather_text": ("{text}, {tmin:.0f} bis {tmax:.0f} °C, Niederschlag {rain:.1f} mm, Wind bis {wind:.0f} km/h",
                       "{text}, {tmin:.0f} to {tmax:.0f} °C, precipitation {rain:.1f} mm, wind up to {wind:.0f} km/h"),
    "v_on_photo": ("{k} (auf {v} Foto{s})", "{k} (on {v} photo{s})"), "v_deliveries": ("{n} Lieferung(en) fotografisch dokumentiert", "{n} delivery/deliveries documented by photo"),
    "v_status_line": ("Leistungsstand {name}: Ist {a:g} / Soll {p:g} {unit}", "Progress {name}: actual {a:g} / planned {p:g} {unit}"),
    "v_frost": ("Betonage {start} bis {end} bei prognostizierter Tiefsttemperatur von {tmin:.0f} °C am {date}.",
                "Concreting {start} to {end} at a forecast minimum temperature of {tmin:.0f} °C on {date}."),
    "v_frost_basis": ("Wetterprognose Open-Meteo: {text}", "Open-Meteo weather forecast: {text}"),
    "v_delay": ("{name}: {days} Arbeitstage Rückstand zum Bauzeitenplan (Soll {p:g} {unit}, Ist {a:g} {unit}).",
                "{name}: {days} working days behind the construction schedule (planned {p:g} {unit}, actual {a:g} {unit})."),
    # chat replies
    "r_no_open_draft": ("Es ist gerade kein Entwurf offen. Erstellen Sie zuerst einen Entwurf, dann kann ich Felder ergänzen.",
                        "No draft is open right now. Create a draft first, then I can add fields."),
    "r_field_not_found": ("Ich finde kein Feld „{l}“ in {title}.", "I can't find a field “{l}” in {title}."),
    "r_field_standard": ("„{l}“ ist ein Standardfeld der {title} und kann nicht entfernt werden; lassen Sie es einfach leer.",
                         "“{l}” is a standard field of the {title} and cannot be removed; just leave it empty."),
    "r_field_removed": ("Feld „{l}“ aus {title} entfernt.", "Field “{l}” removed from {title}."),
    "r_field_failed": ("Das Feld konnte ich nicht anlegen: {e}.", "I could not create the field: {e}."),
    "r_field_added": ("Feld „{l}“ zu {title} hinzugefügt", "Field “{l}” added to {title}"),
    "r_field_exists": ("Das Feld „{l}“ gibt es in {title} bereits", "The field “{l}” already exists in {title}"),
    "r_set_to": (" und auf „{v}“ gesetzt.", " and set to “{v}”."), "r_what_value": (". Was soll dort stehen? (oder „skip“)", ". What should it say? (or “skip”)"),
    "r_daily_created": ("Bautagesbericht-Entwurf für {date} erstellt aus Fotos, Notizen, Soll-Ist und Wetter. ",
                        "Daily site report draft for {date} created from photos, notes, plan-vs-actual and weather. "),
    "r_new_field_set": ("Neues Feld „{l}“ hinzugefügt und auf „{v}“ gesetzt.", "New field “{l}” added and set to “{v}”."),
    "r_changed": ("{l} geändert auf „{v}“.", "{l} changed to “{v}”."),
    "r_locked": (" Das Feld ist jetzt gesperrt, die KI überschreibt es nicht.", " The field is now locked; the AI will not overwrite it."),
    "r_no_field_in": ("Ich finde kein Feld „{n}“ in der {title}.", "I can't find a field “{n}” in the {title}."),
    "r_taken": ("Übernommen: {l} = „{v}“.", "Applied: {l} = “{v}”."), "r_taken_l": ("✓ {l}. ", "✓ {l}. "),
    "r_merged": ("✓ Ergänzt: {title}.", "✓ Added to: {title}."), "r_created": ("✓ Entwurf fertig: {title}.", "✓ Draft ready: {title}."),
    "r_from_msg": ("Aus Ihrer Nachricht übernommen: {l}.", "Taken from your message: {l}."),
    "r_counts": ("{n} Felder mit Quelle gefüllt", "{n} fields filled, each with a source"), "r_counts_open": (", {m} offen.", ", {m} open."), "r_counts_done": (".", "."),
    "r_proposal": ("Bereits belegt, neue Angabe nur als Vorschlag: {l}.", "Already backed by evidence, new value only as a proposal: {l}."),
    "r_gaps": ("Nicht ausreichend belegt und daher leer gelassen: {l}.", "Not sufficiently backed by evidence, left empty: {l}."),
    "r_photos_attached": ("{n} Foto(s) von heute angehängt.", "{n} photo(s) from today attached."),
    "r_review_running": ("Kritische Felder werden im Hintergrund geprüft.", "Critical fields are being checked in the background."),
    "r_also_draft": ("Auch {title} entwerfen", "Also draft {title}"),
    "r_no_question": ("Es gibt gerade keine offene Frage.", "There is no open question right now."), "r_still_open": (" Noch offen: {q}", " Still open: {q}"),
    "r_skipped": ("Übersprungen. ", "Skipped. "),
    "r_unknown_field": ("{title} hat kein Feld „{n}“. Mit „Füge Feld {n} hinzu: {v}“ lege ich es an. Noch offen: {q}",
                        "{title} has no field “{n}”. With “Add field {n}: {v}” I will create it. Still open: {q}"),
    "r_no_answer": ("Das habe ich nicht verstanden. {q}", "I didn't catch that. {q}"),
    "r_diary_noted": ("Im Bautagebuch notiert, geht in den Bautagesbericht ein. Sagen Sie „Tagesbericht“, wenn Sie den Entwurf möchten.",
                      "Noted in the site diary; it goes into the daily report. Say “daily report” if you want the draft."),
    "r_all_filled": ("Alles ausgefüllt. Bitte prüfen und freigeben.", "All filled in. Please review and approve."),
    "r_or_skip": (" (oder „skip“)", " (or “skip”)"),
    "r_one_message": (" (gern alles in einer Nachricht, oder „skip“)", " (answer in one message, or “skip”)"),
    "photo_unverified": ("Kategorie nicht geprüft", "category not verified"),
    "ctx_project": ("Projekt: ", "Project: "), "ctx_manager": ("Bauleiter: ", "Site manager: "),
    "ctx_open_drafts": ("Offene Entwürfe: ", "Open drafts: "), "ctx_n_open": ("{title} ({n} Angaben offen)", "{title} ({n} fields open)"),
    "ctx_question": ("Offene Rückfrage an den Bauleiter: ", "Open question to the site manager: "),
    "help_text": ("Ich bin Ihr Baustellen-Assistent: Ich mache aus Sprachnachrichten, Texten und Fotos Entwürfe wie Nachtragsmeldung, "
                  "Behinderungsanzeige oder Bautagesbericht, mit Quelle je Feld. Nichts wird ohne Ihren Klick versendet.",
                  "I'm your site assistant: I turn voice notes, texts and photos into drafts such as a change order notice, "
                  "obstruction notice or daily report, with a source for every field. Nothing is sent without your click."),
    "chat_fallback": ("Ich bin Ihr Baustellen-Assistent und erstelle aus Sprachnachrichten, Texten und Fotos Dokumententwürfe. Wie kann ich helfen?",
                      "I'm your site assistant and turn voice notes, texts and photos into document drafts. How can I help?"),
})

add({
    "lbl_email": ("E-Mail", "Email"), "lbl_document": ("Dokument", "Document"), "lbl_chat": ("Chatnachricht", "Chat message"),
    "lbl_voice": ("Sprachnachricht", "Voice message"), "lbl_photo": ("Foto vom {taken}", "Photo from {taken}"),
})

add({
    "al_delay": ("{name}: {delay} Arbeitstage Verzug (Soll {p:g} {unit}, Ist {a:g} {unit}).", "{name}: {delay} working days behind (planned {p:g} {unit}, actual {a:g} {unit})."),
    "al_delay_watch": ("{name}: {delay} Tage hinter Plan. Beobachten.", "{name}: {delay} days behind plan. Keep watching."),
    "al_frost": ("Frostgefahr: {name} geplant {start} bis {end}, Prognose am {d} Tmin {tmin:.0f} °C.", "Frost risk: {name} planned {start} to {end}, forecast on {d} Tmin {tmin:.0f} °C."),
    "ol_mail": ("E-Mail „{subject}“ von {frm} importiert ({n} offene Punkte).", "Email “{subject}” from {frm} imported ({n} open items)."),
    "ol_filled": ("{n} Feld(er) ergänzt ({labels})", "{n} field(s) added ({labels})"), "ol_prop": ("Vorschlag zu {labels}", "Proposal for {labels}"),
    "ol_none": ("keine neuen Angaben", "no new information"),
    "ol_check_mail": ("Bitte prüfen – nichts wurde automatisch übernommen oder versendet.", "Please review – nothing was applied or sent automatically."),
    "ol_doc": ("Dokument „{file}“ ({units} Abschnitte) gelesen, {n} offene Punkte.", "Document “{file}” ({units} sections) read, {n} open items."),
    "ol_doc_prop": ("{title}: Vorschlag/Ergänzung zu {labels} (mit Quellenangabe).", "{title}: proposal/addition for {labels} (with source)."),
    "ol_check_doc": ("Bitte prüfen – gesperrte Felder wurden nicht verändert.", "Please review – locked fields were not changed."),
    "sm_we": ("Wir (Empfänger)", "We (recipient)"), "sm_counts": ("{n} offene Punkte, {m} Beschlüsse.", "{n} open items, {m} decisions."),
    "rv_one": ("nur ein Prüfer", "only one reviewer"), "rv_disagree": ("Prüfer uneinig", "Reviewers disagree"),
    "rv_unsupported": ("Wert durch Quelle nicht gestützt", "Value not supported by the source"), "rv_unproven": ("nicht belegt", "not proven"),
    "rv_check": ("Bitte Wert und Quelle prüfen.", "Please check the value and source."),
})

add({"n_photos": ("{n} Foto(s): {val}", "{n} photo(s): {val}"), "management": ("Bauleitung", "Site management")})

add({
    "c_project": ("Projektstammdaten", "Project master data"), "c_page": ("Seite {n}", "Page {n}"),
    "c_bgg": ("Baugrundgutachten, Seite {n}", "Ground investigation report, page {n}"),
    "c_drill": ("Bohrzeitenliste Polier, {id}", "Foreman drilling list, {id}"), "c_row": ("Zeile {id}", "Row {id}"),
    "c_sched": ("Bauzeitenplan, {id}", "Construction schedule, {id}"),
    "c_dr_staff": ("Bautagesbericht {date}, Personal", "Daily site report {date}, staff"), "c_staff": ("Personal", "Staff"),
    "c_dr_equip": ("Bautagesbericht {date}, Geräte", "Daily site report {date}, equipment"), "c_equip": ("Geräte", "Equipment"),
})
