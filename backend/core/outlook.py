"""Outlook + client-document ingestion (W1): .eml -> mail: evidence / proposals on drafts, .ics -> cal- reminders.

.eml  parse headers + plain body -> sanitizer.mask -> summarize -> (if Nachtrag/intent hit) assistant.apply_text(..., "email")
      -> findings land via docs.set_field(by="ai"): new draft, or proposals on a matching open draft (locks win).
.ics  VEVENTs today .. today + OUTLOOK_LOOKAHEAD_DAYS -> reminders (evidence `cal-<uid>`, kind "calendar") + chat notification.
      A calendar entry alone never creates a document.
.pdf/.docx/.xlsx/.csv  client documents / tables -> "units" with exact locators (PDF page, sheet + row range, table rows)
      -> mask -> summarize; a unit only ever feeds an EXISTING open draft (assistant.apply_text merges: locks win, differing values
      become proposals). Evidence ids of units are `msg:doc-<filehash>-<n>` (assistant.apply_text prefixes non-mail ids with `msg:`).
Nothing here changes a document status.
"""
import csv, datetime as dt, hashlib, html as htmllib, io, re, zipfile, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from html.parser import HTMLParser

from . import assistant, docs, llm_bridge, sanitizer, summarize
from .extract import LOC, detect_intents
from .store import env, load, new_id, now, save

MAX_BYTES = 10 * 1024 * 1024
SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "inbox_samples"
FETCH_TIMEOUT = 5
BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "table", "ul", "ol", "blockquote"}


def lookahead_days() -> int:
    try:
        return max(0, int(env("OUTLOOK_LOOKAHEAD_DAYS", "7")))
    except ValueError:
        return 7


# ---------- .eml ----------
class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self.skip = max(0, self.skip - 1)
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(src: str) -> str:
    p = _Text()
    p.feed(src)
    p.close()
    text = htmllib.unescape("".join(p.parts)).replace("\xa0", " ")
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def parse_eml(raw: bytes) -> dict:
    """-> {message_id, from_name, from_addr, subject, date (datetime|None), body, attachments}."""
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    part = msg.get_body(preferencelist=("plain", "html"))
    body = ""
    if part is not None:
        content = part.get_content()
        body = html_to_text(content) if part.get_content_type() == "text/html" else content.strip()
    name, addr = (getaddresses([str(msg.get("From", ""))]) or [("", "")])[0]
    try:
        date = msg["Date"].datetime if msg["Date"] else None
    except Exception:
        date = None
    return {"message_id": str(msg.get("Message-ID") or "").strip(), "from_name": name, "from_addr": addr,
            "subject": str(msg.get("Subject") or "").strip(), "date": date, "body": body,
            "attachments": [a.get_filename() or "" for a in msg.iter_attachments()]}


def message_ref(m: dict) -> str:
    """Stable short hash of the message (Message-ID, else sender|date|subject): evidence id is `mail:<ref>`."""
    key = m["message_id"] or f"{m['from_addr']}|{m['date']}|{m['subject']}"
    return hashlib.sha1(key.encode()).hexdigest()[:10]


def _sender_label(m: dict) -> str:
    """Display name, else the sender's domain: a raw address would reach the LLM through the evidence locator."""
    return m["from_name"] or (m["from_addr"].split("@")[-1] if m["from_addr"] else "unbekannt")


def mail_locator(m: dict) -> str:
    when = m["date"].strftime("%d.%m.%Y %H:%M") if m["date"] else "Datum unbekannt"
    return sanitizer.mask(f"E-Mail {_sender_label(m)}, {when}, Betreff „{m['subject']}“")[0]


def _mail_text(m: dict) -> str:
    return f"Betreff: {m['subject']}\n{m['body']}"


def _summarize_masked(text: str) -> dict:
    """Mask first, summarize the masked text, restore afterwards (summarize may call an LLM)."""
    masked, mapping = sanitizer.mask(text)
    res = sanitizer.unmask(summarize.summarize(masked), mapping)
    res["masked"] = sorted(mapping)
    return res


