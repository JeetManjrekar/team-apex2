"""Construction-site digital twin: site layout, photo placement and per-zone evidence.

Coordinates
-----------
Everything on the plan is in local metres: x = east, y = north, origin (0, 0).
If the layout has an `origin` {lat, lon}, GPS positions are projected onto the plan (equirectangular, accurate to
centimetres over a construction site) and plan positions can be converted back to GPS. Without an origin the site
works purely in relative coordinates; any point in the layout may be given either as [x, y] or as {"lat", "lon"}.

Photo position priority
-----------------------
1. `site_xy` set by the user on the plan                       -> method "plan"
2. GPS from EXIF / set by the user (location_source exif|user)  -> method "gps"
3. otherwise the photo is "unplaced". The site-default GPS fallback is NOT treated as a real position.

Detection positions
-------------------
The detector only gives pixel boxes. With a camera heading (EXIF GPSImgDirection or set on the plan) each box is
projected with a pinhole model: bearing from the box centre column, distance from the box height and a typical
object height per class. Without a heading, objects are drawn in a small ring around the camera and flagged as such.
Every placed object carries `position_method` so the UI never presents an estimate as a survey.
"""
import math, os, datetime as dt
from functools import lru_cache

from PIL import Image

from . import plan
from .store import DATA, load, save, SITE, env

EARTH_M_PER_DEG_LAT = 110_540.0
EARTH_M_PER_DEG_LON = 111_320.0
HFOV_DEG = float(os.environ.get("CAMERA_HFOV_DEG", "65"))      # typical phone main camera
# typical object heights (m) used for the pinhole distance estimate
OBJECT_HEIGHT_M = {"excavator": 3.2, "bulldozer": 3.0, "dump_truck": 3.5, "car": 1.5, "person": 1.75, "tractor": 2.8}
MIN_DIST_M, MAX_DIST_M = 3.0, 80.0


def detector_name():
    return env("DETECTOR_NAME", "RF-DETR Small")


def vision_model_name():
    from .llm_bridge import SETTINGS
    return env("VISION_MODEL_NAME", SETTINGS.model)


# ---------------------------------------------------------------- geometry
def gps_to_xy(lat, lon, layout):
    o = layout.get("origin")
    if not o:
        return None
    x = (lon - o["lon"]) * math.cos(math.radians(o["lat"])) * EARTH_M_PER_DEG_LON
    y = (lat - o["lat"]) * EARTH_M_PER_DEG_LAT
    r = math.radians(layout.get("rotation_deg", 0))   # plan rotated clockwise against true north by rotation_deg
    return [round(x * math.cos(r) - y * math.sin(r), 3), round(x * math.sin(r) + y * math.cos(r), 3)]


def xy_to_gps(x, y, layout):
    o = layout.get("origin")
    if not o:
        return None
    r = math.radians(layout.get("rotation_deg", 0))
    ex, ny = x * math.cos(r) + y * math.sin(r), -x * math.sin(r) + y * math.cos(r)
    return [round(o["lat"] + ny / EARTH_M_PER_DEG_LAT, 7),
            round(o["lon"] + ex / (math.cos(math.radians(o["lat"])) * EARTH_M_PER_DEG_LON), 7)]


def _pt(p, layout):
    if isinstance(p, dict):
        xy = gps_to_xy(p["lat"], p["lon"], layout)
        if xy is None:
            raise ValueError("layout point given as GPS but the layout has no origin")
        return xy
    return [float(p[0]), float(p[1])]


def point_in_poly(x, y, poly):
    inside, j = False, len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------- layout
def empty_layout():
    """Clean empty schema: no boundary, zones, roads, gates or structures, no origin. Nothing is pre-populated."""
    return {"name": "", "origin": None, "rotation_deg": 0, "boundary": [], "zones": [], "roads": [], "gates": [], "structures": []}


default_layout = empty_layout   # fresh start and reset both give the empty schema; sample layout: data/seed/site_layout.json


def get_layout():
    """Stored layout, or the empty schema. Reading never writes: no site_layout.json appears until the user saves one."""
    return load("site_layout", None) or empty_layout()


