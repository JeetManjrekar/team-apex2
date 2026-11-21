"""Draft site layout from the data collected so far: coordinates in site documents + photo EXIF GPS + schedule ids.

The result is a SUGGESTION. It is returned for review and only saved on request. Every zone / structure says where it
came from (`source`) and is marked `estimated`. Nothing is drawn that no input supports:

  origin     anchor point in a document  ->  median of document points  ->  median of real photo GPS  ->  none
  zones      >= 3 labelled corner points / a GeoJSON polygon per code (W1-1..W1-4 -> zone w1)
             -> a single centre point per code (12 x 12 m box, flagged)  ->  groups of photo positions
  structures single labelled points that are not part of a zone (boreholes, piles, survey points) -> markers
  boundary   boundary points  ->  hull of zones + on-site photos, 10 m margin
  activities schedule ids linked to zones by prefix (W1_BP -> w1); unmatched ones are reported, not guessed

Accumulated inputs live in site_points.json (one entry per uploaded file, de-duplicated by content hash).
"""
from __future__ import annotations

import hashlib
import math
import re
import statistics

from . import geo, site_twin
from .store import load, now, save

OUTLIER_M = 1000.0          # points / photos farther than this from the origin are not part of the site
ANCHOR_CONFLICT_M = 50.0
PHOTO_GROUP_M = 12.0
CENTRE_BOX_M = 12.0
MARGIN_M = 10.0

CODE_NAMES = {"W": "Widerlager", "A": "Achse", "P": "Pfeiler", "BE": "Baustelleneinrichtung", "BF": "Baufeld",
              "L": "Lager", "Z": "Zufahrt", "BA": "Bauabschnitt"}
FACILITY_CODES = {"BE", "L", "LAGER"}
_CODE = re.compile(r"^\s*([A-Za-zÄÖÜäöü]{1,4}\d{0,3})(?=$|[\s_\-/.,]|\d)")
_CORNER = re.compile(r"^\s*([A-Za-zÄÖÜäöü]{1,4}\d{0,3})\s*(?:[-/.]\s*|\s+(?:ecke|corner|eckpunkt|punkt|pt|e)\s*)(\d{1,3})\b", re.I)
PALETTE = ["#3f88c5", "#e07a1f", "#2a9d8f", "#9b5de5", "#d1495b", "#8d99ae", "#43aa8b", "#f4a259"]


# ---------------------------------------------------------------- accumulated sources
def sources():
    return load("site_points", [])


def add_sources(files, keep_empty=True):
    """files: [(filename, raw)] -> {"added": [...], "duplicates": [...], "skipped": [...]}

    keep_empty=False (chat / inbox uploads): files without any coordinate are not stored and not reported as skipped,
    because most office documents simply have none."""
    rows = sources()
    known = {r["hash"] for r in rows}
    added, dup, skipped = [], [], []
    for name, raw in files:
        h = hashlib.sha1(raw).hexdigest()[:12]
        if h in known:
            dup.append(name)
            continue
        try:
            res = geo.extract_points(name, raw)
        except ValueError as e:
            if keep_empty:
                skipped.append({"file": name, "reason": str(e)})
            continue
        if not keep_empty and not res["points"] and not res["meta"]:
            continue
        rec = {"file": name, "hash": h, "added_at": now(), **res}
        rows.append(rec)
        known.add(h)
        added.append({"file": name, "points": len(res["points"]), "skipped_rows": len(res["skipped"]),
                      "activities": res["activities"], "meta": res["meta"]})
        if not res["points"] and not res["meta"]:
            skipped.append({"file": name, "reason": "no coordinates found"})
    save("site_points", rows)
    return {"added": added, "duplicates": dup, "skipped": skipped, "total_files": len(rows)}


def summary():
    """Short state for chat replies: what coordinates are known and whether a layout exists yet."""
    rows = sources()
    lay = load("site_layout", None) or {}
    ph = [p for p in load("photos", []) if p.get("location_source") in ("exif", "user")]
    return {"files_with_coordinates": [{"file": r["file"], "points": len(r["points"])} for r in rows if r["points"] or r.get("meta")],
            "points_total": sum(len(r["points"]) for r in rows), "photos_with_gps": len(ph),
            "layout_empty": not (lay.get("zones") or lay.get("boundary"))}