def _drafts_with_evidence(evidence_id: str, prefix: bool = False) -> list:
    out = []
    match = (lambda i: bool(i) and i.startswith(evidence_id)) if prefix else (lambda i: i == evidence_id)
    for d in docs.all_docs():
        for f in d["fields"].values():
            ids = [(f.get("source") or {}).get("evidence_id"), ((f.get("proposal") or {}).get("source") or {}).get("evidence_id")]
            if any(match(i) for i in ids):
                out.append(d)
                break
    return out


def _draft_entry(d, *, merged, filled=(), proposals=(), gaps=()) -> dict:
    lab = lambda keys: [docs.field_meta(d["type"], k)["label"] for k in keys if docs.field_meta(d["type"], k)]
    return {"id": d["id"], "type": d["type"], "title": d["title"], "status": d["status"], "url": f"/api/docs/{d['id']}",
            "created": not merged, "merged": merged, "filled": list(filled), "proposals": list(proposals),
            "filled_labels": lab(filled), "proposal_labels": lab(proposals), "gap_labels": lab(gaps)}


def target_types(summary: dict, text: str) -> list[str]:
    """Documents an email may feed: Nachtrag if the client orders extra/changed work, plus the first detected intent."""
    types = ["nachtragsmeldung"] if summary.get("nachtrag_candidates") else []
    for t in detect_intents(text)[:1]:
        if t not in types:
            types.append(t)
    return types


def import_eml(raw: bytes, filename: str = "") -> tuple[dict, list]:
    """-> (email item, notifications). Never overwrites: apply_text routes to set_field(by="ai") with locks and proposals."""
    m = parse_eml(raw)
    ref = message_ref(m)
    eid = f"mail:{ref}"
    text = _mail_text(m)
    summary = _summarize_masked(f"Von: {m['from_addr']}\n{text}")
    item = {"kind": "mail", "evidence_id": eid, "file": filename, "message_id": m["message_id"], "from": m["from_name"] or m["from_addr"],
            "subject": m["subject"], "date": m["date"].isoformat() if m["date"] else "", "attachments": m["attachments"],
            "summary": summary.get("summary", []), "open_items": summary.get("open_items", []), "decisions": summary.get("decisions", []),
            "nachtrag_candidates": summary.get("nachtrag_candidates", []), "masked": summary.get("masked", []),
            "duplicate": False, "drafts": []}
    known = _drafts_with_evidence(eid)
    if known:                                   # same mail imported twice: report, do not touch anything
        item["duplicate"] = True
        item["drafts"] = [_draft_entry(d, merged=True) for d in known]
        return item, []
    meta = {"headers": {"subject": m["subject"], "date": item["date"], "message_id": ref}}
    for dtype in target_types(summary, text):
        d, filled, proposals, merged, gaps, mode = assistant.apply_text(
            dtype, text, "email", source_ref=ref, origin="email", locator=mail_locator(m), evidence_meta=meta)
        item["drafts"].append(_draft_entry(d, merged=merged, filled=filled, proposals=proposals, gaps=gaps))
    notes = [_mail_notification(item)]
    return item, notes


def _mail_notification(item: dict) -> dict:
    parts = [f"E-Mail „{item['subject']}“ von {item['from']} importiert ({len(item['open_items'])} offene Punkte)."]
    for e in item["drafts"]:
        what = []
        if e["filled"]:
            what.append(f"{len(e['filled'])} Feld(er) ergänzt ({', '.join(e['filled_labels'])})")
        if e["proposals"]:
            what.append(f"Vorschlag zu {', '.join(e['proposal_labels'])}")
        parts.append(f"{e['title']}: {'; '.join(what) or 'keine neuen Angaben'}.")
    if item["drafts"]:
        parts.append("Bitte prüfen – nichts wurde automatisch übernommen oder versendet.")
    return {"text": " ".join(parts), "ref": item["evidence_id"], "doc": item["drafts"][0]["id"] if item["drafts"] else None}


