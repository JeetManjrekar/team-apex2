import datetime as dt
from pathlib import Path
from docx import Document
from docx.shared import Cm
from PIL import Image, ImageDraw

def annotated(rec, data_dir: Path) -> Path:
    src = data_dir / rec["file"]
    im = Image.open(src).convert("RGB"); d = ImageDraw.Draw(im)
    for b in rec.get("detections", []):
        x0, y0, x1, y1 = b["x"] - b["width"] / 2, b["y"] - b["height"] / 2, b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
        d.rectangle([x0, y0, x1, y1], outline="red", width=4)
        d.text((x0 + 4, y0 + 4), f'{b["class"]} {b["confidence"]:.0%}', fill="red")
    out = data_dir / "uploads" / f'{rec["id"]}_ann.jpg'
    im.thumbnail((1400, 1400)); im.save(out, quality=85)
    return out

def build_report(rows, site, out: Path, data_dir: Path) -> Path:
    doc = Document()
    doc.add_heading("Photo documentation (draft)", 0)
    doc.add_paragraph(f'Site: {site["name"]}   |   Created: {dt.datetime.now():%d.%m.%Y %H:%M}   |   Photos: {len(rows)}')
    cats = {}
    for r in rows: cats.setdefault(r["category"], []).append(r)
    doc.add_heading("Summary", 1)
    for c, rs in sorted(cats.items()): doc.add_paragraph(f"{c}: {len(rs)}", style="List Bullet")
    for c, rs in sorted(cats.items()):
        doc.add_heading(c, 1)
        for r in sorted(rs, key=lambda r: r["taken_at"]):
            try: doc.add_picture(str(annotated(r, data_dir)), width=Cm(13))
            except Exception: doc.add_paragraph("[image missing]")
            src = "photo GPS" if r["location_source"] == "exif" else ("manually set" if r["location_source"] == "user" else "site default, no GPS in photo")
            dets = ", ".join(f'{b["class"]} ({b["confidence"]:.0%})' for b in r["detections"]) or "none"
            who = "set by user" if r["category_source"] == "user" else f'suggested by model ({r["confidence"]:.0%})'
            doc.add_paragraph(f'{r["original_name"]}  |  {r["taken_at"]}\nLocation: {r["lat"]:.5f}, {r["lon"]:.5f} ({src})\n'
                              f'Category: {r["category"]} ({who})\nDetected: {dets}' + (f'\nNote: {r["note"]}' if r["note"] else ""))
    doc.add_paragraph("\nDraft created with AI assistance, checked by: ____________   Date: ________")
    doc.save(out)
    return out
