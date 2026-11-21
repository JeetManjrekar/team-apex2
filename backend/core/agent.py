"""AI Site Manager orchestrator: one command -> the tools it needs -> evidence -> UI actions -> spoken answer.

Pipeline per command (each step is timed and returned, so the UI shows what actually ran):
  intent -> data retrieval (plan, twin, photos, docs) -> analysis (rules on real detections) -> evidence -> UI actions -> speech

Honesty rules (same spirit as the document pipeline):
- Every finding cites evidence ids (photo:<id>, sched:<activity>, doc-<id>). No evidence, no finding.
- Safety findings come from deterministic rules over stored detector output. The detector has no PPE class, so helmet
  questions are answered with "cannot be verified" instead of a guess.
- Recommendations are labelled as such and kept apart from verified observations.
- Commands that are about drafting notices (rock at pile 7, excavator idle, ...) are handed back to the existing chat
  pipeline (`handoff: "chat"`), which keeps its evidence and confidence gates.
"""
from __future__ import annotations

import datetime as dt
import html
import re
import time

from . import layout_suggest, plan, site_twin
from .llm_settings import today as demo_today
from .store import DATA, SITE, load, new_id, now, save

MIN_CONF = 0.5                       # detections below this are not used for findings
MACHINES = {"excavator", "dump_truck", "bulldozer", "tractor", "truck", "crane", "loader", "car"}
HEAVY = MACHINES - {"car"}
INCIDENT_WORDS = re.compile(r"unfall|umgekippt|eingebrochen|gestürzt|abgestürzt|verletz|accident|overturn|tipped|fell|collapse|injur|"
                                r"in (?:die|der) grube|into the (?:pit|excavation)", re.I)
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}

# zone vocabulary -> candidate layout zone ids, most specific first. Works for the seed layout (erd/a10/wls/be/wln) and for
# generated layouts (w1/a1/a2/w2/be). The first candidate id that exists in the current layout wins.
# "exact" rules name one specific place (north section, abutment 2, pier 1): if that zone doesn't exist the answer is
# "which area?" rather than a different zone.
ZONE_WORDS = [
    (re.compile(r"\bnord|\bnorth|2\. bauabschnitt|second (?:section|phase)", re.I), ["wln"], True),
    (re.compile(r"widerlager 2|abutment 2|\bw2\b", re.I), ["w2"], True),
    (re.compile(r"achse 1|axis 1|pier 1|pfeiler 1|\ba1\b", re.I), ["a1", "wls"], True),
    (re.compile(r"achse 2|axis 2|pier 2|pfeiler 2|\ba2\b", re.I), ["a2"], True),
    (re.compile(r"\bpiles?\b|pfahl|pfähl|bohrpf|widerlager 1|abutment 1|\bw1\b|\babutment\b", re.I), ["a10", "w1"], False),
    (re.compile(r"achse|axis|\bpier|foundation|fundament", re.I), ["wls", "a1"], False),
    (re.compile(r"excavat|aushub|erdbau|earthwork|\bpit\b|grube", re.I), ["erd"], False),
    (re.compile(r"facilit|einrichtung|container|office|büro", re.I), ["be"], False),
]

INTENTS = [
    ("helmet", re.compile(r"\bhelm\w*|\bhard ?hats?\b|\bppe\b|protective (?:equipment|gear)|safety gear|\bpsa\b|schutzausrüstung|\bwarnweste\w*|\bvests?\b", re.I)),
    ("report", re.compile(r"report|bericht|pdf|protokoll erstellen|export", re.I)),
    ("explain", re.compile(r"explain|erklär|what happened|was ist passiert|details? (?:of|zu|zum)", re.I)),
    ("safety", re.compile(r"safety|sicherheit|violation|verstoß|verstoss|hazard|gefahr|risk|risiko|restricted|sperr|unsafe", re.I)),
    ("incidents", re.compile(r"incident|vorfall|vorfälle|unfall|accident|injur|verletz|alarm|detected|erkannt|detection", re.I)),
    ("changes", re.compile(r"chang|since yesterday|seit gestern|what'?s new|was ist neu|änderung|neu seit|new since", re.I)),
    ("progress", re.compile(r"progress|fortschritt|\bstand\b|plan(?:ned)? vs|soll.?ist|planned|behind|verzug|schedule|bauzeitenplan|on track|status", re.I)),
    # verb + layout noun (either order), so "show me the site plan" stays a focus request
    ("layout", re.compile(r"(?:generat|creat|build|make|suggest|propos|draft|erstell|generier|erzeug|vorschlag|baue?\b|bilde)\w*\b.{0,40}?"
                          r"(?:layout|lageplan|site ?plan|baustellenplan|grundriss)|(?:layout|lageplan|site ?plan|baustellenplan|grundriss)\w*\b.{0,40}?"
                          r"(?:generat|creat|erstell|generier|erzeug|vorschlag|aus (?:den|meinen) (?:dokumenten|daten|fotos))"
                          r"|\bschlag\w*\b.{0,40}?(?:layout|lageplan|baustellenplan)\w*\s+vor\b", re.I)),     # "schlag mir einen Lageplan vor"
    ("focus", re.compile(r"show|zeig|navigate|go to|fly|3d|twin|plan|zone|area|bereich|inspect|prüf", re.I)),
]
# drafting / diary commands stay with the document assistant
DRAFT_RX = re.compile(r"pfahl \d+.*fels|fels|rock at|bagger steht|excavator idle|riss|crack|mangel|defect|tagebuch|diary|aktennotiz|"
                      r"file note|telefonat|lieferung|geliefert|delivered|ändere|change .* to|nachtrag|behinderung|mehrkosten|bedenken", re.I)
EN_RX = re.compile(r"\b(the|what|show|give|me|today|any|are|is|check|generate|report|progress|safety|incident|since|yesterday|how)\b", re.I)


def _lang(text, hint=None):
    if hint in ("de", "en"):
        return hint
    return "en" if len(EN_RX.findall(text or "")) >= 1 else "de"


def _t(lang, en, de):
    return en if lang == "en" else de


