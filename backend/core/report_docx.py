"""Professional Word layout for every document type (the PDF is converted from this file, so both look the same).

Page 1: brand band, status badge, title, key facts, the document's fields.
Then:   site situation from live data (site plan with the document's location, 3D twin snapshot, plan vs actual chart,
        weather), photo documentation with AI detections, completeness check, signature, evidence appendix.
Content comes from export.build_context(); images from core.report_visuals. No value is invented here.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT  # noqa: F401  (kept for callers that switch orientation)
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .i18n import get_lang
from .store import SITE

FONT = "Calibri"            # Word: Calibri; LibreOffice/PDF: metric-compatible Carlito (bundled)
INK, MUT, ACC, OK, BAD = "1E2430", "6E7684", "FF7A00", "2EAD6B", "E5484D"
SOFT, LINE, BAND = "F4F5F8", "E3E6EB", "1E2430"


def _t(en, de):
    return de if get_lang() == "de" else en


# ---------------------------------------------------------------- low-level helpers
def _rgb(h):
    return RGBColor.from_string(h)


def _shade(cell, hex_fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), hex_fill)
    tcPr.append(shd)


def _borders(table, color=None, inside=False, size=4):
    """No borders by default; `color` draws a hairline outside (and inside rows if `inside`)."""
    tblPr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{edge}")
        on = color and (edge in ("top", "bottom", "left", "right") or (inside and edge == "insideH"))
        e.set(qn("w:val"), "single" if on else "nil")
        if on:
            e.set(qn("w:sz"), str(size)); e.set(qn("w:color"), color)
        b.append(e)
    tblPr.append(b)


def _cell_pad(table, top=90, left=140, bottom=90, right=140):
    tblPr = table._tbl.tblPr
    m = OxmlElement("w:tblCellMar")
    for k, v in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        e = OxmlElement(f"w:{k}"); e.set(qn("w:w"), str(v)); e.set(qn("w:type"), "dxa"); m.append(e)
    tblPr.append(m)


def _widths(table, cms):
    table.autofit = False
    for col, w in zip(table.columns, cms):                         # tblGrid: LibreOffice reads the grid, Word the cells
        col.width = Cm(w)
    for row in table.rows:
        for c, w in zip(row.cells, cms):
            c.width = Cm(w)


def _run(par, text, size=10, bold=False, color=INK, italic=False, caps=False, spacing=None):
    r = par.add_run(text)
    r.font.name, r.font.size, r.font.bold, r.font.italic = FONT, Pt(size), bold, italic
    r._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    r.font.color.rgb = _rgb(color)
    if caps:
        r.font.all_caps = True
    if spacing is not None:
        sp = OxmlElement("w:spacing"); sp.set(qn("w:val"), str(spacing)); r._element.rPr.append(sp)
    return r


def _p(container, text="", size=10, bold=False, color=INK, italic=False, align=None, before=0, after=4, caps=False, spacing=None):
    par = container.add_paragraph()
    pf = par.paragraph_format
    pf.space_before, pf.space_after, pf.line_spacing = Pt(before), Pt(after), 1.15
    if align:
        par.alignment = align
    if text:
        _run(par, text, size, bold, color, italic, caps, spacing)
    return par


def _cell_text(cell, text, size=10, bold=False, color=INK, italic=False, align=None, caps=False, spacing=None):
    par = cell.paragraphs[0]
    par.paragraph_format.space_after = Pt(0)
    par.paragraph_format.line_spacing = 1.12
    if align:
        par.alignment = align
    for i, line in enumerate(str(text).split("\n")):
        if i:
            par = cell.add_paragraph(); par.paragraph_format.space_after = Pt(0)
        _run(par, line, size, bold, color, italic, caps, spacing)
    return par


def _field(par, code):
    r = par.add_run()
    for kind, txt in (("begin", None), (None, code), ("end", None)):
        if kind:
            e = OxmlElement("w:fldChar"); e.set(qn("w:fldCharType"), kind)
        else:
            e = OxmlElement("w:instrText"); e.set(qn("xml:space"), "preserve"); e.text = txt
        r._element.append(e)
    r.font.name, r.font.size = FONT, Pt(8)
    r.font.color.rgb = _rgb(MUT)


def _section_title(doc, text, kicker=None):
    if kicker:
        _p(doc, kicker, 8, True, ACC, before=16, after=0, caps=True, spacing=30).paragraph_format.keep_with_next = True
    par = _p(doc, text, 14, True, INK, before=0 if kicker else 14, after=6)
    pPr = par._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr"); bottom = OxmlElement("w:bottom")
    for k, v in (("val", "single"), ("sz", "6"), ("space", "4"), ("color", LINE)):
        bottom.set(qn(f"w:{k}"), v)
    bdr.append(bottom); pPr.append(bdr)
    par.paragraph_format.keep_with_next = True
    return par


def _picture(container, path, width_cm, caption=None, center=True):
    """Image in the document body (always a new paragraph) or in a table cell (its first, still empty paragraph)."""
    is_cell = hasattr(container, "_tc")
    first = container.paragraphs[0] if is_cell else None
    par = first if is_cell and not first.text and not first.runs else container.add_paragraph()
    par.paragraph_format.space_after = Pt(2)
    par.paragraph_format.keep_with_next = bool(caption)
    if center:
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.add_run().add_picture(str(path), width=Cm(width_cm))
    if caption:
        _p(container, caption, 8, False, MUT, align=WD_ALIGN_PARAGRAPH.CENTER if center else None, after=10)


# ---------------------------------------------------------------- page frame
def _frame(doc, title, docno):
    s = doc.sections[0]
    s.page_height, s.page_width = Cm(29.7), Cm(21.0)
    s.left_margin = s.right_margin = Cm(2.0)
    s.top_margin, s.bottom_margin = Cm(2.4), Cm(2.0)
    s.header_distance, s.footer_distance = Cm(0.9), Cm(0.9)
    st = doc.styles["Normal"]
    st.font.name, st.font.size = FONT, Pt(10.5)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)

    h = s.header
    hp = h.paragraphs[0]
    hp.paragraph_format.space_after = Pt(0)
    _run(hp, "Bau", 10, True, INK); _run(hp, "Buddy", 10, True, ACC)
    _run(hp, "   ·   " + (SITE.get("name") or ""), 8, False, MUT)
    hp2 = h.add_paragraph(); hp2.paragraph_format.space_after = Pt(0)
    _run(hp2, f"{title}  ·  {_t('No.', 'Nr.')} {docno}", 8, False, MUT)
    pPr = hp2._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr"); bottom = OxmlElement("w:bottom")
    for k, v in (("val", "single"), ("sz", "4"), ("space", "6"), ("color", LINE)):
        bottom.set(qn(f"w:{k}"), v)
    bdr.append(bottom); pPr.append(bdr)

    f = s.footer
    fp = f.paragraphs[0]
    fp.paragraph_format.space_after = Pt(0)
    _run(fp, _t("Drafted with AI assistance · no legal advice · final review by the site manager", "Mit KI-Unterstützung entworfen · keine Rechtsberatung · finale Prüfung durch die Bauleitung"), 7.5, False, MUT)
    fp2 = f.add_paragraph(); fp2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _run(fp2, _t("Page ", "Seite "), 8, False, MUT); _field(fp2, "PAGE"); _run(fp2, _t(" of ", " von "), 8, False, MUT); _field(fp2, "NUMPAGES")


# ---------------------------------------------------------------- blocks
STATUS = {"draft": (_t("DRAFT", "ENTWURF"), "C8501E", "FDEBDD"), "checked": (_t("CHECKED", "GEPRÜFT"), "1E7A4C", "DDF5E8"),
          "sent": (_t("SENT", "VERSENDET"), "FFFFFF", INK)}


def _title_block(doc, ctx, docrec):
    lab, fg, bg = {"draft": (_t("DRAFT", "ENTWURF"), "B4461A", "FDE9DA"), "checked": (_t("CHECKED", "GEPRÜFT"), "1E7A4C", "DCF4E7"),
                   "sent": (_t("SENT", "VERSENDET"), "FFFFFF", INK)}.get(ctx["status"], ("", INK, SOFT))
    t = doc.add_table(rows=1, cols=2)
    _borders(t); _cell_pad(t, 0, 0, 0, 0); _widths(t, [13.5, 3.5])
    left, right = t.rows[0].cells
    _cell_text(left, ctx["basis"] or "", 8, True, ACC, caps=True, spacing=24)
    par = left.add_paragraph(); par.paragraph_format.space_after = Pt(0)
    par.paragraph_format.line_spacing = 1.0
    _run(par, ctx["title"], 26, True, INK)
    right.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    badge = right.add_table(rows=1, cols=1) if False else None  # noqa: F841 (nested tables render poorly in LibreOffice)
    bp = right.paragraphs[0]; bp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = _run(bp, f"  {lab}  ", 9, True, fg, spacing=30)
    rPr = r._element.get_or_add_rPr(); shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), bg); rPr.append(shd)
    _p(doc, "", after=6)


def _facts(doc, ctx, stats):
    hdr = {h["label"]: h["value"] for h in ctx["header"]}
    keys = list(hdr.items())[:5]
    cells = [(k, v or "–") for k, v in keys]
    cells.append((_t("Completeness", "Vollständigkeit"), f"{stats['filled']} / {stats['total']} {_t('fields', 'Felder')}"))
    t = doc.add_table(rows=2, cols=3)
    _borders(t); _cell_pad(t, 110, 160, 110, 160)
    for i, (k, v) in enumerate(cells[:6]):
        c = t.rows[i // 3].cells[i % 3]
        _shade(c, SOFT)
        _cell_text(c, k, 7, True, MUT, caps=True, spacing=20)
        par = c.add_paragraph(); par.paragraph_format.space_after = Pt(0)
        _run(par, str(v), 10, True, INK)
    _widths(t, [5.67, 5.67, 5.67])
    # thin white gutters between the cards
    tblPr = t._tbl.tblPr; sp = OxmlElement("w:tblCellSpacing"); sp.set(qn("w:w"), "40"); sp.set(qn("w:type"), "dxa"); tblPr.append(sp)
    _p(doc, "", after=2)


def _fields(doc, ctx):
    t = doc.add_table(rows=0, cols=2)
    _borders(t, LINE, inside=True); _cell_pad(t, 100, 160, 100, 160)
    for r in ctx["rows"]:
        row = t.add_row().cells
        _shade(row[0], SOFT)
        req = r["label"].endswith(" *")
        lab = r["label"][:-2] if req else r["label"]
        par = _cell_text(row[0], lab, 9, True, INK)
        if req:
            _run(par, " *", 9, True, ACC)
        open_ = r["value"] in (_t("— (open)", "— (offen)"), "— (open)", "— (offen)") or str(r["value"]).startswith("—")
        _cell_text(row[1], _t("open – please complete", "offen – bitte ergänzen") if open_ else r["value"], 10.5, False,
                   ACC if open_ else INK, italic=open_)
    _widths(t, [5.2, 11.8])


def _site_situation(doc, docrec, images):
    if not any(images.values()):
        return
    _section_title(doc, _t("Site situation", "Lage auf der Baustelle"), _t("Live data at export time", "Live-Daten zum Exportzeitpunkt"))
    now = dt.datetime.now().strftime("%d.%m.%Y %H:%M")
    if images.get("plan"):
        _picture(doc, images["plan"], 17, _t(f"Site plan generated from the site layout and geotagged photos · {now}. P = photo position, dots = AI detections.",
                                              f"Lageplan aus Baustellen-Layout und Fotos mit GPS · {now}. P = Fotostandort, Punkte = KI-Erkennungen."))
    if images.get("twin"):
        _picture(doc, images["twin"], 17, _t("Digital twin (3D), snapshot from the live view.", "Digitaler Zwilling (3D), Aufnahme aus der Live-Ansicht."))
    if images.get("progress"):
        _p(doc, _t("Plan vs actual", "Soll-Ist"), 10, True, INK, before=6, after=2).paragraph_format.keep_with_next = True
        _picture(doc, images["progress"], 17, _t("Actual quantity per activity against today's planned quantity (black line).",
                                                  "Ist-Menge je Vorgang gegen die heutige Soll-Menge (schwarze Linie)."))
    w = images.get("weather")
    if w:
        t = doc.add_table(rows=1, cols=4)
        _borders(t); _cell_pad(t, 90, 140, 90, 140)
        vals = [(_t("Weather", "Wetter"), w.get("text") or "–"), (_t("Temperature", "Temperatur"), f"{w.get('tmin', '–')} … {w.get('tmax', '–')} °C"),
                (_t("Rain", "Niederschlag"), f"{w.get('rain', '–')} mm"), (_t("Wind", "Wind"), f"{w.get('wind', '–')} km/h")]
        for c, (k, v) in zip(t.rows[0].cells, vals):
            _shade(c, SOFT)
            _cell_text(c, k, 7, True, MUT, caps=True, spacing=20)
            par = c.add_paragraph(); par.paragraph_format.space_after = Pt(0); _run(par, v, 10, True, INK)
        _widths(t, [4.25, 4.25, 4.25, 4.25])
        _p(doc, _t("Source: Open-Meteo forecast for the site coordinates.", "Quelle: Open-Meteo-Prognose für die Baustellenkoordinaten."), 7.5, False, MUT, after=4)


def _photos(doc, photos, labels):
    if not photos:
        return
    _section_title(doc, labels["photodoc"], _t("Evidence", "Belege"))
    t = doc.add_table(rows=0, cols=2)
    _borders(t); _cell_pad(t, 60, 80, 120, 80)
    for i in range(0, len(photos), 2):
        row = t.add_row().cells
        for c, ph in zip(row, photos[i:i + 2]):
            if ph.get("path"):
                _picture(c, ph["path"], 8.1)
            _cell_text(c, "", 1) if False else None
            par = c.add_paragraph(); par.paragraph_format.space_after = Pt(2)
            _run(par, ph.get("num", ""), 8, True, ACC); _run(par, "  " + (ph.get("title") or ""), 8, True, INK)
            par2 = c.add_paragraph(); par2.paragraph_format.space_after = Pt(0)
            _run(par2, ph.get("caption", ""), 7, False, MUT)
    _widths(t, [8.5, 8.5])


def _checklist(doc, ctx):
    _section_title(doc, ctx["L"]["completeness"], _t("Formal check", "Formale Prüfung"))
    items = ctx["checklist"]
    t = doc.add_table(rows=(len(items) + 1) // 2, cols=2)
    _borders(t); _cell_pad(t, 50, 100, 50, 100)
    for i, c in enumerate(items):
        cell = t.rows[i // 2].cells[i % 2]
        ok = c["mark"] == "☑"
        par = cell.paragraphs[0]; par.paragraph_format.space_after = Pt(0)
        _run(par, "✓  " if ok else "!  ", 10, True, OK if ok else ACC)
        _run(par, c["label"], 9, False, INK if ok else ACC)
    _widths(t, [8.5, 8.5])
    _p(doc, ctx["checklist_note"], 7.5, False, MUT, italic=True, before=4)


def _signature(doc, ctx):
    if ctx.get("closing"):
        _p(doc, ctx["closing"], 10, before=10, after=6)
    _p(doc, ctx["footer"], 8, False, MUT, italic=True, before=6, after=14)
    if not ctx.get("signature"):
        return
    t = doc.add_table(rows=2, cols=2)
    _borders(t); _cell_pad(t, 0, 0, 0, 300)
    for i, lab in enumerate((_t("Place, date", "Ort, Datum"), ctx["L"]["signature"])):
        top, bot = t.rows[0].cells[i], t.rows[1].cells[i]
        _cell_text(top, "\n", 10)
        tcPr = top._tc.get_or_add_tcPr(); b = OxmlElement("w:tcBorders"); e = OxmlElement("w:bottom")
        e.set(qn("w:val"), "single"); e.set(qn("w:sz"), "6"); e.set(qn("w:color"), INK); b.append(e); tcPr.append(b)
        _cell_text(bot, lab, 7.5, False, MUT)
    _widths(t, [7.0, 7.0])


def _appendix(doc, ctx):
    if not ctx["sources"]:
        return
    par = doc.add_paragraph(); par.add_run().add_break(WD_BREAK.PAGE)
    _section_title(doc, ctx["L"]["sources_title"], _t("Appendix", "Anhang"))
    _p(doc, _t("Every value in this document and where it comes from.", "Jeder Wert in diesem Dokument und seine Herkunft."), 8.5, False, MUT, after=6)
    t = doc.add_table(rows=1, cols=4)
    _borders(t, LINE, inside=True); _cell_pad(t, 70, 110, 70, 110)
    for c, h in zip(t.rows[0].cells, (ctx["L"]["col_field"], ctx["L"]["col_id"], ctx["L"]["col_where"], ctx["L"]["col_excerpt"])):
        _shade(c, BAND); _cell_text(c, h, 7.5, True, "FFFFFF", caps=True, spacing=16)
    tr = t.rows[0]._tr; trPr = tr.get_or_add_trPr(); th = OxmlElement("w:tblHeader"); th.set(qn("w:val"), "true"); trPr.append(th)
    for i, s in enumerate(ctx["sources"]):
        row = t.add_row().cells
        if i % 2:
            for c in row:
                _shade(c, "FAFBFC")
        _cell_text(row[0], s["label"], 8, True)
        _cell_text(row[1], s["evidence_id"] or "–", 7, False, MUT)
        _cell_text(row[2], s["where"], 8)
        _cell_text(row[3], (f"“{s['excerpt']}”" if s["excerpt"] else "–"), 7.5, False, MUT, italic=bool(s["excerpt"]))
    _widths(t, [3.4, 3.0, 4.4, 6.2])


# ---------------------------------------------------------------- entry
def render(docrec: dict, ctx: dict, out: Path) -> Path:
    from . import plan, report_visuals as rv, site_twin
    from .store import load
    doc = Document()
    _frame(doc, ctx["title"], docrec["id"])
    filled = sum(1 for r in ctx["rows"] if not str(r["value"]).startswith("—"))
    _title_block(doc, ctx, docrec)
    _facts(doc, ctx, {"filled": filled, "total": len(ctx["rows"])})
    _fields(doc, ctx)

    images = {}
    try:
        images["plan"] = rv.site_plan(docrec)
    except Exception:
        images["plan"] = None
    images["twin"] = rv.twin_snapshot()
    try:
        images["progress"] = rv.progress_chart(f"progress_{docrec['id']}.png")
    except Exception:
        images["progress"] = None
    try:
        images["weather"] = plan.status(with_weather=True).get("weather_today")
    except Exception:
        images["weather"] = None
    _site_situation(doc, docrec, images)

    # photos: same P-numbers as on the plan
    tw_photos = []
    try:
        tw_photos = site_twin.twin()["photos"]
    except Exception:
        pass
    num = {p["id"]: f"P{i}" for i, p in enumerate(rv.photo_order(tw_photos), 1)}
    recs = {p["id"]: p for p in load("photos", [])}
    photos = []
    for pid in docrec.get("photos") or []:
        p = recs.get(pid)
        if not p:
            continue
        dets = ", ".join(f"{b['class'].replace('_', ' ')} {b['confidence']:.0%}" for b in p.get("detections") or [])
        photos.append({"path": rv.photo(p), "num": num.get(pid, ""), "title": (p.get("taken_at") or "").replace("T", " ")[:16],
                       "caption": " · ".join(x for x in (p.get("original_name"), dets, f"{p['lat']:.5f}, {p['lon']:.5f}" if p.get("lat") else "") if x)})
    _photos(doc, photos, ctx["L"])
    _checklist(doc, ctx)
    _signature(doc, ctx)
    _appendix(doc, ctx)
    doc.save(out)
    return out


# ---------------------------------------------------------------- incident / site inspection report (AI Manager)
SEV = {"high": ("E5484D", "FDE4E5"), "medium": ("C77700", "FDF0D9"), "low": ("5B6B7A", "E9EDF1")}


def render_site_report(*, out: Path, rid: str, title: str, scope: str, lang: str, as_of: str, summary: list[str],
                       incidents: list[dict], zones: dict, prog_rows: list[dict], alerts: list[dict], photos: list[dict],
                       snapshot: Path | None, detector: str, note: str | None = None) -> Path:
    """Word version of the AI Manager report (same facts as the HTML report, designed like the notices)."""
    from .i18n import set_lang
    prev = get_lang()
    set_lang(lang)                       # page frame, badge and footer follow the report's language
    try:
        return _site_report(out=out, rid=rid, title=title, scope=scope, lang=lang, as_of=as_of, summary=summary, incidents=incidents,
                            zones=zones, prog_rows=prog_rows, alerts=alerts, photos=photos, snapshot=snapshot, detector=detector, note=note)
    finally:
        set_lang(prev)


def _site_report(*, out, rid, title, scope, lang, as_of, summary, incidents, zones, prog_rows, alerts, photos, snapshot, detector, note):
    from . import plan, report_visuals as rv  # noqa: F401
    from .store import load
    L = lambda en, de: de if lang == "de" else en  # noqa: E731
    doc = Document()
    _frame(doc, title, rid)
    ctxlike = {"basis": L("AI Site Manager · evidence-based", "KI-Bauleiter · belegbasiert"), "title": title, "status": "draft"}
    _title_block(doc, ctxlike, {"id": rid})

    hi = sum(1 for i in incidents if i["severity"] == "high")
    t = doc.add_table(rows=1, cols=4)
    _borders(t); _cell_pad(t, 110, 160, 110, 160)
    facts = [(L("Project", "Projekt"), SITE.get("name") or "–"), (L("Reporting day", "Berichtstag"), as_of),
             (L("Findings", "Befunde"), f"{len(incidents)} · {hi} {L('high', 'hoch')}"), (L("Report no.", "Bericht-Nr."), rid)]
    for c, (k, v) in zip(t.rows[0].cells, facts):
        _shade(c, SOFT); _cell_text(c, k, 7, True, MUT, caps=True, spacing=20)
        par = c.add_paragraph(); par.paragraph_format.space_after = Pt(0); _run(par, str(v), 10, True, INK)
    _widths(t, [6.0, 3.4, 3.8, 3.8])

    _section_title(doc, L("Summary", "Zusammenfassung"))
    for s in summary:
        par = _p(doc, "", after=2); _run(par, "•  ", 10, True, ACC); _run(par, s, 10.5)
    _p(doc, L("Assembled from the verified data in this report; no free model text.", "Aus den belegten Daten dieses Berichts zusammengestellt, kein freier KI-Text."), 8, False, MUT, italic=True, before=2)

    # incidents as cards
    _section_title(doc, L("Safety findings", "Sicherheitsbefunde"), L("Verified observations", "Belegte Beobachtungen"))
    if not incidents:
        _p(doc, L("No open findings from the rule checks.", "Keine offenen Befunde aus der Regelprüfung."), 10)
    for i in incidents:
        fg, bg = SEV.get(i["severity"], SEV["low"])
        card = doc.add_table(rows=1, cols=1)
        _borders(card, LINE); _cell_pad(card, 140, 200, 140, 200)
        c = card.rows[0].cells[0]
        par = c.paragraphs[0]; par.paragraph_format.space_after = Pt(2)
        r = _run(par, f"  {L({'high': 'HIGH', 'medium': 'MEDIUM', 'low': 'LOW'}[i['severity']], {'high': 'HOCH', 'medium': 'MITTEL', 'low': 'NIEDRIG'}[i['severity']])}  ", 8, True, fg, spacing=24)
        rPr = r._element.get_or_add_rPr(); shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:fill"), bg); rPr.append(shd)
        _run(par, "   " + i.get(f"title_{lang}", i.get("title_en", "")), 12, True, INK)
        rows = [(L("What", "Was"), i.get(f"detail_{lang}", i.get("detail_en", ""))),
                (L("Where", "Wo"), zones.get(i.get("zone"), L("not placed on the plan", "nicht im Plan verortet"))),
                (L("When", "Wann"), (i.get("taken_at") or i.get("created_at") or "").replace("T", " ")[:16]),
                (L("Source", "Quelle"), L("reported by the site team", "vom Bauteam gemeldet") if i.get("source") == "user" else f"{L('rule', 'Regel')} {i.get('rule')} · {detector}")]
        if i.get("objects"):
            rows.insert(1, (L("Objects", "Objekte"), ", ".join(f"{o['class'].replace('_', ' ')} {o['confidence']:.0%}" for o in i["objects"])))
        for k, v in rows:
            par = c.add_paragraph(); par.paragraph_format.space_after = Pt(1)
            _run(par, f"{k}:  ", 9, True, MUT); _run(par, v, 9.5)
        par = c.add_paragraph(); par.paragraph_format.space_before = Pt(4); par.paragraph_format.space_after = Pt(0)
        _run(par, L("Recommendation (AI, not verified):  ", "Empfehlung (KI, nicht geprüft):  "), 9, True, "2F6DB5")
        _run(par, i.get(f"recommendation_{lang}", i.get("recommendation_en", "")), 9.5)
        par = c.add_paragraph(); par.paragraph_format.space_after = Pt(0)
        _run(par, L("Evidence: ", "Beleg: ") + ", ".join(i.get("evidence") or []), 7.5, False, MUT)
        _p(doc, "", after=4)

    # live images
    _section_title(doc, L("Site situation", "Lage auf der Baustelle"), L("Live data at export time", "Live-Daten zum Exportzeitpunkt"))
    first = incidents[0] if scope == "incident" and incidents else None
    pseudo = {"id": f"rep_{rid}", "photos": [first["photo"]] if first and first.get("photo") else [],
              "fields": {"location": {"value": zones.get(first.get("zone"), "") if first else ""}}}
    try:
        plan_img = rv.site_plan(pseudo, name=f"plan_rep_{rid}.png")
    except Exception:
        plan_img = None
    if plan_img:
        _picture(doc, plan_img, 17, L("Site plan from the live layout and geotagged photos. Orange ring = location of the finding.",
                                       "Lageplan aus Live-Layout und Fotos mit GPS. Oranger Ring = Ort des Befunds."))
    if snapshot:
        _picture(doc, snapshot, 17, L("Digital twin (3D), snapshot from the live view.", "Digitaler Zwilling (3D), Aufnahme aus der Live-Ansicht."))
    if scope == "site":
        try:
            chart = rv.progress_chart(f"progress_rep_{rid}.png")
        except Exception:
            chart = None
        if chart:
            _p(doc, L("Plan vs actual", "Soll-Ist"), 10.5, True, before=6, after=2).paragraph_format.keep_with_next = True
            _picture(doc, chart, 17, L("Actual quantity per activity against today's planned quantity (black line).",
                                       "Ist-Menge je Vorgang gegen die heutige Soll-Menge (schwarze Linie)."))
        if alerts:
            _p(doc, L("Early warnings", "Frühwarnungen"), 10.5, True, before=6, after=2)
            for a in alerts:
                par = _p(doc, "", after=2); _run(par, "!  ", 10, True, ACC); _run(par, a["text"], 9.5)

    # photos
    recs = {p["id"]: p for p in load("photos", [])}
    tw_ids = [p["id"] for p in photos]
    ph = []
    for p in photos:
        rec = recs.get(p["id"]) or p
        dets = ", ".join(f"{b['class'].replace('_', ' ')} {b['confidence']:.0%}" for b in rec.get("detections") or [])
        ph.append({"path": rv.photo(rec), "num": "", "title": (rec.get("taken_at") or "").replace("T", " ")[:16] + "  ·  " + zones.get(p.get("zone"), ""),
                   "caption": " · ".join(x for x in (rec.get("original_name"), dets, f"photo:{p['id']}") if x)})
    ctx_only = scope == "incident" and incidents and not incidents[0].get("photo")
    _photos(doc, ph, {"photodoc": L("Photos from this zone (context)", "Fotos aus dieser Zone (Kontext)") if ctx_only else L("Photo evidence", "Fotobelege")})
    if note:
        _section_title(doc, L("Notes", "Hinweise")); _p(doc, note, 10)
    _p(doc, L("DRAFT – created with AI assistance. Every finding cites its evidence. Recommendations are suggestions. No legal advice.",
              "ENTWURF – mit KI-Unterstützung erstellt. Jeder Befund nennt seinen Beleg. Empfehlungen sind Vorschläge. Keine Rechtsberatung."),
       8, False, MUT, italic=True, before=12)
    del tw_ids
    doc.save(out)
    return out
