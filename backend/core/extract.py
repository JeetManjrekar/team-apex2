"""Turns free text (dictation, chat, email) into document fields for the shared registry.
With OPENAI_API_KEY the team's nachweis_llm package extracts (evidence-ID and confidence gates in code);
otherwise the rule-based fallback below runs under the same gates."""
import re, datetime as dt



I = re.I
INTENTS = [
    ("nachtragsmeldung", re.compile(r"\bfels\b|\brock\b|boulder|findling|unexpected|unerwartet|zusatzleistung|additional work|nachtrag|"
                                    r"anders als (?:im|laut)|statt erwartet|instead of expected|bitte führen sie|please proceed|angeordnet|instructed", I)),
    ("mehrkostenanzeige", re.compile(r"mehrkosten|additional cost|extra cost|mehraufwand", I)),
    ("behinderungsanzeige", re.compile(r"\bidle\b|stillstand|steht still|stehen still|standing still|waiting|wartet|warten|blocked|behinder|\bdelay|"
                                       r"verzög|obstruct|cannot (?:continue|start|work)|can't (?:continue|start|work)|kann nicht|können nicht|"
                                       r"keine freigabe|no (?:plan )?release|missing (?:plans?|release|approval)|fehlende? (?:pläne|plan|freigabe)", I)),
    ("maengelanzeige", re.compile(r"defect|\bmangel|mängel|\bcrack|\briss|damage|schaden|beschädig|\bleak|undicht|"
                                  r"wrong(?:ly)? (?:installed|built|placed)|falsch (?:eingebaut|ausgeführt|verlegt)", I)),
    ("bedenkenanmeldung", re.compile(r"concern|bedenken|unsafe|unsicher|not feasible|nicht ausführbar|\bdoubt|zweifel", I)),
    ("aktennotiz", re.compile(r"aktennotiz|note for the file|file note|telefonat|phone call with|besprechung mit|meeting with", I)),
]
DAILY_RX = re.compile(r"daily report|site report|tagesbericht|bautagesbericht", I)
EDIT_RX = re.compile(r"^\s*(?:change|set|update|ändere|setze)\s+(?:the\s+|die\s+|den\s+|das\s+)?(.+?)\s+(?:to|auf|zu|=)\s+(.+?)\s*$", I)

LOC = re.compile(r"(?:bored\s+)?(?:pile|bohrpfahl|pfahl|axis|achse|abutment|widerlager|pier|pfeiler|span|feld|section|abschnitt|"
                 r"bauteil|block|floor|geschoss)\s*(?:no\.?\s*|nr\.?\s*)?[A-Za-z]?\d+[a-z]?(?:\s*(?:south|north|east|west|süd|nord|ost))?"
                 r"|(?:abutment|widerlager)\s+(?:south|north|east|west|süd|nord|ost|west)", I)
TIME = re.compile(r"(?:since|seit|from|ab|at|um)\s+(\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm|uhr|h)\b|\d{1,2}[:.]\d{2})", I)
CAUSE = re.compile(r"(?:because(?:\s+of)?|due\s+to|caused\s+by|weil|wegen|aufgrund(?:\s+von)?|da\s+(?=die|der|das|wir|es|kein))\s+([^.;!?\n]+)", I)
DURATION = re.compile(r"\d+(?:[.,]\d+)?\s*(?:hours?|hrs?|h\b|stunden|std\.?|days?|tagen?|tage|weeks?|wochen)", I)
EQUIP = re.compile(r"\b(?:\d+\s+)?(?:excavators?|bagger|cranes?|kran|(?:drilling\s+)?rig|bohrgerät|trucks?|lkw|concrete pump|betonpumpe|"
                   r"crew|kolonne|workers|arbeiter|men|mann)\b", I)
RESP = re.compile(r"\b(client|bauherr\w*|auftraggeber\w*|owner|employer|planner|planer|tragwerksplan\w*|structural engineer|architect\w*|"
                  r"subcontractor|nachunternehmer|utility|versorger|authority|behörde)\b", I)
SUB = re.compile(r"(?:subcontractor|nachunternehmer|firma|company|\bnu)\s+([A-ZÄÖÜ][\w&\-]+(?:\s+(?:[A-ZÄÖÜ][\w&\-]+|GmbH|AG))*)")
DEADLINE = re.compile(r"(?:by|until|bis(?:\s+zum)?|deadline|frist)\s+(?:\w+,\s*)?(\d{1,2}\.\d{1,2}\.(?:\d{2,4})?|\d{4}-\d{2}-\d{2}|"
                      r"(?:monday|tuesday|wednesday|thursday|friday|montag|dienstag|mittwoch|donnerstag|freitag)|"
                      r"(?:end of (?:the )?week|ende der woche|tomorrow|morgen))", I)
