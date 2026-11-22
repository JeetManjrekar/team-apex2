"""Photo pipeline: EXIF (GPS, time, camera direction), Roboflow detection, categorisation, vision-LLM caption."""
import base64, io, datetime as dt

import exifread, requests
from PIL import Image

from . import llm_bridge, site_twin
from .errors import ApiError
from .store import UPLOADS, load, save, new_id, env, SITE

CATEGORIES = ["progress", "delivery", "defect", "Nachtrag evidence", "obstruction", "safety", "uncategorized"]
# Map detector classes -> category. Edit to match the classes of your Roboflow model.
CLASS_TO_CATEGORY = {
    # classes of the trained Roboflow model (construction-site: car, person, excavator, bulldozer, dump_truck)
    "excavator": "progress", "bulldozer": "progress",
    "dump_truck": "delivery", "car": "delivery",
    # "person" alone says nothing about the category, so it is shown as a detection only.
    # Add e.g. "rock": "Nachtrag evidence", "crack": "defect" once a model for those exists.
}
# Per-class minimum confidence. bulldozer had only 29 training images and fires on people indoors.
MIN_CONF = {"bulldozer": 0.95}
DEFAULT_MIN_CONF = 0.4
# package photo categories -> UI categories
PHOTO_CAT_MAP = {"nachtrag_evidence": "Nachtrag evidence"}


def _deg(v):
    d, m, s = [float(x.num) / float(x.den) for x in v.values]
    return d + m / 60 + s / 3600


def read_exif(raw: bytes):
    tags = exifread.process_file(io.BytesIO(raw), details=False)
    lat = lon = taken = heading = None
    try:
        if "GPS GPSImgDirection" in tags:
            v = tags["GPS GPSImgDirection"].values[0]
            heading = round(float(v.num) / float(v.den), 1) % 360
    except Exception:
        heading = None
    try:
        if "GPS GPSLatitude" in tags and "GPS GPSLongitude" in tags:
            lat, lon = _deg(tags["GPS GPSLatitude"]), _deg(tags["GPS GPSLongitude"])
            if str(tags.get("GPS GPSLatitudeRef")) == "S":
                lat = -lat
            if str(tags.get("GPS GPSLongitudeRef")) == "W":
                lon = -lon
    except Exception:
        lat = lon = None
    t = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
    if t:
        try:
            taken = dt.datetime.strptime(str(t), "%Y:%m:%d %H:%M:%S").isoformat()
        except ValueError:
            pass
    return lat, lon, taken, heading


def read_gps_meta(raw: bytes) -> dict:
    """GPS extras: horizontal accuracy (m) and whether GPSImgDirection is true (T) or magnetic (M) north."""
    tags = exifread.process_file(io.BytesIO(raw), details=False)
    out = {"gps_accuracy_m": None, "heading_ref": None}
    try:
        v = tags.get("GPS GPSHPositioningError") or tags.get("GPS Tag 0x001F")   # older exifread has no name for tag 31
        if v is not None:
            r = v.values[0]
            out["gps_accuracy_m"] = round(float(r.num) / float(r.den), 1) if getattr(r, "den", 1) else None
    except Exception:
        pass
    ref = str(tags.get("GPS GPSImgDirectionRef") or "").strip().upper()
    out["heading_ref"] = ref if ref in ("T", "M") else None
    return out


def true_heading(heading, ref):
    """Magnetic -> true north with MAGNETIC_DECLINATION_DEG (≈ +3.5° in Bavaria, 2026). True / unknown stays as is."""
    if heading is None or ref != "M":
        return heading
    return round((heading + float(env("MAGNETIC_DECLINATION_DEG", "3.5") or 3.5)) % 360, 1)


def detect(raw: bytes):
    """Roboflow hosted inference. None = mock mode (no key configured)."""
    key, model = env("ROBOFLOW_API_KEY"), env("ROBOFLOW_MODEL")
    if not key or not model:
        return None
    try:
        r = requests.post(f"https://detect.roboflow.com/{model}", params={"api_key": key, "confidence": 30},
                          data=base64.b64encode(raw), headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=20)
        r.raise_for_status()
        preds = r.json().get("predictions", [])
    except Exception as e:
        raise ApiError(502, f"Roboflow inference failed: {str(e).replace(key, '***')}")
    return [{"class": p["class"], "confidence": round(p["confidence"], 3), "x": p["x"], "y": p["y"], "width": p["width"], "height": p["height"]}
            for p in preds if p["confidence"] >= MIN_CONF.get(p["class"], DEFAULT_MIN_CONF)]


