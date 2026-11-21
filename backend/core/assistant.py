"""Chat handling (host side): builds evidence lists, calls the extraction layer, persists proposals, asks follow-ups,
handles edits by chat, daily report and proposals from alerts. All status changes stay with the user."""
import re, datetime as dt
from . import docs, plan, sanitizer, llm_bridge, replanner
from .extract import detect_intents, extract, DAILY_RX, EDIT_RX, LOC
from .store import load, save, new_id, now, today, SITE

# Statements that are site diary notes, not answers to an open question
NOTE_RX = re.compile(r"\b(arrived|delivered|geliefert|angeliefert|done|finished|completed|fertig|erledigt|betoniert|poured|started|begonnen)\b", re.I)
SKIP_RX = re.compile(r"^\s*(skip|weiter|überspringen|unknown|unbekannt|keine ahnung|n/?a|-)\s*$", re.I)
KIND_TO_SRC = llm_bridge.KIND_TO_SRC


def _msg(role, text, **kw):
    return dict({"id": new_id(), "role": role, "text": text, "at": now()}, **kw)


def _norm_loc(v):
    v = (v or "").lower()
    num = re.findall(r"\d+", v)
    word = "pile" if re.search(r"pile|pfahl", v) else re.sub(r"[^a-zäöü]", "", v)[:6]
    return f"{word}{''.join(num)}"


def _find_mergeable(dtype, location):
    if not location:
        return None
    for d in reversed(docs.all_docs()):
        if d["type"] == dtype and d["status"] != "sent" and _norm_loc(d["fields"].get("location", {}).get("value")) == _norm_loc(location):
            return d
    return None


# ---------- evidence ----------
def photo_evidence(day):
    ev = []
    for p in load("photos", []):
        if p.get("taken_at", "")[:10] != day:
            continue
        dets = ", ".join(sorted({d["class"] for d in p.get("detections", [])})) or "keine"
        ev.append({"id": f"photo-{p['id']}", "kind": "photo", "locator": f"Foto {p['original_name']}",
                   "excerpt": f"Foto vom {p['taken_at'][:16].replace('T', ' ')}, Kategorie {p['category']}, erkannt: {dets}. {p.get('caption_de', '')}".strip()})
    return ev


def schedule_evidence():
    st = plan.status()
    return [{"id": f"sched-{a['id']}", "kind": "schedule_row", "locator": f"Bauzeitenplan: {a['name']}",
             "excerpt": f"{a['name']} {a['start']} bis {a['end']}: Soll {a['planned']:g}, Ist {a['actual']:g} {a['unit']}, Verzug {a['delay_days']} Tage (Stand {st['as_of']})"}
            for a in st["activities"] if a["light"] != "grey"]


def document_evidence():
    return [{"id": d["id"], "kind": "document_page", "locator": d["locator"], "excerpt": d["excerpt"]} for d in load("client_docs", [])]


def build_evidence(primary):
    """primary: {"id","kind","locator","excerpt"} for the message / email being processed."""
    return [primary] + document_evidence() + schedule_evidence() + photo_evidence(today())


def _source_for(ev_by_id, f):
    eid = f["evidence_id"]
    if eid == "timestamp":
        return {"type": "timestamp", "evidence_id": None, "locator": "Zeitpunkt der Meldung", "quote": now()[:16].replace("T", " ")}
    e = ev_by_id.get(eid, {})
    return {"type": KIND_TO_SRC.get(e.get("kind"), "message"), "evidence_id": eid, "locator": e.get("locator", ""),
            "quote": f.get("quote") or (e.get("excerpt") or "")[:300]}