def clear_sources():
    save("site_points", [])


# ---------------------------------------------------------------- geometry helpers
def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _hull(pts):
    pts = sorted(set((round(p[0], 3), round(p[1], 3)) for p in pts))
    if len(pts) < 3:
        return [list(p) for p in pts]

    def half(seq):
        h = []
        for p in seq:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0]) <= 0:
                h.pop()
            h.append(p)
        return h
    lo, hi = half(pts), half(reversed(pts))
    return [list(p) for p in lo[:-1] + hi[:-1]]


def _grow(poly, m):
    """Push every vertex m metres away from the centroid (good enough for convex site outlines)."""
    cx, cy = sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)
    out = []
    for x, y in poly:
        d = math.hypot(x - cx, y - cy) or 1.0
        out.append([round(x + (x - cx) / d * m, 2), round(y + (y - cy) / d * m, 2)])
    return out


def _box(cx, cy, half):
    return [[round(cx - half, 2), round(cy - half, 2)], [round(cx + half, 2), round(cy - half, 2)],
            [round(cx + half, 2), round(cy + half, 2)], [round(cx - half, 2), round(cy + half, 2)]]


def _code(p):
    """Zone code of a point: explicit GeoJSON group, else the label's leading code (W1-3 -> W1, W1_BP -> W1)."""
    if p.get("group"):
        m = _CODE.match(p["group"])
        return (m.group(1) if m else p["group"]).upper()
    m = _CORNER.match(p["label"]) or _CODE.match(p["label"])
    return m.group(1).upper() if m else None


def _is_corner(p):
    return bool(p.get("group")) or bool(_CORNER.match(p["label"])) or p["kind"] == "zone"


def _zone_name(code, pts):
    names = [re.split(r",|\s+(?:ecke|corner|eckpunkt)\b|\s+-\s+", p.get("name") or p.get("description") or "", flags=re.I)[0].strip()
             for p in pts]
    names = [n for n in names if n and n.upper() != code and not _CORNER.match(n)]
    if names:
        return max(set(names), key=names.count)
    m = re.match(r"([A-Z]+)(\d*)", code)
    if m and m.group(1) in CODE_NAMES:
        return f"{CODE_NAMES[m.group(1)]} {m.group(2)}".strip()
    return code


def _median_ll(pts):
    return {"lat": round(statistics.median(p["lat"] for p in pts), 7), "lon": round(statistics.median(p["lon"] for p in pts), 7)}


