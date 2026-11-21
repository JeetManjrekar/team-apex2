"""Chat handling (host side): builds source chunks, calls the extraction layer, persists proposals, asks follow-ups,
handles edits by chat, daily report and proposals from alerts. All status changes stay with the user.

Voice and LLM meet here: a dictation arrives with its Whisper segments (evidence_meta from routes/voice.py); every
segment becomes its own source chunk (audio:<id>@<start>-<end>), so a field extracted from speech cites the exact
moment of the recording ("Diktat 00:04–00:11")."""
import os, re, datetime as dt
from . import docs, plan, sanitizer, llm_bridge, replanner, sources
from .extract import detect_intents, extract, to_text, DAILY_RX, EDIT_RX, LOC
from .llm_settings import today as llm_today
from .registry import related_fields
from .store import load, save, new_id, now, today, SITE
from .i18n import T, get_lang, set_lang, fmt_date

# Statements that are site diary notes, not answers to an open question
NOTE_RX = re.compile(r"\b(arrived|delivered|geliefert|angeliefert|done|finished|completed|fertig|erledigt|betoniert|poured|started|begonnen)\b", re.I)
FOLLOWUP_BATCH = 3     # missing fields asked together in one Rückfrage
NEW_RX = re.compile(r"\b(neue[rnms]?|new|another|weitere[rnms]?|zweite[rnms]?|noch eine?[rnms]?)\b", re.I)
# user-defined fields on the open draft ("Füge Feld Ort hinzu: Achse 3", "add field location: axis 3", "entferne Feld Ort")
ADD_FIELD_RX = re.compile(
    r"^\s*(?:bitte\s+)?(?:"
    r"(?:füge?|fuege?|füg)\s+(?:(?:bitte|noch)\s+)*(?:(?:das|den|die|ein|eine|ein\s+neues|neues|zusätzliches)\s+)?(?:feld\s+)?"
    r"(?P<a>[^:=]+?)(?:\s+(?:zum|zur|in\s+den|in\s+die|in\s+das|im|ins)\s+[^:=]+?)?\s+hinzu"
    r"|(?:add|create)\s+(?:(?:a|an|the)\s+)?(?:new\s+)?field\s+(?P<b>[^:=]+?)(?:\s+to\s+(?:the\s+)?[^:=]+?)?"
    r"|(?:add|create)\s+(?:(?:a|an|the)\s+)?(?:new\s+)?(?P<e>[^:=]+?)\s+field(?:\s+to\s+(?:the\s+)?[^:=]+?)?"
    r"|(?:neues|zusätzliches)\s+feld\s+(?P<c>[^:=]+?)"
    r")\s*(?:[:=]\s*(?P<v>\S.*?))?\s*$", re.I)
REMOVE_FIELD_RX = re.compile(r"^\s*(?:bitte\s+)?(?:entferne|lösche|loesche|remove|delete)\s+(?:(?:das|the)\s+)?(?:feld|field)\s+(?P<l>.+?)\s*$", re.I)
# "Ort: Achse 3" -- an explicit field assignment (label of at most 4 words)
LABEL_VALUE_RX = re.compile(r"^\s*(?P<l>[A-Za-zÄÖÜäöüß][\wÄÖÜäöüß /().-]{0,40}?)\s*[:=]\s*(?P<v>\S.*?)\s*$", re.S)
SKIP_RX = re.compile(r"^\s*(skip|weiter|überspringen|unknown|unbekannt|keine ahnung|weiß (?:ich )?nicht|weiss (?:ich )?nicht|n/?a|-)\s*$", re.I)
KIND_TO_SRC = llm_bridge.KIND_TO_SRC


def _msg(role, text, **kw):
    return dict({"id": new_id(), "role": role, "text": text, "at": now()}, **kw)


def _norm_loc(v):
    v = (v or "").lower()
    num = re.findall(r"\d+", v)
    word = "pile" if re.search(r"pile|pfahl", v) else re.sub(r"[^a-zäöü]", "", v)[:6]
    return f"{word}{''.join(num)}"


def _find_mergeable(dtype, location):
    """Hero merge (one incident = one draft per type): same type, same location, not sent yet."""
    if not location:
        return None
    for d in reversed(docs.all_docs()):
        if d["type"] == dtype and d["status"] != "sent" and _norm_loc(d["fields"].get("location", {}).get("value")) == _norm_loc(location):
            return d
    return None


# ---------- evidence ----------
def primary_chunks(text, source_kind="text", source_ref=None, locator=None, evidence_meta=None):
    """Source chunks for what the user sent this turn. Voice -> one chunk per Whisper segment."""
    ref = source_ref or new_id()
    if source_kind == "audio" and evidence_meta and (evidence_meta.get("segments") or text):
        return sources.audio_chunks(ref, evidence_meta.get("segments") or [], evidence_meta.get("audio_file"), text)
    return [sources.message_chunk(ref, text, {"email": "email", "document_page": "document"}.get(source_kind, "text"), locator)]


