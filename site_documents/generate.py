"""Generates the fictitious site documents + geotagged photos used to test site layout generation.

Run from the repo root:   python site_documents/generate.py            (German originals + photos + ground truth)
                          python site_documents/generate.py --lang en  (English duplicates *_en.*, same geometry)
Everything is invented (BW 27 über den Erlbach, fictitious). The anchor 48.2935 N / 11.8890 E is deliberately NOT the
anchor of backend/data (48.3069 / 11.9081): tests can tell which data a layout came from.

Ground truth is defined once below in plan metres (x = east, y = north, origin = anchor, plan aligned to true north) and
written into every format: survey CSV (WGS84, decimal commas), schedule XLSX (UTM 32N), geotechnical report PDF + DOCX
(UTM 32N and WGS84), site plan GeoJSON, a project reference JSON, and EXIF GPS in copies of the seed photos.
"""
import csv
import json
import math
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
UP = HERE / "upload"            # what a user attaches (documents + geotagged photos)
GT = HERE / "ground_truth"      # what the tests compare against – do NOT upload these
sys.path.insert(0, str(ROOT / "backend"))

from core.geo import wgs84_to_utm                      # noqa: E402
from core.site_twin import point_in_poly, xy_to_gps   # noqa: E402

SUF = ""                        # "" = German originals, "_en" = English duplicates (python site_documents/generate.py --lang en)
TX = {   # German text; replaced by EN below when --lang en
    "anchor_label": "Bezugspunkt BP0 – Brückenachse / Erlbach-Mitte", "note": "Fiktive Baustelle. Lageplan nach Norden ausgerichtet.",
    "anchor_desc": "Bezugspunkt Brückenachse", "anchor_typ": "bezugspunkt", "boundary_desc": "Grundstücksgrenze", "boundary_typ": "grenze",
    "corner": "Ecke", "csv_head": ["id", "bezeichnung", "typ", "breite", "laenge"],
    "xlsx_title": "Bauzeitenplan", "xlsx_head": ["ID", "Vorgang", "Bauteil", "Beginn", "Ende", "Menge", "Einheit", "RW (UTM 32N)", "HW (UTM 32N)"],
    "rep_title": "Baugrundgutachten – Auszug (fiktiv)", "rep_crs": "Koordinatenbezug: ETRS89 / UTM Zone 32N (EPSG:25832), Lage zusätzlich in WGS84.",
    "rep_map": "Lageplan der Aufschlüsse im Maßstab 1:500 (Anlage 2).", "rep_cores": "Aufschlüsse (Kernbohrungen):",
    "rock_from": "Fels ab", "below_ground": "u. GOK", "rep_eval1": "Bewertung: Ab ca. 9 bis 11 m unter Gelände steht verwitterter Kalkstein an.",
    "rep_eval2": "Für Bohrpfähle im Bereich Widerlager 1 ist mit Felsbohrung zu rechnen.", "rep_fict": "Dieses Dokument ist fiktiv und dient nur zu Testzwecken.",
    "docx_head": ["Bohrung", "Bezeichnung", "Rechtswert (UTM 32N)", "Hochwert (UTM 32N)", "Breite (WGS84)", "Länge (WGS84)"],
    "docx_core": "Kernbohrung", "docx_eval": "Bewertung: Ab ca. 9 bis 11 m unter Gelände steht verwitterter Kalkstein an. Dieses Dokument ist fiktiv.",
    "plan_name": "Lageplan BW 27 (fiktiv)",
}
ANCHOR = {"lat": 48.2935, "lon": 11.8890}
LAY = {"origin": ANCHOR, "rotation_deg": 0}
NAME = "Ersatzneubau Brücke BW 27 über den Erlbach (fiktiv)"

ZONES = {   # id: (name, corners in metres SW, SE, NE, NW)
    "W1": ("Widerlager 1", [(-58, -15), (-30, -15), (-30, 15), (-58, 15)]),
    "A1": ("Achse 1", [(-20, -12), (-10, -12), (-10, 12), (-20, 12)]),
    "A2": ("Achse 2", [(10, -12), (20, -12), (20, 12), (10, 12)]),
    "W2": ("Widerlager 2", [(30, -15), (58, -15), (58, 15), (30, 15)]),
    "BE": ("Baustelleneinrichtung", [(-70, -45), (-40, -45), (-40, -22), (-70, -22)]),
}
CORNER_NAMES = ["SW", "SO", "NO", "NW"]