# ---------- .ics ----------
def _naive(v) -> dt.datetime:
    """date / (aware) datetime -> naive local datetime."""
    if isinstance(v, dt.datetime):
        return v.astimezone().replace(tzinfo=None) if v.tzinfo else v
    return dt.datetime.combine(v, dt.time.min)


def _occurrences(ev, wstart: dt.datetime, wend: dt.datetime) -> list[tuple[dt.datetime, dt.datetime]]:
    """Start/end of the event's occurrences overlapping [wstart, wend); expands a simple RRULE."""
    raw_start = ev.decoded("DTSTART")
    all_day = not isinstance(raw_start, dt.datetime)
    start = _naive(raw_start)
    if "DTEND" in ev:
        end = _naive(ev.decoded("DTEND"))
    elif "DURATION" in ev:
        end = start + ev.decoded("DURATION")
    else:
        end = start + (dt.timedelta(days=1) if all_day else dt.timedelta())
    length = max(end - start, dt.timedelta())
    starts = [start]
    if "RRULE" in ev:
        try:
            from dateutil.rrule import rrulestr
            starts = list(rrulestr("RRULE:" + ev["RRULE"].to_ical().decode(), dtstart=start).between(wstart - length, wend, inc=True)) or []
        except Exception:
            starts = [start]
    return [(s, s + length) for s in starts if s < wend and (s + length > wstart or s >= wstart)]


def _people(ev) -> list[str]:
    att = ev.get("ATTENDEE", [])
    att = att if isinstance(att, list) else [att]
    return [str(a.params.get("CN")) for a in att if getattr(a, "params", None) and a.params.get("CN")]


def parse_ics(raw: bytes, today: dt.date | None = None, days: int | None = None) -> list[dict]:
    """VEVENTs from today through today + `days` (default OUTLOOK_LOOKAHEAD_DAYS), sorted by start. Cancelled events are skipped."""
    from icalendar import Calendar
    today = today or dt.date.today()
    days = lookahead_days() if days is None else days
    wstart = dt.datetime.combine(today, dt.time.min)
    wend = wstart + dt.timedelta(days=days + 1)
    out = []
    for ev in Calendar.from_ical(raw).walk("VEVENT"):
        if str(ev.get("STATUS", "")).upper() == "CANCELLED" or "DTSTART" not in ev:
            continue
        recurring = "RRULE" in ev
        for s, e in _occurrences(ev, wstart, wend):
            uid = re.sub(r"[^\w.\-]", "-", str(ev.get("UID") or new_id()))[:64]
            out.append({"uid": uid + (f"-{s:%Y%m%d}" if recurring else ""), "title": str(ev.get("SUMMARY") or "Termin"), "start": s, "end": e,
                        "all_day": not isinstance(ev.decoded("DTSTART"), dt.datetime), "location": str(ev.get("LOCATION") or ""),
                        "description": str(ev.get("DESCRIPTION") or ""), "attendees": _people(ev)})
    return sorted(out, key=lambda x: x["start"])


def _when(start: dt.datetime, all_day: bool, today: dt.date) -> str:
    day = "" if start.date() == today else f"am {start:%d.%m.} "
    return day + ("" if all_day else f"{start:%H:%M}")


def reminder(ev: dict, today: dt.date) -> dict:
    """Reminder for one event; open points come from its (masked) description via summarize."""
    text = f"{ev['title']}\n{ev['location']}\n{ev['description']}"
    open_items = _summarize_masked(ev["description"])["open_items"] if ev["description"].strip() else []
    m = LOC.search(text)
    topic = m.group(0).strip() if m else ""
    msg = f"{ev['title']} {_when(ev['start'], ev['all_day'], today)}".strip()
    if open_items:
        msg += f" – {len(open_items)} offene Punkte" + (f" zu {topic}" if topic else "")
    return {"evidence_id": f"cal-{ev['uid']}", "kind": "calendar", "title": ev["title"], "start": ev["start"].isoformat(),
            "end": ev["end"].isoformat(), "all_day": ev["all_day"], "location": ev["location"], "attendees": ev["attendees"],
            "topic": topic, "open_items": open_items, "message": msg}


