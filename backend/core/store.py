import json, os, threading, uuid, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
_lock = threading.Lock()


def env(k, d=""):
    v = os.environ.get(k, d)
    return d if isinstance(v, str) and v.strip().startswith("#") else v   # "KEY=   # comment" in .env = empty


def load(name, default):
    p = DATA / f"{name}.json"
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def save(name, obj):
    with _lock:
        (DATA / f"{name}.json").write_text(json.dumps(obj, indent=2, ensure_ascii=False))


def new_id():
    return uuid.uuid4().hex[:8]


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def today():
    return dt.date.today().isoformat()


def _project():
    """Demo project master data (data/demo/project.json): the one dataset the LLM cites, the eval and the seed use."""
    try:
        return json.loads((DATA / "demo" / "project.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


_P = _project()
# SITE_* env vars override; empty = taken from data/demo/project.json
SITE = {
    "lat": float(env("SITE_LAT") or _P.get("lat", 48.3069)),
    "lon": float(env("SITE_LON") or _P.get("lon", 11.9081)),
    "name": env("SITE_NAME") or _P.get("name_de", "Ersatzneubau Straßenbrücke BW 12"),
    "client": env("SITE_CLIENT") or _P.get("bauherr", "Bauherr / Auftraggeber"),
    "manager": env("SITE_MANAGER") or (f"{_P['site_manager']}, Bauleitung" if _P.get("site_manager") else "Bauleitung"),
}
