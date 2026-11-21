"""Word export and a print view (browser 'Save as PDF') for every document."""
import datetime as dt, html
from pathlib import Path
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from PIL import Image, ImageDraw
from .docs import DOC_TYPES, missing
from .store import load, DATA, SITE

SRC_DE = {"voice": "Diktat", "project": "Projektstammdaten", "document": "Unterlage", "calendar": "Kalender", "message": "Chat-Nachricht", "answer": "Antwort im Chat", "user": "manuell bearbeitet", "timestamp": "Zeitstempel",
          "weather": "Wetterdienst (Open-Meteo)", "photo": "Fotos", "schedule": "Bauzeitenplan", "diary": "Bautagebuch",
          "documents": "Anzeigen", "email": "E-Mail", "minutes": "Protokoll", "drilling": "Bohrzeitenliste Polier"}


def _fmt(ts):
    return dt.datetime.fromisoformat(ts).strftime("%d.%m.%Y %H:%M") if ts else ""


def annotated(p):
    src = DATA / p["file"]
    out = DATA / "uploads" / f"{p['id']}_ann.jpg"
    try:
        im = Image.open(src).convert("RGB")
    except Exception:
        return None
    d = ImageDraw.Draw(im)
    for b in p.get("detections", []):
        x0, y0 = b["x"] - b["width"] / 2, b["y"] - b["height"] / 2
        d.rectangle([x0, y0, x0 + b["width"], y0 + b["height"]], outline="red", width=4)
        d.text((x0 + 4, y0 + 4), f"{b['class']} {b['confidence']:.0%}", fill="red")
    im.thumbnail((1400, 1400))
    im.save(out, quality=85)
    return out


def _photo_caption(p):
    loc = "GPS aus Foto" if p["location_source"] == "exif" else "Standort Baustelle (kein GPS im Foto)"
    dets = ", ".join(f"{b['class']} {b['confidence']:.0%}" for b in p.get("detections", [])) or "keine"
    unverified = " · Kategorie nicht geprüft, bitte bestätigen" if p.get("category") == "uncategorized" else ""
    return f"{p['original_name']} · {p['taken_at'].replace('T', ' ')} · {p['lat']:.5f}, {p['lon']:.5f} ({loc}) · Erkennung: {dets}{unverified}"


def _footer(doc):
    if doc["status"] in ("checked", "sent"):
        return f"Entwurf mit KI-Unterstützung erstellt, geprüft von {doc['checked_by']} am {_fmt(doc['checked_at'])}."
    return "ENTWURF – mit KI-Unterstützung erstellt, noch nicht geprüft. Keine Rechtsberatung."


def docx(doc) -> Path:
    t = DOC_TYPES[doc["type"]]
    photos = {p["id"]: p for p in load("photos", [])}
    d = Document()
    st = d.styles["Normal"]
    st.font.name, st.font.size = "Arial", Pt(10.5)
    if doc["status"] == "draft":
        r = d.add_paragraph().add_run("ENTWURF")
        r.bold, r.font.color.rgb = True, RGBColor(0xC8, 0x50, 0x1E)
    d.add_heading(t["title"], 0)
    if t["basis"]:
        d.add_paragraph(t["basis"])
    hdr = d.add_table(rows=0, cols=2)
    hdr.style = "Light Grid Accent 1"
    for a, b in [("Bauvorhaben", SITE["name"]), ("Empfänger", t.get("recipient") or SITE["client"]),
                 ("Absender", SITE["manager"]), ("Datum", dt.date.today().strftime("%d.%m.%Y")), ("Dokument-Nr.", doc["id"])]:
        c = hdr.add_row().cells
        c[0].text, c[1].text = a, b
    d.add_paragraph()
    tbl = d.add_table(rows=0, cols=2)
    tbl.style = "Table Grid"
    for k, label, req, crit, *_ in t["fields"]:
        f = doc["fields"][k]
        c = tbl.add_row().cells
        c[0].text = label + (" *" if req else "")
        c[1].text = f["value"] or "— (offen)"
        c[0].width, c[1].width = Cm(5), Cm(11)
    if t.get("closing"):
        d.add_paragraph("\n" + t["closing"])
    d.add_heading("Formale Vollständigkeit", 2)
    miss = missing(doc)
    for k, label, req, *_ in t["fields"]:
        if req:
            d.add_paragraph(f"{'☐ fehlt' if k in miss else '☑'}  {label}")
    d.add_paragraph("Hinweis: Nur formale Prüfung der Angaben, keine rechtliche Bewertung von Anspruch oder Höhe.").runs[0].italic = True
    pics = [photos[i] for i in doc["photos"] if i in photos]
    if pics:
        d.add_heading("Fotodokumentation", 2)
        for p in pics:
            a = annotated(p)
            if a:
                d.add_picture(str(a), width=Cm(13))
            cap = d.add_paragraph(_photo_caption(p))
            cap.runs[0].font.size = Pt(8)
    d.add_heading("Nachweise je Feld", 2)
    for k, label, *_ in t["fields"]:
        f = doc["fields"][k]
        if f["value"] and f["source"]:
            src = f["source"]
            p = d.add_paragraph(f"{label}: {SRC_DE.get(src['type'], src['type'])}, {src.get('locator') or ''}"
                                + (f" [{src['evidence_id']}]" if src.get("evidence_id") else "") + f" – \"{(src.get('quote') or '')[:200]}\"")
            p.runs[0].font.size = Pt(8)
    d.add_paragraph()
    d.add_paragraph(_footer(doc)).runs[0].italic = True
    if doc["type"] not in ("bautagesbericht", "aktennotiz"):
        d.add_paragraph("\n\n______________________________\nUnterschrift Bauleitung")
    out = DATA / f"{doc['type']}_{doc['id']}.docx"
    d.save(out)
    return out


