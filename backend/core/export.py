"""Word export (docxtpl templates, python-docx fallback), PDF via headless LibreOffice, and a print view.

Pipeline per document:  build_context(doc) -> render template -> (watermark if Draft) -> .docx -> soffice -> .pdf
Each step is a small function; HTTP concerns live in routes/documents.py.
"""
import datetime as dt, html, os, shutil, subprocess, tempfile, threading
from pathlib import Path
from docx import Document
from docx.oxml import parse_xml
from docx.shared import Cm, Mm, Pt, RGBColor
from PIL import Image, ImageDraw
from . import llm_bridge
from .docs import DOC_TYPES, missing
from .store import ROOT, load, DATA, SITE, env

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


TEMPLATE_FOR = {"nachtragsmeldung": "nachtrag.docx", "mehrkostenanzeige": "nachtrag.docx", "bautagesbericht": "tagesbericht.docx",
                "behinderungsanzeige": "notice.docx", "maengelanzeige": "notice.docx", "bedenkenanmeldung": "notice.docx",
                "aktennotiz": "notice.docx"}
NO_SIGNATURE = ("bautagesbericht", "aktennotiz")
EXCERPT_MAX = 300
PHOTO_WIDTH_MM = 130
LO_PROFILE = "file:///tmp/lo_nachweis"    # own LibreOffice profile: avoids lock clashes with a running desktop instance
LO_TIMEOUT_S = 60
SOFFICE_PATHS = ("/usr/bin/soffice", "/Applications/LibreOffice.app/Contents/MacOS/soffice")
_soffice_lock = threading.Lock()          # one conversion at a time: concurrent soffice runs share (and lock) the profile


class PdfUnavailable(RuntimeError):
    """PDF cannot be produced on this host (soffice missing, conversion failed or timed out). The print view still works."""


# ---------- template context ----------
def _header_rows(doc, t):
    return [{"label": a, "value": b} for a, b in [
        ("Bauvorhaben", SITE["name"]), ("Empfänger", t.get("recipient") or SITE["client"]), ("Absender", SITE["manager"]),
        ("Datum", dt.date.today().strftime("%d.%m.%Y")), ("Dokument-Nr.", doc["id"])]]


def _field_rows(doc, t):
    return [{"label": label + (" *" if req else ""), "value": doc["fields"][k]["value"] or "— (offen)"}
            for k, label, req, *_ in t["fields"]]


def _checklist(doc, t):
    miss = missing(doc)
    return [{"mark": "☐ fehlt" if k in miss else "☑", "label": label} for k, label, req, *_ in t["fields"] if req]


def _source_rows(doc, t):
    """Source appendix: one row per filled field, whatever its origin (AI evidence, user edit, chat answer)."""
    rows = []
    for k, label, *_ in t["fields"]:
        f = doc["fields"][k]
        if not f["value"]:
            continue
        src = f["source"] or {}
        kind = src.get("type") or ""
        kind_de, locator = SRC_DE.get(kind, kind or "unbekannt"), src.get("locator") or ""
        rows.append({"label": label, "evidence_id": src.get("evidence_id") or None, "kind": kind, "kind_de": kind_de, "locator": locator,
                     "where": locator if locator.startswith(kind_de) else f"{kind_de}, {locator}" if locator else kind_de,
                     "excerpt": (src.get("quote") or "")[:EXCERPT_MAX]})
    return rows


def _photo_entries(doc, tpl=None):
    """Attached photos with caption. With a template, `image` is an InlineImage of the annotated file (None if unreadable)."""
    from docxtpl import InlineImage
    photos = {p["id"]: p for p in load("photos", [])}
    out = []
    for i in doc["photos"]:
        p = photos.get(i)
        if not p:
            continue
        path = annotated(p)
        out.append({"id": i, "path": path, "caption": _photo_caption(p),
                    "image": InlineImage(tpl, str(path), width=Mm(PHOTO_WIDTH_MM)) if tpl is not None and path else None})
    return out