# English duplicates: same ids, geometry and dates; only the words change
EN = {
    "NAME": "Replacement bridge BW 27 over the Erlbach (fictitious)",
    "ZONES": {"W1": "Abutment 1", "A1": "Axis 1", "A2": "Axis 2", "W2": "Abutment 2", "BE": "Site facilities"},
    "CORNER_NAMES": ["SW", "SE", "NE", "NW"],
    "CRANE": "Tower crane",
    "SCHEDULE": {"W1_BP": "Bored piles Abutment 1 (8 × 12 m)", "W1_BET": "Concreting Abutment 1", "A1_BP": "Bored piles Axis 1 (4 × 12 m)",
                 "A1_BET": "Concreting Axis 1", "A2_BP": "Bored piles Axis 2 (4 × 12 m)", "A2_BET": "Concreting Axis 2",
                 "W2_BP": "Bored piles Abutment 2 (8 × 12 m)", "W2_BET": "Concreting Abutment 2",
                 "UB1_MONT": "Superstructure erection (position follows with detailed design)"},
    "UNIT": {"Vorgang": "activity"},
    "TX": {"anchor_label": "Reference point BP0 – bridge axis / Erlbach centre", "note": "Fictitious site. Site plan oriented to north.",
           "anchor_desc": "Reference point bridge axis", "anchor_typ": "reference", "boundary_desc": "Property boundary", "boundary_typ": "boundary",
           "corner": "corner", "csv_head": ["id", "description", "type", "latitude", "longitude"],
           "xlsx_title": "Construction schedule", "xlsx_head": ["ID", "Activity", "Element", "Start", "End", "Quantity", "Unit", "Easting (UTM 32N)", "Northing (UTM 32N)"],
           "rep_title": "Geotechnical report – excerpt (fictitious)", "rep_crs": "Coordinate reference: ETRS89 / UTM zone 32N (EPSG:25832), position also in WGS84.",
           "rep_map": "Site plan of the boreholes at scale 1:500 (annex 2).", "rep_cores": "Boreholes (core drillings):",
           "rock_from": "rock from", "below_ground": "below ground", "rep_eval1": "Assessment: weathered limestone from approx. 9 to 11 m below ground.",
           "rep_eval2": "Rock drilling is to be expected for bored piles at Abutment 1.", "rep_fict": "This document is fictitious and for testing only.",
           "docx_head": ["Borehole", "Description", "Easting (UTM 32N)", "Northing (UTM 32N)", "Latitude (WGS84)", "Longitude (WGS84)"],
           "docx_core": "Core drilling", "docx_eval": "Assessment: weathered limestone from approx. 9 to 11 m below ground. This document is fictitious.",
           "plan_name": "Site plan BW 27 (fictitious)"},
}


def use_english():
    """Switch the tables above to English (ids, coordinates and dates unchanged) and write *_en files."""
    global SUF, NAME, CORNER_NAMES, CRANE, SCHEDULE
    SUF, NAME, CORNER_NAMES = "_en", EN["NAME"], EN["CORNER_NAMES"]
    for k, v in EN["TX"].items():
        TX[k] = v
    for zid in ZONES:
        ZONES[zid] = (EN["ZONES"][zid], ZONES[zid][1])
    de_to_en = {de_name: EN["ZONES"][zid] for zid, (de_name, _c) in zip(ZONES, [("Widerlager 1", 0), ("Achse 1", 0), ("Achse 2", 0), ("Widerlager 2", 0), ("Baustelleneinrichtung", 0)])}
    for bk, (part, xy, rock) in list(BOREHOLES.items()):
        BOREHOLES[bk] = (de_to_en.get(part, part), xy, rock)
    CRANE = (CRANE[0], EN["CRANE"], CRANE[2])
    SCHEDULE = [(a, EN["SCHEDULE"].get(a, n), part, x, y, q, EN["UNIT"].get(u, u)) for a, n, part, x, y, q, u in SCHEDULE]
BOUNDARY = [(-75, -50), (75, -50), (75, 40), (60, 50), (-75, 50)]
BOREHOLES = {"BK1": ("Widerlager 1", (-44, 0), 9.8), "BK2": ("Achse 1", (-15, 0), 11.2),
             "BK3": ("Achse 2", (15, 0), 10.5), "BK4": ("Widerlager 2", (44, 0), 8.9)}
