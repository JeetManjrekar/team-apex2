"""Coordinates from site documents: CSV / XLSX / DOCX / PDF / GeoJSON / JSON -> labelled WGS84 points with provenance.

Supported notations
-------------------
- WGS84 decimal degrees, dot or comma decimals ("48.2935", "48,2935"), optional ° and N/S/E/O/W
- WGS84 degrees-minutes-seconds ("48°17'36.6\"N")
- UTM zone 32N / 33N easting/northing, with or without the zone prefix on the easting ("RW 32 690 123,4  HW 5 351 456,7")
Gauß-Krüger (DHDN) is NOT supported: it needs a datum shift, and a silently wrong position is worse than none.

Every point: {"label", "kind", "lat", "lon", "source", "locator"}; kind is one of anchor | boundary | zone | marker | point.
No coordinate is invented: a value that cannot be parsed or lies outside plausible ranges is reported, not guessed.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re

# ---------------------------------------------------------------- UTM <-> WGS84 (Krüger series, GRS80/WGS84 ellipsoid)
_A, _F = 6378137.0, 1 / 298.257223563
_K0, _E0 = 0.9996, 500000.0
_N = _F / (2 - _F)
_AA = _A / (1 + _N) * (1 + _N ** 2 / 4 + _N ** 4 / 64)
_ALPHA = (_N / 2 - 2 * _N ** 2 / 3 + 5 * _N ** 3 / 16, 13 * _N ** 2 / 48 - 3 * _N ** 3 / 5, 61 * _N ** 3 / 240)
_BETA = (_N / 2 - 2 * _N ** 2 / 3 + 37 * _N ** 3 / 96, _N ** 2 / 48 + _N ** 3 / 15, 17 * _N ** 3 / 480)
_DELTA = (2 * _N - 2 * _N ** 2 / 3 - 2 * _N ** 3, 7 * _N ** 2 / 3 - 8 * _N ** 3 / 5, 56 * _N ** 3 / 15)


def _lon0(zone):
    return math.radians(zone * 6 - 183)


def wgs84_to_utm(lat, lon, zone=None):
    """-> (easting, northing, zone). Northern hemisphere only (all German sites)."""
    zone = zone or int((lon + 180) // 6) + 1
    phi, lam = math.radians(lat), math.radians(lon) - _lon0(zone)
    e2 = 2 * math.sqrt(_N) / (1 + _N)
    t = math.sinh(math.atanh(math.sin(phi)) - e2 * math.atanh(e2 * math.sin(phi)))
    xi, eta = math.atan2(t, math.cos(lam)), math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    e = _E0 + _K0 * _AA * (eta + sum(a * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j, a in enumerate(_ALPHA, 1)))
    n = _K0 * _AA * (xi + sum(a * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j, a in enumerate(_ALPHA, 1)))
    return e, n, zone


def utm_to_wgs84(easting, northing, zone=32):
    """-> (lat, lon) in degrees."""
    xi, eta = northing / (_K0 * _AA), (easting - _E0) / (_K0 * _AA)
    xi_ = xi - sum(b * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j, b in enumerate(_BETA, 1))
    eta_ = eta - sum(b * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j, b in enumerate(_BETA, 1))
    chi = math.asin(math.sin(xi_) / math.cosh(eta_))
    phi = chi + sum(d * math.sin(2 * j * chi) for j, d in enumerate(_DELTA, 1))
    lam = _lon0(zone) + math.atan2(math.sinh(eta_), math.cos(xi_))
    return math.degrees(phi), math.degrees(lam)


# ---------------------------------------------------------------- number / coordinate parsing
def num(s):
    """'5 351 456,7' / '48,2935' / '1.234,5' / '690123.4' -> float, else None."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).strip().replace(" ", " ").replace(" ", " ")
    t = re.sub(r"(?<=\d)[ '](?=\d{3}\b)", "", t)            # thousands separators: space / apostrophe
    if "," in t and "." in t:                                # 1.234,5 -> 1234.5
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    m = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s*", t)
    return float(m.group(1)) if m else None