def categorize(dets):
    best = None
    for d in dets or []:
        c = CLASS_TO_CATEGORY.get(d["class"].lower())
        if c and (best is None or d["confidence"] > best[1]):
            best = (c, d["confidence"])
    return best or ("uncategorized", 0.0)


def ingest(files, replay=None):
    """files: iterable of (filename, mimetype, raw bytes). Returns the new photo records.
    replay: optional {filename: stored record} -> reuse its detections/caption instead of calling the detector and
    vision model (offline demo loading; the stored output came from the same models)."""
    rows, out = load("photos", []), []
    for filename, mime, raw in files:
        try:
            Image.open(io.BytesIO(raw)).verify()
        except Exception:
            raise ApiError(400, f"{filename} is not a valid image")
        pid = new_id()
        (UPLOADS / f"{pid}.jpg").write_bytes(raw)
        lat, lon, taken, heading = read_exif(raw)
        gmeta = read_gps_meta(raw)
        heading = true_heading(heading, gmeta["heading_ref"])
        try:
            img_w, img_h = Image.open(io.BytesIO(raw)).size
        except Exception:
            img_w = img_h = None
        rp = (replay or {}).get(filename)
        dets = [{k: d[k] for k in ("class", "confidence", "x", "y", "width", "height")} for d in rp["detections"]] if rp else detect(raw)
        cat, conf = categorize(dets)
        src, caption, confirm = "model", (rp or {}).get("caption_de", ""), conf < 0.5
        dets_txt = ", ".join(sorted({d["class"] for d in dets or []})) or "keine"
        cls = None if rp else llm_bridge.classify_photo(raw, mime or "image/jpeg", f"photo:{pid}", f"Objekterkennung: {dets_txt}")
        if cls is not None:
            caption, confirm = cls.caption_de, cls.needs_human_confirmation
            if cls.category and not cls.needs_human_confirmation:
                cat, conf, src = PHOTO_CAT_MAP.get(cls.category, cls.category), cls.confidence, "llm"
        rec = {"id": pid, "file": f"uploads/{pid}.jpg", "original_name": filename, "category": cat, "category_source": src,
               "confidence": conf, "detections": dets or [], "mock": dets is None, "caption_de": caption, "needs_confirmation": confirm,
               "lat": lat if lat is not None else SITE["lat"], "lon": lon if lon is not None else SITE["lon"],
               "location_source": "exif" if lat is not None else "site_default",
               "taken_at": taken or dt.datetime.now().isoformat(timespec="seconds"),
               "uploaded_at": dt.datetime.now().isoformat(timespec="seconds"), "note": "",
               "heading": heading, "heading_source": "exif" if heading is not None else None, "img_w": img_w, "img_h": img_h,
               "heading_ref": gmeta["heading_ref"] if heading is not None else None,
               "gps_accuracy_m": gmeta["gps_accuracy_m"] if lat is not None else None,
               "detector": {"name": site_twin.detector_name(), "endpoint": env("ROBOFLOW_MODEL"), "recorded": True} if dets is not None else None,
               "caption_model": site_twin.vision_model_name() if caption else None}
        rows.append(rec)
        out.append(rec)
    save("photos", rows)
    return out


def patch(pid, body):
    rows = load("photos", [])
    for r in rows:
        if r["id"] == pid:
            if "category" in body:
                if body["category"] not in CATEGORIES:
                    raise ApiError(400, "bad category")
                r["category"], r["category_source"], r["needs_confirmation"] = body["category"], "user", False
            if "note" in body:
                r["note"] = body["note"]
            if "lat" in body and "lon" in body:
                r["lat"], r["lon"], r["location_source"] = body["lat"], body["lon"], "user"
            if "site_xy" in body:   # manual position on the site plan (metres), null clears it
                xy = body["site_xy"]
                if xy is not None and not (isinstance(xy, list) and len(xy) == 2 and all(isinstance(v, (int, float)) for v in xy)):
                    raise ApiError(400, "site_xy must be [x, y] in metres or null")
                r["site_xy"] = [round(float(v), 2) for v in xy] if xy else None
            if "heading" in body:   # camera direction, degrees clockwise from plan north, null clears it
                hd = body["heading"]
                if hd is not None and not isinstance(hd, (int, float)):
                    raise ApiError(400, "heading must be a number or null")
                r["heading"] = round(float(hd) % 360, 1) if hd is not None else None
                r["heading_source"] = "user" if hd is not None else None
            if "zone" in body:      # manual zone assignment, null = automatic from position
                r["zone"] = body["zone"] or None
            save("photos", rows)
            return r
    raise ApiError(404, "photo not found")