ORDER = re.compile(r"(?:ordered|instructed|requested)\s+by\s+[^.;!?\n]+|(?:auf anordnung|angeordnet|beauftragt|verlangt)\s+(?:durch|des|der|von)\s+[^.;!?\n]+|"
                   r"(?:bitte führen sie|please (?:proceed|continue)|wir ordnen an|hiermit ordnen wir)[^.;!?\n]*", I)
MEASURES = re.compile(r"(?:we|wir)\s+(?:have\s+)?(?:informed|notified|moved|relocated|called|haben\s+\w+\s+(?:informiert|umgesetzt|verständigt))[^.;!?\n]*", I)
EXPECT_KW = re.compile(r"expected|erwartet|according to|laut |lt\. |soil report|gutachten", I)
FOUND_KW = re.compile(r"\brock\b|\bfels|boulder|findling|groundwater|grundwasser|contaminat|altlast|obstacle|hindernis|hit |angetroffen|gestoßen", I)
DEFECT_KW = re.compile(r"defect|mangel|mängel|crack|riss|damage|schaden|beschädig|leak|undicht|wrong|falsch", I)
RISK_KW = re.compile(r"risk|risiko|gefahr|danger|could|könnte|damage|schäden", I)
PROPOSE = re.compile(r"(?:we\s+)?(?:suggest|propose|recommend|schlagen vor|empfehlen|vorschlag)[^.;!?\n]*", I)


def clauses(text):
    parts = re.split(r"(?<=[a-zäöüß0-9)]{2}[.;!?])\s+|\n+|,\s+|\s+(?=(?:but|aber|however|jedoch)\b)", text)
    return [p.strip(" .;") for p in parts if p and len(p.strip(" .;")) > 2]


def first_clause(text, rx, exclude=None):
    for c in clauses(text):
        if rx.search(c) and not (exclude and exclude.search(c)):
            return c
    return None


def detect_intents(text):
    return [name for name, rx in INTENTS if rx.search(text)]


def _date_from_text(text, ts):
    if re.search(r"\byesterday\b|\bgestern\b", text, I):
        return (ts.date() - dt.timedelta(days=1)).strftime("%d.%m.%Y"), re.search(r"\byesterday\b|\bgestern\b", text, I).group(0)
    m = re.search(r"\b\d{1,2}\.\d{1,2}\.(?:\d{2,4})?", text)
    if m:
        return m.group(0), m.group(0)
    return ts.date().strftime("%d.%m.%Y"), None


HEADER_RX = re.compile(r"^(?:von|an|cc|from|to|datum|date|betreff|subject|tel\.?|telefon)\s*:.*$|^(?:sehr geehrte\w*|hallo|liebe\w*|dear)\b.*$", I | re.M)


def strip_mail(text):
    text = re.split(r"\n\s*(?:mit freundlichen grüßen|viele grüße|best regards|kind regards|mfg)\b", text, flags=I)[0]
    return HEADER_RX.sub("", text).strip()