class _Steps:
    def __init__(self):
        self.rows, self._t = [], None

    def run(self, key, label, fn):
        t0 = time.perf_counter()
        try:
            out, ok, err = fn(), True, None
        except Exception as e:      # a failing tool is reported, not hidden
            out, ok, err = None, False, str(e)
        self.rows.append({"key": key, "label": label, "ms": round((time.perf_counter() - t0) * 1000, 1), "ok": ok,
                          **({"error": err} if err else {})})
        return out


# ---------------------------------------------------------------- incident detection (rules over stored detector output)
def _boxes_close(a, b):
    """Image-space proximity of two detection boxes (x/y are box centres). True if they overlap or nearly touch."""
    dx, dy = abs(a["x"] - b["x"]), abs(a["y"] - b["y"])
    return dx < (a["width"] + b["width"]) / 2 * 1.15 and dy < (a["height"] + b["height"]) / 2 * 1.15


def _zone_info(layout):
    return {z["id"]: z for z in layout["zones"]}


def _mk(rule, photo, severity, title_en, title_de, detail_en, detail_de, rec_en, rec_de, dets, zone):
    return {"key": f"{rule}:{photo['id']}", "rule": rule, "severity": severity,
            "title_en": title_en, "title_de": title_de, "detail_en": detail_en, "detail_de": detail_de,
            "recommendation_en": rec_en, "recommendation_de": rec_de,
            "photo": photo["id"], "file": photo["file"], "ann_file": photo.get("ann_file"),
            "zone": zone, "taken_at": photo.get("taken_at"),
            "objects": [{"class": d["class"], "confidence": round(d["confidence"], 3), "index": d.get("index")} for d in dets],
            "confidence": round(min((d["confidence"] for d in dets), default=1.0), 3),
            "evidence": [f"photo:{photo['id']}"] + ([f"zone:{zone}"] if zone else []),
            "detector": (photo.get("detector") or {}).get("name"), "source": "rule"}


def detect_incidents(tw=None) -> list[dict]:
    """Deterministic checks. Each result names the rule, the photo, the objects and their model confidence."""
    tw = tw or site_twin.twin()
    zones = _zone_info(tw["layout"])
    out = []
    for p in tw["photos"]:
        dets = [d for d in p["detections"] if d["confidence"] >= MIN_CONF]
        zone = p.get("zone")
        persons = [d for d in dets if d["class"] == "person"]
        heavy = [d for d in dets if d["class"] in HEAVY]
        text = " ".join([p.get("caption") or "", load_note(p["id"])])
        if INCIDENT_WORDS.search(text):
            out.append(_mk("reported_incident", p, "high", "Incident described on a site photo", "Vorfall auf Baustellenfoto beschrieben",
                           f"Photo note / caption: “{text.strip()[:160]}”.", f"Fotonotiz / Bildbeschreibung: „{text.strip()[:160]}“.",
                           "Secure the area, check for injured persons, inform the site manager and document the scene.",
                           "Bereich sichern, auf Verletzte prüfen, Bauleitung informieren, Lage dokumentieren.", heavy or dets, zone))
        for pr in persons:
            near = [m for m in heavy if _boxes_close(pr, m)]
            if near:
                m = near[0]
                out.append(_mk("person_near_machine", p, "high", f"Person close to an operating {m['class'].replace('_', ' ')}",
                               f"Person im Gefahrenbereich: {m['class'].replace('_', ' ')}",
                               "In the image the person's box overlaps the machine's working area.",
                               "Im Bild überlappt die Person mit dem Arbeitsbereich der Maschine.",
                               "Stop the machine, keep the swing radius clear, brief the operator and banksman.",
                               "Maschine stoppen, Schwenkbereich freihalten, Fahrer und Einweiser unterweisen.", [pr, m], zone))
                break
        z = zones.get(zone)
        if z and z.get("kind") in ("future", "facilities") and heavy:
            out.append(_mk("machine_in_restricted_zone", p, "medium",
                           f"Heavy equipment in a non-work zone ({z['name']})", f"Großgerät in Nicht-Arbeitsbereich ({z['name']})",
                           f"Zone type “{z['kind']}” has no scheduled machine work.", f"Zonentyp „{z['kind']}“ hat keine geplante Maschinenarbeit.",
                           "Check whether the work is approved; otherwise move the equipment back to the work zone.",
                           "Prüfen, ob die Arbeit freigegeben ist; sonst Gerät in den Arbeitsbereich zurück.", heavy[:2], zone))
        if p.get("category") == "safety" and not any(o["photo"] == p["id"] for o in out):
            out.append(_mk("flagged_safety_photo", p, "low", "Photo classified as safety-relevant", "Foto als sicherheitsrelevant eingestuft",
                           p.get("caption") or "Category set to “safety” by the photo pipeline.", p.get("caption") or "Kategorie „Sicherheit“ aus der Fotopipeline.",
                           "Review the photo and confirm or dismiss the finding.", "Foto prüfen und Befund bestätigen oder verwerfen.", dets, zone))
    return out


def load_note(pid):
    return next((p.get("note") or "" for p in load("photos", []) if p["id"] == pid), "")


def scan() -> list[dict]:
    """Merge rule results into incidents.json (stable keys, first-seen timestamp kept). Returns the new incidents."""
    known = {i["key"]: i for i in load("incidents", [])}
    new = []
    for f in detect_incidents():
        if f["key"] in known:
            known[f["key"]].update({k: v for k, v in f.items() if k not in ("id", "created_at", "status")})
        else:
            f.update(id=new_id(), created_at=now(), status="open")
            known[f["key"]] = f
            new.append(f)
    save("incidents", sorted(known.values(), key=lambda i: (SEV_ORDER[i["severity"]], i["created_at"])))
    return new


