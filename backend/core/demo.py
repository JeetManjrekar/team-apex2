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
        for pat in ("*.docx", "*.pdf") + (() if keep_metrics else ("llm_metrics.jsonl",)):
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


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["reset"]:
        print(reset())
