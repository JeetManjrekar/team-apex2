"""One-command reset: wipe ALL runtime state back to the clean, empty fresh-start state.
Sample data (data/seed, data/demo, data/eval) is never touched; load it explicitly (POST /api/demo/load, tests).
CLI: python -m core.demo reset"""
import shutil

from .store import DATA, UPLOADS, _lock

STATE = ["project", "incidents", "chat_state", "client_docs", "docs", "messages", "notes", "photos", "progress", "schedule", "site_layout", "site_points"]


def reset(keep_metrics: bool = True) -> dict:
    """Delete every runtime JSON (incl. site_layout -> empty schema on next read), uploads and generated exports."""
    removed = []
    with _lock:
        for n in STATE:
            p = DATA / f"{n}.json"
            if p.exists():
                p.unlink(); removed.append(p.name)
        for pat in ("*.docx", "*.pdf", "twin_snapshot.png") + (() if keep_metrics else ("llm_metrics.jsonl",)):
            for p in DATA.glob(pat):
                p.unlink(); removed.append(p.name)
        if UPLOADS.exists():
            for p in UPLOADS.iterdir():
                shutil.rmtree(p) if p.is_dir() else p.unlink()
                removed.append(f"uploads/{p.name}")
        rep = DATA / "reports"
        if rep.exists():
            for p in rep.iterdir():
                shutil.rmtree(p) if p.is_dir() else p.unlink()
                removed.append(f"reports/{p.name}")
        UPLOADS.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "removed": len(removed)}


# ---------------------------------------------------------------- full demo state
ROOT = DATA.parent.parent
SITE_DOCS = ROOT / "site_documents" / "upload"
LAYOUT_FILES = ["project_reference.json", "vermessung_punkte.csv", "bauzeitenplan.xlsx", "baugrundgutachten.pdf",
                "baugrundgutachten.docx", "lageplan.geojson"]
SKIP_PHOTOS = {"site_4d007fe8.jpg"}      # test fixture with a deliberately wrong GPS fix (Tokyo); not part of the story


def load_full() -> dict:
    """Clean slate + everything the "day in the life" needs, offline and in about a second:
    project/schedule/progress, site documents -> generated layout, geotagged photos (stored detections replayed,
    timestamps moved onto the demo day), incident scan."""
    import datetime as dt, json
    from . import agent, layout_suggest, photos, plan, site_twin
    from .llm_settings import today
    from .store import load, save

    reset()
    plan.load_demo()
    layout_suggest.clear_sources()
    from .store import localized                                   # English: the *_en duplicates of the same site documents
    files = [localized(SITE_DOCS / n) for n in LAYOUT_FILES]
    layout_suggest.add_sources([(f.name, f.read_bytes()) for f in files if f.exists()])
    seed = {f"site_{p['id']}.jpg": p for p in json.loads((DATA / "seed" / "photos.json").read_text(encoding="utf-8"))}
    files = [(f.name, "image/jpeg", f.read_bytes()) for f in sorted((SITE_DOCS / "photos").glob("site_*.jpg"))
             if f.name not in SKIP_PHOTOS and f.name in seed]
    recs = photos.ingest(files, replay=seed)
    day = today().isoformat()
    rows = load("photos", [])
    for r in rows:
        if r.get("taken_at"):
            r["taken_at"] = day + r["taken_at"][10:]
    save("photos", rows)
    res = layout_suggest.suggest()
    proj = load("project", {}) or {}
    from .store import project_name
    if project_name(proj):                 # the site documents are a separate fixture; keep one project name in the demo
        res["layout"]["name"] = project_name(proj)
    site_twin.save_layout(res["layout"])
    new = agent.scan()
    return {"ok": True, "photos": len(recs), "zones": len(res["layout"].get("zones", [])), "incidents": len(new)}


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["reset"]:
        print(reset())
    elif sys.argv[1:] == ["full"]:
        print(load_full())
