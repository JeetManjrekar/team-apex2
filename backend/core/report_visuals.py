"""Images for the Word/PDF export, drawn from live data at export time (no screenshots, no stock art).

site_plan(doc)   -> PNG of the site layout: zones, photo positions, AI detections, the document's location highlighted
progress_chart() -> PNG of planned vs actual per schedule activity (colour = traffic light of core.plan)
photo(p)         -> JPEG of a site photo with clean, colour-coded detection boxes and labels
twin_snapshot()  -> the latest 3D twin snapshot the browser uploaded (POST /api/site/snapshot), if recent

All drawing is supersampled 2x and scaled down, so lines and text stay crisp in the PDF.
"""
from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import store


def _out() -> Path:
    return store.DATA / "reports" / "img"


def snapshot_path() -> Path:
    return store.DATA / "twin_snapshot.png"


SNAPSHOT_MAX_AGE_H = 12

INK, MUT, LINE, BG = (30, 36, 48), (110, 118, 132), (222, 226, 232), (247, 248, 250)
ACC, OK, WARN, BAD = (255, 122, 0), (46, 173, 107), (242, 163, 58), (229, 72, 77)
CLASS_COL = {"excavator": (255, 140, 30), "dump_truck": (64, 132, 246), "bulldozer": (168, 85, 247), "person": (229, 72, 77),
             "car": (20, 184, 166)}
LIGHT_COL = {"green": OK, "yellow": WARN, "red": BAD, "grey": (170, 176, 186)}

_FONT_FILES = [("/System/Library/Fonts/Avenir Next.ttc", {"regular": 7, "medium": 5, "demi": 2, "bold": 0}),
               ("/System/Library/Fonts/HelveticaNeue.ttc", {"regular": 0, "medium": 10, "demi": 1, "bold": 1}),
               ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", {"regular": 0, "medium": 0, "demi": 0, "bold": 0})]


def font(size: int, weight: str = "regular"):
    for path, idx in _FONT_FILES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size, index=idx.get(weight, 0))
            except OSError:
                continue
    return ImageFont.load_default()


def _rgba(c, a):
    return (*c[:3], a)


def _hex(s, default=(150, 160, 175)):
    try:
        s = s.lstrip("#")
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return default