def context_chunks(photo_ids=None):
    """Project context + today's photos; photos attached to this message carry their full detector output."""
    days = list(dict.fromkeys([today(), llm_today().isoformat()]))
    attached = sources.photo_chunks(ids=photo_ids) if photo_ids else []
    seen = {c.ref for c in attached}
    return sources.context_chunks(llm_today()) + attached + [c for d in days for c in sources.photo_chunks(d) if c.ref not in seen]


def _source_for(by_ref, f):
    refs = [r for r in f["refs"] if r in by_ref]
    if not refs:
        return {"type": "timestamp", "evidence_id": None, "locator": T("loc_report_time"), "quote": now()[:16].replace("T", " ")}
    return sources.field_source(refs, by_ref, f.get("quote"))


UNVERIFIED_CAT = "uncategorized"
PHOTO_WINDOW_MIN = int(os.environ.get("PHOTO_ATTACH_WINDOW_MIN", "120"))


def attach_photos(doc):
    """Attach today's photos that fit the document type (category = registry photo_cat).
    Also attach recent photos nobody could categorise (no vision model / Roboflow saw nothing): uploaded within
    PHOTO_ATTACH_WINDOW_MIN minutes and not attached to another open draft. They are marked "Kategorie nicht geprüft"
    in the draft and the export until the site manager confirms or removes them."""
    cat = docs.DOC_TYPES[doc["type"]]["photo_cat"]
    cutoff = (dt.datetime.now() - dt.timedelta(minutes=PHOTO_WINDOW_MIN)).isoformat(timespec="seconds")
    taken_elsewhere = {pid for d in docs.all_docs() if d["id"] != doc["id"] and d["status"] != "sent" for pid in d.get("photos", [])}
    days = {today(), llm_today().isoformat()}       # real date and DEMO_TODAY (demo photos carry the demo day in EXIF)
    for p in load("photos", []):
        if p["id"] in doc["photos"]:
            continue
        if (cat is None or p["category"] == cat) and p.get("taken_at", "")[:10] in days:
            doc["photos"].append(p["id"])
        elif p["category"] == UNVERIFIED_CAT and p.get("uploaded_at", "") >= cutoff and p["id"] not in taken_elsewhere:
            doc["photos"].append(p["id"])        # just uploaded in this session: upload time counts, not the EXIF date


def _photo_label(p):
    cat = T("photo_unverified") if p["category"] == UNVERIFIED_CAT else p["category"]
    return f"{p['original_name']} ({cat}, {p['taken_at'][11:16]})"


def _host_fields(doc):
    """Deterministic host data, filled only when empty: project master data (cited as doc:project@p1) and attached photos."""
    f = doc["fields"]
    proj = sources.project()
    pchunk = next((c for c in sources.context_chunks(llm_today()) if c.ref == "doc:project@p1"), None)
    for key, val in (("project", proj.get("name_de") or SITE["name"]), ("addressee", proj.get("bauherr")),
                     ("contract_ref", proj.get("contract_ref"))):
        if key in f and not f[key]["value"] and val:
            src = sources.field_source([pchunk.ref], {pchunk.ref: pchunk}, val) if pchunk else \
                {"type": "project", "evidence_id": None, "locator": "Projektstammdaten", "quote": val}
            docs.set_field(doc, key, val, src, "ai", 1.0, fill_only=True)
    photos = {p["id"]: p for p in load("photos", [])}
    pics = [photos[i] for i in doc["photos"] if i in photos]
    key = next((k for k in ("photos", "photo_evidence", "evidence") if k in f), None)
    if key and pics:
        val = "; ".join(_photo_label(p) for p in pics)
        docs.set_field(doc, key, T("n_photos", n=len(pics), val=val), {"type": "photo", "evidence_id": ",".join(f"photo:{p['id']}" for p in pics),
                                                                 "locator": T("loc_photo_store"), "quote": val}, "ai", 1.0)


