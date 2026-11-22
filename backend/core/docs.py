"""Document model: every field has value, source, author, lock and an edit log with undo."""
import re
import threading

from .store import load, save, new_id, now, today
from . import registry
from .llm_settings import today as demo_today
from .i18n import get_lang, T
from collections.abc import Mapping
from functools import lru_cache

# Re-entrant lock for read-modify-write of docs.json from background threads (reviewer).
LOCK = threading.RLock()


def de(t):
    return t or ""


# Host-only metadata per registry document type (legal basis line, photo category, recipient, closing sentence)
HOST = {
    "nachtragsmeldung": {"en": "Nachtrag report (internal, for the Nachtragsmanager)", "basis": "Interne Dokumentation für das Nachtragsmanagement",
                         "photo_cat": "Nachtrag evidence", "recipient": "Nachtragsmanagement (intern)",
                         "closing": "Sachliche Dokumentation des Vorgangs. Keine Bewertung von Anspruch oder Höhe.",
                         "basis_en": "Internal documentation for change-order management", "recipient_en": "Change-order management (internal)",
                         "closing_en": "Factual documentation of the event. No assessment of entitlement or amount."},
    "mehrkostenanzeige": {"en": "Additional cost notice", "basis": "gem. § 2 Abs. 5 / 6 VOB/B", "photo_cat": "Nachtrag evidence", "recipient": None,
                          "closing": "Wir kündigen hiermit an, dass für die beschriebene Leistung Mehrkosten entstehen. Die Höhe wird nach Abschluss der Feststellungen gesondert mitgeteilt.",
                          "basis_en": "pursuant to § 2 (5) / (6) VOB/B", "closing_en": "We hereby notify you that additional costs arise for the work described. The amount will be communicated separately once the findings are complete."},
    "behinderungsanzeige": {"en": "Delay / obstruction notice", "basis": "gem. § 6 Abs. 1 VOB/B", "photo_cat": "obstruction", "recipient": None,
                            "closing": "Wir zeigen hiermit die oben beschriebene Behinderung an und bitten um Abhilfe bzw. Ihre Entscheidung.",
                            "basis_en": "pursuant to § 6 (1) VOB/B", "closing_en": "We hereby give notice of the obstruction described above and ask for remedy or your decision."},
    "maengelanzeige": {"en": "Defect notice", "basis": "gem. § 4 Abs. 7 VOB/B", "photo_cat": "defect", "recipient": "Zuständiges Unternehmen",
                       "closing": "Wir fordern Sie auf, den Mangel innerhalb angemessener Frist zu beseitigen.",
                       "basis_en": "pursuant to § 4 (7) VOB/B", "recipient_en": "Responsible company",
                       "closing_en": "We request that you remedy the defect within a reasonable period."},
    "bedenkenanmeldung": {"en": "Notice of concern", "basis": "gem. § 4 Abs. 3 VOB/B", "photo_cat": "safety", "recipient": None,
                          "closing": "Wir melden hiermit unsere Bedenken an und bitten um Ihre Entscheidung.",
                          "basis_en": "pursuant to § 4 (3) VOB/B", "closing_en": "We hereby register our concerns and ask for your decision."},
    "aktennotiz": {"en": "File note (internal)", "basis": "", "photo_cat": None, "recipient": "intern", "closing": "", "recipient_en": "internal"},
    "bautagesbericht": {"en": "Daily site report", "basis": "", "photo_cat": None, "recipient": "intern", "closing": "", "recipient_en": "internal"},
}