def _save(im: Image.Image, name: str, scale: int) -> Path:
    _out().mkdir(parents=True, exist_ok=True)
    if scale > 1:
        im = im.resize((im.width // scale, im.height // scale), Image.LANCZOS)
    p = _out() / name
    im.convert("RGB").save(p, optimize=True)
    return p


def _pill(d, xy, text, fill, fg=(255, 255, 255), f=None, pad=(14, 7), anchor="lm"):
    f = f or font(26, "demi")
    x, y = xy
    w = d.textlength(text, font=f)
    h = f.size + pad[1] * 2
    if anchor == "mm":
        x -= (w + pad[0] * 2) / 2
    d.rounded_rectangle([x, y - h / 2, x + w + pad[0] * 2, y + h / 2], radius=h / 2, fill=fill)
    d.text((x + pad[0], y), text, font=f, fill=fg, anchor="lm")
    return w + pad[0] * 2


def photo_order(photos):
    """Same P-numbers as the 3D twin (frontend/js/site3d.js): by time taken, then id."""
    return sorted(photos, key=lambda p: ((p.get("taken_at") or ""), p["id"]))


# ---------------------------------------------------------------- site plan
def site_plan(doc: dict | None = None, name: str | None = None) -> Path | None:
    """Plan view of the live layout. The document's location (field `location`) is resolved like the twin does it."""
    from . import site_twin
    tw = site_twin.twin()
    L = tw["layout"]
    zones = L.get("zones") or []
    if not zones and not L.get("boundary"):
        return None
    S = 2
    u = lambda v: v * S                                              # design units (final px) -> canvas px
    pts = [p for z in zones for p in z["polygon"]] + [p["plan_xy"] for p in tw["photos"] if p.get("plan_xy")]
    pts += [dd["xy"] for p in tw["photos"] for dd in p.get("detections") or [] if dd.get("xy")]
    pts = pts or list(L.get("boundary") or [])
    PAD = 8                                                          # metres around the content
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs) - PAD, max(xs) + PAD, min(ys) - PAD, max(ys) + PAD
    W, H, M, LEG = 1600, 900, 40, 80
    W2, H2 = u(W), u(H)
    k = min((W - 2 * M) / max(1, x1 - x0), (H - 2 * M - LEG) / max(1, y1 - y0)) * S
    ox = (W2 - (x1 - x0) * k) / 2 - x0 * k
    oy = (H2 - u(LEG) - (y1 - y0) * k) / 2 + y1 * k
    P = lambda x, y: (ox + x * k, oy - y * k)                       # north up

    im = Image.new("RGB", (W2, H2), (255, 255, 255))
    d = ImageDraw.Draw(im, "RGBA")
    d.rectangle([0, 0, W2, H2 - u(LEG)], fill=BG)
    step = 10 * k                                                    # 10 m grid
    gx = ox % step
    while gx < W2:
        d.line([(gx, 0), (gx, H2 - u(LEG))], fill=LINE, width=S)
        gx += step
    gy = oy % step
    while gy < H2 - u(LEG):
        d.line([(0, gy), (W2, gy)], fill=LINE, width=S)
        gy += step
    if L.get("boundary"):
        bnd = [P(*p) for p in L["boundary"]]
        d.line(bnd + [bnd[0]], fill=(150, 156, 168), width=u(2))

    hl_zone, spot = None, None
    if doc:
        loc = (doc.get("fields", {}).get("location") or {}).get("value") or ""
        xy, _how = site_twin.resolve_location(loc, L) if loc else (None, None)
        if xy:
            spot, hl_zone = xy, site_twin.zone_of(xy, L)

    fz, fzs = font(u(19), "demi"), font(u(15), "demi")
    labels = []
    for z in zones:
        poly = [P(*p) for p in z["polygon"]]
        col = ACC if z["id"] == hl_zone else _hex(z.get("color"))
        hl = z["id"] == hl_zone
        d.polygon(poly, fill=_rgba(col, 70 if hl else 38))
        d.line(poly + [poly[0]], fill=col, width=u(4 if hl else 2))
        zs = next((x for x in tw["zones"] if x["id"] == z["id"]), None)
        late = [a for a in (zs or {}).get("activities", []) if a.get("delay_days", 0) > 0.4]
        top = min(p[1] for p in poly)
        cx = sum(p[0] for p in poly) / len(poly)
        labels.append((cx, top, z["name"], late[0]["delay_days"] if late else None, col))

    doc_photos = set((doc or {}).get("photos") or [])
    for p in tw["photos"]:
        for det in p.get("detections") or []:
            if det.get("xy") and p.get("plan_xy"):
                cx, cy = P(*det["xy"])
                c = CLASS_COL.get(det["class"], MUT)
                r = u(6)
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c, outline=(255, 255, 255), width=u(2))
    for i, p in enumerate(photo_order(tw["photos"]), 1):
        if not p.get("plan_xy"):
            continue
        cx, cy = P(*p["plan_xy"])
        mine = p["id"] in doc_photos
        r = u(15 if mine else 12)
        d.ellipse([cx - r - u(3), cy - r - u(3), cx + r + u(3), cy + r + u(3)], fill=(255, 255, 255))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=INK if mine else ACC)
        d.text((cx, cy), f"P{i}", font=font(u(12 if mine else 10), "bold"), fill=(255, 255, 255), anchor="mm")

    if spot:
        cx, cy = P(*spot)
        for rr, a in ((u(34), 45), (u(22), 80)):
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=_rgba(ACC, a))
        d.ellipse([cx - u(8), cy - u(8), cx + u(8), cy + u(8)], fill=ACC, outline=(255, 255, 255), width=u(3))

    # zone labels last: on top of everything, at the top edge of each zone
    for cx, top, txt, late, col in labels:
        tw_ = d.textlength(txt, font=fz)
        y = top + u(20)
        d.rounded_rectangle([cx - tw_ / 2 - u(10), y - u(14), cx + tw_ / 2 + u(10), y + u(14)], radius=u(14), fill=(255, 255, 255, 235))
        d.text((cx, y), txt, font=fz, fill=INK, anchor="mm")
        if late:
            _pill(d, (cx, y + u(32)), f"{late:g} d behind", BAD, f=fzs, pad=(u(9), u(5)), anchor="mm")
    if spot:
        cx, cy = P(*spot)
        _pill(d, (cx + u(26), cy - u(30)), "Location in this document", ACC, f=font(u(14), "demi"), pad=(u(10), u(5)))

    # north arrow + scale bar
    nx, ny = W2 - u(46), u(42)
    d.polygon([(nx, ny - u(20)), (nx - u(11), ny + u(12)), (nx, ny + u(5)), (nx + u(11), ny + u(12))], fill=INK)
    d.text((nx, ny + u(28)), "N", font=font(u(16), "bold"), fill=INK, anchor="mm")
    bar_m = 20
    bx, by = u(28), H2 - u(LEG) - u(26)
    d.rectangle([bx, by, bx + bar_m * k, by + u(6)], fill=INK)
    d.rectangle([bx + bar_m * k / 2, by, bx + bar_m * k, by + u(6)], fill=(255, 255, 255), outline=INK, width=u(1))
    d.text((bx + bar_m * k + u(10), by + u(3)), f"{bar_m} m", font=font(u(14), "medium"), fill=INK, anchor="lm")

    # legend
    ly = H2 - u(LEG) / 2
    d.line([(0, H2 - u(LEG)), (W2, H2 - u(LEG))], fill=LINE, width=u(1))
    x = u(28)
    fl = font(u(15), "medium")
    items = [("dot", ACC, "Photo (GPS)")] + ([("dot", INK, "Photo in this document")] if doc_photos else []) + \
            [("det", CLASS_COL[c], c.replace("_", " ").capitalize()) for c in sorted({dd["class"] for p in tw["photos"] for dd in p.get("detections") or []}) if c in CLASS_COL]
    if spot:
        items.append(("ring", ACC, "Location in this document"))
    for kind, c, label in items:
        r = u(9)
        if kind == "dot":
            d.ellipse([x, ly - r, x + 2 * r, ly + r], fill=c)
        elif kind == "det":
            d.ellipse([x + u(3), ly - u(6), x + u(15), ly + u(6)], fill=c, outline=(255, 255, 255), width=u(2))
        else:
            d.ellipse([x, ly - r, x + 2 * r, ly + r], fill=_rgba(ACC, 90), outline=ACC, width=u(3))
        d.text((x + u(26), ly), label, font=fl, fill=INK, anchor="lm")
        x += u(26) + d.textlength(label, font=fl) + u(30)
    return _save(im, name or f"plan_{(doc or {}).get('id', 'site')}.png", S)