# ---------------------------------------------------------------- suggestion
def suggest(sched_ids=None):
    srcs = sources()
    doc_pts = [p for s in srcs for p in s["points"]]
    meta = {}
    for s in srcs:
        meta.update(s.get("meta") or {})
    photos = [p for p in load("photos", []) if p.get("location_source") in ("exif", "user") and p.get("lat") is not None]
    report = {"generated_at": now(), "inputs": {"files": [s["file"] for s in srcs], "document_points": len(doc_pts),
                                                "photos_with_gps": len(photos)},
              "zones": [], "structures": [], "outliers": [], "warnings": [], "unmatched_activities": []}

    # ---- origin
    anchors = [p for p in doc_pts if p["kind"] == "anchor"]
    if anchors:
        origin, osrc = {"lat": anchors[0]["lat"], "lon": anchors[0]["lon"]}, f"anchor point “{anchors[0]['label']}” in {anchors[0]['source']} ({anchors[0]['locator']})"
    elif doc_pts:
        origin, osrc = _median_ll(doc_pts), f"median of {len(doc_pts)} document points"
    elif photos:
        origin, osrc = _median_ll(photos), f"median GPS of {len(photos)} photos"
    else:
        report["origin_source"] = None
        report["warnings"].append("No anchor: no document coordinates and no photo with real GPS. Upload a survey point list, "
                                  "a plan with coordinates, or geotagged photos.")
        return {"layout": site_twin.empty_layout(), "report": report}
    report["origin_source"] = osrc
    lay_geo = {"origin": origin, "rotation_deg": float(meta.get("rotation_deg", 0) or 0)}
    xy = lambda p: site_twin.gps_to_xy(p["lat"], p["lon"], lay_geo)   # noqa: E731

    for a in anchors[1:]:
        d = _dist(xy(a), [0, 0])
        if d > ANCHOR_CONFLICT_M:
            report["warnings"].append(f"Anchor in {a['source']} ({a['locator']}) is {d:.0f} m from the chosen origin – check which one is right.")

    # ---- document points -> plan metres, outliers out
    pts = []
    for p in doc_pts:
        q = dict(p, xy=xy(p))
        if _dist(q["xy"], [0, 0]) > OUTLIER_M:
            report["outliers"].append({"kind": "document point", "label": p["label"], "source": p["source"], "locator": p["locator"],
                                       "distance_m": round(_dist(q["xy"], [0, 0]))})
        else:
            pts.append(q)

    # ---- photos -> plan metres, outliers out
    ph = []
    for p in photos:
        pxy = xy(p)
        d = _dist(pxy, [0, 0])
        if d > OUTLIER_M:
            report["outliers"].append({"kind": "photo", "label": p.get("original_name") or p["id"], "photo": p["id"], "distance_m": round(d)})
        else:
            ph.append({"id": p["id"], "xy": pxy, "name": p.get("original_name")})
    if ph and pts:
        mx, my = statistics.median(q["xy"][0] for q in ph), statistics.median(q["xy"][1] for q in ph)
        if math.hypot(mx, my) > 300:
            report["warnings"].append(f"The photos are centred {math.hypot(mx, my):.0f} m from the document origin – they may belong to another site.")

    # ---- zones from labelled corners / polygons
    groups = {}
    for p in pts:
        if p["kind"] in ("anchor", "boundary"):
            continue
        c = _code(p)
        if c and _is_corner(p):
            groups.setdefault(c, []).append(p)
    zones, used = [], set()
    for code, gp in sorted(groups.items()):
        poly = _hull([p["xy"] for p in gp])
        if len(poly) < 3:
            continue
        files = sorted({p["source"] for p in gp})
        zones.append({"id": code.lower(), "name": _zone_name(code, gp), "polygon": poly, "color": PALETTE[len(zones) % len(PALETTE)],
                      "kind": "facilities" if code in FACILITY_CODES else "work", "activities": [],
                      "source": f"{len(gp)} corner points from {', '.join(files)}", "estimated": True})
        used.update(id(p) for p in gp)

    # ---- single points: centre of an unknown zone code -> box; everything else -> marker
    zone_codes = {z["id"].upper() for z in zones}
    singles = [p for p in pts if id(p) not in used and p["kind"] not in ("anchor", "boundary")]
    centres, markers = {}, []
    for p in singles:
        c = _code(p)
        if c and c in zone_codes:
            continue                                  # e.g. schedule row W1_BP at the W1 centre: confirms the zone, adds nothing
        if c and re.fullmatch(r"(W|A|P|BE|BA)\d{0,2}", c) and p["kind"] != "marker":
            centres.setdefault(c, []).append(p)
        else:
            markers.append(p)
    for code, gp in sorted(centres.items()):
        cx, cy = statistics.mean(p["xy"][0] for p in gp), statistics.mean(p["xy"][1] for p in gp)
        zones.append({"id": code.lower(), "name": _zone_name(code, gp), "polygon": _box(cx, cy, CENTRE_BOX_M / 2),
                      "color": PALETTE[len(zones) % len(PALETTE)], "kind": "facilities" if code in FACILITY_CODES else "work",
                      "activities": [], "source": f"centre point only ({gp[0]['source']}, {gp[0]['locator']}); size is a placeholder",
                      "estimated": True})
        report["warnings"].append(f"Zone {code}: only a centre point is known, drawn as a {CENTRE_BOX_M:.0f} m box. Add corner points for the real outline.")

    # ---- markers (de-duplicated by label within 1 m)
    structs = []
    unlabelled = [p for p in markers if not p["label"].strip()]
    markers = [p for p in markers if p["label"].strip()]
    report["unlabelled_points"] = [{"source": p["source"], "locator": p["locator"]} for p in unlabelled]
    if unlabelled:
        report["warnings"].append(f"{len(unlabelled)} coordinate(s) without a name were ignored "
                                  f"({', '.join(sorted({p['source'] for p in unlabelled}))}).")
    for p in markers:
        if any(s["name"] == p["label"] and _dist([s["x"], s["y"]], p["xy"]) < 1.0 for s in structs):
            continue
        sid = re.sub(r"[^a-z0-9]+", "_", p["label"].lower()).strip("_") or f"pt{len(structs) + 1}"
        while any(s["id"] == sid for s in structs):
            sid += "_"
        structs.append({"id": sid, "kind": "marker", "name": p["label"], "x": p["xy"][0], "y": p["xy"][1],
                        **({"note": p["description"]} if p.get("description") else {}),
                        "source": f"{p['source']} ({p['locator']})", "estimated": True})

    # ---- no zones from documents: group photo positions
    if not zones and ph:
        groups_ph = []
        for q in ph:
            g = next((g for g in groups_ph if any(_dist(q["xy"], o["xy"]) <= PHOTO_GROUP_M for o in g)), None)
            g.append(q) if g is not None else groups_ph.append([q])
        for i, g in enumerate(groups_ph, 1):
            xs, ys = [q["xy"][0] for q in g], [q["xy"][1] for q in g]
            pad = 6.0
            zones.append({"id": f"area{i}", "name": f"Bereich {i} (aus Fotos)",
                          "polygon": [[min(xs) - pad, min(ys) - pad], [max(xs) + pad, min(ys) - pad], [max(xs) + pad, max(ys) + pad], [min(xs) - pad, max(ys) + pad]],
                          "color": PALETTE[(i - 1) % len(PALETTE)], "kind": "work", "activities": [],
                          "source": f"positions of {len(g)} photo(s)", "estimated": True})

    # ---- boundary
    bpts = [p for p in pts if p["kind"] == "boundary"]
    if len(bpts) >= 3:
        boundary, bsrc = _hull([p["xy"] for p in bpts]), f"{len(bpts)} boundary points from {', '.join(sorted({p['source'] for p in bpts}))}"
    else:
        allp = [v for z in zones for v in z["polygon"]] + [q["xy"] for q in ph] + [[s["x"], s["y"]] for s in structs]
        boundary, bsrc = (_grow(_hull(allp), MARGIN_M), f"outline of zones/photos/markers + {MARGIN_M:.0f} m") if len(allp) >= 3 else ([], None)
    outside = [q for q in ph if boundary and not site_twin.point_in_poly(q["xy"][0], q["xy"][1], boundary)]
    for q in outside:
        report["warnings"].append(f"Photo {q['name'] or q['id']} lies outside the boundary.")

    # ---- activities by code prefix
    ids = set(sched_ids if sched_ids is not None else [a["id"] for a in load("schedule", []) if isinstance(a, dict) and a.get("id")])
    ids |= {a for s in srcs for a in s.get("activities", [])}
    for z in zones:
        z["activities"] = sorted(a for a in ids if a.upper().startswith(z["id"].upper() + "_"))
    linked = {a for z in zones for a in z["activities"]}
    report["unmatched_activities"] = sorted(ids - linked)

    layout = {"name": meta.get("name") or "", "origin": origin, "rotation_deg": lay_geo["rotation_deg"],
              "boundary": boundary, "zones": zones, "roads": [], "gates": [], "structures": structs,
              "generated": {"at": report["generated_at"], "by": "layout_suggest", "origin_source": osrc, "boundary_source": bsrc}}
    site_twin.normalise(layout)                       # the draft must be saveable as-is
    report["boundary_source"] = bsrc
    report["zones"] = [{"id": z["id"], "name": z["name"], "source": z["source"], "activities": z["activities"]} for z in zones]
    report["structures"] = [{"id": s["id"], "name": s["name"], "source": s["source"]} for s in structs]
    report["photos_on_site"] = len(ph)
    return {"layout": layout, "report": report}