def report_verbal(text, zone, lang):
    """An incident the user describes (voice or text). Evidence is the message itself; nothing is inferred beyond it."""
    rows = load("incidents", [])
    mid = new_id()
    inc = {"key": f"verbal_report:{mid}", "rule": "verbal_report", "severity": "high", "id": mid, "created_at": now(), "status": "open",
           "title_en": "Incident reported by the site team", "title_de": "Vorfall vom Bauteam gemeldet",
           "detail_en": f"Reported: “{text.strip()[:200]}”", "detail_de": f"Gemeldet: „{text.strip()[:200]}“",
           "recommendation_en": "Secure the area, check for injured persons, call emergency services if needed, inform the site manager, "
                                "and add photos of the scene as evidence.",
           "recommendation_de": "Bereich sichern, auf Verletzte prüfen, ggf. Notruf, Bauleitung informieren und Fotos der Lage als Beleg hinzufügen.",
           "photo": None, "file": None, "ann_file": None, "zone": zone, "taken_at": now(), "objects": [], "confidence": None,
           "evidence": [f"msg:{mid}"] + ([f"zone:{zone}"] if zone else []), "detector": None, "source": "user", "text": text.strip()}
    rows.insert(0, inc)
    save("incidents", rows)
    return inc


def incidents(open_only=True):
    rows = load("incidents", [])
    return [i for i in rows if i["status"] == "open"] if open_only else rows


def events(since: str | None):
    scan()
    rows = incidents()
    return [i for i in rows if not since or i["created_at"] > since]


def set_status(iid, status):
    rows = load("incidents", [])
    for i in rows:
        if i["id"] == iid:
            i["status"] = status
            i["status_at"] = now()
    save("incidents", rows)
    return next((i for i in rows if i["id"] == iid), None)


# ---------------------------------------------------------------- tools
def _zone_from_text(text, layout):
    """Zone named in the text: full zone name, then an id with a digit as a word (W1, A2), then vocabulary aliases."""
    t = (text or "").lower()
    ids = {z["id"] for z in layout["zones"]}
    for z in sorted(layout["zones"], key=lambda z: -len(z["name"])):          # longest name first ("Achse 1 – Fundament")
        if z["name"] and z["name"].lower() in t:
            return z["id"]
    for z in layout["zones"]:
        if re.search(r"\d", z["id"]) and re.search(rf"\b{re.escape(z['id'].lower())}\b", t):
            return z["id"]
    for rx, cands, exact in ZONE_WORDS:
        if rx.search(text or ""):
            hit = next((c for c in cands if c in ids), None)
            if hit or exact:
                return hit
    return None


def _progress(st, tw, lang):
    acts = [a for a in st["activities"] if a["light"] != "grey"]
    zone_of_act = {a: z["id"] for z in tw["layout"]["zones"] for a in z["activities"]}
    behind = [a for a in acts if a["delay_days"] >= 0.5]
    rows = [{"id": a["id"], "name": a["name"], "actual": a["actual"], "planned": a["planned"], "total": a["total"], "unit": a["unit"],
             "pct_actual": round(100 * a["actual"] / a["total"]) if a["total"] else 0,
             "pct_planned": round(100 * a["planned"] / a["total"]) if a["total"] else 0,
             "delay_days": a["delay_days"], "light": a["light"], "zone": zone_of_act.get(a["id"]), "evidence": f"sched:{a['id']}"}
            for a in st["activities"]]
    if not st["activities"]:
        say = _t(lang, "No schedule is loaded, so I can't compare plan and actual. Load the demo data first.",
                 "Es ist kein Bauzeitenplan geladen, daher kann ich Soll und Ist nicht vergleichen. Bitte zuerst die Demodaten laden.")
    elif behind:
        worst = max(behind, key=lambda a: a["delay_days"])
        say = _t(lang, f"{len(acts)} {'activity is' if len(acts) == 1 else 'activities are'} running; {len(behind)} {'is' if len(behind) == 1 else 'are'} behind plan. "
                       f"Most critical: {worst['name']}, {worst['delay_days']} days behind ({worst['actual']:g} of {worst['planned']:g} {worst['unit']} planned).",
                 f"{len(acts)} {'Vorgang läuft' if len(acts) == 1 else 'Vorgänge laufen'}, {len(behind)} hinter Plan. Kritischster: {worst['name']}, {worst['delay_days']} Tage Verzug "
                 f"({worst['actual']:g} von {worst['planned']:g} {worst['unit']} Soll).")
    else:
        say = _t(lang, f"All {len(acts)} running activities are on plan.", f"Alle {len(acts)} laufenden Vorgänge liegen im Plan.")
    alerts = [{"level": a["level"], "text": a["text"], "activity": a.get("activity"), "zone": zone_of_act.get(a.get("activity")),
               "evidence": f"sched:{a['activity']}" if a.get("activity") else None} for a in st["alerts"]]
    hl = [{"id": r["zone"], "level": "red" if r["light"] == "red" else "amber"} for r in rows if r["zone"] and r["light"] in ("red", "yellow")]
    return {"kind": "progress", "as_of": st["as_of"], "rows": rows, "alerts": alerts,
            "weather": st.get("weather_today"), "behind": len(behind)}, say, hl


def _safety(tw, lang, kinds=None):
    found = [i for i in incidents() if not kinds or i["rule"] in kinds]
    n_photos = len(tw["photos"])
    n_det = sum(len(p["detections"]) for p in tw["photos"])
    if not n_photos:
        say = _t(lang, "There are no site photos yet, so there is nothing to check. Upload photos or start the live camera.",
                 "Es gibt noch keine Baustellenfotos zum Prüfen. Bitte Fotos hochladen oder die Live-Kamera starten.")
    elif found:
        hi = sum(1 for i in found if i["severity"] == "high")
        top = found[0]
        say = _t(lang, f"I checked {n_photos} photos with {n_det} detections and found {len(found)} issue{'s' if len(found) != 1 else ''}"
                       f"{f', {hi} high severity' if hi else ''}. Top finding: {top['title_en']}.",
                 f"Ich habe {n_photos} Fotos mit {n_det} Erkennungen geprüft und {len(found)} Befund{'e' if len(found) != 1 else ''} gefunden"
                 f"{f', davon {hi} mit hoher Priorität' if hi else ''}. Wichtigster Befund: {top['title_de']}.")
    else:
        say = _t(lang, f"I checked {n_photos} photos with {n_det} detections. No rule-based safety issue was found.",
                 f"Ich habe {n_photos} Fotos mit {n_det} Erkennungen geprüft. Kein regelbasierter Sicherheitsbefund.")
    hl = [{"id": i["zone"], "level": "red" if i["severity"] == "high" else "amber"} for i in found if i["zone"]]
    return {"kind": "incidents", "items": found, "checked_photos": n_photos, "checked_detections": n_det,
            "rules": ["person_near_machine", "machine_in_restricted_zone", "reported_incident", "flagged_safety_photo"]}, say, hl