CRANE = ("KR-01", "Turmdrehkran", (-58, -38))
SCHEDULE = [   # id, activity, structure, start, end, qty, unit
    ("W1_BP", "Bohrpfähle Widerlager 1 (8 × 12 m)", "W1", "2026-11-09", "2026-11-20", 96, "m"),
    ("W1_BET", "Betonieren Widerlager 1", "W1", "2026-11-23", "2026-11-27", 1, "Vorgang"),
    ("A1_BP", "Bohrpfähle Achse 1 (4 × 12 m)", "A1", "2026-11-16", "2026-11-20", 48, "m"),
    ("A1_BET", "Betonieren Achse 1", "A1", "2026-11-30", "2026-12-02", 1, "Vorgang"),
    ("A2_BP", "Bohrpfähle Achse 2 (4 × 12 m)", "A2", "2026-11-23", "2026-11-27", 48, "m"),
    ("A2_BET", "Betonieren Achse 2", "A2", "2026-12-07", "2026-12-09", 1, "Vorgang"),
    ("W2_BP", "Bohrpfähle Widerlager 2 (8 × 12 m)", "W2", "2026-11-30", "2026-12-11", 96, "m"),
    ("W2_BET", "Betonieren Widerlager 2", "W2", "2026-12-14", "2026-12-18", 1, "Vorgang"),
    ("UB1_MONT", "Überbau Montage (Lage folgt mit Ausführungsplanung)", "", "2027-01-11", "2027-02-05", 1, "Vorgang"),
]
# seed photos (all show excavators / dump trucks): plan position, heading, accuracy. Two pairs are deliberate:
# 07179547 <-> a7b1a4f1 exactly 25.0 m apart; ecae8902 <-> 8d694186 2.0 m apart at ±4/5 m (same spot within GPS error).
PHOTOS = [  # id, xy (or explicit lat/lon), heading, ref, accuracy, taken, expected zone, note
    ("ecae8902", (-44.0, 2.0), 90, "T", 4.0, "2026-11-18 08:05:00", "w1", "Aushub Widerlager 1, Blick nach Osten"),
    ("8d694186", (-42.8, 3.6), None, None, 5.0, "2026-11-18 08:07:00", "w1", "gleiche Stelle wie ecae8902 (2 m, innerhalb GPS-Genauigkeit)"),
    ("07179547", (-12.5, 4.0), 180, "T", 3.0, "2026-11-18 10:12:00", "a1", "Achse 1"),
    ("a7b1a4f1", (12.5, 4.0), None, None, 3.0, "2026-11-18 10:40:00", "a2", "Achse 2, genau 25,0 m von 07179547"),
    ("1c92357b", (44.0, 1.0), 270, "M", 4.0, "2026-11-18 13:30:00", "w2", "Widerlager 2, Richtung magnetisch Nord (M)"),
    ("6342cd1c", (-52.0, -30.0), 45, "T", 6.0, "2026-11-18 15:02:00", "be", "Bagger in der Baustelleneinrichtung"),
    ("4d007fe8", {"lat": 35.6812, "lon": 139.7671}, None, None, 10.0, "2026-11-18 16:00:00", "", "falsche GPS-Position (Tokio): muss als Ausreißer erkannt werden"),
]


def ll(xy):
    lat, lon = xy_to_gps(xy[0], xy[1], LAY)
    return lat, lon


def de(v, nd=7):
    return f"{v:.{nd}f}".replace(".", ",")


def utm(xy):
    e, n, z = wgs84_to_utm(*ll(xy), zone=32)
    return e, n


def utm_txt(v):
    s = f"{v:,.1f}".replace(",", " ").replace(".", ",")
    return s