# ---------------------------------------------------------------- progress chart
def progress_chart(name: str = "progress.png") -> Path | None:
    from . import plan
    st = plan.status(with_weather=False)
    acts = [a for a in st["activities"] if a.get("total")]
    if not acts:
        return None
    acts = sorted(acts, key=lambda a: (a["light"] == "grey", a["start"]))[:7]
    S, W, ROW, TOP = 2, 1600, 104, 24
    H = TOP + ROW * len(acts) + 70
    im = Image.new("RGBA", (W * S, H * S), (255, 255, 255, 255))
    d = ImageDraw.Draw(im, "RGBA")
    fn, fv, fs = font(27 * S, "demi"), font(25 * S, "medium"), font(21 * S, "regular")
    lx, bx0, bx1 = 30 * S, 600 * S, 1240 * S
    for i, a in enumerate(acts):
        y = (TOP + i * ROW + ROW / 2) * S
        label = a["name"] if len(a["name"]) <= 38 else a["name"][:36] + "…"
        d.text((lx, y - 16 * S), label, font=fn, fill=INK, anchor="lm")
        d.text((lx, y + 20 * S), f"{a['start'][5:].replace('-', '.')} – {a['end'][5:].replace('-', '.')}", font=fs, fill=MUT, anchor="lm")
        h = 26 * S
        d.rounded_rectangle([bx0, y - h / 2, bx1, y + h / 2], radius=h / 2, fill=(238, 240, 244))
        frac = max(0.0, min(1.0, a["actual"] / a["total"]))
        if frac > 0:
            d.rounded_rectangle([bx0, y - h / 2, bx0 + max(h, (bx1 - bx0) * frac), y + h / 2], radius=h / 2, fill=LIGHT_COL.get(a["light"], OK))
        pf = max(0.0, min(1.0, a["planned"] / a["total"]))
        px = bx0 + (bx1 - bx0) * pf
        d.line([(px, y - h / 2 - 9 * S), (px, y + h / 2 + 9 * S)], fill=INK, width=3 * S)
        status = ("not started" if a["light"] == "grey" else f"{a['delay_days']:g} d behind" if a["delay_days"] >= 0.5 else "on plan")
        d.text((bx1 + 28 * S, y - 16 * S), f"{a['actual']:g} / {a['total']:g} {a['unit']}", font=fv, fill=INK, anchor="lm")
        d.text((bx1 + 28 * S, y + 18 * S), status, font=fs, fill=LIGHT_COL.get(a["light"], MUT) if a["light"] != "green" else OK, anchor="lm")
        if i < len(acts) - 1:
            d.line([(lx, y + ROW * S / 2), (W * S - lx, y + ROW * S / 2)], fill=LINE, width=S)
    ly = (H - 34) * S
    x = lx
    for c, label in ((OK, "on plan"), (WARN, "slightly behind"), (BAD, "behind"), (None, "planned today")):
        if c:
            d.rounded_rectangle([x, ly - 10 * S, x + 30 * S, ly + 10 * S], radius=10 * S, fill=c)
        else:
            d.line([(x + 15 * S, ly - 14 * S), (x + 15 * S, ly + 14 * S)], fill=INK, width=3 * S)
        d.text((x + 42 * S, ly), label, font=fs, fill=MUT, anchor="lm")
        x += 42 * S + d.textlength(label, font=fs) + 40 * S
    d.text((W * S - lx, ly), f"as of {st['as_of']}", font=fs, fill=MUT, anchor="rm")
    return _save(im, name, S)