def _photos_card(tw, ids=None, zone=None, limit=6):
    ps = tw["photos"]
    if ids:
        ps = [p for p in ps if p["id"] in ids]
    elif zone:
        ps = [p for p in ps if p["zone"] == zone]
    ps = sorted(ps, key=lambda p: p.get("taken_at") or "", reverse=True)[:limit]
    return {"kind": "photos", "items": [{"id": p["id"], "file": p["file"], "ann_file": p.get("ann_file"), "taken_at": p.get("taken_at"),
                                         "zone": p["zone"], "category": p.get("category"), "detector": p["detector"].get("name"),
                                         "detections": [{"class": d["class"], "confidence": round(d["confidence"], 3)} for d in p["detections"]]}
                                        for p in ps]}


def _changes(tw, st, lang):
    day = demo_today()
    real = dt.date.today()
    since = {(day - dt.timedelta(days=1)).isoformat(), (real - dt.timedelta(days=1)).isoformat()}
    cut = min(since)
    new_photos = [p for p in tw["photos"] if (p.get("taken_at") or "")[:10] > cut]
    prog = [e for e in load("progress", []) if e["date"] > cut]
    docs = [d for d in load("docs", []) if (d.get("created_at") or d.get("date") or "")[:10] > cut]
    inc = [i for i in incidents(False) if i["created_at"][:10] > cut]
    names = {a["id"]: a["name"] for a in st["activities"]}
    items = ([{"kind": "progress", "text": f"{names.get(e['activity'], e['activity'])}: +{e['qty']:g}" + (f" – {e['note']}" if e.get("note") else ""),
               "date": e["date"], "evidence": f"sched:{e['activity']}"} for e in prog]
             + [{"kind": "photo", "text": f"{p.get('original_name') or p['id']}: " + (", ".join(sorted({d['class'] for d in p['detections']})) or "no detections"),
                 "date": p.get("taken_at"), "evidence": p["evidence_id"]} for p in new_photos]
             + [{"kind": "document", "text": f"{d.get('title')} ({d.get('status')})", "date": d.get("created_at") or d.get("date"), "evidence": f"doc-{d['id']}"} for d in docs]
             + [{"kind": "incident", "text": i[f"title_{lang}"], "date": i["created_at"], "evidence": f"photo:{i['photo']}"} for i in inc])
    items.sort(key=lambda x: x["date"] or "", reverse=True)
    say = _t(lang, f"Since yesterday: {len(prog)} progress entries, {len(new_photos)} new photos, {len(docs)} documents and {len(inc)} incidents.",
             f"Seit gestern: {len(prog)} Leistungsmeldungen, {len(new_photos)} neue Fotos, {len(docs)} Dokumente und {len(inc)} Vorfälle.")
    return {"kind": "changes", "since": cut, "items": items[:20]}, say


def _zone_card(tw, zid, lang):
    z = next(z for z in tw["layout"]["zones"] if z["id"] == zid)
    zs = next((x for x in tw["zones"] if x["id"] == zid), {"photos": [], "activities": [], "machinery": []})
    acts = "; ".join(f"{a['name']} {a['actual']:g}/{a['total']:g} {a['unit']}" + (f", {a['delay_days']} d behind" if a["delay_days"] >= 0.5 else "")
                     for a in zs["activities"]) or _t(lang, "no scheduled activity", "kein geplanter Vorgang")
    mach = ", ".join(f"{m['count']}× {m['class'].replace('_', ' ')}" for m in zs["machinery"])
    say = _t(lang, f"{z['name']}: {acts}. {len(zs['photos'])} photos" + (f", detected {mach}." if mach else "."),
             f"{z['name']}: {acts}. {len(zs['photos'])} Fotos" + (f", erkannt: {mach}." if mach else "."))
    return {"kind": "zone", "id": zid, "name": z["name"], "zone_kind": z.get("kind"), "activities": zs["activities"],
            "machinery": zs["machinery"], "photos": zs["photos"]}, say


# ---------------------------------------------------------------- orchestrator
DAILY_DOC_RX = re.compile(r"tagesbericht|daily (?:site )?(?:report|diary)|bautagebuch", re.I)
# explicit notice names: always the document pipeline, even when the text also contains safety/progress words ("Standsicherheit")
NOTICE_RX = re.compile(r"bedenken|bedenkenanmeldung|behinderungsanzeige|mehrkostenanzeige|nachtragsmeldung|mängelanzeige|aktennotiz", re.I)
# a question or a negation is not an incident report ("Did anyone get injured?", "Kein Unfall heute")
_QUESTION_RX = re.compile(r"\?\s*$|^\s*(?:did|does|do|has|have|was|were|is|are|hat|haben|wurde|ist|sind)\b", re.I)
_NEGATION_RX = re.compile(r"\b(?:kein(?:e|en|er|em)?|nicht|nichts|niemand|no|not|nobody|nothing|without|ohne)\b|nur eine übung|just a drill", re.I)


def is_incident_report(text):
    """True only for a statement that something happened. Questions, negations and show/explain/report requests are not reports."""
    t = text or ""
    return bool(INCIDENT_WORDS.search(t) and not _QUESTION_RX.search(t) and not _NEGATION_RX.search(t)
                and not re.search(r"\b(show|zeig|explain|erklär|report|bericht|any|gibt es)\b", t, re.I))


def route(text):
    if DAILY_DOC_RX.search(text or "") or NOTICE_RX.search(text or ""):
        return ["chat"]
    if DRAFT_RX.search(text or "") and not re.search(r"report|bericht|show|zeig|safety|sicherheit|progress|fortschritt", text or "", re.I):
        return ["chat"]
    found = [name for name, rx in INTENTS if rx.search(text or "")]
    if "layout" in found:
        return ["layout"]
    if "helmet" in found:
        found = ["helmet", "safety"] + [f for f in found if f not in ("helmet", "safety")]
    return found or ["chat"]