def import_ics(raw: bytes, filename: str = "", today: dt.date | None = None) -> tuple[list, list]:
    """-> (reminders, notifications). No document is created from a calendar entry."""
    today = today or dt.date.today()
    rems = [dict(reminder(ev, today), file=filename) for ev in parse_ics(raw, today)]
    return rems, [{"text": r["message"], "ref": r["evidence_id"], "doc": None} for r in rems]


# ---------- client documents & tables (.pdf .docx .xlsx .csv) ----------
DOC_EXTS = ("pdf", "docx", "xlsx", "csv")
ROWS_PER_UNIT = 25          # table rows per citation unit
MAX_UNITS = 40              # units that may feed drafts per file
MAX_XML = 50 * 1024 * 1024  # decompressed size cap per OOXML part (zip bombs)


class Unsupported(Exception):
    """File cannot be turned into text (empty, scanned, encrypted, missing library, ...): reported in `skipped`."""


def _cell(v) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()


def _row_units(rows: list[tuple[int, list[str]]], where: str) -> list[dict]:
    """rows: [(row_number, cells)] -> units of ROWS_PER_UNIT rows; the header (first non-empty row) is repeated for context."""
    rows = [(n, c) for n, c in rows if any(c)]
    if not rows:
        return []
    header = rows[0][1]
    units = []
    for i in range(0, len(rows), ROWS_PER_UNIT):
        chunk = rows[i:i + ROWS_PER_UNIT]
        lines = ([" | ".join(header)] if i else []) + [" | ".join(c for c in cells if c) for _, cells in chunk]
        units.append({"locator": f"{where}, Zeile {chunk[0][0]}" + (f"–{chunk[-1][0]}" if chunk[-1][0] != chunk[0][0] else ""), "text": "\n".join(lines)})
    return units


def _units_csv(raw: bytes) -> list[dict]:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [(n, [_cell(c) for c in r]) for n, r in enumerate(csv.reader(io.StringIO(text), dialect), 1)]
    return _row_units(rows, "Tabelle")


def _units_pdf(raw: bytes) -> list[dict]:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise Unsupported("PDF support needs the 'pypdf' package (pip install pypdf)")
    try:
        rd = PdfReader(io.BytesIO(raw))
        if rd.is_encrypted and not rd.decrypt(""):
            raise Unsupported("PDF is password-protected")
        pages = [(n, (pg.extract_text() or "").strip()) for n, pg in enumerate(rd.pages, 1)]
    except Unsupported:
        raise
    except Exception as e:
        raise Unsupported(f"PDF could not be read ({type(e).__name__})")
    units = [{"locator": f"Seite {n}", "text": t} for n, t in pages if t]
    if not units:
        raise Unsupported("PDF contains no extractable text (scanned? OCR is not supported)")
    return units


def _units_docx(raw: bytes) -> list[dict]:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    try:
        d = Document(io.BytesIO(raw))
    except Exception as e:
        raise Unsupported(f"Word file could not be read ({type(e).__name__})")
    units, paras, p_from, n_par, n_tab = [], [], 0, 0, 0

    def flush():
        if paras:
            units.append({"locator": f"Absatz {p_from}" + (f"–{n_par}" if n_par != p_from else ""), "text": "\n".join(paras)})
            paras.clear()
    for el in d.element.body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            t = _cell(Paragraph(el, d).text)
            if t:
                n_par += 1
                if not paras:
                    p_from = n_par
                paras.append(t)
                if sum(map(len, paras)) > 3000:
                    flush()
        elif tag == "tbl":
            flush()
            n_tab += 1
            rows = [(n, [_cell(c.text) for c in r.cells]) for n, r in enumerate(Table(el, d).rows, 1)]
            rows = [(n, [c for i, c in enumerate(cs) if i == 0 or c != cs[i - 1]]) for n, cs in rows]     # merged cells repeat
            units += _row_units(rows, f"Tabelle {n_tab}")
    flush()
    return units