_DMS = re.compile(r"(\d{1,3})\s*°\s*(\d{1,2})\s*['′]\s*(\d{1,2}(?:[.,]\d+)?)?\s*(?:\"|″|'')?\s*([NSEOW])?", re.I)


def parse_coord(s, axis=None):
    """One latitude or longitude value: decimal (dot/comma, optional °/hemisphere) or DMS. -> float or None."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).strip()
    m = _DMS.search(t)
    if m:
        v = int(m.group(1)) + int(m.group(2)) / 60 + (num(m.group(3)) or 0) / 3600
        return -v if (m.group(4) or "").upper() in ("S", "W") else v
    hemi = re.search(r"[NSEOW]\s*$", t, re.I)
    v = num(re.sub(r"[°NSEOW\s]+$", "", t, flags=re.I).strip())
    if v is None:
        return None
    return -v if hemi and hemi.group(0).strip().upper() in ("S", "W") else v


def plausible(lat, lon):
    return lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0)


def _utm_pair(e, n, zone=None):
    """Easting may carry the zone prefix (32690123 / '32 690 123'). -> (lat, lon) or None."""
    if e is None or n is None:
        return None
    if e >= 1e7:                                              # zone prefix glued to the easting
        zone, e = int(e // 1e6), e % 1e6
    zone = zone or 32
    if not (100000 <= e <= 900000 and 0 <= n <= 9400000 and zone in range(1, 61)):
        return None
    return utm_to_wgs84(e, n, zone)


# ---------------------------------------------------------------- kind + label
_KIND_WORDS = [
    ("anchor", re.compile(r"bezugspunkt|referenzpunkt|reference|anchor|origin|ursprung|nullpunkt", re.I)),
    ("boundary", re.compile(r"grenz|boundary|grundstück|baufeld(?:grenze)?|property", re.I)),
    ("zone", re.compile(r"\bzone\b|bereich|ecke|corner|polygon", re.I)),
    ("marker", re.compile(r"bohrung|borehole|bohrpunkt|sondierung|\bbk\s?\d|\bdpm?\s?\d|pfahl|pile|messpunkt|pegel", re.I)),
]
_KIND_ALIASES = {"bezugspunkt": "anchor", "referenz": "anchor", "anchor": "anchor", "origin": "anchor", "reference": "anchor",
                 "grenze": "boundary", "grenzpunkt": "boundary", "boundary": "boundary", "zone": "zone", "eckpunkt": "zone",
                 "ecke": "zone", "corner": "zone", "bohrung": "marker", "borehole": "marker", "marker": "marker", "pfahl": "marker"}


def kind_of(label, explicit=None):
    if explicit:
        k = str(explicit).strip().lower()
        for key, v in _KIND_ALIASES.items():
            if k.startswith(key):
                return v
    for k, rx in _KIND_WORDS:
        if rx.search(label or ""):
            return k
    return "point"


def _pt(label, kind, lat, lon, source, locator, **extra):
    return {"label": (label or "").strip()[:80], "kind": kind, "lat": round(lat, 8), "lon": round(lon, 8),
            "source": source, "locator": locator, **extra}


# ---------------------------------------------------------------- tables (header detection)
_H = {
    "lat": re.compile(r"^(lat|latitude|breite|geogr\.? ?breite|n(?:orth)?\s*\(?wgs|y_?wgs)", re.I),
    "lon": re.compile(r"^(lon|lng|long|longitude|länge|laenge|geogr\.? ?länge|e(?:ast)?\s*\(?wgs|x_?wgs)", re.I),
    "e": re.compile(r"^(rw|rechtswert|easting|ost(?:wert)?|e(?:_?utm)?|x(?:_?utm)?)\b", re.I),
    "n": re.compile(r"^(hw|hochwert|northing|nord(?:wert)?|n(?:_?utm)?|y(?:_?utm)?)\b", re.I),
    "label": re.compile(r"^(id|nr\.?|punkt(?:nr)?|point|label|name|bezeichnung|bohrung|bauteil|code)\b", re.I),
    "desc": re.compile(r"^(beschreibung|description|bezeichnung|name|vorgang|bauteil)", re.I),
    "kind": re.compile(r"^(typ|type|art|kind|kategorie)\b", re.I),
    "zone": re.compile(r"^(utm[- ]?zone|zone|epsg)\b", re.I),
}


def _header_map(cells):
    m = {}
    for i, c in enumerate(cells):
        c = (c or "").strip()
        for k, rx in _H.items():
            if k not in m and rx.search(c):
                if k in ("e", "n") and re.search(r"wgs|breite|länge|lat|lon", c, re.I):
                    continue
                m[k] = i
                break
    if "desc" in m and m.get("desc") == m.get("label"):
        m.pop("desc")
    utm_hint = next((c for c in cells if re.search(r"utm\s*3[23]|epsg[: ]*258(3[23])|32n|33n", c or "", re.I)), "")
    m["_zone"] = 33 if re.search(r"33|25833", utm_hint) else 32
    return m


def points_from_rows(rows, source, where="Tabelle"):
    """rows: [(row_number, [cells])]. The first row with coordinate headers starts a table; several tables per sheet work."""
    out, skipped, hm, utm_zone = [], [], None, 32
    for rn, cells in rows:
        cells = [str(c if c is not None else "").strip() for c in cells]
        if not any(cells):
            continue
        cand = _header_map(cells)
        # a header row names coordinate columns and holds no numbers in them
        if ({"lat", "lon"} <= set(cand) or {"e", "n"} <= set(cand)) and \
                all(num(cells[cand[k]]) is None for k in ("lat", "lon", "e", "n") if k in cand):
            hm, utm_zone = cand, cand["_zone"]
            continue
        if not hm:
            continue
        get = lambda k: cells[hm[k]] if k in hm and hm[k] < len(cells) else ""   # noqa: E731
        label = get("label") or get("desc")
        desc = get("desc") if "desc" in hm and hm.get("desc") != hm.get("label") else ""
        loc = f"{where}, Zeile {rn}"
        ll = None
        if "lat" in hm and "lon" in hm:
            lat, lon = parse_coord(get("lat")), parse_coord(get("lon"))
            ll = (lat, lon) if plausible(lat, lon) else None
        if ll is None and "e" in hm and "n" in hm:
            z = num(get("zone")) if "zone" in hm else None
            z = int(z % 100) if z and z >= 25800 else (int(z) if z else utm_zone)   # EPSG 25832 -> 32
            ll = _utm_pair(num(get("e")), num(get("n")), z)
        if ll is None:
            if any(get(k) for k in ("lat", "lon", "e", "n")):
                skipped.append({"locator": loc, "reason": "coordinate could not be read", "label": label})
            continue
        out.append(_pt(label, kind_of(f"{label} {desc}", get("kind")), ll[0], ll[1], source, loc,
                       **({"description": desc} if desc else {})))
    return out, skipped


# ---------------------------------------------------------------- free text (PDF pages, DOCX paragraphs)
_DEC = r"(\d{1,2}[.,]\d{4,})\s*°?\s*([NS])?"
_DEC_LON = r"(\d{1,3}[.,]\d{4,})\s*°?\s*([EOW])?"
RX_WGS = re.compile(_DEC + r"\s*[,;/|]?\s+(?:[A-Za-zä]+\s*[:=]?\s*)?" + _DEC_LON, re.I)
RX_WGS_KW = re.compile(r"(?:breite|lat(?:itude)?)\s*[:=]?\s*" + _DEC + r".{0,40}?(?:länge|laenge|lon(?:gitude)?)\s*[:=]?\s*" + _DEC_LON, re.I | re.S)
RX_DMS2 = re.compile(_DMS.pattern + r"\s*[,;/|]?\s*" + _DMS.pattern, re.I)
RX_UTM = re.compile(r"(?:RW|Rechtswert|E(?:asting)?|Ost)\s*[:=]?\s*((?:3[23]\s?)?\d{3}\s?\d{3}(?:[.,]\d+)?)\s*(?:m\b)?[\s,;|/]*"
                    r"(?:HW|Hochwert|N(?:orthing)?|Nord)\s*[:=]?\s*(\d\s?\d{3}\s?\d{3}(?:[.,]\d+)?)", re.I)
RX_LABEL = re.compile(r"\b([A-ZÄÖÜ]{1,4}[- ]?\d{1,3}(?:[-/.]\d{1,3})?)\b")


_NOT_LABEL = re.compile(r"^(RW|HW|UTM|EPSG|NN|NHN|DHHN|ETRS|WGS|GK|KM|CM|MM)\b", re.I)


def _label_before(text, start):
    """Label of a coordinate: the first id-like token on the line before it (BK1, W1-3, P07), else the last words."""
    pre = text[:start].rsplit("\n", 1)[-1]
    for m in RX_LABEL.finditer(pre):
        if not _NOT_LABEL.match(m.group(1)):
            return m.group(1), pre.strip(" |:;-–")
    words = [w for w in re.sub(r"[|:;()]+", " ", pre).split() if not _NOT_LABEL.match(w) and num(w) is None]
    return " ".join(words[:4]), pre.strip(" |:;-–")


def points_from_text(text, source, locator):
    out = []
    zone = 33 if re.search(r"utm\s*(?:zone\s*)?33|25833", text, re.I) else 32
    for line in text.splitlines():
        if not line.strip():
            continue
        hits = []
        for m in RX_WGS_KW.finditer(line):
            hits.append((m.start(), parse_coord(m.group(1) + (m.group(2) or "")), parse_coord(m.group(3) + (m.group(4) or ""))))
        if not hits:
            for m in RX_DMS2.finditer(line):
                parts = _DMS.findall(m.group(0))
                if len(parts) >= 2:
                    f = lambda p: (int(p[0]) + int(p[1]) / 60 + (num(p[2]) or 0) / 3600) * (-1 if p[3].upper() in ("S", "W") else 1)  # noqa: E731
                    hits.append((m.start(), f(parts[0]), f(parts[1])))
        if not hits:
            for m in RX_WGS.finditer(line):
                lat, lon = parse_coord(m.group(1) + (m.group(2) or "")), parse_coord(m.group(3) + (m.group(4) or ""))
                if lat is not None and lon is not None and 35 <= lat <= 72 and -25 <= lon <= 45:    # Europe: avoids stray decimals
                    hits.append((m.start(), lat, lon))
        if not hits:
            for m in RX_UTM.finditer(line):
                ll = _utm_pair(num(m.group(1)), num(m.group(2)), zone)
                if ll:
                    hits.append((m.start(), ll[0], ll[1]))
        for start, lat, lon in hits:
            if not plausible(lat, lon):
                continue
            label, ctx = _label_before(line, start)
            out.append(_pt(label, kind_of(ctx or label), lat, lon, source, locator, **({"description": ctx[:120]} if ctx and ctx != label else {})))
    return out


# ---------------------------------------------------------------- GeoJSON / JSON reference
def points_from_geojson(obj, source):
    out = []
    feats = obj.get("features") if obj.get("type") == "FeatureCollection" else [obj] if obj.get("type") == "Feature" else []
    for i, f in enumerate(feats, 1):
        g, props = f.get("geometry") or {}, f.get("properties") or {}
        label = str(props.get("id") or props.get("name") or props.get("label") or f"Feature {i}")
        name = str(props.get("name") or props.get("bezeichnung") or label)
        kind = kind_of(f"{label} {name}", props.get("kind") or props.get("typ"))
        loc = f"Feature {i}"
        t, c = g.get("type"), g.get("coordinates")
        if t == "Point":
            out.append(_pt(label, kind if kind != "point" else "marker", c[1], c[0], source, loc, name=name))
        elif t in ("Polygon", "LineString"):
            ring = c[0] if t == "Polygon" else c
            if len(ring) > 1 and ring[0] == ring[-1]:
                ring = ring[:-1]
            k = kind if kind in ("boundary", "zone") else ("zone" if t == "Polygon" else "boundary")
            for j, (lon, lat, *_) in enumerate(ring, 1):
                out.append(_pt(f"{label}-{j}", k, lat, lon, source, f"{loc}, Punkt {j}", group=label, name=name))
    return out


def reference_from_json(obj, source):
    """{"anchor"|"origin"|"reference": {lat, lon}, "rotation_deg"?, "name"?} -> ([anchor point], meta)."""
    for key in ("anchor", "origin", "reference", "bezugspunkt"):
        o = obj.get(key)
        if isinstance(o, dict):
            lat, lon = parse_coord(o.get("lat")), parse_coord(o.get("lon"))
            if plausible(lat, lon):
                meta = {k: obj[k] for k in ("rotation_deg", "name") if k in obj}
                return [_pt(o.get("label") or "Bezugspunkt", "anchor", lat, lon, source, key)], meta
    return [], {}


# ---------------------------------------------------------------- file entry point
def _rows_csv(raw):
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
    return [(n, r) for n, r in enumerate(csv.reader(io.StringIO(text), dialect), 1)]


def _sheets_xlsx(raw):
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    for ws in wb.worksheets:
        yield ws.title, [(n, ["" if v is None else str(v) for v in row]) for n, row in enumerate(ws.iter_rows(values_only=True), 1)]


def extract_points(filename, raw):
    """-> {"points": [...], "skipped": [...], "meta": {...}, "activities": [ids]}. Raises ValueError for unreadable files."""
    name = filename.rsplit("/", 1)[-1]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    pts, skipped, meta, texts = [], [], {}, []
    if ext in ("geojson", "json"):
        try:
            obj = json.loads(raw.decode("utf-8-sig"))
        except Exception as e:
            raise ValueError(f"{name}: not valid JSON ({type(e).__name__})")
        if obj.get("type") in ("FeatureCollection", "Feature"):
            pts = points_from_geojson(obj, name)
        else:
            pts, meta = reference_from_json(obj, name)
        texts.append(json.dumps(obj))
    elif ext == "csv":
        rows = _rows_csv(raw)
        pts, skipped = points_from_rows(rows, name)
        texts.append("\n".join(" ".join(r) for _, r in rows))
    elif ext == "xlsx":
        try:
            for title, rows in _sheets_xlsx(raw):
                p, s = points_from_rows(rows, name, f"Blatt „{title}“")
                pts += p; skipped += s
                texts.append("\n".join(" ".join(r) for _, r in rows))
        except Exception as e:
            raise ValueError(f"{name}: Excel file could not be read ({type(e).__name__})")
    elif ext == "docx":
        from docx import Document
        try:
            d = Document(io.BytesIO(raw))
        except Exception as e:
            raise ValueError(f"{name}: Word file could not be read ({type(e).__name__})")
        for ti, t in enumerate(d.tables, 1):
            rows = [(ri, [c.text for c in r.cells]) for ri, r in enumerate(t.rows, 1)]
            p, s = points_from_rows(rows, name, f"Tabelle {ti}")
            pts += p; skipped += s
            texts.append("\n".join(" ".join(r) for _, r in rows))
        para = "\n".join(p.text for p in d.paragraphs)
        pts += points_from_text(para, name, "Text")
        texts.append(para)
    elif ext == "pdf":
        from .outlook import Unsupported, extract_units
        try:
            units = extract_units("pdf", raw)
        except Unsupported as e:
            raise ValueError(f"{name}: {e}")
        for u in units:
            pts += points_from_text(u["text"], name, u["locator"])
            texts.append(u["text"])
    else:
        raise ValueError(f"{name}: unsupported file type (use csv, xlsx, docx, pdf, geojson or json)")
    acts = sorted(set(re.findall(r"\b([A-Z]{1,3}\d{1,2}_[A-Z]{2,5})\b", "\n".join(texts))))
    return {"points": pts, "skipped": skipped, "meta": meta, "activities": acts}