def normalise(layout):
    """Validates a layout and converts every GPS point to plan metres. Raises ValueError with a readable message."""
    if not isinstance(layout, dict):
        raise ValueError("layout must be an object")
    lay = dict(layout)
    o = lay.get("origin")
    if o is not None and not (isinstance(o, dict) and {"lat", "lon"} <= set(o)):
        raise ValueError("origin must be {lat, lon} or null")
    lay.setdefault("boundary", [])
    if not isinstance(lay["boundary"], list) or (lay["boundary"] and len(lay["boundary"]) < 3):
        raise ValueError("boundary needs at least 3 points (or none for an empty layout)")
    lay["boundary"] = [_pt(p, lay) for p in lay["boundary"]]
    zones = []
    for i, z in enumerate(lay.get("zones", [])):
        if len(z.get("polygon", [])) < 3:
            raise ValueError(f"zone {z.get('id', i)} needs a polygon with at least 3 points")
        zones.append(dict(z, id=str(z.get("id") or f"z{i}"), name=z.get("name") or f"Zone {i + 1}",
                          polygon=[_pt(p, lay) for p in z["polygon"]], activities=list(z.get("activities", []))))
    lay["zones"] = zones
    lay["roads"] = [dict(r, points=[_pt(p, lay) for p in r.get("points", [])]) for r in lay.get("roads", [])]
    lay["gates"] = [dict(g, at=_pt(g["at"], lay)) for g in lay.get("gates", [])]
    structs = []
    for s in lay.get("structures", []):
        s = dict(s)
        if "at" in s:   # GPS or [x, y] alternative to x/y
            s["x"], s["y"] = _pt(s.pop("at"), lay)
        structs.append(s)
    lay["structures"] = structs
    return lay


# ---------------------------------------------------------------- photos & detections
@lru_cache(maxsize=512)
def _img_size(path, mtime):
    with Image.open(path) as im:
        return im.size


def image_size(p):
    if p.get("img_w") and p.get("img_h"):
        return p["img_w"], p["img_h"]
    path = DATA / p["file"]
    try:
        return _img_size(str(path), path.stat().st_mtime)
    except Exception:
        return None


def photo_position(p, layout):
    if p.get("site_xy"):
        return [float(p["site_xy"][0]), float(p["site_xy"][1])], "plan"
    if p.get("location_source") in ("exif", "user") and p.get("lat") is not None:
        xy = gps_to_xy(p["lat"], p["lon"], layout)
        if xy:
            return xy, "gps"
    return None, "unplaced"


def place_detections(p, pos, layout):
    size = image_size(p)
    heading = p.get("heading")
    out = []
    dets = p.get("detections") or []
    for i, d in enumerate(dets):
        item = {"index": i, "class": d["class"], "confidence": d["confidence"],
                "bbox": {k: d[k] for k in ("x", "y", "width", "height")}}
        if pos is not None:
            if heading is not None and size:
                w, h = size
                f_px = (w / 2) / math.tan(math.radians(HFOV_DEG / 2))
                bearing = heading + math.degrees(math.atan(((d["x"] - w / 2)) / f_px))
                obj_h = OBJECT_HEIGHT_M.get(d["class"].lower(), 2.5)
                dist = max(MIN_DIST_M, min(MAX_DIST_M, obj_h * f_px / max(d["height"], 1)))
                # bearing is clockwise from plan-north
                x = pos[0] + dist * math.sin(math.radians(bearing))
                y = pos[1] + dist * math.cos(math.radians(bearing))
                item.update(xy=[round(x, 2), round(y, 2)], bearing_deg=round(bearing % 360, 1), distance_m=round(dist, 1),
                            position_method="pinhole_estimate")
            else:
                ang = 2 * math.pi * i / max(len(dets), 1)
                r = 5.0 + 1.5 * (i % 2)
                item.update(xy=[round(pos[0] + r * math.sin(ang), 2), round(pos[1] + r * math.cos(ang), 2)],
                            position_method="near_camera")
            if layout.get("origin"):
                item["gps_estimate"] = xy_to_gps(item["xy"][0], item["xy"][1], layout)
        out.append(item)
    return out


def zone_of(xy, layout):
    if xy is None:
        return None
    for z in layout["zones"]:
        if point_in_poly(xy[0], xy[1], z["polygon"]):
            return z["id"]
    return None