@lru_cache
def _build(lang):
    """Document types from backend/registry/doc_types/*.yaml (merged APEX 2 registry) + host metadata above, in `lang`."""
    out = {}
    for k in registry.doc_types():
        spec = registry.doc_spec(k)
        title = registry.tr(spec, "label", lang)
        h = dict(HOST.get(k, {"en": title, "basis": "", "photo_cat": None, "recipient": None, "closing": ""}))
        for x in ("basis", "recipient", "closing"):
            h[x] = h.get(f"{x}_{lang}") or h.get(x)
        out[k] = dict(h, title=title, description=registry.tr(spec, "static_text", lang),
                      checklist=[dict(c, label=registry.tr(c, "label", lang)) for c in spec.get("checklist", [])],
                      fields=[(f["key"], registry.tr(f, "label", lang), bool(f.get("required")), bool(f.get("critical")),
                               registry.tr(f, "question", lang) or (T("generic_q", lang) + registry.tr(f, "label", lang)), f.get("type", "text"), bool(f.get("derived")))
                              for f in spec["fields"]])
    return out


class _DocTypes(Mapping):
    """The registry document types in the current request language (core.i18n); behaves like a dict.
    Tuples: key, label, required, critical, follow-up question, type, derived."""
    def _d(self):
        return _build(get_lang())

    def __getitem__(self, k):
        return self._d()[k]

    def __iter__(self):
        return iter(self._d())

    def __len__(self):
        return len(self._d())


DOC_TYPES = _DocTypes()

STATUSES = ["draft", "checked", "sent"]


def fields_of(doc):
    """Field tuples of one document: the registry fields of its type plus the fields the user added to this draft
    (`custom_fields`, optional free text). Everything that lists, labels or exports fields goes through here."""
    return DOC_TYPES[doc["type"]]["fields"] + [(c["key"], c["label"], False, False, T("generic_q") + c["label"], "text", False)
                                               for c in doc.get("custom_fields", [])]


def field_meta(doc_or_type, key):
    """doc_or_type: a document (includes its custom fields) or a type key (registry fields only)."""
    fields = fields_of(doc_or_type) if isinstance(doc_or_type, dict) else DOC_TYPES[doc_or_type]["fields"]
    for f in fields:
        if f[0] == key:
            return {"key": f[0], "label": f[1], "required": f[2], "critical": f[3], "question": f[4], "type": f[5], "derived": f[6]}
    return None


def _empty_field():
    return {"value": "", "source": None, "by": None, "locked": False, "confidence": None, "proposal": None, "version": 0, "review": None}


def _normalize(doc):
    """Docs stored before the registry merge: add slots for new registry fields (old keys stay, they are just not shown)."""
    for f in fields_of(doc):
        doc["fields"].setdefault(f[0], _empty_field())
    doc["title"] = DOC_TYPES[doc["type"]]["title"]    # re-rendered in the current language
    return doc


def _tokens(s):
    return [t for t in re.split(r"[^a-z0-9äöüß]+", (s or "").lower()) if t]


def find_field(doc, name):
    """Field key of `doc` the user means by `name` ("Ort", "location", "Personal je Firma"): exact key or label first,
    then the name as a whole word group of a label ("ort" -> "Ort / Bauabschnitt"). None if nothing matches."""
    n = " ".join(_tokens(name))
    if not n:
        return None
    fs = fields_of(doc)
    for k, label, *_ in fs:
        if n in (" ".join(_tokens(k)), " ".join(_tokens(label))):
            return k
    for k, label, *_ in fs:
        words = _tokens(label)
        if any(" ".join(words[i:i + len(n.split())]) == n for i in range(len(words))):
            return k
    return None


def add_field(doc, label, by="user"):
    """Add a free-text field to this draft (e.g. "Ort" on a Bautagesbericht). Returns (key, created); an existing
    field with that name is reused instead of adding a duplicate."""
    label = re.sub(r"\s+", " ", (label or "").strip(" .:;,\"'„“")).strip()
    if not label or len(label) > 60:
        raise ValueError(T("err_fieldname"))
    key = find_field(doc, label)
    if key:
        return key, False
    if doc["status"] == "sent":
        raise ValueError("Document was already sent")
    base = "custom_" + ("_".join(_tokens(label))[:40] or "feld")
    key, i = base, 2
    while key in doc["fields"]:
        key, i = f"{base}_{i}", i + 1
    doc.setdefault("custom_fields", []).append({"key": key, "label": label[:1].upper() + label[1:]})
    doc["fields"][key] = _empty_field()
    doc["log"].append({"at": now(), "by": by, "kind": "field_added", "field": key, "new": label})
    return key, True