def rules(dtype, text, ts):
    """Rule-based fallback. Returns {key: (value, quote, confidence)}; quote is a verbatim span of the text.
    Fields whose value comes from the message time get quote None (host labels them as timestamp)."""
    out = {}
    text = strip_mail(text) or text

    def put(k, m, grp=0, conf=0.7):
        if m:
            q = m.group(0).strip(" .,")
            out[k] = ((m.group(grp) if grp else q).strip(" .,"), q, conf)

    def clause(k, rx, conf=0.7, exclude=None):
        c = first_clause(text, rx, exclude)
        if c:
            out[k] = (c, c, conf)

    put("location", LOC.search(text), conf=0.9)
    cl = clauses(text)
    first = cl[0] if cl else text
    first_main = re.split(CAUSE.pattern, first, flags=I)[0].strip(" .,") or first
    tm = TIME.search(text)
    date_txt, date_q = _date_from_text(DEADLINE.sub("", text), ts)
    if tm:
        out["event_datetime"] = (f"{date_txt}, {tm.group(1)}", tm.group(0).strip(), 0.8)
    elif date_q:
        out["event_datetime"] = (date_txt, date_q, 0.8)

    if dtype == "nachtragsmeldung":
        out["description"] = (first, first, 0.7)
        clause("expected_ground", EXPECT_KW)
        clause("found_ground", FOUND_KW, exclude=EXPECT_KW)
        put("instruction_by", ORDER.search(text), conf=0.6)
        clause("drilling_times", re.compile(r"(?:bohrzeit|drilling time)\w*[^.;\n]*\d|\d+(?:[.,]\d+)?\s*(?:h|hours?|stunden|std)\b", I))
        put("equipment", EQUIP.search(text), conf=0.7)
        if ORDER.search(text):
            put("related_instruction", ORDER.search(text), conf=0.6)
    elif dtype == "mehrkostenanzeige":
        out["description"] = (first_main, first_main, 0.7)
        put("cause", CAUSE.search(text), 1, 0.7)
        if "cause" not in out:
            clause("cause", FOUND_KW, exclude=EXPECT_KW)
        clause("additional_effort", re.compile(r"bohrzeit|drilling time|\d+(?:[.,]\d+)?\s*(?:h|hours?|stunden|std|m3|m³|t)\b", I), 0.6)
        put("instruction_by", ORDER.search(text), conf=0.6)
    elif dtype == "behinderungsanzeige":
        cause = CAUSE.search(text)
        desc = first if cause and cause.group(0) in first else (first_main + (f", {cause.group(0)}" if cause else ""))
        out["obstruction_description"] = (desc, first, 0.7)
        imp = first_clause(text, re.compile(r"idle|stillstand|steht still|stehen still|standing still|cannot|kann nicht|delay|verzug", I))
        if imp and imp != first:
            out["impact_on_work"] = (imp, imp, 0.6)
        put("expected_duration", DURATION.search(text), conf=0.6)
        r = RESP.search(cause.group(0)) if cause else None
        if r:
            out["instruction_by"] = (r.group(1), cause.group(0).strip(" ."), 0.6)
    elif dtype == "maengelanzeige":
        clause("defect_description", DEFECT_KW)
        s_ = SUB.search(text)
        if s_:
            out["responsible_party"] = (s_.group(1), s_.group(0), 0.8)
        put("affected_trade", re.search(r"formwork|schalung|rebar|bewehrung|concrete|beton|masonry|mauerwerk|drywall|trockenbau|electric\w*|elektro|plumbing|sanitär", text, I), conf=0.6)
        put("measure_taken", MEASURES.search(text), conf=0.6)
    elif dtype == "bedenkenanmeldung":
        c = CAUSE.search(text)
        if c:
            out["concern_description"] = (c.group(1).strip(" ."), c.group(0).strip(" ."), 0.6)
        else:
            clause("concern_description", re.compile(r"concern|bedenken|unsafe|unsicher|not feasible|nicht ausführbar|doubt|zweifel", I), 0.6)
        put("proposed_clarification", PROPOSE.search(text), conf=0.6)
    elif dtype == "aktennotiz":
        out["date"] = (date_txt, date_q, 0.9 if date_q else 0.6)
        out["subject"] = (first_main, first_main, 0.6)
        out["facts"] = (text.strip(), text.strip(), 0.7)
        p = re.search(r"(?:mit|with)\s+((?:Hr\.|Fr\.|Herrn?|Frau|Mr\.|Ms\.)?\s*[A-ZÄÖÜ][\w.\-]+(?:\s+[A-ZÄÖÜ][\w.\-]+)?)", text)
        if p:
            out["participants"] = (p.group(1), p.group(0), 0.6)
        put("next_steps", PROPOSE.search(text) or re.search(r"(?:next|nächste[rn]?|bis)\s[^.;!?\n]+", text, I), conf=0.6)
    return out


def extract(dtype, text, evidence, locked=None, ts=None, run_id="run"):
    """Extract fields for one document type.
    evidence: list of {"id","kind","locator","excerpt"}; evidence[0] is the primary source (the message/email).
    Returns (fields {key: {value, evidence_id, confidence, quote}}, gaps, mode, extraction_result_or_None)."""
    from . import llm_bridge
    ts = ts or dt.datetime.now()
    locked = locked or {}
    res = llm_bridge.extract(dtype, text, evidence, locked, run_id)
    if res is not None:
        fields, gaps, extraction = res
        by_id = {e["id"]: e for e in evidence}
        return ({k: dict(v, quote=(by_id.get(v["evidence_id"], {}).get("excerpt") or "")[:300]) for k, v in fields.items()},
                gaps, "llm", extraction)
    with llm_bridge.Timer("rules_extraction", run_id, document_type=dtype):
        base = rules(dtype, text, ts)
    primary = evidence[0]["id"]
    thr = llm_bridge.SETTINGS.confidence_threshold
    out, gaps = {}, []
    for k, (val, quote, conf) in base.items():
        if k in locked:
            continue
        if conf < thr:             # same gate as the package: below threshold becomes a gap
            gaps.append(k)
            continue
        out[k] = {"value": val, "evidence_id": primary if quote else "timestamp", "confidence": conf, "quote": quote}
    return out, gaps, "rules", None