# ---------------------------------------------------------------- photos
def photo(p: dict) -> Path | None:
    src = store.DATA / p["file"]
    try:
        im = Image.open(src).convert("RGB")
    except Exception:
        return None
    S = 1
    d = ImageDraw.Draw(im, "RGBA")
    lw = max(3, im.width // 260)
    f = font(max(16, im.width // 48), "demi")
    for b in p.get("detections", []) or []:
        c = CLASS_COL.get(b["class"], ACC)
        x0, y0 = b["x"] - b["width"] / 2, b["y"] - b["height"] / 2
        x1, y1 = x0 + b["width"], y0 + b["height"]
        d.rounded_rectangle([x0, y0, x1, y1], radius=lw * 3, outline=c + (255,), width=lw)
        d.rounded_rectangle([x0, y0, x1, y1], radius=lw * 3, fill=c + (26,))
        label = f"{b['class'].replace('_', ' ')} {b['confidence']:.0%}"
        tw = d.textlength(label, font=f)
        th = f.size + lw * 3
        ty = y0 - th - lw if y0 - th - lw > 0 else y0 + lw
        d.rounded_rectangle([x0, ty, x0 + tw + lw * 5, ty + th], radius=th / 2, fill=c + (240,))
        d.text((x0 + lw * 2.5, ty + th / 2), label, font=f, fill=(255, 255, 255), anchor="lm")
    im.thumbnail((1400, 1400))
    _out().mkdir(parents=True, exist_ok=True)
    out = _out() / f"photo_{p['id']}.jpg"
    im.save(out, quality=88)
    return out


def twin_snapshot() -> Path | None:
    snap = snapshot_path()
    if not snap.exists():
        return None
    age_h = (dt.datetime.now().timestamp() - snap.stat().st_mtime) / 3600
    return snap if age_h <= SNAPSHOT_MAX_AGE_H else None
