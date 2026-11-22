"""Live positions of the people using the app (laptop or phone), shown as "You" in the 3D twin and on the map.

Each device reports its browser geolocation (POST /api/site/presence). Positions live in memory only and expire after
PRESENCE_TTL_S: nothing is written to disk, nothing is sent anywhere else. A device may ask for a simulated position
on the site (demo: the real person is not standing on the fictional site); such entries are flagged `simulated`.
"""
from __future__ import annotations

import math
import threading
import time

from . import site_twin

PRESENCE_TTL_S = 90
_lock = threading.Lock()
_devices: dict[str, dict] = {}


def _clean(v, lo, hi):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None


def _site_spot(layout) -> list[float] | None:
    """Where a simulated person stands: the site facilities (office/containers), else the middle of all zones."""
    zones = layout.get("zones") or []
    fac = [z for z in zones if "facilit" in (z.get("kind") or "") or "einricht" in (z.get("name") or "").lower()]
    pick = fac or zones
    pts = [p for z in pick for p in z["polygon"]]
    if not pts:
        return [0.0, 0.0] if layout.get("origin") else None
    return [round(sum(p[0] for p in pts) / len(pts), 2), round(sum(p[1] for p in pts) / len(pts), 2)]


def update(body: dict) -> dict:
    dev = str(body.get("device") or "")[:40]
    if not dev:
        raise ValueError("device id missing")
    rec = {"device": dev, "name": (str(body.get("name") or "You"))[:30], "kind": "phone" if body.get("kind") == "phone" else "laptop",
           "simulated": bool(body.get("simulate")), "at": time.time()}
    if not rec["simulated"]:
        lat, lon = _clean(body.get("lat"), -90, 90), _clean(body.get("lon"), -180, 180)
        if lat is None or lon is None:
            raise ValueError("lat/lon missing or out of range")
        rec.update(lat=lat, lon=lon, accuracy=_clean(body.get("accuracy"), 0, 100000), heading=_clean(body.get("heading"), 0, 360))
    with _lock:
        _devices[dev] = rec
    return enrich(rec)


def remove(dev: str):
    with _lock:
        _devices.pop(dev, None)


def enrich(rec: dict, layout=None) -> dict:
    layout = layout or site_twin.normalise(site_twin.get_layout())
    out = dict(rec)
    o = layout.get("origin")
    if rec.get("simulated"):
        xy = _site_spot(layout)
        out.update(plan_xy=xy, accuracy=4.0, heading=None)
        if xy and o:
            out["lat"], out["lon"] = site_twin.xy_to_gps(xy[0], xy[1], layout)
    elif o:
        out["plan_xy"] = site_twin.gps_to_xy(rec["lat"], rec["lon"], layout)
    if o and out.get("lat") is not None:
        dy = (out["lat"] - o["lat"]) * 111_320
        dx = (out["lon"] - o["lon"]) * 111_320 * math.cos(math.radians(o["lat"]))
        out["distance_m"] = round(math.hypot(dx, dy), 1)
        out["bearing_deg"] = round((math.degrees(math.atan2(dx, dy)) + 360) % 360, 1)   # from the site to the person
    xy = out.get("plan_xy")
    bnd = layout.get("boundary") or [p for z in layout.get("zones", []) for p in z["polygon"]]
    if xy and bnd:
        xs, ys = [p[0] for p in bnd], [p[1] for p in bnd]
        out["on_site"] = min(xs) - 30 <= xy[0] <= max(xs) + 30 and min(ys) - 30 <= xy[1] <= max(ys) + 30
        out["zone"] = site_twin.zone_of(xy, layout)
    else:
        out["on_site"] = False
    out["age_s"] = round(time.time() - rec["at"], 1)
    return out


def active() -> list[dict]:
    now = time.time()
    with _lock:
        for k in [k for k, v in _devices.items() if now - v["at"] > PRESENCE_TTL_S]:
            _devices.pop(k, None)
        recs = list(_devices.values())
    layout = site_twin.normalise(site_twin.get_layout())
    return [enrich(r, layout) for r in recs]