def _xml_root(zf: zipfile.ZipFile, name: str):
    import xml.etree.ElementTree as ET
    with zf.open(name) as f:
        data = f.read(MAX_XML + 1)
    if len(data) > MAX_XML or b"<!DOCTYPE" in data[:2048] or b"<!ENTITY" in data:
        raise Unsupported("spreadsheet part rejected (too large or contains entity declarations)")
    return ET.fromstring(data)


def _col_index(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref.upper()).group(0):
        n = n * 26 + ord(ch) - 64
    return n


def _units_xlsx(raw: bytes) -> list[dict]:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
          "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        wb = _xml_root(zf, "xl/workbook.xml")
        rels = {r.get("Id"): r.get("Target") for r in _xml_root(zf, "xl/_rels/workbook.xml.rels").findall("rel:Relationship", ns)}
        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            shared = ["".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")) for si in _xml_root(zf, "xl/sharedStrings.xml").findall("m:si", ns)]
        units = []
        for sh in wb.find("m:sheets", ns).findall("m:sheet", ns):
            if sh.get("state") in ("hidden", "veryHidden"):
                continue
            target = rels.get(sh.get(f"{{{ns['r']}}}id"), "")
            path = target.lstrip("/") if target.startswith("/") else "xl/" + target
            if path not in zf.namelist():
                continue
            rows = []
            for row in _xml_root(zf, path).iter(f"{{{ns['m']}}}row"):
                cells = {}
                for c in row.findall("m:c", ns):
                    t, v = c.get("t"), c.find("m:v", ns)
                    if t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(f"{{{ns['m']}}}t"))
                    elif v is None or v.text is None:
                        continue
                    elif t == "s":
                        val = shared[int(v.text)] if int(v.text) < len(shared) else ""
                    elif t == "b":
                        val = "ja" if v.text == "1" else "nein"
                    else:
                        val = v.text
                    cells[_col_index(c.get("r", "A1"))] = _cell(val)
                rows.append((int(row.get("r", len(rows) + 1)), [cells.get(i, "") for i in range(1, max(cells, default=0) + 1)]))
            units += _row_units(rows, f"Blatt „{sh.get('name')}“")
    except Unsupported:
        raise
    except Exception as e:
        raise Unsupported(f"Excel file could not be read ({type(e).__name__})")
    return units


def extract_units(ext: str, raw: bytes) -> list[dict]:
    """-> [{"locator": "Seite 3" | "Blatt „LV“, Zeile 5–29" | "Tabelle 2, Zeile 1–25" | "Absatz 1–9", "text"}]. Raises Unsupported."""
    units = {"pdf": _units_pdf, "docx": _units_docx, "xlsx": _units_xlsx, "csv": _units_csv}[ext](raw)
    if not units:
        raise Unsupported("file is empty (no text or table rows)")
    return units