def apply_text(dtype, text, source_kind="text", source_ref=None, origin="chat", locator=None, evidence_meta: dict | None = None,
               photo_ids: list[str] | None = None):
    """Extract fields from text into a new or matching draft (one incident = one draft per type).
    Returns (doc, filled, proposals, merged, gaps, mode)."""
    run_id = f"{dtype}-{new_id()}"
    primary = primary_chunks(text, source_kind, source_ref, locator, evidence_meta)
    context = context_chunks(photo_ids)
    by_ref = {c.ref: c for c in primary + context}
    for c in primary + context:
        for a in c.aliases:
            by_ref.setdefault(a, c)
    # find an open draft for the same incident first, so its user edits are passed as locked fields
    doc = _find_mergeable(dtype, rules_loc(text))
    merged = doc is not None
    locked = {k: v["value"] for k, v in (doc["fields"].items() if doc else []) if v["locked"]}
    res = extract(dtype, text, primary, context, locked, run_id=run_id, focus={"pile_id": sources.pile_id(text)})
    fields, gaps, mode = res["fields"], res["gaps"], res["mode"]
    if not doc:
        doc = _find_mergeable(dtype, (fields.get("location") or {}).get("value"))
        merged = doc is not None
    if not doc:
        doc = docs.create(dtype, origin=origin)
    filled, proposals = [], []
    for k, f in fields.items():
        if k not in doc["fields"]:
            continue
        r = docs.set_field(doc, k, f["value"], _source_for(by_ref, f), "ai", f["confidence"], fill_only=merged)
        (filled if r == "set" else proposals if r == "proposal" else []).append(k)
    doc["photos"] += [i for i in photo_ids or [] if i not in doc["photos"]]
    attach_photos(doc)
    if mode == "rules" and "expected_ground_ref" in doc["fields"] and re.search(r"gutachten|soil report|fels|rock", text, re.I):
        g = by_ref.get("doc:bgg@p14")
        if g:
            docs.set_field(doc, "expected_ground_ref", g.label_de, sources.field_source([g.ref], by_ref, g.text), "ai", 0.7, fill_only=True)
    _host_fields(doc)
    doc["extraction_mode"] = mode
    # LLM follow-up wording per field (the registry question is the fallback); used by _ask_next
    doc["followup_q"] = {**doc.get("followup_q", {}), **{f["field_key"]: f["question_de"] for f in res["followups"] if f.get("field_key")}}
    doc["assistant_message_de"] = res["message"]
    docs.put(doc)
    if mode == "llm":
        llm_bridge.start_review(doc["id"])     # background, critical fields only; no-op unless the reviewer is enabled
        doc = docs.get(doc["id"])
    return doc, filled, proposals, merged, gaps, mode


def answer_followup(doc, asked, text, msg_id):
    """Read a Rückfrage answer against the whole draft, not only the asked field: an answer may name any field in any
    order (time and location in one sentence, another field than the one asked, several facts plus a correction).
    Asked fields, their registry `followup_related` fields and every empty field are filled from the answer; fields
    that already hold an AI value only get a proposal (fill_only), locked fields are never touched, nothing is invented
    (the answer is the only source). Returns (filled, proposals, mode); filled empty = the answer held none of them."""
    asked = [asked] if isinstance(asked, str) else list(asked)
    open_keys = set(asked + [r for k in asked for r in related_fields(doc["type"], k)]) | \
        {k for k, v in doc["fields"].items() if not v["value"]}
    only = list(dict.fromkeys(asked + sorted(open_keys - set(asked)) + [k for k in doc["fields"] if k not in open_keys]))
    primary = [sources.message_chunk(msg_id, text, locator=T("loc_chat_answer", t=now()[11:16]))]
    locked = {k: v["value"] for k, v in doc["fields"].items() if v["locked"]}
    only = [k for k in only if k not in locked]
    res = extract(doc["type"], text, primary, [], locked, run_id=f"followup-{doc['id']}", only_fields=only, followup=True)
    by_ref = {c.ref: c for c in primary}
    filled, proposals = [], []
    for k, f in res["fields"].items():
        # corrections of filled fields (proposals) only from the model; rule clauses are too coarse for that
        if k not in doc["fields"] or not f["value"] or (res["mode"] == "rules" and k not in open_keys):
            continue
        r = docs.set_field(doc, k, f["value"], _source_for(by_ref, f), "ai", f["confidence"], fill_only=k not in open_keys)
        (filled if r == "set" else proposals if r == "proposal" else []).append(k)
    docs.put(doc)
    if filled:
        llm_bridge.start_review(doc["id"])
    return filled, proposals, res["mode"]


def rules_loc(text):
    m = LOC.search(text)
    return m.group(0) if m else None


def _asked(state):
    """Fields of the open Rückfrage, main question first (older chat states only carry `field`)."""
    p = state.get("pending") or {}
    return p.get("fields") or ([p["field"]] if p.get("field") else [])




def _question(doc, keys):
    """One Rückfrage for one or several fields: generic "Bitte ergänzen: X" questions are merged into one list."""
    keys = [k for k in keys if docs.field_meta(doc, k)]
    qs = [doc.get("followup_q", {}).get(k) or docs.field_meta(doc, k)["question"] for k in keys]
    if len(qs) <= 1:
        return f"{''.join(qs)}{T('r_or_skip')}"
    GENERIC_Q = T("generic_q")
    generic = [q[len(GENERIC_Q):] for q in qs if q.startswith(GENERIC_Q)]
    parts = [q for q in qs if not q.startswith(GENERIC_Q)] + ([GENERIC_Q + ", ".join(generic) + "."] if generic else [])
    return " ".join(parts) + T("r_one_message")