def _host_fields(doc):
    """Deterministic host data: project master data and the list of attached evidence."""
    f = doc["fields"]
    if "project" in f and not f["project"]["value"]:
        docs.set_field(doc, "project", SITE["name"], {"type": "project", "evidence_id": None, "locator": "Projektstammdaten", "quote": SITE["name"]}, "ai", 1.0)
    photos = {p["id"]: p for p in load("photos", [])}
    pics = [photos[i] for i in doc["photos"] if i in photos]
    key = "photo_evidence" if "photo_evidence" in f else ("evidence" if "evidence" in f else None)
    if key and pics:
        val = "; ".join(f"{p['original_name']} ({p['category']}, {p['taken_at'][11:16]})" for p in pics)
        docs.set_field(doc, key, f"{len(pics)} Foto(s): {val}", {"type": "photo", "evidence_id": ",".join(f"photo-{p['id']}" for p in pics),
                                                                 "locator": "Fotoablage", "quote": val}, "ai", 1.0)


def apply_text(dtype, text, source_kind="text", source_ref=None, origin="chat", locator=None, evidence_meta: dict | None = None):
    """Extract fields from text into a new or matching draft (one incident = one draft per type)."""
    masked, mapping = sanitizer.mask(text)
    run_id = f"{dtype}-{new_id()}"
    primary = {"id": f"{'mail' if source_kind == 'email' else 'msg'}-{source_ref or new_id()}", "kind": source_kind,
               "locator": locator or {"email": "E-Mail", "audio": "Diktat (Spracherkennung)"}.get(source_kind, f"Chat-Nachricht {now()[11:16]}"),
               "excerpt": masked}
    if evidence_meta:
        primary["meta"] = evidence_meta   # audio segments, mail headers (W1/W2)
    evidence = build_evidence(primary)
    # find an open draft for the same incident first, so its user edits are passed as locked fields
    pre = rules_loc(text)
    doc = _find_mergeable(dtype, pre)
    merged = doc is not None
    locked = {k: v["value"] for k, v in (doc["fields"].items() if doc else []) if v["locked"]}
    fields, gaps, mode, extraction = extract(dtype, masked, evidence, locked, run_id=run_id)
    fields = {k: dict(v, value=sanitizer.unmask(v["value"], mapping), quote=sanitizer.unmask(v.get("quote") or "", mapping)) for k, v in fields.items()}
    if not doc:
        doc = _find_mergeable(dtype, (fields.get("location") or {}).get("value"))
        merged = doc is not None
    if not doc:
        doc = docs.create(dtype, origin=origin)
    ev_by_id = {e["id"]: sanitizer.unmask(e, mapping) for e in evidence}
    filled, proposals = [], []
    for k, f in fields.items():
        if k not in doc["fields"]:
            continue
        r = docs.set_field(doc, k, f["value"], _source_for(ev_by_id, f), "ai", f["confidence"], fill_only=merged)
        (filled if r == "set" else proposals if r == "proposal" else []).append(k)
    cat = docs.DOC_TYPES[dtype]["photo_cat"]
    for p in load("photos", []):
        if p.get("taken_at", "")[:10] == today() and (cat is None or p["category"] == cat) and p["id"] not in doc["photos"]:
            doc["photos"].append(p["id"])
    if mode == "rules" and "expected_ground_page" in doc["fields"] and re.search(r"gutachten|soil report", text, re.I):
        g = next((e for e in evidence if e["id"].startswith("gutachten")), None)
        if g:
            docs.set_field(doc, "expected_ground_page", g["locator"], {"type": "document", "evidence_id": g["id"], "locator": g["locator"], "quote": g["excerpt"]}, "ai", 0.7, fill_only=True)
    _host_fields(doc)
    doc["extraction_mode"] = mode
    if extraction is not None and llm_bridge.SETTINGS.reviewer_enabled:
        doc["review"] = {"status": "running", "findings": []}
        did = doc["id"]

        def done(result):
            d = docs.get(did)
            if d:
                d["review"] = result
                docs.put(d)
        llm_bridge.review_in_background(extraction, evidence, done)
    docs.put(doc)
    return doc, filled, proposals, merged, gaps, mode


def rules_loc(text):
    m = LOC.search(text)
    return m.group(0) if m else None