def build_context(doc, tpl=None) -> dict:
    """Everything a template (or the fallback writer) needs; plain data except photo images."""
    t = DOC_TYPES[doc["type"]]
    return {"title": t["title"], "basis": t["basis"], "draft": doc["status"] == "draft", "status": doc["status"],
            "header": _header_rows(doc, t), "rows": _field_rows(doc, t), "closing": t.get("closing") or "",
            "checklist": _checklist(doc, t),
            "checklist_note": "Hinweis: Nur formale Prüfung der Angaben, keine rechtliche Bewertung von Anspruch oder Höhe.",
            "photos": _photo_entries(doc, tpl), "sources": _source_rows(doc, t), "footer": _footer(doc),
            "signature": doc["type"] not in NO_SIGNATURE}


# ---------- Word ----------
def templates_dir() -> Path:
    d = Path(env("EXPORT_TEMPLATES_DIR", "templates"))
    return d if d.is_absolute() else ROOT / d


def _multiline(obj):
    """docxtpl needs Listing for values with line breaks (keeps the template styling)."""
    from docxtpl import Listing
    if isinstance(obj, str):
        return Listing(obj) if "\n" in obj else obj
    if isinstance(obj, list):
        return [_multiline(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _multiline(v) for k, v in obj.items()}
    return obj


def _render_template(doc, template: Path, out: Path):
    from docxtpl import DocxTemplate
    tpl = DocxTemplate(str(template))
    ctx = build_context(doc, tpl)
    tpl.render(_multiline(ctx), autoescape=True)
    tpl.save(out)


_WATERMARK = """<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:v="urn:schemas-microsoft-com:vml"
 xmlns:o="urn:schemas-microsoft-com:office:office"><w:pPr><w:pStyle w:val="Header"/></w:pPr><w:r><w:rPr><w:noProof/></w:rPr><w:pict>
<v:shapetype id="_x0000_t136" coordsize="21600,21600" o:spt="136" adj="10800" path="m@7,l@8,m@5,21600l@6,21600e"><v:formulas>
<v:f eqn="sum #0 0 10800"/><v:f eqn="prod #0 2 1"/><v:f eqn="sum 21600 0 @1"/><v:f eqn="sum 0 0 @2"/><v:f eqn="sum 21600 0 @3"/>
<v:f eqn="if @0 @3 0"/><v:f eqn="if @0 21600 @1"/><v:f eqn="if @0 0 @2"/><v:f eqn="if @0 @4 21600"/><v:f eqn="mid @5 @6"/>
<v:f eqn="mid @8 @5"/><v:f eqn="mid @7 @8"/><v:f eqn="mid @6 @7"/><v:f eqn="sum @6 0 @5"/></v:formulas>
<v:path textpathok="t" o:connecttype="custom" o:connectlocs="@9,0;@10,10800;@11,21600;@12,10800" o:connectangles="270,180,90,0"/>
<v:textpath on="t" fitshape="t"/><o:lock v:ext="edit" text="t" shapetype="t"/></v:shapetype>
<v:shape id="PowerPlusWaterMarkObject1" o:spid="_x0000_s2049" type="#_x0000_t136" style="position:absolute;margin-left:0;margin-top:0;width:430pt;height:140pt;rotation:315;z-index:-251658752;mso-position-horizontal:center;mso-position-horizontal-relative:margin;mso-position-vertical:center;mso-position-vertical-relative:margin"
 o:allowincell="f" fillcolor="#e8a98c" stroked="f"><v:fill opacity=".45"/><v:textpath style="font-family:&quot;Arial&quot;;font-size:1pt" string="ENTWURF"/></v:shape>
</w:pict></w:r></w:p>"""


def add_watermark(path: Path, text="ENTWURF"):
    """Diagonal Word watermark in every page header (LibreOffice renders it into the PDF)."""
    d = Document(str(path))
    for s in d.sections:
        s.header.is_linked_to_previous = False
        s.header._element.append(parse_xml(_WATERMARK.replace('string="ENTWURF"', f'string="{html.escape(text)}"')))
    d.save(str(path))


def _docx_fallback(doc, ctx, out: Path):
    """python-docx writer used when no template is available (same content as the templates)."""
    d = Document()
    st = d.styles["Normal"]
    st.font.name, st.font.size = "Arial", Pt(10.5)
    if ctx["draft"]:
        r = d.add_paragraph().add_run("ENTWURF")
        r.bold, r.font.color.rgb = True, RGBColor(0xC8, 0x50, 0x1E)
    d.add_heading(ctx["title"], 0)
    if ctx["basis"]:
        d.add_paragraph(ctx["basis"])
    hdr = d.add_table(rows=0, cols=2)
    hdr.style = "Light Grid Accent 1"
    for h in ctx["header"]:
        c = hdr.add_row().cells
        c[0].text, c[1].text = h["label"], h["value"]
    d.add_paragraph()
    tbl = d.add_table(rows=0, cols=2)
    tbl.style = "Table Grid"
    for r in ctx["rows"]:
        c = tbl.add_row().cells
        c[0].text, c[1].text = r["label"], r["value"]
        c[0].width, c[1].width = Cm(5), Cm(11)
    if ctx["closing"]:
        d.add_paragraph("\n" + ctx["closing"])
    d.add_heading("Formale Vollständigkeit", 2)
    for c in ctx["checklist"]:
        d.add_paragraph(f"{c['mark']}  {c['label']}")
    d.add_paragraph(ctx["checklist_note"]).runs[0].italic = True
    if ctx["photos"]:
        d.add_heading("Fotodokumentation", 2)
        for p in ctx["photos"]:
            if p["path"]:
                d.add_picture(str(p["path"]), width=Mm(PHOTO_WIDTH_MM))
            d.add_paragraph(p["caption"]).runs[0].font.size = Pt(8)
    d.add_heading("Nachweise je Feld", 2)
    for s in ctx["sources"]:
        p = d.add_paragraph(f"{s['label']}: {s['kind_de']}, {s['locator']}" + (f" [{s['evidence_id']}]" if s["evidence_id"] else "")
                            + f" – \"{s['excerpt']}\"")
        p.runs[0].font.size = Pt(8)
    d.add_paragraph()
    d.add_paragraph(ctx["footer"]).runs[0].italic = True
    if ctx["signature"]:
        d.add_paragraph("\n\n______________________________\nUnterschrift Bauleitung")
    d.save(out)


def docx(doc) -> Path:
    """Render the document to <data>/<type>_<id>.docx: template if present, python-docx fallback otherwise."""
    with llm_bridge.Timer("export_docx", doc["id"], document_type=doc["type"]):
        out = DATA / f"{doc['type']}_{doc['id']}.docx"
        template = templates_dir() / TEMPLATE_FOR.get(doc["type"], "notice.docx")
        try:
            if not template.is_file():
                raise FileNotFoundError(template)
            _render_template(doc, template, out)
        except Exception:      # missing or broken template: never fail the export
            _docx_fallback(doc, build_context(doc), out)
        if doc["status"] == "draft":
            add_watermark(out)
        return out


# ---------- PDF ----------
def find_soffice() -> str | None:
    """SOFFICE_BIN -> PATH -> /usr/bin/soffice -> macOS app bundle. None if LibreOffice is not installed."""
    for cand in (env("SOFFICE_BIN"), shutil.which("soffice"), *SOFFICE_PATHS):
        if cand and Path(cand).is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


def convert_to_pdf(docx_path: Path, outdir: Path, soffice: str) -> Path:
    cmd = [soffice, f"-env:UserInstallation={LO_PROFILE}", "--headless", "--convert-to", "pdf", "--outdir", str(outdir), str(docx_path)]
    try:
        with _soffice_lock:
            subprocess.run(cmd, check=True, capture_output=True, timeout=LO_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise PdfUnavailable(f"LibreOffice did not finish within {LO_TIMEOUT_S} s")
    except (subprocess.CalledProcessError, OSError) as e:
        raise PdfUnavailable(f"LibreOffice conversion failed: {e}")
    pdf_path = outdir / (docx_path.stem + ".pdf")
    if not pdf_path.is_file():
        raise PdfUnavailable("LibreOffice produced no PDF")
    return pdf_path


def pdf(doc) -> Path:
    """Render the .docx, convert it with headless LibreOffice and return <data>/<type>_<id>.pdf. Raises PdfUnavailable."""
    with llm_bridge.Timer("export_pdf", doc["id"], document_type=doc["type"]):
        soffice = find_soffice()
        if not soffice:
            raise PdfUnavailable("LibreOffice (soffice) is not installed")
        word = docx(doc)
        with tempfile.TemporaryDirectory(prefix="nachweis_pdf_") as tmp:
            made = convert_to_pdf(word, Path(tmp), soffice)
            out = DATA / f"{doc['type']}_{doc['id']}.pdf"
            shutil.move(str(made), out)
        return out


# ---------- template generation ----------
def _cell(row, i, text, width_cm=None, bold=False):
    c = row.cells[i]
    c.text = text
    if bold:
        c.paragraphs[0].runs[0].bold = True
    if width_cm:
        c.width = Cm(width_cm)


def _loop_table(d, var, cols, widths, style, header_labels=None):
    """Table with a docxtpl row loop `r in <var>`; `cols` = jinja expressions. Rows: [header,] for-tag, data, endfor-tag."""
    tbl = d.add_table(rows=0, cols=len(cols))
    tbl.style = style
    if header_labels:
        r = tbl.add_row()
        for i, h in enumerate(header_labels):
            _cell(r, i, h, widths[i], bold=True)
    for tag in ("{%tr for r in " + var + " %}", None, "{%tr endfor %}"):
        r = tbl.add_row()
        if tag is None:
            for i, expr in enumerate(cols):
                _cell(r, i, "{{ " + expr + " }}", widths[i])
        else:
            _cell(r, 0, tag, widths[0])
    return tbl


def _build_template(kind: str) -> Document:
    """kind: notice | nachtrag | tagesbericht. All three share the context of build_context(); they differ in layout details."""
    d = Document()
    st = d.styles["Normal"]
    st.font.name, st.font.size = "Arial", Pt(10.5)
    d.add_paragraph("{%p if draft %}")
    p = d.add_paragraph("ENTWURF")
    p.runs[0].bold, p.runs[0].font.color.rgb = True, RGBColor(0xC8, 0x50, 0x1E)
    d.add_paragraph("{%p endif %}")
    d.add_heading("{{ title }}", 0)
    d.add_paragraph("{{ basis }}")

    _loop_table(d, "header", ["r.label", "r.value"], [5, 11], "Light Grid Accent 1")
    d.add_paragraph()
    if kind != "notice":
        d.add_heading("Angaben zum Vorgang" if kind == "nachtrag" else "Angaben zum Berichtstag", 2)
    _loop_table(d, "rows", ["r.label", "r.value"], [5, 11], "Table Grid")
    d.add_paragraph("{%p if closing %}")
    d.add_paragraph("{{ closing }}")
    d.add_paragraph("{%p endif %}")
    d.add_heading("Formale Vollständigkeit", 2)
    d.add_paragraph("{%p for c in checklist %}")
    d.add_paragraph("{{ c.mark }}  {{ c.label }}")
    d.add_paragraph("{%p endfor %}")
    d.add_paragraph("{{ checklist_note }}").runs[0].italic = True
    d.add_paragraph("{%p if photos %}")
    d.add_heading("Fotodokumentation", 2)
    d.add_paragraph("{%p for p in photos %}")
    d.add_paragraph("{{ p.image }}")
    cap = d.add_paragraph("{{ p.caption }}")
    cap.runs[0].font.size = Pt(8)
    d.add_paragraph("{%p endfor %}")
    d.add_paragraph("{%p endif %}")
    d.add_heading("Quellenanhang – Nachweise je Feld", 2)
    tbl = _loop_table(d, "sources", ["r.label", "r.evidence_id or '–'", "r.where", "r.excerpt"], [3.2, 2.8, 4.5, 5.5], "Table Grid",
               ["Feld", "Beleg-ID", "Quelle, Fundstelle", "Auszug"])
    for row in tbl.rows:
        for c in row.cells:
            for r in c.paragraphs[0].runs:
                r.font.size = Pt(8)
    d.add_paragraph()
    d.add_paragraph("{{ footer }}").runs[0].italic = True
    if kind != "tagesbericht":
        d.add_paragraph("{%p if signature %}")
        d.add_paragraph("\n\n______________________________\nUnterschrift Bauleitung")
        d.add_paragraph("{%p endif %}")
    return d


def build_templates(dest: Path | None = None) -> list[Path]:
    """(Re)generate notice.docx, nachtrag.docx, tagesbericht.docx. Run: `python -c "from core import export; export.build_templates()"`."""
    dest = Path(dest) if dest else templates_dir()
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for kind in ("notice", "nachtrag", "tagesbericht"):
        p = dest / f"{kind}.docx"
        _build_template(kind).save(p)
        out.append(p)
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