def import_document(raw: bytes, filename: str, ext: str) -> tuple[dict, list]:
    """-> (document item, notifications). Units feed only EXISTING open drafts (never a new one); text is masked before any summarize/LLM step."""
    units = extract_units(ext, raw)
    ref = hashlib.sha1(raw).hexdigest()[:10]
    eid = f"doc-{ref}"
    stem = sanitizer.mask(filename.rsplit("/", 1)[-1])[0]
    item = {"kind": "document", "evidence_id": eid, "file": filename, "format": ext, "units": len(units), "duplicate": False, "truncated": False,
            "locators": [u["locator"] for u in units[:200]], "summary": [], "open_items": [], "decisions": [], "nachtrag_candidates": [],
            "masked": [], "drafts": [], "unmatched": []}
    known = _drafts_with_evidence(f"msg:doc-{ref}-", prefix=True)
    if known:
        item["duplicate"] = True
        item["drafts"] = [_draft_entry(d, merged=True) for d in known]
        return item, []
    summary = _summarize_masked("\n".join(u["text"] for u in units)[:20000])
    for k in ("summary", "open_items", "decisions", "nachtrag_candidates", "masked"):
        item[k] = summary.get(k, [])
    entries = {}
    for i, u in enumerate(units[:MAX_UNITS]):
        for dtype in detect_intents(u["text"])[:1]:
            loc = assistant.rules_loc(u["text"])
            if not assistant._find_mergeable(dtype, loc):          # documents are reference material: never open a new draft
                if u["locator"] not in item["unmatched"]:
                    item["unmatched"].append(u["locator"])
                continue
            locator = sanitizer.mask(f"Dokument {stem}, {u['locator']}")[0]
            d, filled, proposals, merged, gaps, mode = assistant.apply_text(
                dtype, u["text"], "document_page", source_ref=f"doc-{ref}-{i}", origin="document", locator=locator,
                evidence_meta={"file": stem, "unit": u["locator"]})
            e = entries.setdefault(d["id"], {"d": d, "filled": [], "proposals": [], "gaps": []})
            e["d"] = d
            for key, vals in (("filled", filled), ("proposals", proposals), ("gaps", gaps)):
                e[key] += [v for v in vals if v not in e[key]]
    item["truncated"] = len(units) > MAX_UNITS
    item["drafts"] = [_draft_entry(e["d"], merged=True, filled=e["filled"], proposals=e["proposals"], gaps=e["gaps"]) for e in entries.values()]
    return item, [_doc_notification(item)]


def _doc_notification(item: dict) -> dict:
    parts = [f"Dokument „{item['file']}“ ({item['units']} Abschnitte) gelesen, {len(item['open_items'])} offene Punkte."]
    for e in item["drafts"]:
        if e["proposals"] or e["filled"]:
            parts.append(f"{e['title']}: Vorschlag/Ergänzung zu {', '.join(e['proposal_labels'] + e['filled_labels'])} (mit Quellenangabe).")
    if item["drafts"]:
        parts.append("Bitte prüfen – gesperrte Felder wurden nicht verändert.")
    return {"text": " ".join(parts), "ref": item["evidence_id"], "doc": item["drafts"][0]["id"] if item["drafts"] else None}


# ---------- chat notifications ----------
def post_notifications(notes: list[dict]) -> list[dict]:
    """Append assistant messages to the chat (skips refs already announced). Returns the messages added."""
    msgs = load("messages", [])
    seen = {m.get("ref") for m in msgs}
    added = []
    for n in notes:
        if n["ref"] in seen:
            continue
        m = {"id": new_id(), "role": "assistant", "text": n["text"], "at": now(), "ref": n["ref"]}
        if n.get("doc"):
            m["doc"] = n["doc"]
        added.append(m)
        seen.add(n["ref"])
    if added:
        save("messages", msgs + added)
    return added


