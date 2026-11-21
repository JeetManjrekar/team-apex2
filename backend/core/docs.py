"""Document model: every field has value, source, author, lock and an edit log with undo."""
from .store import load, save, new_id, now, today

from nachweis_llm.registry import DOCUMENT_REGISTRY
from .llm_bridge import SETTINGS

# Display fixes for the registry's ASCII umlauts (labels/questions only; field names stay as in the registry).
_UML = [("Maengel", "Mängel"), ("maengel", "mängel"), ("Geraete", "Geräte"), ("Taetig", "Tätig"), ("taetig", "tätig"),
        ("Zusaetz", "Zusätz"), ("zusaetz", "zusätz"), ("Zustaend", "Zuständ"), ("zustaend", "zuständ"), ("Massnahmen", "Maßnahmen"),
        ("Ausgefuehrt", "Ausgeführt"), ("ausgefuehrt", "ausgeführt"), ("Naechste", "Nächste"), ("Zugehoerig", "Zugehörig"),
        ("zugehoerig", "zugehörig"), ("Klaerung", "Klärung"), ("Pruef", "Prüf"), ("pruef", "prüf"), ("fuer ", "für "),
        ("Fuer ", "Für "), ("moeglich", "möglich"), ("geaendert", "geändert"), ("verhaeltnisse", "verhältnisse"),
        ("Geraet", "Gerät"), ("aeusser", "äußer"), ("stuetz", "stütz"), ("Rueckmeldung", "Rückmeldung"),
        ("Unterlagen", "Unterlagen"), ("gehoeren", "gehören"), ("unvollstaendig", "unvollständig"), ("Bestaetig", "Bestätig"),
        ("bestaetig", "bestätig"), ("Erklaer", "Erklär"), ("durchgefuehrt", "durchgeführt"), ("Gelaende", "Gelände")]


def de(t):
    for a, b in _UML:
        t = t.replace(a, b)
    return t


# Host-only metadata per registry document type (legal basis line, photo category, recipient, closing sentence)
HOST = {
    "nachtragsmeldung": {"en": "Nachtrag report (internal, for the Nachtragsmanager)", "basis": "Interne Dokumentation für das Nachtragsmanagement",
                         "photo_cat": "Nachtrag evidence", "recipient": "Nachtragsmanagement (intern)",
                         "closing": "Sachliche Dokumentation des Vorgangs. Keine Bewertung von Anspruch oder Höhe."},
    "mehrkostenanzeige": {"en": "Additional cost notice", "basis": "gem. § 2 Abs. 5 / 6 VOB/B", "photo_cat": "Nachtrag evidence", "recipient": None,
                          "closing": "Wir kündigen hiermit an, dass für die beschriebene Leistung Mehrkosten entstehen. Die Höhe wird nach Abschluss der Feststellungen gesondert mitgeteilt."},
    "behinderungsanzeige": {"en": "Delay / obstruction notice", "basis": "gem. § 6 Abs. 1 VOB/B", "photo_cat": "obstruction", "recipient": None,
                            "closing": "Wir zeigen hiermit die oben beschriebene Behinderung an und bitten um Abhilfe bzw. Ihre Entscheidung."},
    "maengelanzeige": {"en": "Defect notice", "basis": "gem. § 4 Abs. 7 VOB/B", "photo_cat": "defect", "recipient": "Zuständiges Unternehmen",
                       "closing": "Wir fordern Sie auf, den Mangel innerhalb angemessener Frist zu beseitigen."},
    "bedenkenanmeldung": {"en": "Notice of concern", "basis": "gem. § 4 Abs. 3 VOB/B", "photo_cat": "safety", "recipient": None,
                          "closing": "Wir melden hiermit unsere Bedenken an und bitten um Ihre Entscheidung."},
    "aktennotiz": {"en": "File note (internal)", "basis": "", "photo_cat": None, "recipient": "intern", "closing": ""},
    "bautagesbericht": {"en": "Daily site report", "basis": "", "photo_cat": None, "recipient": "intern", "closing": ""},
}


def _build():
    out = {}
    for dtype, spec in DOCUMENT_REGISTRY.items():
        k = dtype.value
        title = de(spec.title_de.split(" - ")[0])
        out[k] = dict(HOST.get(k, {"en": title, "basis": "", "photo_cat": None, "recipient": None, "closing": ""}),
                      title=title, description=de(spec.description_de),
                      fields=[(f.name, de(f.label_de), f.required, f.name in SETTINGS.critical_fields, de(f.question_de))
                              for f in spec.fields])
    return out


# key, German label, required, critical, follow-up question (German, from the shared registry)
DOC_TYPES = _build()

STATUSES = ["draft", "checked", "sent"]