def run(text: str, ctx: dict | None = None, lang_hint: str | None = None) -> dict:
    ctx = dict(ctx or {})
    lang = _lang(text, lang_hint)
    steps = _Steps()
    intents = steps.run("intent", _t(lang, "Understand the request", "Anfrage verstehen"), lambda: route(text))
    if is_incident_report(text):
        intents = ["reported"]
    if intents == ["chat"]:
        return {"handoff": "chat", "intents": intents, "lang": lang, "steps": steps.rows, "ctx": ctx}

    if intents == ["layout"]:
        return _layout(text, ctx, lang, steps)

    st = steps.run("plan", _t(lang, "Read schedule and progress", "Bauzeitenplan und Leistung lesen"), lambda: plan.status())
    tw = steps.run("twin", _t(lang, "Load site twin, photos and detections", "Digitalen Zwilling, Fotos und Erkennungen laden"), site_twin.twin)
    if st is None or tw is None:
        return {"intents": intents, "lang": lang, "steps": steps.rows, "ctx": ctx, "cards": [],
                "speech": _t(lang, "I couldn't read the site data. Please check that the server is running.", "Ich konnte die Baustellendaten nicht lesen."),
                "actions": []}
    new = steps.run("scan", _t(lang, "Run safety rules on the detections", "Sicherheitsregeln auf Erkennungen anwenden"), scan) or []

    cards, speech, actions, highlights = [], [], [], []
    zone = _zone_from_text(text, tw["layout"])
    refers_back = re.search(r"\b(it|that|this one|es|das|dafür|dazu|ihn|sie)\b", text, re.I)

    if "reported" in intents:
        inc = steps.run("record", _t(lang, "Create incident record", "Vorfall anlegen"), lambda: report_verbal(text, zone, lang))
        ctx["incident"] = inc["id"]
        zname = next((z["name"] for z in tw["layout"]["zones"] if z["id"] == zone), None)
        speech.append(_t(lang, f"Incident recorded as high severity{f' in {zname}' if zname else ''}. {inc['recommendation_en']} "
                               "Should I generate the incident report?",
                         f"Vorfall mit hoher Priorität erfasst{f' im Bereich {zname}' if zname else ''}. {inc['recommendation_de']} "
                         "Soll ich den Vorfallbericht erstellen?"))
        cards.append({"kind": "incidents", "items": [inc]})
        if zone:
            highlights.append({"id": zone, "level": "red"})
            cards.append(_photos_card(tw, zone=zone))
        actions.append({"type": "incident.open", "id": inc["id"]})
        actions.append({"type": "camera.offer"})

    if "helmet" in intents:
        speech.append(_t(lang, f"I can't verify helmets: the detector ({tw['models']['detector']}) has no helmet or safety-vest class. "
                               "I'll show the photos with people so you can check them yourself.",
                         f"Helme kann ich nicht prüfen: Der Detektor ({tw['models']['detector']}) kennt keine Helm- oder Westenklasse. "
                         "Ich zeige die Fotos mit Personen zur manuellen Prüfung."))
        people = [p["id"] for p in tw["photos"] if any(d["class"] == "person" for d in p["detections"])]
        cards.append({"kind": "notice", "level": "info", "text": speech[-1]})
        if people:
            cards.append(_photos_card(tw, ids=people))

    if "progress" in intents:
        card, say, hl = steps.run("progress", _t(lang, "Compare planned and actual progress", "Soll-Ist-Vergleich"), lambda: _progress(st, tw, lang))
        cards.append(card); speech.append(say); highlights += hl

    if "safety" in intents or "incidents" in intents:
        kinds = {"machine_in_restricted_zone"} if re.search(r"restricted|sperr|non-work", text, re.I) else None
        card, say, hl = steps.run("safety", _t(lang, "Collect incidents and evidence", "Vorfälle und Belege sammeln"), lambda: _safety(tw, lang, kinds))
        cards.append(card); speech.append(say); highlights += hl
        if card["items"]:
            top = card["items"][0]
            ctx["incident"] = top["id"]
            cards.append(_photos_card(tw, ids=list(dict.fromkeys(i["photo"] for i in card["items"]))))
            if top["zone"]:
                zone = zone or top["zone"]
            actions.append({"type": "incident.open", "id": top["id"]}) if top["severity"] == "high" else None

    if "changes" in intents:
        card, say = steps.run("changes", _t(lang, "Compare with yesterday", "Mit gestern vergleichen"), lambda: _changes(tw, st, lang))
        cards.append(card); speech.append(say)

    if "explain" in intents:
        iid = ctx.get("incident") if (refers_back or not zone) else None
        inc = next((i for i in incidents(False) if i["id"] == iid), None) or next(iter(incidents()), None)
        if inc:
            ctx["incident"] = inc["id"]
            zname = next((z["name"] for z in tw["layout"]["zones"] if z["id"] == inc["zone"]), None)
            objs = ", ".join(f"{o['class'].replace('_', ' ')} {round(o['confidence'] * 100)}%" for o in inc["objects"])
            speech.append(_t(lang, f"{inc['title_en']}. {inc['detail_en']} Objects: {objs}. Location: {zname or 'photo not placed on the plan yet'}. "
                                   f"Recommendation: {inc['recommendation_en']}",
                             f"{inc['title_de']}. {inc['detail_de']} Objekte: {objs}. Ort: {zname or 'Foto noch nicht im Plan verortet'}. "
                             f"Empfehlung: {inc['recommendation_de']}"))
            cards.append({"kind": "incidents", "items": [inc]})
            cards.append(_photos_card(tw, ids=[inc["photo"]]))
            actions.append({"type": "incident.open", "id": inc["id"]})
            zone = zone or inc["zone"]
            if inc["zone"]:
                highlights.append({"id": inc["zone"], "level": "red" if inc["severity"] == "high" else "amber"})
        else:
            speech.append(_t(lang, "There is no open incident to explain.", "Es gibt keinen offenen Vorfall."))

    if zone and ("focus" in intents or not cards) and "reported" not in intents:
        card, say = _zone_card(tw, zone, lang)
        cards.append(card); speech.append(say)
        cards.append(_photos_card(tw, zone=zone))
    elif "focus" in intents and not cards:
        speech.append(_t(lang, "Which area? For example: excavation, piles, foundation, site facilities.",
                         "Welcher Bereich? Zum Beispiel Aushub, Bohrpfähle, Fundament, Baustelleneinrichtung."))

    if zone:
        ctx["zone"] = zone
        actions.append({"type": "twin.focus", "zone": zone})
    if highlights:
        seen = {}
        for h in highlights:
            if h["id"] and (h["id"] not in seen or h["level"] == "red"):
                seen[h["id"]] = h["level"]
        actions.append({"type": "twin.highlight", "zones": [{"id": k, "level": v} for k, v in seen.items()]})

    if "report" in intents:
        scope = "incident" if (refers_back and ctx.get("incident")) or re.search(r"incident|vorfall|unfall", text, re.I) and ctx.get("incident") else "site"
        actions.append({"type": "report.generate", "scope": scope, "incident": ctx.get("incident") if scope == "incident" else None})
        speech.append(_t(lang, "I'm compiling the report from the verified site data." if scope == "site" else "I'm compiling the incident report.",
                         "Ich stelle den Bericht aus den geprüften Baustellendaten zusammen." if scope == "site" else "Ich erstelle den Vorfallbericht."))
    elif cards:
        actions.append({"type": "offer.report"})

    if new:
        actions.append({"type": "incident.new", "ids": [i["id"] for i in new]})
    actions = [a for a in actions if a]
    steps.rows.append({"key": "actions", "label": _t(lang, f"Update {len(actions)} views", f"{len(actions)} Ansichten aktualisieren"), "ms": 0, "ok": True})
    ctx["last_intents"] = intents
    return {"intents": intents, "lang": lang, "steps": steps.rows, "cards": cards, "actions": actions,
            "speech": " ".join(s for s in speech if s), "ctx": ctx, "generated_at": now()}