def twin():
    layout = normalise(get_layout())
    photos = load("photos", [])
    docs = load("docs", [])
    sched_rows = {r["id"]: r for r in plan.status(with_weather=False)["activities"]}
    progress = load("progress", [])
    det_default = detector_name()
    zone_ids = {z["id"] for z in layout["zones"]}

    placed = []
    for p in photos:
        pos, method = photo_position(p, layout)
        zone = p.get("zone") if p.get("zone") in zone_ids else zone_of(pos, layout)
        size = image_size(p)
        rec = {
            "id": p["id"], "evidence_id": f"photo:{p['id']}", "file": p["file"],
            "ann_file": p["file"].replace(".jpg", "_ann.jpg") if (DATA / p["file"].replace(".jpg", "_ann.jpg")).exists() else None,
            "original_name": p.get("original_name"), "category": p.get("category"), "taken_at": p.get("taken_at"),
            "lat": p.get("lat"), "lon": p.get("lon"), "location_source": p.get("location_source"),
            "gps_is_real": p.get("location_source") in ("exif", "user"),
            "heading": p.get("heading"), "heading_source": p.get("heading_source"),
            "img_w": size[0] if size else None, "img_h": size[1] if size else None,
            "mock": bool(p.get("mock")),
            "detector": p.get("detector") or {"name": det_default, "recorded": False},
            "caption": p.get("caption_de") or "", "caption_model": p.get("caption_model") if p.get("caption_de") else None,
            "plan_xy": pos, "position_method": method, "zone": zone, "zone_source": "user" if p.get("zone") in zone_ids else ("auto" if zone else None),
            "plan_gps": xy_to_gps(pos[0], pos[1], layout) if pos and layout.get("origin") else None,
            "detections": place_detections(p, pos, layout),
            "docs": [{"id": d["id"], "title": d.get("title"), "type": d.get("type"), "status": d.get("status")}
                     for d in docs if p["id"] in (d.get("photos") or [])],
        }
        placed.append(rec)

    zones = []
    for z in layout["zones"]:
        zp = [p for p in placed if p["zone"] == z["id"]]
        machinery = {}
        for p in zp:
            for d in p["detections"]:
                m = machinery.setdefault(d["class"], {"class": d["class"], "count": 0, "max_confidence": 0.0, "photos": set()})
                m["count"] += 1
                m["max_confidence"] = max(m["max_confidence"], d["confidence"])
                m["photos"].add(p["evidence_id"])
        acts = [sched_rows[a] for a in z["activities"] if a in sched_rows]
        timeline = [{"date": p["taken_at"], "kind": "photo", "evidence_id": p["evidence_id"],
                     "text": f"{p['original_name']}: " + (", ".join(f"{d['class']} {round(d['confidence'] * 100)}%" for d in p["detections"]) or "no detections")}
                    for p in zp if p.get("taken_at")]
        for e in progress:
            if e["activity"] in z["activities"]:
                row = sched_rows.get(e["activity"], {})
                timeline.append({"date": e["date"], "kind": "progress", "evidence_id": f"sched:{e['activity']}",
                                 "text": f"{row.get('name', e['activity'])}: +{e['qty']:g} {row.get('unit', '')}" + (f" – {e['note']}" if e.get("note") else "")})
        timeline.sort(key=lambda t: t["date"], reverse=True)
        evidence = [{"id": p["evidence_id"], "kind": "photo", "label": p["original_name"]} for p in zp]
        evidence += [{"id": f"sched:{a['id']}", "kind": "schedule", "label": a["name"]} for a in acts]
        seen = set()
        for p in zp:
            for d in p["docs"]:
                if d["id"] not in seen:
                    seen.add(d["id"])
                    evidence.append({"id": f"doc-{d['id']}", "kind": "document", "label": f"{d['title']} ({d['status']})"})
        zones.append({"id": z["id"], "photos": [p["id"] for p in zp], "activities": acts,
                      "machinery": sorted(({**m, "photos": sorted(m["photos"])} for m in machinery.values()), key=lambda m: -m["count"]),
                      "timeline": timeline, "evidence": evidence})

    return {"layout": layout, "photos": placed, "zones": zones, "schedule": list(sched_rows.values()),
            "models": {"detector": det_default, "vision": vision_model_name()},
            "camera": {"hfov_deg": HFOV_DEG, "object_height_m": OBJECT_HEIGHT_M},
            "generated_at": dt.datetime.now().isoformat(timespec="seconds")}


def save_layout(layout):
    normalise(layout)          # validate only; store what the user wrote (GPS points stay GPS)
    save("site_layout", layout)
    return layout