def _ask_next(doc, state):
    skipped = state.get("skipped", {}).get(doc["id"], [])
    miss = [k for k in docs.missing(doc) if k not in skipped]
    if not miss:
        state.pop("pending", None)
        return "Alle Pflichtangaben sind gefüllt. Bitte prüfen Sie den Entwurf (Quelle je Feld antippen) und markieren Sie ihn dann als geprüft."
    k = miss[0]
    state["pending"] = {"doc": doc["id"], "field": k}
    return f"{docs.field_meta(doc['type'], k)['question']} (oder „skip“)"


def _labels(doc, keys):
    return ", ".join(docs.field_meta(doc["type"], k)["label"] for k in keys if docs.field_meta(doc["type"], k))


def handle(text, voice=False):
    with llm_bridge.Timer("chat_turn_end_to_end"):
        return _handle(text, voice)


def _handle(text, voice):
    msgs, state = load("messages", []), load("chat_state", {})
    user = _msg("user", text, voice=voice)
    _, mapping = sanitizer.mask(text)
    if mapping:
        user["masked"] = sorted(mapping.keys())
    msgs.append(user)
    out = []
    active = docs.get(state.get("active")) if state.get("active") else None
    intents = detect_intents(text)

    if DAILY_RX.search(text) and len(text) < 120:
        doc = daily_report()
        state["active"] = doc["id"]
        out.append(_msg("assistant", f"Bautagesbericht-Entwurf für {doc['fields']['date']['value']} erstellt aus Fotos, Notizen, Soll-Ist und Wetter. "
                                     + _ask_next(doc, state), doc=doc["id"]))
    elif EDIT_RX.match(text) and active:
        m = EDIT_RX.match(text)
        name, value = m.group(1).lower(), m.group(2)
        key = next((f[0] for f in docs.DOC_TYPES[active["type"]]["fields"]
                    if name in f[0].replace("_", " ") or name in f[1].lower() or f[0].replace("_", " ") in name), None)
        if key:
            docs.set_field(active, key, value, {"type": "user", "evidence_id": None, "locator": "Änderung im Chat", "quote": text}, by="user")
            docs.put(active)
            out.append(_msg("assistant", f"{docs.field_meta(active['type'], key)['label']} geändert auf „{value}“. Das Feld ist jetzt gesperrt, die KI überschreibt es nicht.", doc=active["id"]))
        else:
            out.append(_msg("assistant", f"Ich finde kein Feld „{name}“ in der {active['title']}.", doc=active["id"]))
    elif intents:
        primary = intents[0]
        doc, filled, proposals, merged, gaps, mode = apply_text(primary, text, "audio" if voice else "text", user["id"])
        state["active"] = doc["id"]
        parts = [f"{'Zum bestehenden Entwurf hinzugefügt' if merged else 'Entwurf erstellt'}: {doc['title']}."]
        if filled:
            parts.append(f"Aus Ihrer Nachricht übernommen: {_labels(doc, filled)}.")
        if proposals:
            parts.append(f"Bereits belegt, neue Angabe nur als Vorschlag: {_labels(doc, proposals)}.")
        if gaps:
            parts.append(f"Nicht ausreichend belegt und daher leer gelassen: {_labels(doc, gaps)}.")
        if doc["photos"]:
            parts.append(f"{len(doc['photos'])} Foto(s) von heute angehängt.")
        if doc.get("review", {}).get("status") == "running":
            parts.append("Kritische Felder werden im Hintergrund geprüft.")
        parts.append(_ask_next(doc, state))
        extra = intents[1:] + (["mehrkostenanzeige"] if primary == "nachtragsmeldung" and "mehrkostenanzeige" not in intents else [])
        actions = [{"label": f"Auch {docs.DOC_TYPES[i]['title']} entwerfen", "type": i, "text": text} for i in extra]
        actions += replanner.actions_for(doc)
        out.append(_msg("assistant", " ".join(parts), doc=doc["id"], actions=actions, mode=mode))
    elif SKIP_RX.match(text) and not state.get("pending"):
        out.append(_msg("assistant", "Es gibt gerade keine offene Frage."))
    elif state.get("pending") and docs.get(state["pending"]["doc"]) and not NOTE_RX.search(text):
        p = state["pending"]
        doc = docs.get(p["doc"])
        if SKIP_RX.match(text):
            state.setdefault("skipped", {}).setdefault(doc["id"], []).append(p["field"])
            reply = "Übersprungen. " + _ask_next(doc, state)
        else:
            docs.set_field(doc, p["field"], text, {"type": "answer", "evidence_id": f"msg-{user['id']}", "locator": f"Antwort im Chat {now()[11:16]}", "quote": text}, by="user")
            docs.put(doc)
            reply = f"Übernommen als {docs.field_meta(doc['type'], p['field'])['label']}. " + _ask_next(doc, state)
        state["active"] = doc["id"]
        out.append(_msg("assistant", reply, doc=doc["id"]))
    else:
        notes = load("notes", [])
        notes.append({"id": user["id"], "date": today(), "at": now(), "text": text})
        save("notes", notes)
        reply = "Im Bautagebuch notiert, geht in den Bautagesbericht ein. Sagen Sie „Tagesbericht“, wenn Sie den Entwurf möchten."
        p = state.get("pending")
        if p and docs.get(p["doc"]):
            reply += f" Noch offen: {docs.field_meta(docs.get(p['doc'])['type'], p['field'])['question']}"
        out.append(_msg("assistant", reply))
    msgs.extend(out)
    save("messages", msgs)
    save("chat_state", state)
    return {"user": user, "replies": out, "active": state.get("active")}