def print_html(doc) -> str:
    t = DOC_TYPES[doc["type"]]
    photos = {p["id"]: p for p in load("photos", [])}
    e = html.escape
    rows = "".join(f"<tr><th>{e(label)}{' *' if req else ''}</th><td>{e(doc['fields'][k]['value'] or '— (offen)').replace(chr(10), '<br>')}</td></tr>"
                   for k, label, req, *_ in t["fields"])
    miss = missing(doc)
    check = "".join(f"<li>{'☐ fehlt' if k in miss else '☑'} {e(label)}</li>" for k, label, req, *_ in t["fields"] if req)
    pics = "".join(f"<figure><img src='/data/{photos[i]['file']}'><figcaption>{e(_photo_caption(photos[i]))}</figcaption></figure>"
                   for i in doc["photos"] if i in photos)
    ev = "".join(f"<li><b>{e(label)}:</b> {e(SRC_DE.get(doc['fields'][k]['source']['type'], ''))}, {e(doc['fields'][k]['source'].get('locator') or '')}"
                 f"{(' [' + e(doc['fields'][k]['source']['evidence_id']) + ']') if doc['fields'][k]['source'].get('evidence_id') else ''} – „{e((doc['fields'][k]['source'].get('quote') or '')[:200])}“</li>"
                 for k, label, *_ in t["fields"] if doc["fields"][k]["value"] and doc["fields"][k]["source"])
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><title>{e(t['title'])} {doc['id']}</title>
<style>body{{font:11pt Arial,sans-serif;max-width:800px;margin:30px auto;color:#111}}h1{{margin:0 0 4px}}table{{border-collapse:collapse;width:100%;margin:12px 0}}
th,td{{border:1px solid #bbb;padding:6px 8px;text-align:left;vertical-align:top}}th{{width:32%;background:#f3f3f3}}.d{{color:#c8501e;font-weight:bold}}
figure{{margin:10px 0;page-break-inside:avoid}}img{{max-width:100%;max-height:420px}}figcaption,.ev{{font-size:8pt;color:#555}}.f{{font-style:italic;margin-top:24px}}
@media print{{.noprint{{display:none}}}}</style></head><body>
<p class="noprint"><button onclick="print()">Save as PDF / Print</button></p>
{'<p class="d">ENTWURF</p>' if doc['status'] == 'draft' else ''}<h1>{e(t['title'])}</h1><div>{e(t['basis'])}</div>
<table><tr><th>Bauvorhaben</th><td>{e(SITE['name'])}</td></tr><tr><th>Empfänger</th><td>{e(t.get('recipient') or SITE['client'])}</td></tr>
<tr><th>Absender</th><td>{e(SITE['manager'])}</td></tr><tr><th>Datum</th><td>{dt.date.today().strftime('%d.%m.%Y')}</td></tr></table>
<table>{rows}</table>{('<p>' + e(t['closing']) + '</p>') if t.get('closing') else ''}<h3>Formale Vollständigkeit</h3><ul>{check}</ul><p class="ev">Nur formale Prüfung, keine rechtliche Bewertung.</p>
{('<h3>Fotodokumentation</h3>' + pics) if pics else ''}<h3>Nachweise je Feld</h3><ul class="ev">{ev}</ul>
<p class="f">{e(_footer(doc))}</p><script>setTimeout(()=>print(),400)</script></body></html>"""