def _layout(text, ctx, lang, steps):
    """Draft a site layout from the uploaded site documents and photo GPS. Nothing is saved: the UI offers Save / Review."""
    res = steps.run("layout", _t(lang, "Build a layout draft from documents and photo GPS", "Lageplan-Entwurf aus Dokumenten und Foto-GPS erstellen"),
                    layout_suggest.suggest)
    base = {"intents": ["layout"], "lang": lang, "steps": steps.rows, "ctx": ctx, "generated_at": now()}
    if res is None:
        err = next((r.get("error") for r in steps.rows if r["key"] == "layout"), "")
        return {**base, "cards": [], "actions": [],
                "speech": _t(lang, f"I couldn't build a layout from the uploaded data: {err}", f"Aus den hochgeladenen Daten ließ sich kein Lageplan erstellen: {err}")}
    lay, rep = res["layout"], res["report"]
    if not rep.get("origin_source"):
        return {**base, "cards": [{"kind": "notice", "level": "info", "text": rep["warnings"][0]}], "actions": [],
                "speech": _t(lang, "I can't build a layout yet: there are no coordinates. Attach a survey point list, a plan or report with "
                                   "coordinates (CSV, Excel, Word, PDF, GeoJSON) or photos with GPS, then ask again.",
                             "Noch kein Lageplan möglich: Es fehlen Koordinaten. Bitte eine Punktliste, einen Plan oder ein Gutachten mit "
                             "Koordinaten (CSV, Excel, Word, PDF, GeoJSON) oder Fotos mit GPS anhängen und erneut fragen.")}
    zn = ", ".join(z["name"] for z in rep["zones"]) or _t(lang, "none", "keine")
    n_out = len(rep["outliers"])
    say = _t(lang, f"I drafted a site layout with {len(rep['zones'])} zone{'s' if len(rep['zones']) != 1 else ''} ({zn}) and "
                   f"{len(rep['structures'])} marker{'s' if len(rep['structures']) != 1 else ''}. "
                   f"{rep.get('photos_on_site', 0)} photos are on site" + (f", {n_out} item{'s' if n_out != 1 else ''} left out as too far away" if n_out else "") + ". "
                   + (f"{len(rep['warnings'])} warning{'s' if len(rep['warnings']) != 1 else ''} to check. " if rep["warnings"] else "")
                   + "It is not saved yet: review it and press Save layout.",
             f"Ich habe einen Lageplan-Entwurf mit {len(rep['zones'])} Zone{'n' if len(rep['zones']) != 1 else ''} ({zn}) und "
             f"{len(rep['structures'])} Markierung{'en' if len(rep['structures']) != 1 else ''} erstellt. "
             f"{rep.get('photos_on_site', 0)} Fotos liegen auf der Baustelle" + (f", {n_out} zu weit entfernt und ausgelassen" if n_out else "") + ". "
             + (f"{len(rep['warnings'])} Hinweis{'e' if len(rep['warnings']) != 1 else ''} prüfen. " if rep["warnings"] else "")
             + "Noch nicht gespeichert: bitte prüfen und „Lageplan speichern“ drücken.")
    steps.rows.append({"key": "actions", "label": _t(lang, "Offer the draft for review", "Entwurf zur Prüfung anbieten"), "ms": 0, "ok": True})
    return {**base, "cards": [{"kind": "layout", "layout": lay, "report": rep}], "actions": [{"type": "layout.offer"}], "speech": say}