def daily_report(day=None):
    with llm_bridge.Timer("daily_report_generation"):
        return _daily_report(day)


def _daily_report(day=None):
    day = day or today()
    doc = next((d for d in docs.all_docs() if d["type"] == "bautagesbericht" and d["date"] == day and d["status"] != "sent"), None) \
        or docs.create("bautagesbericht", origin="daily")
    doc["date"] = day
    S = lambda t, loc, q, eid=None: {"type": t, "evidence_id": eid, "locator": loc, "quote": q}
    docs.set_field(doc, "date", dt.date.fromisoformat(day).strftime("%d.%m.%Y"), S("timestamp", "Berichtstag", day), "ai", 1.0)
    w = (plan.weather() or {}).get(day)
    if w:
        docs.set_field(doc, "weather", f"{w['text']}, Niederschlag {w['rain']:.1f} mm, Wind bis {w['wind']:.0f} km/h",
                       S("weather", f"Open-Meteo {day}", plan.weather_text(w), "weather-api"), "ai", 0.9)
        docs.set_field(doc, "temperature", f"{w['tmin']:.0f} bis {w['tmax']:.0f} °C", S("weather", f"Open-Meteo {day}", plan.weather_text(w), "weather-api"), "ai", 0.9)
    photos = [p for p in load("photos", []) if p.get("taken_at", "")[:10] == day]
    counts = {}
    for p in photos:
        for c in {d["class"] for d in p.get("detections", [])}:
            counts[c] = counts.get(c, 0) + 1
    if counts:
        docs.set_field(doc, "equipment", ", ".join(f"{k} (auf {v} Foto{'s' if v > 1 else ''})" for k, v in sorted(counts.items())),
                       S("photo", "Objekterkennung (Roboflow)", "Erkennung auf Fotos von heute", ",".join("photo-" + p["id"] for p in photos)), "ai", 0.7)
    notes = [n for n in load("notes", []) if n["date"] == day]
    prog = [p for p in load("progress", []) if p["date"] == day]
    sched = {s["id"]: s for s in load("schedule", [])}
    st = plan.status(day)
    work = [n["text"] for n in notes] + [f"{sched.get(p['activity'], {}).get('name', p['activity'])}: {p['qty']:g} {sched.get(p['activity'], {}).get('unit', '')}"
                                          + (f" ({p['note']})" if p["note"] else "") for p in prog]
    work += [f"Umplanung (bestätigt): {r['text']}" if isinstance(r, dict) and r.get("text") else str(r) for r in replanner.accepted_for(day)]
    status_lines = [f"Leistungsstand {a['name']}: Ist {a['actual']:g} / Soll {a['planned']:g} {a['unit']}" for a in st["activities"] if a["light"] != "grey"]
    if work or status_lines:
        docs.set_field(doc, "work_performed", "\n".join(work + status_lines),
                       S("diary", "Bautagebuch und Bauzeitenplan", "Einträge und Leistungsmeldungen von heute", ",".join("msg-" + n["id"] for n in notes) or "sched"), "ai", 0.8)
    deliveries = [p for p in photos if p["category"] == "delivery"]
    if deliveries:
        docs.set_field(doc, "deliveries", f"{len(deliveries)} Lieferung(en) fotografisch dokumentiert", S("photo", "Fotos Kategorie delivery", ", ".join(p["original_name"] for p in deliveries)), "ai", 0.6)
    notices = [d for d in docs.all_docs() if d["type"] != "bautagesbericht" and d["created_at"][:10] == day]
    inc = [f"{d['title']}: {d['fields'].get('location', {}).get('value') or ''}".strip(": ") for d in notices] + [a["text"] for a in st["alerts"]]
    if inc:
        docs.set_field(doc, "obstructions_incidents", "\n".join(inc), S("documents", "Anzeigen von heute und Soll-Ist-Vergleich", f"{len(notices)} Anzeige(n), {len(st['alerts'])} Warnung(en)"), "ai", 0.8)
    if photos:
        docs.set_field(doc, "photo_captions", "\n".join(f"{p['original_name']} ({p['taken_at'][11:16]}): {p.get('caption_de') or p['category']}" for p in photos),
                       S("photo", "Fotoablage", f"{len(photos)} Fotos von heute"), "ai", 0.8)
    doc["photos"] = [p["id"] for p in photos]
    return docs.put(doc)