def _ask_next(doc, state):
    """Ask for up to FOLLOWUP_BATCH missing fields at once when a model reads the answer (answer_followup). Without a
    model one field per question: an answer no rule recognises is stored verbatim, so it needs one unambiguous target.
    Either way every answer is still read against all empty fields."""
    skipped = state.get("skipped", {}).get(doc["id"], [])
    miss = [k for k in docs.missing(doc) if k not in skipped]
    if not miss:
        state.pop("pending", None)
        return T("r_all_filled")
    ask = miss[:FOLLOWUP_BATCH if llm_bridge.CFG.llm_ready else 1]
    state["pending"] = {"doc": doc["id"], "field": ask[0], "fields": ask}
    return _question(doc, ask)


def _locs(v):
    return {_norm_loc(m.group(0)) for m in LOC.finditer(v or "")}


def _answers_pending(intents, text, state):
    """A message naming the type of the draft whose Rückfrage is open ("Nachtrag: war um 10:30 an Pfahl 7") completes
    that draft instead of starting or merging another one, unless it says it is a new incident or names a location
    the draft does not have."""
    p = state.get("pending")
    doc = docs.get(p["doc"]) if p else None
    if not doc or doc["status"] == "sent" or not intents or intents[0] != doc["type"] or NEW_RX.search(text):
        return False
    said, have = _locs(text), _locs((doc["fields"].get("location") or {}).get("value"))
    return not (said and have and not said & have)


def _intents(text, state):
    """Document types this message asks for. Registry keywords and the bilingual regexes first; the LLM intent
    router only when nothing matched and no follow-up question is waiting (an answer must not become a new draft)."""
    found = detect_intents(text)
    hit = llm_bridge.detect_intent(text) if not found and not state.get("pending") else None
    if hit is None:
        from .llm_extract import rule_intent
        hit = rule_intent(text)
    if hit and hit.doc_type and hit.doc_type != "bautagesbericht" and hit.doc_type not in found:
        found = ([hit.doc_type] + found) if hit.by == "rule" else found + [hit.doc_type]
    return found, hit


# ---------- non-incident messages: chat answer vs. diary note ----------
SITE_RX = re.compile(r"\b(pfahl|pile|achse|axis|widerlager|abutment|bagger|excavator|kran|crane|beton|concrete|schalung|formwork|"
                     r"bewehrung|rebar|lieferung|delivery|geliefert|delivered|kolonne|crew|polier|nachunternehmer|baustelle|site|"
                     r"aushub|bohr|drill|regen|rain|frost|wetter|weather|lkw|truck|material|m3|m³|meter|uhr)\b", re.I)
CHAT_RX = re.compile(r"\?\s*$|^\s*(hi|hallo|hello|hey|servus|moin|guten (morgen|tag|abend)|danke|thanks|thank you|test|testing)\b|"
                     r"\b(wer bist du|who are you|was kannst du|what can you do|hilfe|help|how are you|wie geht)\b", re.I)
DE_RX = re.compile(r"[äöüß]|\b(ich|du|wir|ist|nicht|und|der|die|das|wie|was|wer|bitte|danke|hallo|kannst)\b", re.I)


def _is_chat(text, hit):
    """True if the message asks/greets/tests instead of reporting something from the site."""
    if NOTE_RX.search(text):
        return False
    if hit is not None and hit.by == "llm":
        return hit.intent == "smalltalk"
    return bool(CHAT_RX.search(text)) and not SITE_RX.search(text)


def _chat_context(state):
    lines = [T("ctx_project") + SITE["name"], T("ctx_manager") + SITE["manager"]] if SITE["name"] else []
    open_docs = [d for d in docs.all_docs() if d["status"] != "sent"][-5:]
    if open_docs:
        lines.append(T("ctx_open_drafts") + "; ".join(T("ctx_n_open", title=d["title"], n=len(docs.missing(d))) for d in open_docs))
    p = state.get("pending")
    if p and docs.get(p["doc"]):
        pd = docs.get(p["doc"])
        lines.append(T("ctx_question") + _question(pd, _asked(state)))
    return "\n".join(lines)


def _help_text(text, lang=None):
    return T("help_text", lang or get_lang())


def chat_reply(text, state, lang=None):
    return llm_bridge.converse(text, _chat_context(state), lang=lang) or _help_text(text, lang)


def _labels(doc, keys):
    return ", ".join(docs.field_meta(doc, k)["label"] for k in keys if docs.field_meta(doc, k))


def _target(state):
    """Draft a field command refers to: the one with the open Rückfrage, else the active one (never a sent one)."""
    for i in ((state.get("pending") or {}).get("doc"), state.get("active")):
        d = docs.get(i) if i else None
        if d and d["status"] != "sent":
            return d
    return None