def greeting(lang="en"):
    st = plan.status(with_weather=False)
    inc = incidents()
    behind = [a for a in st["activities"] if a["light"] in ("red", "yellow")]
    hour = dt.datetime.now().hour
    hi = _t(lang, "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening",
            "Guten Morgen" if hour < 12 else "Guten Tag" if hour < 18 else "Guten Abend")
    facts = _t(lang, f"{len(behind)} {'activity' if len(behind) == 1 else 'activities'} behind plan, {len(inc)} open incident{'' if len(inc) == 1 else 's'}.",
               f"{len(behind)} Vorgänge hinter Plan, {len(inc)} offene Vorfälle.")
    name = SITE["name"]
    if not name:
        return {"text": _t(lang, f"{hi}. I'm your AI Site Manager. How can I help you today?",
                           f"{hi}. Ich bin Ihr KI-Bauleiter. Wie kann ich Ihnen helfen?"),
                "behind": 0, "incidents": 0, "as_of": st["as_of"]}
    return {"text": _t(lang, f"{hi}. I'm your AI Site Manager for {name}. I've read the latest site data: {facts} "
                             "Shall I review today's progress or check for safety issues?",
                       f"{hi}. Ich bin Ihr KI-Bauleiter für {name}. Aktueller Stand: {facts} "
                       "Soll ich den Fortschritt prüfen oder nach Sicherheitsproblemen suchen?"),
            "behind": len(behind), "incidents": len(inc), "as_of": st["as_of"]}


# ---------------------------------------------------------------- report (HTML, print / save as PDF in the browser)
def _e(s):
    return html.escape(str(s if s is not None else ""))


def report(scope="site", incident_id=None, snapshot=None, lang="en", findings_note=None, plan_snapshot=None) -> dict:
    scan()
    st, tw = plan.status(), site_twin.twin()
    L = lambda en, de: _t(lang, en, de)  # noqa: E731
    zones = {z["id"]: z["name"] for z in tw["layout"]["zones"]}
    inc_all = incidents()
    incs = [i for i in inc_all if i["id"] == incident_id] if scope == "incident" and incident_id else inc_all
    prog, _, _ = _progress(st, tw, lang)
    photo_ids = list(dict.fromkeys([i["photo"] for i in incs] + ([] if scope == "incident" else [p["id"] for p in tw["photos"]][:6])))
    photos = [p for p in tw["photos"] if p["id"] in photo_ids]
    rid = new_id()
    behind = [r for r in prog["rows"] if r["light"] in ("red", "yellow")]
    hi = sum(1 for i in incs if i["severity"] == "high")

    # executive summary: assembled only from the verified numbers above (no model text)
    summary = [L(f"Reporting day {st['as_of']} (demo day), generated {now().replace('T', ' ')}.",
                 f"Berichtstag {st['as_of']} (Demotag), erstellt {now().replace('T', ' ')}.")]
    if scope == "site":
        n_run = len([r for r in prog['rows'] if r['light'] != 'grey'])
        summary.append(L(f"{n_run} {'activity' if n_run == 1 else 'activities'} running, {len(behind)} behind plan.",
                         f"{n_run} {'Vorgang läuft' if n_run == 1 else 'Vorgänge laufen'}, {len(behind)} hinter Plan."))
    summary.append(L(f"{len(incs)} open safety finding(s), {hi} high severity, from rule checks on {len(tw['photos'])} photos.",
                     f"{len(incs)} offene Sicherheitsbefunde, davon {hi} hoch, aus Regelprüfung von {len(tw['photos'])} Fotos."))

    def sev(s):
        return {"high": L("High", "Hoch"), "medium": L("Medium", "Mittel"), "low": L("Low", "Niedrig")}[s]

    rows_prog = "".join(
        f"<tr><td><span class='dot {r['light']}'></span>{_e(r['name'])}</td><td>{_e(zones.get(r['zone'], '—'))}</td>"
        f"<td>{r['actual']:g} / {r['planned']:g} {_e(r['unit'])}</td><td>{r['pct_actual']}% / {r['pct_planned']}%</td>"
        f"<td>{'—' if r['light'] == 'grey' else (str(r['delay_days']) + ' d' if r['delay_days'] >= 0.5 else L('on plan', 'im Plan'))}</td>"
        f"<td class='ref'>{_e(r['evidence'])}</td></tr>" for r in prog["rows"])
    rows_inc = "".join(
        f"<tr><td><span class='sev {i['severity']}'>{sev(i['severity'])}</span></td><td><b>{_e(i[f'title_{lang}'])}</b><br><small>{_e(i[f'detail_{lang}'])}</small></td>"
        f"<td>{_e(zones.get(i['zone'], L('not placed on plan', 'nicht verortet')))}</td>"
        f"<td>{_e(', '.join(o['class'].replace('_', ' ') + ' ' + str(round(o['confidence'] * 100)) + '%' for o in i['objects']))}</td>"
        f"<td>{_e((i.get('taken_at') or '').replace('T', ' ')[:16])}</td><td class='ref'>{_e(', '.join(i['evidence']))}</td></tr>" for i in incs)
    recs = "".join(f"<li><b>{_e(i[f'title_{lang}'])}:</b> {_e(i[f'recommendation_{lang}'])}</li>" for i in incs)
    alerts = "".join(f"<li>{_e(a['text'])} <span class='ref'>{_e(a['evidence'] or '')}</span></li>" for a in prog["alerts"])
    figs = "".join(
        f"<figure><img src='/data/{_e(p.get('ann_file') or p['file'])}'><figcaption>{_e(p.get('original_name') or p['id'])} · "
        f"{_e((p.get('taken_at') or '').replace('T', ' ')[:16])} · {_e(zones.get(p['zone'], L('no plan position', 'ohne Planposition')))} · "
        f"{_e(', '.join(d['class'].replace('_', ' ') + ' ' + str(round(d['confidence'] * 100)) + '%' for d in p['detections']) or L('no detections', 'keine Erkennungen'))} "
        f"<span class='ref'>photo:{_e(p['id'])}</span></figcaption></figure>" for p in photos)
    snap = "".join(f"<h2>{_e(t)}</h2><img class='snap' src='{_e(img)}'>" for t, img in
                   [(L("2D site plan (affected zones highlighted)", "2D-Lageplan (betroffene Zonen markiert)"), plan_snapshot),
                    (L("3D site twin snapshot", "3D-Zwilling – Ansicht"), snapshot)] if img and str(img).startswith("data:image/"))
    outstanding = "".join(f"<li>{_e(r['name'])}: {r['delay_days']} {L('days behind plan', 'Tage Verzug')}</li>" for r in behind)
    outstanding += "".join(f"<li>{_e(i[f'title_{lang}'])} ({sev(i['severity'])}) – {L('open', 'offen')}</li>" for i in incs)
    title = L("Incident report", "Vorfallbericht") if scope == "incident" else L("Site inspection report", "Baustellen-Prüfbericht")
    page = f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><title>{_e(title)} – {_e(SITE['name'])}</title>