# ---------------------------------------------------------------- files
def project_reference():
    (UP / f"project_reference{SUF}.json").write_text(json.dumps({
        "name": NAME, "crs": "EPSG:4326 (WGS84)", "rotation_deg": 0,
        "anchor": {"label": TX["anchor_label"], **ANCHOR},
        "note": TX["note"]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def survey_csv():
    rows = [("BP0", TX["anchor_desc"], TX["anchor_typ"], (0, 0))]
    rows += [(f"B{i}", TX["boundary_desc"], TX["boundary_typ"], p) for i, p in enumerate(BOUNDARY, 1)]
    for zid, (name, corners) in ZONES.items():
        rows += [(f"{zid}-{i}", f"{name}, {TX['corner']} {CORNER_NAMES[i - 1]}", "zone", p) for i, p in enumerate(corners, 1)]
    with open(UP / f"vermessung_punkte{SUF}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(TX["csv_head"])
        for pid, desc, typ, p in rows:
            lat, lon = ll(p)
            w.writerow([pid, desc, typ, de(lat), de(lon)])


def schedule_xlsx():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = TX["xlsx_title"]
    ws.append(TX["xlsx_head"])
    for aid, name, part, a, b, q, unit in SCHEDULE:
        if part:
            cx = sum(p[0] for p in ZONES[part][1]) / 4
            cy = sum(p[1] for p in ZONES[part][1]) / 4
            e, n = utm((cx, cy))
            ws.append([aid, name, part, a, b, q, unit, round(32_000_000 + e, 1), round(n, 1)])
        else:
            ws.append([aid, name, part, a, b, q, unit, None, None])
    for col, wdt in zip("ABCDEFGHI", (10, 46, 9, 12, 12, 8, 9, 15, 14)):
        ws.column_dimensions[col].width = wdt
    wb.save(UP / f"bauzeitenplan{SUF}.xlsx")


def report_lines():
    out = [TX["rep_title"], NAME, "", TX["rep_crs"], TX["rep_map"], "", TX["rep_cores"]]
    for i, (bk, (part, xy, rock)) in enumerate(BOREHOLES.items()):
        e, n = utm(xy)
        lat, lon = ll(xy)
        if i < 2:      # BK1, BK2: UTM and WGS84 on the line
            out.append(f"{bk} ({part}): RW 32 {utm_txt(e)} HW {utm_txt(n)} | {de(lat, 6)}° N {de(lon, 6)}° E | {TX['rock_from']} {de(rock, 1)} m")
        else:          # BK3, BK4: UTM only
            out.append(f"{bk} ({part}): RW 32 {utm_txt(e)} HW {utm_txt(n)} | {TX['rock_from']} {de(rock, 1)} m {TX['below_ground']}")
    out += ["", TX["rep_eval1"], TX["rep_eval2"], TX["rep_fict"]]
    return out


def report_pdf():
    """Minimal one-page PDF with a real text layer (Helvetica, WinAnsi) – no PDF library needed."""
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    y, ops = 800, []
    for i, line in enumerate(report_lines()):
        size = 14 if i == 0 else 9
        ops.append(f"BT /F1 {size} Tf 50 {y} Td ({esc(line)}) Tj ET")
        y -= 20 if i == 0 else 14
    stream = "\n".join(ops).encode("cp1252")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    out, offs = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    (UP / f"baugrundgutachten{SUF}.pdf").write_bytes(bytes(out))


def report_docx():
    from docx import Document
    d = Document()
    d.add_heading(TX["rep_title"], 1)
    d.add_paragraph(NAME)
    d.add_paragraph(TX["rep_crs"])
    t = d.add_table(rows=1, cols=6)
    for c, h in zip(t.rows[0].cells, TX["docx_head"]):
        c.text = h
    for bk, (part, xy, rock) in BOREHOLES.items():
        e, n = utm(xy)
        lat, lon = ll(xy)
        for c, v in zip(t.add_row().cells, [bk, f"{TX['docx_core']} {part}, {TX['rock_from']} {de(rock, 1)} m", utm_txt(32_000_000 + e), utm_txt(n), de(lat, 7), de(lon, 7)]):
            c.text = v
    d.add_paragraph(TX["docx_eval"])
    d.save(UP / f"baugrundgutachten{SUF}.docx")


def plan_geojson():
    feats = []
    for zid, (name, corners) in ZONES.items():
        ring = [[round(ll(p)[1], 8), round(ll(p)[0], 8)] for p in corners]
        feats.append({"type": "Feature", "properties": {"id": zid, "name": name, "kind": "zone"},
                      "geometry": {"type": "Polygon", "coordinates": [ring + [ring[0]]]}})
    lat, lon = ll(CRANE[2])
    feats.append({"type": "Feature", "properties": {"id": CRANE[0], "name": f"{CRANE[1]} {CRANE[0]}", "kind": "marker"},
                  "geometry": {"type": "Point", "coordinates": [round(lon, 8), round(lat, 8)]}})
    (UP / f"lageplan{SUF}.geojson").write_text(json.dumps({"type": "FeatureCollection", "name": TX["plan_name"], "features": feats},
                                                      indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _dms(v):
    from PIL.TiffImagePlugin import IFDRational as R
    d = int(v)
    m = int((v - d) * 60)
    s = (v - d - m / 60) * 3600
    return (R(d), R(m), R(round(s * 10000), 10000))


def photos():
    from PIL import ExifTags, Image
    from PIL.TiffImagePlugin import IFDRational as R
    src, dst = ROOT / "backend" / "data" / "seed" / "uploads", UP / "photos"
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir()
    rows = []
    for pid, pos, hd, ref, acc, taken, zone, note in PHOTOS:
        lat, lon = (pos["lat"], pos["lon"]) if isinstance(pos, dict) else ll(pos)
        im = Image.open(src / f"{pid}.jpg")
        ex = im.getexif()
        g = ex.get_ifd(ExifTags.IFD.GPSInfo)
        g.update({1: "N" if lat >= 0 else "S", 2: _dms(abs(lat)), 3: "E" if lon >= 0 else "W", 4: _dms(abs(lon)),
                  31: R(round(acc * 10), 10)})
        if hd is not None:
            g.update({16: ref, 17: R(round(hd * 10), 10)})
        ex.get_ifd(ExifTags.IFD.Exif)[36867] = taken.replace("-", ":")
        name = f"site_{pid}.jpg"
        im.save(dst / name, exif=ex, quality=90)
        rows.append([pid, name, de(lat, 7), de(lon, 7), "" if hd is None else hd, ref or "", de(acc, 1), taken, zone,
                     "" if isinstance(pos, dict) else de(pos[0], 1), "" if isinstance(pos, dict) else de(pos[1], 1), note])
    with open(GT / "photo_positions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["photo_id", "file", "breite", "laenge", "richtung_grad", "richtung_bezug", "genauigkeit_m", "aufgenommen",
                    "erwartete_zone", "erwartet_x_m", "erwartet_y_m", "hinweis"])
        w.writerows(rows)


def expected():
    zones = {}
    for zid, (name, corners) in ZONES.items():
        zones[zid.lower()] = {"name": name, "polygon": [list(p) for p in corners],
                              "centroid": [sum(p[0] for p in corners) / 4, sum(p[1] for p in corners) / 4],
                              "activities": sorted(a for a, *_ in SCHEDULE if a.startswith(zid + "_"))}
    ph = {pid: {"zone": zone or None, "xy": None if isinstance(pos, dict) else list(pos), "outlier": isinstance(pos, dict)}
          for pid, pos, _h, _r, _a, _t, zone, _n in PHOTOS}
    for pid, v in ph.items():      # sanity: ground truth is self-consistent
        if v["xy"]:
            assert point_in_poly(v["xy"][0], v["xy"][1], zones[v["zone"]]["polygon"]), pid
    (GT / "expected_layout.json").write_text(json.dumps({
        "_doc": "Ground truth in plan metres (x east, y north, origin = anchor). Tolerances used by the tests: origin 1 m, zone centroid 3 m, distances 0.5 m.",
        "origin": ANCHOR, "rotation_deg": 0, "boundary": [list(p) for p in BOUNDARY], "zones": zones,
        "markers": {**{bk: list(xy) for bk, (_p, xy, _r) in BOREHOLES.items()}, CRANE[0]: list(CRANE[2])},
        "photos": ph,
        "distances": [{"a": "07179547", "b": "a7b1a4f1", "m": 25.0, "within_accuracy": False},
                      {"a": "ecae8902", "b": "8d694186", "m": round(math.dist((-44.0, 2.0), (-42.8, 3.6)), 2), "within_accuracy": True}],
        "unmatched_activities": ["UB1_MONT"]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    UP.mkdir(exist_ok=True)
    GT.mkdir(exist_ok=True)
    english = "--lang" in sys.argv and sys.argv[sys.argv.index("--lang") + 1:sys.argv.index("--lang") + 2] == ["en"]
    if english:
        use_english()
    # photos and the ground truth are shared by both languages: only the German run writes them
    steps = (project_reference, survey_csv, schedule_xlsx, report_pdf, report_docx, plan_geojson) + (() if english else (photos, expected))
    for fn in steps:
        fn()
        print("ok", fn.__name__)