def _label_value(text):
    m = LABEL_VALUE_RX.match(text)
    return (m.group("l").strip(), m.group("v")) if m and len(m.group("l").split()) <= 4 else None


def _set_by_user(doc, key, value, text, msg_id):
    docs.set_field(doc, key, value, {"type": "user", "evidence_id": f"msg:{msg_id}", "locator": T("loc_chat_value", t=now()[11:16]),
                                     "quote": text}, by="user")


def _field_command(text, state, msg_id):
    """Add / remove a user-defined field on the open draft. Returns the reply text."""
    doc = _target(state)
    if not doc:
        return T("r_no_open_draft")
    rm = REMOVE_FIELD_RX.match(text)
    if rm:
        key = docs.find_field(doc, rm.group("l"))
        if not key:
            return T("r_field_not_found", l=rm.group("l"), title=doc["title"])
        label = docs.field_meta(doc, key)["label"]
        try:
            docs.remove_field(doc, key)
        except ValueError:
            return T("r_field_standard", l=label, title=doc["title"])
        docs.put(doc)
        if (state.get("pending") or {}).get("doc") == doc["id"] and key in _asked(state):
            _ask_next(doc, state)
        return T("r_field_removed", l=label, title=doc["title"])
    m = ADD_FIELD_RX.match(text)
    label, value = next(g for g in (m.group("a"), m.group("b"), m.group("c"), m.group("e")) if g), m.group("v")
    try:
        key, created = docs.add_field(doc, label)
    except ValueError as e:
        return T("r_field_failed", e=e)
    label = docs.field_meta(doc, key)["label"]
    reply = T("r_field_added" if created else "r_field_exists", l=label, title=doc["title"])
    state["active"] = doc["id"]
    if value:
        _set_by_user(doc, key, value, text, msg_id)
        reply += T("r_set_to", v=value)
    else:
        state["pending"] = {"doc": doc["id"], "field": key, "fields": [key]}     # the next message is its value
        reply += T("r_what_value")
    docs.put(doc)
    return reply


def handle(text, voice=False, evidence_meta: dict | None = None, photo_ids: list[str] | None = None,
           lang: str | None = None):
    """evidence_meta (voice): {"audio_file", "segments", "duration_s", "stt_model"} from core.stt.
    photo_ids: photos the user attached to this message; their detector output goes into the LLM sources."""
    if lang:
        set_lang(lang)
    known = {p["id"] for p in load("photos", [])}
    photo_ids = [i for i in dict.fromkeys(photo_ids or []) if isinstance(i, str) and i in known]
    with llm_bridge.Timer("chat_turn_end_to_end"):
        return _handle(text, voice, evidence_meta, photo_ids, lang)


def _audio_locator(meta):
    from .stt import fmt_ts
    segs = meta.get("segments") or []
    end = segs[-1]["end"] if segs else meta.get("duration_s", 0)
    return f"Diktat 00:00–{fmt_ts(end)}" + (f" · {meta['audio_file']}" if meta.get("audio_file") else "")