def remove_field(doc, key, by="user"):
    """Remove a field the user added; registry fields of the type cannot be removed (they can be left empty)."""
    custom = [c for c in doc.get("custom_fields", []) if c["key"] == key]
    if not custom:
        raise ValueError(T("err_only_custom"))
    if doc["status"] == "sent":
        raise ValueError("Document was already sent")
    doc["custom_fields"] = [c for c in doc["custom_fields"] if c["key"] != key]
    old = doc["fields"].pop(key, {}).get("value", "")
    doc["log"].append({"at": now(), "by": by, "kind": "field_removed", "field": key, "old": old, "new": custom[0]["label"]})
    return doc


def all_docs():
    # documents of types no longer in the registry (older demo data) are ignored
    return [_normalize(d) for d in load("docs", []) if d.get("type") in DOC_TYPES]


def get(doc_id):
    return next((d for d in all_docs() if d["id"] == doc_id), None)


def put(doc):
    with LOCK:
        docs = all_docs()
        doc["updated_at"] = now()
        for i, d in enumerate(docs):
            if d["id"] == doc["id"]:
                cp_new, cp_old = doc.get("claim_potential"), d.get("claim_potential")
                if cp_old and (not cp_new or cp_old.get("at", "") > cp_new.get("at", "")):
                    doc["claim_potential"] = cp_old   # estimate stored by the background thread after `doc` was read
                docs[i] = doc
                break
        else:
            docs.append(doc)
        save("docs", docs)
    from . import claim_potential       # lazy: claim_potential imports this module
    claim_potential.schedule(doc)       # background, debounced, no-op unless a claim's fields changed
    return doc


def create(dtype, origin="chat"):
    t = DOC_TYPES[dtype]
    doc = {"id": new_id(), "type": dtype, "title": t["title"], "status": "draft", "origin": origin,
           "created_at": now(), "updated_at": now(), "date": demo_today().isoformat(),   # DEMO_TODAY or real date
           "fields": {f[0]: _empty_field() for f in t["fields"]},
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
              "locked": f["locked"] or by == "user", "proposal": None, "version": f.get("version", 0) + 1,
              "review": None})   # new value -> earlier reviewer verdict no longer applies
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
    if e.get("kind") != "edit" or e.get("undone") or e["field"] not in doc["fields"]:   # field removed since
        return doc
    f = doc["fields"][e["field"]]
    doc["log"].append({"at": now(), "by": "user", "kind": "undo", "field": e["field"], "old": f["value"], "new": e["old"]})
    f.update({"value": e["old"], "source": e["old_source"], "by": e["old_by"], "locked": e["old_locked"], "proposal": None,
              "version": f.get("version", 0) + 1, "review": None})
    e["undone"] = True
    _drop_to_draft(doc, "user")
    return doc


def missing(doc):
    return [f[0] for f in fields_of(doc) if f[2] and not doc["fields"][f[0]]["value"]]


def set_status(doc, status, user=None):
    user = user or T("management")
    if status not in STATUSES:
        raise ValueError("bad status")
    old = doc["status"]
    if status == "checked" and missing(doc):
        raise ValueError("Required fields missing: " + ", ".join(field_meta(doc, k)["label"] for k in missing(doc)))
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
    custom = {c["key"] for c in doc.get("custom_fields", [])}
    d["title"] = t["title"]    # the registry title in the current language, not the one stored at creation
    d["meta"] = {"en": t["en"], "basis": t["basis"], "description": t["description"],
                 "fields": [{"key": f[0], "label": f[1], "required": f[2], "critical": f[3], "type": f[5], "derived": f[6],
                             "custom": f[0] in custom} for f in fields_of(doc)]}
    d["missing"] = missing(doc)
    return d