def propose_from_alert(alert):
    st = plan.status()
    a = next((x for x in st["activities"] if x["id"] == alert.get("activity")), None)
    if not a:
        raise ValueError("unknown activity")
    S = {"type": "schedule", "evidence_id": f"sched-{a['id']}", "locator": f"Bauzeitenplan: {a['name']}",
         "quote": f"{a['name']}: Soll {a['planned']:g}, Ist {a['actual']:g} {a['unit']} (Stand {st['as_of']})"}
    if alert.get("kind") == "frost":
        al = next((x for x in st["alerts"] if x["kind"] == "frost" and x["activity"] == a["id"]), None)
        doc = docs.create("bedenkenanmeldung", origin="alert")
        W = {"type": "weather", "evidence_id": "weather-api", "locator": "Open-Meteo Prognose", "quote": al["text"] if al else ""}
        docs.set_field(doc, "location", a["name"], S, "ai", 0.9)
        if al:
            docs.set_field(doc, "concern_description", f"Betonage {a['start']} bis {a['end']} bei prognostizierter Tiefsttemperatur von {al['tmin']:.0f} °C am {al['weather_date']}.", W, "ai", 0.9)
            docs.set_field(doc, "technical_basis", f"Wetterprognose Open-Meteo: {al['text']}", W, "ai", 0.9)
    else:
        doc = docs.create("behinderungsanzeige", origin="alert")
        docs.set_field(doc, "affected_activity", a["name"], S, "ai", 0.9)
        docs.set_field(doc, "impact_on_work", f"{a['delay_days']} Arbeitstage Rückstand zum Bauzeitenplan (Soll {a['planned']:g} {a['unit']}, Ist {a['actual']:g} {a['unit']}).", S, "ai", 0.9)
        notes = [p["note"] for p in load("progress", []) if p["activity"] == a["id"] and p["note"]]
        if notes:
            loc = LOC.search(notes[-1])
            if loc:
                docs.set_field(doc, "location", loc.group(0), {"type": "schedule", "evidence_id": f"sched-{a['id']}", "locator": "Leistungsmeldung", "quote": notes[-1]}, "ai", 0.7)
    _host_fields(doc)
    doc["proposal_from"] = alert.get("kind")
    return docs.put(doc)