def field_meta(dtype, key):
    for f in DOC_TYPES[dtype]["fields"]:
        if f[0] == key:
            return {"key": f[0], "label": f[1], "required": f[2], "critical": f[3], "question": f[4]}
    return None


def all_docs():
    # documents of types no longer in the registry (older demo data) are ignored
    return [d for d in load("docs", []) if d.get("type") in DOC_TYPES]


def get(doc_id):
    return next((d for d in all_docs() if d["id"] == doc_id), None)


def put(doc):
    docs = all_docs()
    doc["updated_at"] = now()
    for i, d in enumerate(docs):
        if d["id"] == doc["id"]:
            docs[i] = doc
            break
    else:
        docs.append(doc)
    save("docs", docs)
    return doc


def create(dtype, origin="chat"):
    t = DOC_TYPES[dtype]
    doc = {"id": new_id(), "type": dtype, "title": t["title"], "status": "draft", "origin": origin,
           "created_at": now(), "updated_at": now(), "date": today(),
           "fields": {f[0]: {"value": "", "source": None, "by": None, "locked": False, "confidence": None, "proposal": None}
                      for f in t["fields"]},
           "photos": [], "log": [], "checked_by": None, "checked_at": None, "sent_at": None}
    return put(doc)


def _drop_to_draft(doc, by):
    if doc["status"] != "draft":
        doc["log"].append({"at": now(), "by": by, "kind": "status", "old": doc["status"], "new": "draft",
                           "note": "edited after check, back to draft"})
        doc["status"] = "draft"
        doc["checked_by"] = doc["checked_at"] = None


def set_field(doc, key, value, source=None, by="ai", confidence=None, fill_only=False):
    """AI never overwrites a user-locked field (or, with fill_only, any filled field); it stores a proposal instead."""
    if doc["status"] == "sent":
        return "sent"
    f = doc["fields"][key]
    value = (value or "").strip()
    if by == "ai" and (f["locked"] or (fill_only and f["value"])):
        if value and value.lower() not in f["value"].lower():
            f["proposal"] = {"value": value, "source": source}
            doc["log"].append({"at": now(), "by": "ai", "kind": "proposal", "field": key, "new": value})
            return "proposal"
        return "unchanged"
    if value == f["value"]:
        return "unchanged"
    doc["log"].append({"at": now(), "by": by, "kind": "edit", "field": key, "old": f["value"], "new": value,
                       "old_source": f["source"], "old_by": f["by"], "old_locked": f["locked"]})
    f.update({"value": value, "source": source, "by": by, "confidence": confidence,
              "locked": f["locked"] or by == "user", "proposal": None})
    _drop_to_draft(doc, by)   # any change of a reviewed document (user or AI, e.g. a mail import) sends it back to Draft
    return "set"


def accept_proposal(doc, key):
    p = doc["fields"][key].get("proposal")
    if p:
        doc["fields"][key]["locked"] = False
        set_field(doc, key, p["value"], p["source"], by="user")
        doc["fields"][key]["source"] = p["source"]
    return doc


def undo(doc, index):
    e = doc["log"][index]
    if e.get("kind") != "edit" or e.get("undone"):
        return doc
    f = doc["fields"][e["field"]]
    doc["log"].append({"at": now(), "by": "user", "kind": "undo", "field": e["field"], "old": f["value"], "new": e["old"]})
    f.update({"value": e["old"], "source": e["old_source"], "by": e["old_by"], "locked": e["old_locked"], "proposal": None})
    e["undone"] = True
    _drop_to_draft(doc, "user")
    return doc


def missing(doc):
    return [f[0] for f in DOC_TYPES[doc["type"]]["fields"] if f[2] and not doc["fields"][f[0]]["value"]]


def set_status(doc, status, user="Bauleitung"):
    if status not in STATUSES:
        raise ValueError("bad status")
    old = doc["status"]
    if status == "checked" and missing(doc):
        raise ValueError("Required fields missing: " + ", ".join(field_meta(doc["type"], k)["label"] for k in missing(doc)))
    if status == "sent" and old != "checked":
        raise ValueError("Mark as checked first")
    doc["status"] = status
    if status == "checked":
        doc["checked_by"], doc["checked_at"] = user, now()
    if status == "sent":
        doc["sent_at"] = now()
    doc["log"].append({"at": now(), "by": "user", "kind": "status", "old": old, "new": status})
    return doc


def public(doc):
    """Doc plus metadata the UI needs."""
    t = DOC_TYPES[doc["type"]]
    d = dict(doc)
    d["meta"] = {"en": t["en"], "basis": t["basis"], "description": t["description"],
                 "fields": [{"key": f[0], "label": f[1], "required": f[2], "critical": f[3]} for f in t["fields"]]}
    d["missing"] = missing(doc)
    return d