def _handle(text, voice, evidence_meta=None, photo_ids=None, lang=None):
    msgs, state = load("messages", []), load("chat_state", {})
    extra = {"audio": evidence_meta.get("audio_file"), "audio_s": evidence_meta.get("duration_s")} if evidence_meta else {}
    if photo_ids:
        extra["photos"] = photo_ids
    user = _msg("user", text, voice=voice, **extra)
    _, mapping = sanitizer.mask(text)
    if mapping:
        user["masked"] = sorted(mapping.keys())
    msgs.append(user)
    out = []
    active = docs.get(state.get("active")) if state.get("active") else None
    intents, hit = _intents(text, state)
    answers = False

    if ADD_FIELD_RX.match(text) or REMOVE_FIELD_RX.match(text):
        reply = _field_command(text, state, user["id"])
        out.append(_msg("assistant", reply, doc=state.get("active")))
    elif DAILY_RX.search(text) and len(text) < 120:
        doc = daily_report(text=text, msg_id=user["id"], photo_ids=photo_ids)
        state["active"] = doc["id"]
        out.append(_msg("assistant", T("r_daily_created", date=doc["fields"]["date"]["value"]) + _ask_next(doc, state), doc=doc["id"]))
    elif EDIT_RX.match(text) and active:
        m = EDIT_RX.match(text)
        name, value = m.group(1).lower(), m.group(2)
        key = docs.find_field(active, name) or next((f[0] for f in docs.fields_of(active)
                                                     if name in f[0].replace("_", " ") or name in f[1].lower() or f[0].replace("_", " ") in name), None)
        added = False
        if not key and active["status"] != "sent":
            try:
                key, added = docs.add_field(active, name)      # "setze Ort auf Achse 3" on a draft without Ort: add it
            except ValueError:
                key = None
        if key:
            docs.set_field(active, key, value, {"type": "user", "evidence_id": None, "locator": T("loc_chat_edit"), "quote": text}, by="user")
            docs.put(active)
            label = docs.field_meta(active, key)["label"]
            out.append(_msg("assistant", (T("r_new_field_set", l=label, v=value) if added else T("r_changed", l=label, v=value)) + T("r_locked"), doc=active["id"]))
        else:
            out.append(_msg("assistant", T("r_no_field_in", n=name, title=active["title"]), doc=active["id"]))
    elif not intents and (lv := _label_value(text)) and (tgt := _target(state)) and (lv_key := docs.find_field(tgt, lv[0])):
        # "Ort: Achse 3" names a field of the open draft: the user's value, set directly
        _set_by_user(tgt, lv_key, lv[1], text, user["id"])
        docs.put(tgt)
        state["active"] = tgt["id"]
        reply = T("r_taken", l=docs.field_meta(tgt, lv_key)["label"], v=lv[1])
        if (state.get("pending") or {}).get("doc") == tgt["id"]:
            reply += " " + _ask_next(tgt, state)
        out.append(_msg("assistant", reply, doc=tgt["id"]))
    elif intents and not (answers := _answers_pending(intents, text, state)):
        primary = intents[0]
        doc, filled, proposals, merged, gaps, mode = apply_text(primary, text, "audio" if voice else "text", user["id"],
                                                                locator=_audio_locator(evidence_meta) if evidence_meta else None,
                                                                evidence_meta=evidence_meta, photo_ids=photo_ids)
        state["active"] = doc["id"]
        parts = [T("r_merged" if merged else "r_created", title=doc["title"])]
        if doc.get("assistant_message_de"):
            parts.append(doc["assistant_message_de"])
        if filled:
            parts.append(T("r_from_msg", l=_labels(doc, filled)))
        if proposals:
            parts.append(T("r_proposal", l=_labels(doc, proposals)))
        if gaps:
            parts.append(T("r_gaps", l=_labels(doc, gaps)))
        if doc["photos"]:
            parts.append(T("r_photos_attached", n=len(doc["photos"])))
        if (doc.get("review") or {}).get("status") == "running":
            parts.append(T("r_review_running"))
        parts.append(_ask_next(doc, state))
        extra = intents[1:] + (["mehrkostenanzeige"] if primary == "nachtragsmeldung" and "mehrkostenanzeige" not in intents else [])
        actions = [{"label": T("r_also_draft", title=docs.DOC_TYPES[i]["title"]), "type": i, "text": text} for i in extra]
        actions += replanner.actions_for(doc)
        out.append(_msg("assistant", " ".join(parts), doc=doc["id"], actions=actions, mode=mode))
    elif SKIP_RX.match(text) and not state.get("pending"):
        out.append(_msg("assistant", T("r_no_question")))
    elif state.get("pending") and docs.get(state["pending"]["doc"]) and CHAT_RX.search(text) and not SITE_RX.search(text):
        pd = docs.get(state["pending"]["doc"])
        out.append(_msg("assistant", chat_reply(text, state, lang) + T("r_still_open", q=_question(pd, _asked(state))), doc=pd["id"], kind="chat"))
    elif state.get("pending") and docs.get(state["pending"]["doc"]) and (answers or not NOTE_RX.search(text)):
        # a site note (delivered, finished, ...) goes to the diary unless it names the open draft's type
        p, asked = state["pending"], _asked(state)
        doc = docs.get(p["doc"])
        if SKIP_RX.match(text):
            skipped = state.setdefault("skipped", {}).setdefault(doc["id"], [])
            skipped += [k for k in asked if k not in skipped]
            reply = T("r_skipped") + _ask_next(doc, state)
        elif asked[0] in {c["key"] for c in doc.get("custom_fields", [])}:
            # a field the user added: no extraction schema knows it, the answer is its value
            _set_by_user(doc, asked[0], text, text, user["id"])
            docs.put(doc)
            reply = T("r_taken_l", l=_labels(doc, [asked[0]])) + _ask_next(doc, state)
        else:
            filled, proposals, mode = answer_followup(doc, asked, text, user["id"])
            doc = docs.get(doc["id"])
            # "Schalung: 40 m2" names a field this draft does not have (known labels were set before this branch):
            # not an answer to the question; new fields only on an explicit command, so say how
            unknown = _label_value(text) if not filled and not proposals else None
            if not filled and not proposals and mode == "rules" and not unknown:
                # no model and no pattern matched: the answer itself is the value of the main question
                docs.set_field(doc, asked[0], text, {"type": "answer", "evidence_id": f"msg:{user['id']}", "locator": T("loc_chat_answer", t=now()[11:16]), "quote": text}, by="user")
                filled = [asked[0]]
            if photo_ids:
                doc["photos"] += [i for i in photo_ids if i not in doc["photos"]]
            docs.put(doc)
            if unknown:
                reply = T("r_unknown_field", title=doc["title"], n=unknown[0], v=unknown[1], q=_question(doc, asked))
            elif filled or proposals:
                reply = (T("r_taken_l", l=_labels(doc, filled)) if filled else "") + \
                        (T("r_proposal", l=_labels(doc, proposals)) + " " if proposals else "") + _ask_next(doc, state)
            else:
                reply = T("r_no_answer", q=_question(doc, asked))
        state["active"] = doc["id"]
        out.append(_msg("assistant", reply, doc=doc["id"]))
    elif _is_chat(text, hit):
        out.append(_msg("assistant", chat_reply(text, state, lang), kind="chat"))
    else:
        out.append(_msg("assistant", _note(text, user, state)))
    msgs.extend(out)
    save("messages", msgs)
    save("chat_state", state)
    return {"user": user, "replies": out, "active": state.get("active")}


