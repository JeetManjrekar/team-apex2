"""Generate the German sample upload set for BW 12 Mühlbach (fictional) into backend/data/demo/upload_samples/.

Scenario (consistent with data/demo): Bauvertrag Nr. 2026-117 (VOB/B). The Baugrundgutachten and the LV only
foresee Sand/Kies (Homogenbereich B1) for the Bohrpfähle. On 17.11.2026 Pfahl 7 (P07, Widerlager 1) hits Fels
(Kalkstein) at 4,0 m -> Behinderungs-/Mehrvergütungsanzeige, Nachtrag.

Needs: reportlab, openpyxl (not in requirements.txt; dev-only), soffice (recalculates the xlsx so cached values exist).
Run:   python backend/scripts/generate_upload_samples.py
No images are generated. These files are never loaded automatically; upload them manually in the app.
"""
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(__file__).resolve().parents[1] / "data" / "demo" / "upload_samples"
TZ = ZoneInfo("Europe/Berlin")
FIKTIV = "Fiktives Projekt – alle Namen, Daten und Werte sind erfunden."


def dt(day: int, hh: int, mm_: int) -> datetime:
    return datetime(2026, 11, day, hh, mm_, tzinfo=TZ)


# ------------------------------------------------------------------ Baugrundgutachten (PDF)
def gutachten() -> None:
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["BodyText"], fontName="Helvetica", fontSize=10, leading=14, spaceAfter=6)
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=14, spaceBefore=10, spaceAfter=8)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=11, spaceBefore=8, spaceAfter=4)
    title = ParagraphStyle("t", parent=h1, fontSize=22, leading=28, spaceAfter=14)
    small = ParagraphStyle("s", parent=body, fontSize=8.5, leading=11)

    def tbl(rows, widths, head=True):
        t = Table([[Paragraph(str(c), small) for c in r] for r in rows], colWidths=[w * mm for w in widths], repeatRows=1 if head else 0)
        st = [("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]
        if head:
            st.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")))
        t.setStyle(TableStyle(st))
        return t

    def footer(c, d):
        c.saveState(); c.setFont("Helvetica", 8)
        c.drawString(20 * mm, 12 * mm, "Geo-Süd Ingenieure GmbH (fiktiv) · Gutachten Nr. 2026-0481 · Baugrundgutachten BW 12 Mühlbach")
        c.drawRightString(190 * mm, 12 * mm, f"Seite {d.page}")
        c.restoreState()

    s = []
    s += [Spacer(1, 40 * mm), Paragraph("Baugrundgutachten", title),
          Paragraph("Ersatzneubau Straßenbrücke BW 12 über den Mühlbach", h1),
          Paragraph("Geotechnischer Bericht nach DIN 4020 / DIN EN 1997-2 mit Homogenbereichen nach DIN 18301", body), Spacer(1, 10 * mm),
          tbl([["Gutachten-Nr.", "2026-0481"], ["Auftraggeber", "Staatliches Bauamt (fiktiv)"],
               ["Bearbeiter", "Dr.-Ing. Petra Nowak, Geo-Süd Ingenieure GmbH (fiktiv)"],
               ["Datum", "28.08.2026"], ["Umfang", "Textteil, Anlagen 1–2 (Schichtenverzeichnisse, Kennwerte)"]], [45, 120], head=False),
          Spacer(1, 12 * mm), Paragraph(FIKTIV, small), PageBreak()]

    s += [Paragraph("Inhaltsverzeichnis", h1)]
    for line in ["1 Veranlassung und Aufgabenstellung", "2 Unterlagen und Erkundung", "3 Baugrundaufbau, allgemein",
                 "4 Widerlager 1 und Widerlager 2", "5 Grundwasser", "6 Homogenbereiche und Bodenkennwerte",
                 "7 Gründungsempfehlung Bohrpfähle", "8 Hinweise zur Bauausführung, Restrisiko",
                 "Anlage 1 Schichtenverzeichnisse BK 1 bis BK 4", "Anlage 2 Kennwerte"]:
        s.append(Paragraph(line, body))
    s.append(PageBreak())

    s += [Paragraph("1 Veranlassung und Aufgabenstellung", h1),
          Paragraph("Das Staatliche Bauamt plant den Ersatzneubau der Straßenbrücke BW 12 über den Mühlbach. Die Brücke wird "
                    "auf Bohrpfählen (Durchmesser 0,9 m, Länge 12,0 m) gegründet. Die Geo-Süd Ingenieure GmbH wurde beauftragt, "
                    "den Baugrund zu erkunden, zu beschreiben und Gründungsempfehlungen zu geben.", body),
          Paragraph("2 Unterlagen und Erkundung", h1),
          Paragraph("Zur Erkundung wurden im Juli 2026 vier Kernbohrungen (BK 1 bis BK 4) mit Endtiefen von 9,0 m bis 9,5 m unter GOK "
                    "abgeteuft. Die Bohrungen wurden nach DIN EN ISO 22475-1 aufgenommen und bodenmechanisch angesprochen. "
                    "Ergänzend wurden zwei Rammsondierungen (DPH 1, DPH 2) ausgeführt.", body),
          tbl([["Aufschluss", "Lage", "Endtiefe [m u. GOK]", "Bemerkung"],
               ["BK 1", "Widerlager 1 (West), Achse W1-links", "9,0", "Fels nicht angetroffen"],
               ["BK 2", "Widerlager 1 (West), Achse W1-rechts", "9,5", "Fels nicht angetroffen"],
               ["BK 3", "Widerlager 2 (Ost), Achse W2-links", "9,0", "Fels nicht angetroffen"],
               ["BK 4", "Widerlager 2 (Ost), Achse W2-rechts", "9,0", "Fels nicht angetroffen"],
               ["DPH 1 / DPH 2", "Widerlager 1 / Widerlager 2", "8,0 / 8,0", "Schlagzahlen steigen mit der Tiefe"]],
              [28, 62, 32, 48]),
          Spacer(1, 4 * mm),
          Paragraph("Die Pfahlsohle der Bohrpfähle liegt bei 12,0 m unter GOK und damit unterhalb der Endtiefe der Aufschlüsse. "
                    "Der Untergrund unterhalb von 9,0 m wurde nicht direkt erkundet.", body), PageBreak()]

    s += [Paragraph("3 Baugrundaufbau, allgemein", h1),
          Paragraph("Im Bereich des Ersatzneubaus wurden vier Kernbohrungen (BK 1 bis BK 4) abgeteuft. Unter einer geringmächtigen "
                    "Auffüllung (bis ca. 0,5 m) folgen quartäre Flussablagerungen des Mühlbachs.", body),
          Paragraph("Der Untergrund ist im Bereich der Widerlager überwiegend nichtbindig (Sand, Kies). Die Lagerungsdichte nimmt mit der "
                    "Tiefe zu. BK 1 und BK 2 liegen im Bereich des Widerlagers 1 (West), BK 3 und BK 4 im Bereich des Widerlagers 2 (Ost).", body),
          Paragraph("Geologisch liegt das Gebiet im Randbereich einer Flussterrasse. Der tiefere Untergrund wird regional von verkarstetem "
                    "Kalkstein gebildet; dessen Oberfläche wurde in den Bohrungen BK 1 bis BK 4 bis zur jeweiligen Endtiefe nicht erreicht.", body),
          PageBreak()]

    s += [Paragraph("4 Widerlager 1 und Widerlager 2", h1),
          Paragraph("<b>Widerlager 1, Bohrungen BK 1 und BK 2:</b> Sand und Kies, mitteldicht bis dicht gelagert, bis mindestens 9,0 m unter GOK; "
                    "Fels nicht erkundet.", body),
          Paragraph("Für die Bohrpfähle (Durchmesser 0,9 m, Länge 12 m) ist im Bereich des Widerlagers 1 mit normalem Bohrfortschritt in "
                    "nichtbindigem Boden zu rechnen.", body),
          Paragraph("<b>Widerlager 2, Bohrungen BK 3 und BK 4:</b> Sand und Kies, mitteldicht gelagert, bis ca. 8,0 m unter GOK; darunter steifer Schluff.", body),
          Paragraph("Hinweis: Zwischen den Bohrungen sind Abweichungen der Schichtgrenzen nicht auszuschließen.", body),
          Paragraph("Die Pfahlachsen P01 bis P08 liegen auf einer Linie zwischen BK 1 und BK 2 (Achsabstand der Bohrungen ca. 14 m). "
                    "Zwischen den beiden Bohrungen wurde die Schichtgrenze nicht gesondert aufgeschlossen.", body), PageBreak()]

    s += [Paragraph("5 Grundwasser", h1),
          Paragraph("In allen vier Bohrungen wurde Grundwasser zwischen 3,2 m und 3,6 m unter GOK angetroffen (Stand Erkundung). "
                    "Für die Bauzeit ist eine offene Wasserhaltung in den Baugruben vorzusehen. Der Wasserstand im Mühlbach schwankt jahreszeitlich.", body),
          Paragraph("Die Bohrpfähle sind unter Wasserauflast, z. B. mit Stützflüssigkeit oder Verrohrung, herzustellen. "
                    "Betonieren im Kontraktorverfahren.", body),
          Paragraph("6 Homogenbereiche und Bodenkennwerte", h1),
          Paragraph("Für Bohrarbeiten (DIN 18301) werden folgende Homogenbereiche gebildet. <b>Ein Homogenbereich Fels ist nicht gebildet, "
                    "da Fels in den Aufschlüssen nicht angetroffen wurde.</b>", body),
          tbl([["Homogenbereich", "Boden / Beschreibung", "Tiefe [m u. GOK]", "Lagerung", "Wichte γ [kN/m³]", "Reibungswinkel φ' [°]"],
               ["B0", "Auffüllung, sandig-kiesig", "0,0 – 0,5", "locker", "18", "30"],
               ["B1", "Sand, Kies (quartäre Flussablagerung), nichtbindig", "0,5 – 9,0+", "mitteldicht bis dicht", "19 – 21", "32,5 – 37,5"],
               ["B2", "Schluff, steif (nur Widerlager 2)", "ab ca. 8,0", "steif", "20", "27,5"]],
              [26, 54, 24, 28, 22, 24]), PageBreak()]

    s += [Paragraph("7 Gründungsempfehlung Bohrpfähle", h1),
          Paragraph("Die Bohrpfähle (D = 0,9 m, L = 12,0 m) werden im Homogenbereich B1 hergestellt. Die charakteristische Mantelreibung und der "
                    "Spitzenwiderstand sind Anlage 2 zu entnehmen. Die Bohrleistung in B1 liegt erfahrungsgemäß bei etwa 4 Stunden je Pfahl.", body),
          Paragraph("Bemessungsrelevante Setzungen sind bei einer Gründung im Homogenbereich B1 gering.", body),
          Paragraph("8 Hinweise zur Bauausführung, Restrisiko", h1),
          Paragraph("Die Aufschlüsse sind punktförmig. Zwischen den Aufschlüssen sowie unterhalb der Endtiefe kann der Baugrund von den "
                    "dargestellten Verhältnissen abweichen (Baugrundrisiko, vgl. DIN 4020). Bei Abweichungen vom beschriebenen Baugrund, "
                    "insbesondere beim Antreffen von Fels, Findlingen oder Hindernissen, ist der Baugrundgutachter unverzüglich zu verständigen "
                    "und der Auftraggeber zu informieren.", body),
          Paragraph("Die Baugrundverhältnisse sind während der Herstellung der Pfähle durch Bohrprotokolle zu dokumentieren.", body),
          PageBreak()]

    s += [Paragraph("Anlage 1 – Schichtenverzeichnisse", h1)]
    for bk, rows in {
        "BK 1 (Widerlager 1, Endtiefe 9,0 m)": [["0,0", "0,5", "Auffüllung, sandig-kiesig", "B0"], ["0,5", "3,2", "Sand, kiesig, mitteldicht", "B1"], ["3,2", "9,0", "Kies, sandig, dicht (ab 3,4 m unter Wasser)", "B1"]],
        "BK 2 (Widerlager 1, Endtiefe 9,5 m)": [["0,0", "0,5", "Auffüllung, sandig-kiesig", "B0"], ["0,5", "3,0", "Sand, kiesig, mitteldicht", "B1"], ["3,0", "9,5", "Kies, sandig, dicht", "B1"]],
        "BK 3 (Widerlager 2, Endtiefe 9,0 m)": [["0,0", "0,4", "Auffüllung", "B0"], ["0,4", "8,0", "Sand, Kies, mitteldicht", "B1"], ["8,0", "9,0", "Schluff, steif", "B2"]],
        "BK 4 (Widerlager 2, Endtiefe 9,0 m)": [["0,0", "0,5", "Auffüllung", "B0"], ["0,5", "8,1", "Sand, Kies, mitteldicht", "B1"], ["8,1", "9,0", "Schluff, steif", "B2"]],
    }.items():
        s += [Paragraph(bk, h2), tbl([["von [m]", "bis [m]", "Schichtbeschreibung", "Homogenbereich"]] + rows, [22, 22, 90, 36])]
    s.append(PageBreak())

    s += [Paragraph("Anlage 2 – Kennwerte", h1),
          tbl([["Kennwert", "B1 (Sand/Kies)", "B2 (Schluff)"],
               ["Charakt. Mantelreibung qs,k [kN/m²]", "60 – 110", "40"],
               ["Charakt. Spitzenwiderstand qb,k [kN/m²]", "3 000 (bei s = 0,1 D)", "–"],
               ["Steifemodul Es [MN/m²]", "60 – 120", "8"],
               ["Durchlässigkeit kf [m/s]", "1·10⁻³ bis 1·10⁻⁴", "1·10⁻⁷"],
               ["Bodenklasse (alt) / Lösbarkeit", "nichtbindig, rammbar/bohrbar", "bindig, bohrbar"]], [70, 55, 45]),
          Spacer(1, 6 * mm), Paragraph(FIKTIV, small)]

    SimpleDocTemplate(str(OUT / "baugrundgutachten_BW12.pdf"), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                      topMargin=20 * mm, bottomMargin=20 * mm, title="Baugrundgutachten BW 12 Mühlbach (fiktiv)",
                      author="Geo-Süd Ingenieure GmbH (fiktiv)").build(s, onFirstPage=footer, onLaterPages=footer)


# ------------------------------------------------------------------ Leistungsverzeichnis (XLSX)
LV = [  # OZ, Kurztext, Menge, Einheit, EP, Homogenbereich / Bemerkung
    ("01", "Baustelleneinrichtung", None, None, None, ""),
    ("01.01.0010", "Baustelleneinrichtung vorhalten, einrichten und räumen", 1, "psch", 38500.00, ""),
    ("01.01.0020", "Wasserhaltung offen, Baugruben W1, W2, A1, A2", 1, "psch", 21800.00, "GW 3,2–3,6 m u. GOK (Gutachten Kap. 5)"),
    ("02", "Erdarbeiten", None, None, None, ""),
    ("02.01.0010", "Aushub Baugrube Widerlager 1, Boden B0/B1", 420, "m³", 14.80, "Homogenbereich B0/B1"),
    ("02.01.0020", "Aushub Baugrube Widerlager 2, Boden B0/B1/B2", 410, "m³", 15.20, "Homogenbereich B0/B1/B2"),
    ("02.01.0030", "Aushub Baugruben Achse 1 und 2", 520, "m³", 14.80, "Homogenbereich B0/B1"),
    ("03", "Bohrpfahlgründung", None, None, None, ""),
    ("03.02.0010", "Bohrpfahl D = 0,90 m herstellen, Widerlager 1 und Achsen 1/2, in Boden B1, Länge 12,0 m (16 Stück, 192 m)", 192, "m", 168.00, "Homogenbereich B1 (Sand/Kies); Fels nicht Bestandteil"),
    ("03.02.0020", "Bohrpfahl D = 0,90 m herstellen, Widerlager 2, in Boden B1/B2, Länge 12,0 m (8 Stück, 96 m)", 96, "m", 172.00, "Homogenbereich B1/B2"),
    ("03.02.0030", "Bewehrungskorb Bohrpfahl liefern und einbauen", 24, "Stk", 1450.00, ""),
    ("03.02.0040", "Beton C30/37 für Bohrpfähle, Kontraktorverfahren", 366, "m³", 142.00, ""),
    ("03.02.0050", "Bohrgerät auf- und abbauen, Umsetzen je Pfahl", 24, "Stk", 310.00, ""),
    ("03.02.0900", "Bedarfsposition (nicht beauftragt): Mehrleistung Bohren in Fels, Homogenbereich nicht gebildet – Beauftragung nur nach schriftlicher Anordnung des AG", 0, "m", None, "Eventualposition, ohne Einheitspreis; Preis nach Nachtrag (§ 2 Abs. 6 VOB/B)"),
    ("04", "Stahlbeton Unterbau", None, None, None, ""),
    ("04.01.0010", "Beton C30/37 Widerlager 1, einschl. Schalung", 86, "m³", 395.00, ""),
    ("04.01.0020", "Beton C30/37 Widerlager 2, einschl. Schalung", 86, "m³", 395.00, ""),
    ("04.01.0030", "Beton C30/37 Achse 1 und 2 Pfahlkopfbalken, einschl. Schalung", 64, "m³", 410.00, ""),
    ("04.01.0040", "Betonstahl BSt 500 S liefern, schneiden, biegen, verlegen", 38.0, "t", 1620.00, ""),
    ("04.01.0050", "Aussparung DN 100 in Flügelwand W2 herstellen", 1, "Stk", 240.00, "Position nachträglich angeordnet (Schreiben 16.11.2026)"),
]

FILL = PatternFill("solid", fgColor="D9D9D9")


def lv_xlsx() -> None:
    wb = Workbook()
    ws = wb.active; ws.title = "Leistungsverzeichnis"
    ws.append(["Bauvertrag Nr. 2026-117 · Leistungsverzeichnis · BW 12 Mühlbach (fiktiv)"]); ws["A1"].font = Font(bold=True, size=13)
    ws.append(["Bauherr: Staatliches Bauamt (fiktiv) · AN: Muster Bau GmbH (fiktiv) · VOB/B vereinbart · Stand 14.09.2026"])
    ws.append([])
    ws.append(["OZ", "Kurztext", "Menge", "Einheit", "EP [€]", "GP [€]", "Anmerkung"])
    for c in ws[4]:
        c.font = Font(bold=True); c.fill = FILL
    r0 = 5
    for i, (oz, text, menge, einheit, ep, note) in enumerate(LV):
        r = r0 + i
        ws.append([oz, text, menge, einheit, ep, f"=C{r}*E{r}" if ep is not None and menge is not None else None, note])
        if menge is None:
            for c in ws[r]:
                c.font = Font(bold=True); c.fill = PatternFill("solid", fgColor="F2F2F2")
    rl = r0 + len(LV) - 1
    ws.append([]); ws.append(["", "Summe netto", None, None, None, f"=SUM(F{r0}:F{rl})"])
    ws.append(["", "MwSt. 19 %", None, None, None, f"=F{rl + 2}*0.19"])
    ws.append(["", "Summe brutto", None, None, None, f"=F{rl + 2}+F{rl + 3}"])
    for c in ws[rl + 2] + ws[rl + 4]:
        c.font = Font(bold=True)
    for col, w in zip("ABCDEFG", (13, 78, 10, 8, 12, 14, 52)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=5):
        row[1].alignment = Alignment(wrap_text=True, vertical="top")
        row[6].alignment = Alignment(wrap_text=True, vertical="top")
        for c in (row[4], row[5]):
            c.number_format = '#,##0.00'
    ws.freeze_panes = "A5"

    v = wb.create_sheet("Vertragsgrundlagen")
    for row in [
        ["Thema", "Regelung (fiktiv)"],
        ["Vertragsgrundlage", "Bauvertrag Nr. 2026-117, VOB/B vereinbart, VOB/C ATV DIN 18301 Bohrarbeiten"],
        ["Baugrund", "Baugrundgutachten Nr. 2026-0481 (Geo-Süd, 28.08.2026) ist Vertragsbestandteil"],
        ["Bohrpfähle", "Pos. 03.02.0010/0020: Bohren in Homogenbereich B1 (Sand/Kies) bzw. B1/B2. Fels ist kein Leistungsbestandteil."],
        ["Mehrvergütung", "§ 2 Abs. 5/6 VOB/B: Anspruch auf Mehrvergütung bei geänderter/zusätzlicher Leistung; Ankündigung vor Ausführungsbeginn"],
        ["Bedenken/Behinderung", "§ 4 Abs. 3 und § 6 Abs. 1 VOB/B: schriftliche Anzeige an den AG"],
        ["Anzeigepflicht Baugrund", "Abweichung vom Baugrund-Gutachten, insbesondere Fels, ist dem AG unverzüglich schriftlich anzuzeigen"],
        ["Bohrleistung (Kalkulationsansatz)", "24 m je Arbeitstag = 2 Pfähle à 12 m in B1, ca. 4 h je Pfahl"],
        ["Vertragsfristen", "Meilenstein Unterbau fertig: 02.12.2026"],
    ]:
        v.append(row)
    for c in v[1]:
        c.font = Font(bold=True); c.fill = FILL
    v.column_dimensions["A"].width = 30; v.column_dimensions["B"].width = 110

    n = wb.create_sheet("Nachtrag_P07_Entwurf")
    n.append(["Nachtragskalkulation Fels Pfahl 7 – ENTWURF, ungeprüft (fiktive Ansätze)"]); n["A1"].font = Font(bold=True, size=12)
    n.append([])
    n.append(["Position", "Menge", "Einheit", "Ansatz [€]", "Betrag [€]", "Herleitung"])
    for c in n[3]:
        c.font = Font(bold=True); c.fill = FILL
    n.append(["Bohren in Fels P07, 4,0 – 12,0 m", 8.0, "m", 410.00, "=B4*D4", "Mehrleistung ggü. Pos. 03.02.0010 (B1)"])
    n.append(["Zusatzstunden Bohrgerät BG-01", 14, "h", 420.00, "=B5*D5", "Fiktiver interner Satz 420 €/h"])
    n.append(["Personal (3 Mann)", 14, "h", 174.00, "=B6*D6", "3 × 58 €/h"])
    n.append(["Verschleiß Bohrwerkzeug (Felsmeißel)", 1, "psch", 3800.00, "=B7*D7", "Schätzung"])
    n.append(["Stillstand/Behinderung 17.11. (Wartezeit)", 3, "h", 150.00, "=B8*D8", "Stillstandssatz 150 €/h"])
    n.append(["Summe netto", None, None, None, "=SUM(E4:E8)", "ohne Zuschläge"])
    n.append(["Risikohinweis: Weitere Pfähle (P08 – P24) können ebenfalls betroffen sein; Erkundungsbohrung BK 5 empfohlen."])
    for col, w in zip("ABCDEF", (44, 10, 9, 13, 14, 44)):
        n.column_dimensions[col].width = w
    for r in range(4, 10):
        n.cell(r, 5).number_format = '#,##0.00'

    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "lv.xlsx"; wb.save(raw)
        # round-trip through LibreOffice so formula results are cached for parsers reading with data_only
        out = Path(td) / "out"; out.mkdir()
        subprocess.run(["soffice", "--headless", "--convert-to", "xlsx", "--outdir", str(out), str(raw)], check=True, capture_output=True)
        shutil.copy(out / "lv.xlsx", OUT / "leistungsverzeichnis_BW12.xlsx")


# ------------------------------------------------------------------ E-Mails (.eml)
def eml(name, frm, to, subject, when, body, cc=None, msgid=None):
    m = EmailMessage(policy=SMTP)
    m["From"], m["To"], m["Subject"], m["Date"] = frm, to, subject, format_datetime(when)
    if cc:
        m["Cc"] = cc
    m["Message-ID"] = f"<{msgid or name}@upload-sample.example>"
    m.set_content(body, charset="utf-8", cte="quoted-printable")
    (OUT / "emails").mkdir(exist_ok=True)
    (OUT / "emails" / f"{name}.eml").write_bytes(m.as_bytes())


def emails() -> None:
    BR, LI, KE, HU, NO = ("Markus Brandl <m.brandl@muster-bau.example>", "Hans Lindner <h.lindner@bauamt.example>",
                          "Sabine Keller <s.keller@muster-bau.example>", "Josef Huber <j.huber@muster-bau.example>",
                          "Dr. Petra Nowak <p.nowak@geo-sued.example>")
    eml("01_huber_an_brandl_fels_p07", HU, BR, "Pfahl 7: Fels bei 4 m – Bohrfortschritt stark reduziert", dt(17, 11, 25),
        """Hallo Markus,

bei Pfahl 7 (Widerlager 1) sind wir bei 4,0 m auf Fels (Kalkstein, stark verwittert bis fest) gestoßen.
Im Gutachten steht für Widerlager 1 durchgehend Sand/Kies. Stand 11:20 Uhr: 4,6 m erreicht, normal wären
um diese Zeit ca. 8 m. BG-01 braucht jetzt den Felsmeißel, Anton Weber schätzt etwa den dreifachen Zeitbedarf je Meter.

Fotos und Bohrprotokoll (handschriftlich) liegen vor, die Bohrkerne/Bohrgut habe ich sichergestellt.
Ich stoppe P08 vorerst nicht, bitte um deine Entscheidung.

Gruß Josef
""")
    eml("02_brandl_an_bauamt_behinderungsanzeige", BR, LI, "BW 12, Widerlager 1, Pfahl 7: Fels bei 4,0 m – Anzeige gem. § 4 Abs. 3, § 6 Abs. 1 und § 2 Abs. 6 VOB/B",
        dt(17, 14, 10), """Sehr geehrter Herr Lindner,

bei der Herstellung des Bohrpfahls P07 am Widerlager 1 wurde am 17.11.2026 ab 4,0 m Tiefe Fels (Kalkstein, stark verwittert bis fest)
angetroffen. Gemäß Baugrundgutachten Nr. 2026-0481 (Kapitel 4, Widerlager 1, BK 1/BK 2) ist für die Pfähle am Widerlager 1 mit "normalem
Bohrfortschritt in nichtbindigem Boden" zu rechnen; Fels wurde nicht erkundet und ist in keinem Homogenbereich (B0 – B2) enthalten.
Das LV (Pos. 03.02.0010) beschreibt das Bohren in Boden B1.

Wir zeigen hiermit an:
1. Abweichung vom vertraglich beschriebenen Baugrund (Bedenkenanmeldung nach § 4 Abs. 3 VOB/B).
2. Behinderung der Ausführung durch deutlich verlangsamten Bohrfortschritt (§ 6 Abs. 1 VOB/B).
3. Anspruch auf Mehrvergütung für die Mehrleistung Bohren in Fels, voraussichtlich 8,0 m je betroffenem Pfahl (§ 2 Abs. 6 VOB/B).
   Eine erste Kostenschätzung für P07 folgt gesondert als Nachtragsangebot.

Wir bitten um Anordnung, wie weiter zu verfahren ist (Erkundung, Weiterbohren im Fels mit Spezialwerkzeug, Änderung der Gründung).
Bis zu Ihrer Entscheidung bohren wir P07 im Fels weiter und stellen die Arbeiten an P08 zurück. Der Termin für den Meilenstein
„Unterbau fertig“ (02.12.2026) ist gefährdet.

Anlagen: Bohrprotokoll P07 vom 17.11.2026 (separat per Post/Upload)

Mit freundlichen Grüßen
Markus Brandl
Bauleiter, Muster Bau GmbH (fiktiv)
""", cc=KE)
    eml("03_bauamt_an_brandl_antwort", LI, BR, "AW: BW 12, Widerlager 1, Pfahl 7: Fels bei 4,0 m", dt(18, 9, 30),
        """Guten Tag Herr Brandl,

Ihre Anzeige vom 17.11.2026 ist eingegangen. Eine Anerkennung dem Grunde oder der Höhe nach erfolgt hiermit ausdrücklich noch nicht.
Wir bitten um folgende Unterlagen bis Freitag, 20.11.2026:
- vollständiges Bohrprotokoll P07 mit Schichtenverzeichnis und Fotos,
- Bohrzeiten P01 – P07 zum Vergleich (Bohrleistung je Pfahl),
- prüffähiges Nachtragsangebot mit Mengen und Einheitspreisen.

Der Baugrundgutachter, Frau Dr. Nowak, wird eine ergänzende Stellungnahme abgeben. Die Arbeiten an den übrigen Pfählen
am Widerlager 1 sind fortzuführen, sofern dies technisch möglich ist; P08 ist nach Rücksprache mit dem Gutachter zu bohren.
Wir laden zu einer Baubesprechung am Donnerstag, 19.11.2026, 10:00 Uhr (Einladung folgt).

Mit freundlichen Grüßen
Hans Lindner
Staatliches Bauamt (fiktiv)
""", cc=KE)
    eml("04_gutachter_stellungnahme", NO, LI + ", " + BR, "BW 12: Ergänzende Stellungnahme zum Felsantreffen bei P07", dt(19, 8, 15),
        """Sehr geehrte Herren,

nach Sichtung der Bohrprotokolle und Fotos von P07 (Widerlager 1) halte ich fest:

1. Der angetroffene Kalkstein (stark verwittert bis fest) ab 4,0 m u. GOK entspricht dem regional verkarsteten Felsuntergrund. Die
   Felsoberfläche wurde in BK 1 (9,0 m) und BK 2 (9,5 m) nicht erreicht; ein lokaler Felsrücken zwischen den Aufschlüssen
   war aufgrund der punktförmigen Erkundung nicht auszuschließen, aber auch nicht prognostizierbar.
2. Das Gutachten Nr. 2026-0481 weist für Widerlager 1 keinen Fels aus (Kapitel 4 und 6). Ein Homogenbereich Fels wurde nicht gebildet.
3. Ich empfehle eine ergänzende Aufschlussbohrung BK 5 im Bereich P08/P09 vor dem Weiterbohren und die Bildung eines
   Homogenbereichs B3 (Fels, Kalkstein) für die weitere Ausschreibung.
4. Pfahllängen und Tragfähigkeit sind bei Einbindung in den Fels unkritisch; maßgeblich ist der Bohraufwand.

Mit freundlichen Grüßen
Dr.-Ing. Petra Nowak
Geo-Süd Ingenieure GmbH (fiktiv)
""")
    eml("05_keller_an_brandl_nachtrag", KE, BR, "Nachtrag Fels P07 – benötigte Zahlen", dt(19, 13, 40),
        """Hallo Markus,

für das Nachtragsangebot Fels P07 brauche ich bis Freitag:
- Bohrzeit P07 (Start 06:45, Ende?), Tiefe, Zeit im Fels, Stillstandszeiten am 17.11.,
- Vergleich mit P01 – P06 (ca. 4 h je Pfahl),
- Einsatz Bohrgerät, Personal, Verschleißteile (Felsmeißel).
Entwurf liegt als Tabelle „Nachtrag_P07_Entwurf“ im Leistungsverzeichnis. Bitte beachte: Wir müssen die Anzeige vom 17.11.
(§ 6 VOB/B) und die Ankündigung nach § 2 Abs. 6 VOB/B sauber zitieren.

Danke, Sabine
""")


# ------------------------------------------------------------------ Kalender (.ics)
def ics() -> None:
    def esc(t): return t.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    def fold(line):
        b, out = line.encode(), []
        while len(b) > 74:
            cut = 74
            while b[cut] & 0xC0 == 0x80:
                cut -= 1
            out.append(b[:cut].decode()); b = b[cut:]; b = b" " + b
        out.append(b.decode())
        return "\r\n".join(out)
    events = [
        ("2026-11-19-baubesprechung-fels", dt(19, 10, 0), dt(19, 11, 0), "Baubesprechung Bauherr: Fels bei Pfahl 7 (BW 12)",
         "Baustelle BW 12 Mühlbach, Container BE",
         "Tagesordnung:\n1. Fels bei P07 ab 4,0 m (Anzeige vom 17.11.2026, Gutachten Nr. 2026-0481)\n2. Ergänzende Stellungnahme Baugrundgutachter, Aufschlussbohrung BK 5\n"
         "3. Terminfolge Bohrpfähle P08 – P24, Meilenstein Unterbau fertig 02.12.2026\n4. Nachtragsangebot Fels P07, Unterlagen\n5. Aussparung DN 100 Flügelwand W2",
         [("Hans Lindner", "h.lindner@bauamt.example"), ("Markus Brandl", "m.brandl@muster-bau.example"), ("Josef Huber", "j.huber@muster-bau.example"),
          ("Sabine Keller", "s.keller@muster-bau.example"), ("Dr. Petra Nowak", "p.nowak@geo-sued.example")]),
        ("2026-11-20-nachtragsunterlagen", dt(20, 12, 0), dt(20, 12, 30), "Frist: Nachtragsangebot Fels P07 beim Bauamt einreichen",
         "Büro Muster Bau GmbH", "Bohrprotokoll P07, Bohrzeiten P01–P07, Nachtragsangebot mit Mengen und EP.",
         [("Sabine Keller", "s.keller@muster-bau.example")]),
        ("2026-11-23-bk5", dt(23, 7, 0), dt(23, 15, 0), "Aufschlussbohrung BK 5 im Bereich P08/P09",
         "Baustelle BW 12, Widerlager 1", "Ergänzende Erkundung durch Geo-Süd; Bohrgerät BG-01 steht bereit.",
         [("Dr. Petra Nowak", "p.nowak@geo-sued.example"), ("Josef Huber", "j.huber@muster-bau.example")]),
    ]
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//BW12 Upload Sample (fiktiv)//DE", "CALSCALE:GREGORIAN", "METHOD:REQUEST",
         "BEGIN:VTIMEZONE", "TZID:Europe/Berlin", "BEGIN:STANDARD", "TZOFFSETFROM:+0200", "TZOFFSETTO:+0100", "TZNAME:CET",
         "DTSTART:19701025T030000", "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU", "END:STANDARD",
         "BEGIN:DAYLIGHT", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0200", "TZNAME:CEST", "DTSTART:19700329T020000",
         "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU", "END:DAYLIGHT", "END:VTIMEZONE"]
    for uid, s, e, summ, loc, desc, att in events:
        L += ["BEGIN:VEVENT", f"UID:{uid}@upload-sample.example", "DTSTAMP:20261118T093500Z", "SEQUENCE:0",
              f"DTSTART;TZID=Europe/Berlin:{s:%Y%m%dT%H%M%S}", f"DTEND;TZID=Europe/Berlin:{e:%Y%m%dT%H%M%S}",
              f"SUMMARY:{esc(summ)}", f"LOCATION:{esc(loc)}", f"DESCRIPTION:{esc(desc)}",
              "ORGANIZER;CN=Hans Lindner:mailto:h.lindner@bauamt.example", "STATUS:CONFIRMED"]
        L += [f"ATTENDEE;CN={n};ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION:mailto:{a}" for n, a in att]
        L += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{esc(summ)}", "TRIGGER:-PT30M", "END:VALARM", "END:VEVENT"]
    L.append("END:VCALENDAR")
    (OUT / "baubesprechung_BW12.ics").write_bytes(("\r\n".join(fold(x) for x in L) + "\r\n").encode())


def readme() -> None:
    (OUT / "README.md").write_text(f"""# Upload-Samples BW 12 Mühlbach

{FIKTIV} Generiert mit `python backend/scripts/generate_upload_samples.py` (Bilder: keine).
Diese Dateien werden **nicht** automatisch geladen (App startet leer); im Chat/Dokumente-Dialog hochladen.
Ergänzen `../inbox/pfahl7_bohrprotokoll.pdf` und `../outlook/` (gleiches Szenario, gleiche Namen/Werte).

| Datei | Inhalt |
|---|---|
| `baugrundgutachten_BW12.pdf` | 9-seitiges Gutachten Nr. 2026-0481; Kap. 4 (S. 5): W1 Sand/Kies, Fels nicht erkundet; Kap. 6: Homogenbereiche B0–B2, **kein** Fels |
| `leistungsverzeichnis_BW12.xlsx` | LV (Pos. 03.02.0010 Bohren in B1; Bedarfsposition 03.02.0900 Fels, nicht beauftragt), Blatt Vertragsgrundlagen, Blatt Nachtrag_P07_Entwurf |
| `emails/01–05_*.eml` | Polier-Meldung, Anzeige Brandl (§ 4 Abs. 3, § 6 Abs. 1, § 2 Abs. 6 VOB/B), Antwort Bauamt, Gutachter-Stellungnahme, Nachtrag-Rückfrage |
| `baubesprechung_BW12.ics` | Baubesprechung 19.11.2026 10:00 (Fels P07), Frist Nachtrag 20.11., BK 5 am 23.11. |

## Kernabweichung (zitierbar)
Pfahl 7 (Widerlager 1): ab **4,0 m** Fels (Kalkstein), Zieltiefe 12,0 m, 17.11.2026. Vertrag/Gutachten: nur Boden B1. Mehrleistung ca. 8,0 m Fels.
Kalkulationsbeträge im Nachtragsentwurf sind erfundene Ansätze.
""", encoding="utf-8")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    gutachten(); lv_xlsx(); emails(); ics(); readme()
    print("written to", OUT)