# ---------- entry point ----------
def import_files(files: list, today: dt.date | None = None) -> dict:
    """files: list of (filename, bytes) -> {"created", "drafts", "reminders", "emails", "notifications", "skipped"}. Timer: `outlook_import`."""
    out = {"created": [], "drafts": [], "reminders": [], "emails": [], "documents": [], "notifications": [], "skipped": []}
    notes = []
    with llm_bridge.Timer("outlook_import", f"outlook-{new_id()}", files=len(files)):
        for name, raw in files:
            ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
            try:
                if len(raw) > MAX_BYTES:
                    out["skipped"].append({"file": name, "reason": "file too large (max 10 MB)"})
                elif ext == "eml":
                    item, n = import_eml(raw, name)
                    out["emails"].append(item)
                    out["created"].append({"kind": "mail", "evidence_id": item["evidence_id"], "title": item["subject"], "duplicate": item["duplicate"]})
                    out["drafts"] += [e for e in item["drafts"] if e["id"] not in {d["id"] for d in out["drafts"]}]
                    notes += n
                elif ext == "ics":
                    rems, n = import_ics(raw, name, today)
                    out["reminders"] += rems
                    out["created"] += [{"kind": "calendar", "evidence_id": r["evidence_id"], "title": r["message"], "duplicate": False} for r in rems]
                    notes += n
                    if not rems:
                        out["skipped"].append({"file": name, "reason": f"no events today or in the next {lookahead_days()} days"})
                elif ext in DOC_EXTS:
                    item, n = import_document(raw, name, ext)
                    out["documents"].append(item)
                    out["created"].append({"kind": "document", "evidence_id": item["evidence_id"], "title": item["file"], "duplicate": item["duplicate"]})
                    out["drafts"] += [e for e in item["drafts"] if e["id"] not in {d["id"] for d in out["drafts"]}]
                    notes += n
                else:
                    out["skipped"].append({"file": name, "reason": "only .eml, .ics, .pdf, .docx, .xlsx and .csv files are supported"})
            except Unsupported as e:
                out["skipped"].append({"file": name, "reason": str(e)})
            except Exception as e:   # one broken file must not fail the whole batch
                out["skipped"].append({"file": name, "reason": f"could not be read: {e}"})
        out["notifications"] = post_notifications(notes)
    return out


# ---------- one-click sync (user-initiated only; nothing here runs on startup or in the background) ----------
class SyncError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def validate_ics_url(url: str) -> str:
    url = (url or "").strip()
    u = urllib.parse.urlparse(url)
    if u.scheme not in ("http", "https") or not u.netloc:
        raise SyncError(400, "ics_url must be an http:// or https:// URL")
    return url


class _HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).scheme not in ("http", "https"):
            raise urllib.error.URLError("redirect to unsupported scheme")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_ics(url: str) -> bytes:
    """Read-only GET of an iCal feed (5 s timeout, size capped). Errors never echo the URL: feed URLs often embed secret tokens."""
    url = validate_ics_url(url)
    req = urllib.request.Request(url, headers={"Accept": "text/calendar", "User-Agent": "nachweis-sync"})
    try:
        with urllib.request.build_opener(_HttpsOnlyRedirect).open(req, timeout=FETCH_TIMEOUT) as r:
            raw = r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise SyncError(502, f"calendar feed answered HTTP {e.code}") from None
    except Exception as e:
        raise SyncError(502, f"calendar feed could not be fetched ({type(e).__name__})") from None
    if len(raw) > MAX_BYTES:
        raise SyncError(502, "calendar feed too large (max 10 MB)")
    return raw


def sync(ics_url: str | None = None, include_samples: bool = True, today: dt.date | None = None) -> dict:
    """Explicit one-click sync: sample .eml/.ics files + an iCal URL (request value, else ICS_FEED_URL) -> same result as import_files, plus `sources_synced`."""
    files, sources = [], []
    if include_samples and SAMPLES_DIR.is_dir():
        found = sorted(p for p in SAMPLES_DIR.iterdir() if p.is_file() and p.suffix.lower().lstrip(".") in ("eml", "ics") + DOC_EXTS)
        files += [(p.name, p.read_bytes()[:MAX_BYTES + 1]) for p in found]
        sources.append({"source": "samples", "ok": True, "files": [p.name for p in found]})
    url = (ics_url or "").strip() or env("ICS_FEED_URL", "").strip()
    if url:
        validate_ics_url(url)                      # reject before touching the network
        try:
            files.append(("calendar-feed.ics", fetch_ics(url)))
            sources.append({"source": "ics_url", "ok": True, "files": ["calendar-feed.ics"]})
        except SyncError as e:
            if not files:
                raise                              # nothing else to import: surface the failure
            sources.append({"source": "ics_url", "ok": False, "error": e.detail, "files": []})
    out = import_files(files, today)
    out["sources_synced"] = sources
    return out