def _note(text, user, state):
    """Store a diary note; repeat the open Rückfrage, if any."""
    notes = load("notes", [])
    notes.append({"id": user["id"], "date": today(), "at": now(), "text": text})
    save("notes", notes)
    reply = T("r_diary_noted")
    p = state.get("pending")
    if p and docs.get(p["doc"]):
        reply += T("r_still_open", q=_question(docs.get(p["doc"]), _asked(state)))
    return reply


def daily_report(day=None, text=None, msg_id=None, photo_ids=None):
    with llm_bridge.Timer("daily_report_generation"):
        doc = _daily_report(day)
    return _daily_report_llm(doc, text, msg_id, photo_ids)


def _daily_report(day=None):
    day = day or llm_today().isoformat()     # DEMO_TODAY pins the demo day; empty = real date
    doc = next((d for d in docs.all_docs() if d["type"] == "bautagesbericht" and d["date"] == day and d["status"] != "sent"), None) \
        or docs.create("bautagesbericht", origin="daily")
    doc["date"] = day
    S = lambda t, loc, q, eid=None: {"type": t, "evidence_id": eid, "locator": loc, "quote": q}
    docs.set_field(doc, "date", fmt_date(dt.date.fromisoformat(day)), S("timestamp", T("loc_report_day"), day), "ai", 1.0)
    w = (plan.weather() or {}).get(day)
    if w:
        docs.set_field(doc, "weather", T("v_weather", **w),
                       S("weather", f"Open-Meteo {day}", plan.weather_text(w), "weather-api"), "ai", 0.9)
        docs.set_field(doc, "temperature_min_c", f"{w['tmin']:.0f}", S("weather", f"Open-Meteo {day}", plan.weather_text(w), "weather-api"), "ai", 0.9)
        docs.set_field(doc, "temperature_max_c", f"{w['tmax']:.0f}", S("weather", f"Open-Meteo {day}", plan.weather_text(w), "weather-api"), "ai", 0.9)
    photos = [p for p in load("photos", []) if p.get("taken_at", "")[:10] == day]
    counts = {}
    for p in photos:
        for c in {d["class"] for d in p.get("detections", [])}:
            counts[c] = counts.get(c, 0) + 1
    if counts:
        docs.set_field(doc, "equipment", ", ".join(T("v_on_photo", k=k, v=v, s="s" if v > 1 else "") for k, v in sorted(counts.items())),
                       S("photo", T("loc_detection"), T("q_detection"), ",".join("photo:" + p["id"] for p in photos)), "ai", 0.7)
    notes = [n for n in load("notes", []) if n["date"] == day]
    prog = [p for p in load("progress", []) if p["date"] == day]
    sched = {s["id"]: s for s in load("schedule", [])}
    st = plan.status(day)
    work = [n["text"] for n in notes] + [f"{sched.get(p['activity'], {}).get('name', p['activity'])}: {p['qty']:g} {sched.get(p['activity'], {}).get('unit', '')}"
                                          + (f" ({p['note']})" if p["note"] else "") for p in prog]
    moves = [r["text"] if isinstance(r, dict) and r.get("text") else str(r) for r in replanner.accepted_for(day)]
    if moves:
        docs.set_field(doc, "reassignments", "\n".join(moves), S("documents", T("loc_replanner"), T("q_moves", n=len(moves))), "ai", 1.0)
    status_lines = [T("v_status_line", name=a["name"], a=a["actual"], p=a["planned"], unit=a["unit"]) for a in st["activities"] if a["light"] != "grey"]
    if work or status_lines:
        docs.set_field(doc, "work_done", "\n".join(work + status_lines),
                       S("diary", T("loc_diary_sched"), T("q_diary_sched"), ",".join("msg:" + n["id"] for n in notes) or "sched"), "ai", 0.8)
    deliveries = [p for p in photos if p["category"] == "delivery"]
    if deliveries:
        docs.set_field(doc, "deliveries", T("v_deliveries", n=len(deliveries)), S("photo", T("loc_photos_cat"), ", ".join(p["original_name"] for p in deliveries)), "ai", 0.6)
    notices = [d for d in docs.all_docs() if d["type"] != "bautagesbericht" and d.get("date", d["created_at"][:10]) == day]
    inc = [f"{d['title']}: {d['fields'].get('location', {}).get('value') or ''}".strip(": ") for d in notices] + [a["text"] for a in st["alerts"]]
    if inc:
        docs.set_field(doc, "incidents", "\n".join(inc), S("documents", T("loc_notices_day"), T("q_notices_day", n=len(notices), m=len(st["alerts"]))), "ai", 0.8)
    if photos:
        docs.set_field(doc, "photos", "\n".join(f"{p['original_name']} ({p['taken_at'][11:16]}): {p.get('caption_de') or p['category']}" for p in photos),
                       S("photo", T("loc_photo_store"), T("q_photos_today", n=len(photos))), "ai", 0.8)
    doc["photos"] = [p["id"] for p in photos]
    return docs.put(doc)