<style>
body{{font:13px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;color:#111;max-width:900px;margin:24px auto;padding:0 18px}}
h1{{font-size:22px;margin:0}} h2{{font-size:15px;margin:22px 0 6px;border-bottom:2px solid #ff6a00;padding-bottom:3px}}
.meta{{color:#555}} table{{width:100%;border-collapse:collapse;margin:6px 0}} td,th{{border:1px solid #ddd;padding:5px 7px;vertical-align:top;text-align:left}}
th{{background:#f4f4f4}} .ref{{font:11px ui-monospace,monospace;color:#666}} .dot{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;background:#aaa}}
.dot.red{{background:#d33}} .dot.yellow{{background:#e6a100}} .dot.green{{background:#2a9d4b}}
.sev{{font-weight:700;padding:1px 7px;border-radius:9px;color:#fff;font-size:11px}} .sev.high{{background:#c62828}} .sev.medium{{background:#e08a00}} .sev.low{{background:#607d8b}}
.box{{border:1px solid #ddd;border-left:4px solid #ff6a00;padding:8px 12px;background:#fafafa}} .ai{{border-left-color:#2f6db5}}
figure{{display:inline-block;width:48%;margin:0 1% 12px 0;vertical-align:top}} figure img,.snap{{width:100%;border:1px solid #ccc}} figcaption{{font-size:11px;color:#444}}
.bar{{position:sticky;top:0;background:#fff;padding:8px 0;display:flex;gap:8px}} button{{padding:7px 14px;border-radius:8px;border:1px solid #ccc;background:#ff6a00;color:#fff;font-weight:600;cursor:pointer}}
.foot{{margin-top:24px;font-size:11px;color:#666;border-top:1px solid #ddd;padding-top:8px}}
@media print{{.bar{{display:none}} body{{margin:0}} h2{{break-after:avoid}} figure{{break-inside:avoid}}}}
</style></head><body>
<div class="bar"><button onclick="print()">{L('Save as PDF / print', 'Als PDF speichern / drucken')}</button></div>
<h1>{_e(title)}</h1><div class="meta">{_e(SITE['name'])} · {_e(SITE['client'])} · {_e(SITE['manager'])}<br>
{L('Reporting day', 'Berichtstag')}: {_e(st['as_of'])} · {L('Report id', 'Bericht-Nr.')} {rid} · {L('Status: DRAFT, not yet checked by a person', 'Status: ENTWURF, noch nicht von einer Person geprüft')}</div>
<h2>{L('Executive summary', 'Zusammenfassung')}</h2><div class="box">{'<br>'.join(_e(s) for s in summary)}
<br><small>{L('Assembled automatically from the verified data below; no free model text.', 'Automatisch aus den unten belegten Daten zusammengestellt, kein freier KI-Text.')}</small></div>
{f"<h2>{L('Planned vs actual', 'Soll-Ist-Vergleich')}</h2><table><tr><th>{L('Activity', 'Vorgang')}</th><th>{L('Zone', 'Zone')}</th><th>{L('Actual / planned', 'Ist / Soll')}</th><th>%</th><th>{L('Delay', 'Verzug')}</th><th>{L('Evidence', 'Beleg')}</th></tr>{rows_prog}</table>" if scope == "site" else ""}
{f"<h2>{L('Early warnings', 'Frühwarnungen')}</h2><ul>{alerts}</ul>" if alerts and scope == "site" else ""}
<h2>{L('Safety findings (verified observations)', 'Sicherheitsbefunde (belegte Beobachtungen)')}</h2>
{f"<table><tr><th>{L('Severity', 'Priorität')}</th><th>{L('Finding', 'Befund')}</th><th>{L('Zone', 'Zone')}</th><th>{L('Detected objects (model confidence)', 'Erkannte Objekte (Modellkonfidenz)')}</th><th>{L('Time', 'Zeit')}</th><th>{L('Evidence', 'Beleg')}</th></tr>{rows_inc}</table>" if incs else f"<p>{L('No open findings from the rule checks.', 'Keine offenen Befunde aus der Regelprüfung.')}</p>"}
<p class="ref">{L('Detector', 'Detektor')}: {_e(tw['models']['detector'])} · {L('rules', 'Regeln')}: person_near_machine, machine_in_restricted_zone, reported_incident, flagged_safety_photo · {L('detections below', 'Erkennungen unter')} {int(MIN_CONF * 100)}% {L('ignored', 'ignoriert')}.
{L('The detector has no helmet / vest class: PPE is not checked.', 'Der Detektor kennt keine Helm-/Westenklasse: PSA wird nicht geprüft.')}</p>
{f"<h2>{L('Recommended corrective actions (AI recommendation, not verified)', 'Empfohlene Maßnahmen (KI-Empfehlung, nicht geprüft)')}</h2><div class='box ai'><ul>{recs}</ul></div>" if recs else ""}
{f"<h2>{L('Outstanding issues', 'Offene Punkte')}</h2><ul>{outstanding}</ul>" if outstanding else ""}
{snap}
{f"<h2>{L('Photo evidence', 'Fotobelege')}</h2>{figs}" if figs else ""}
{f"<h2>{L('Notes', 'Hinweise')}</h2><p>{_e(findings_note)}</p>" if findings_note else ""}
<div class="foot">{L('DRAFT – created with AI assistance. Every finding cites its evidence id. Recommendations are suggestions. No legal advice.',
                       'ENTWURF – mit KI-Unterstützung erstellt. Jeder Befund nennt seinen Beleg. Empfehlungen sind Vorschläge. Keine Rechtsberatung.')}</div>
</body></html>"""
    out = DATA / "reports"
    out.mkdir(exist_ok=True)
    name = f"{'incident' if scope == 'incident' else 'inspection'}_{rid}.html"
    (out / name).write_text(page, encoding="utf-8")
    return {"id": rid, "url": f"/data/reports/{name}", "scope": scope, "incidents": len(incs), "photos": len(photos),
            "title": title}