def _daily_report_llm(doc, text=None, msg_id=None, photo_ids=None):
    """LLM step after the rule-based report (only with a configured model): fills empty fields from the day's sources
    and attached photos; filled or locked fields only get proposals (fill_only). No model -> report unchanged."""
    if not llm_bridge.CFG.llm_ready or doc["status"] == "sent" or doc["date"] != llm_today().isoformat():   # sources cover today only
        return doc
    text = text or docs.DOC_TYPES["bautagesbericht"]["title"]
    primary = [sources.message_chunk(msg_id or new_id(), text)]
    context = context_chunks(photo_ids)
    by_ref = {c.ref: c for c in primary + context}
    for c in primary + context:
        for a in c.aliases:
            by_ref.setdefault(a, c)
    locked = {k: v["value"] for k, v in doc["fields"].items() if v["locked"]}
    res = extract("bautagesbericht", text, primary, context, locked, run_id=f"daily-{doc['id']}")
    if res["mode"] != "llm":
        return doc
    for k, f in res["fields"].items():
        if k in doc["fields"]:
            docs.set_field(doc, k, f["value"], _source_for(by_ref, f), "ai", f["confidence"], fill_only=True)
    doc["photos"] += [i for i in photo_ids or [] if i not in doc["photos"]]
    doc["extraction_mode"] = "llm"
    doc = docs.put(doc)
    llm_bridge.start_review(doc["id"])     # background, no-op unless the reviewer is enabled
    return docs.get(doc["id"])


def propose_from_alert(alert):
    st = plan.status()
    a = next((x for x in st["activities"] if x["id"] == alert.get("activity")), None)
    if not a:
        raise ValueError("unknown activity")
    S = {"type": "schedule", "evidence_id": f"sched:{a['id']}", "locator": T("loc_schedule", name=a["name"]),
         "quote": T("q_schedule", name=a["name"], p=a["planned"], a=a["actual"], unit=a["unit"], asof=st["as_of"])}
    if alert.get("kind") == "frost":
        al = next((x for x in st["alerts"] if x["kind"] == "frost" and x["activity"] == a["id"]), None)
        doc = docs.create("bedenkenanmeldung", origin="alert")
        W = {"type": "weather", "evidence_id": "weather-api", "locator": T("loc_forecast"), "quote": al["text"] if al else ""}
        docs.set_field(doc, "location", a["name"], S, "ai", 0.9)
        if al:
            docs.set_field(doc, "concern_description", T("v_frost", start=a["start"], end=a["end"], tmin=al["tmin"], date=al["weather_date"]), W, "ai", 0.9)
            docs.set_field(doc, "technical_basis", T("v_frost_basis", text=al["text"]), W, "ai", 0.9)
    else:
        doc = docs.create("behinderungsanzeige", origin="alert")
        # cause stays empty on purpose: the schedule shows the delay, not why -> follow-up question
        docs.set_field(doc, "affected_work", T("v_delay", name=a["name"], days=a["delay_days"], p=a["planned"], a=a["actual"], unit=a["unit"]), S, "ai", 0.9)
        notes = [p["note"] for p in load("progress", []) if p["activity"] == a["id"] and p["note"]]
        if notes:
            loc = LOC.search(notes[-1])
            if loc:
                docs.set_field(doc, "location", loc.group(0), {"type": "schedule", "evidence_id": f"sched:{a['id']}", "locator": T("loc_progress_report"), "quote": notes[-1]}, "ai", 0.7)
    _host_fields(doc)
    doc["proposal_from"] = alert.get("kind")
    return docs.put(doc)
