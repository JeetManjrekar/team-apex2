import json, os, threading, uuid, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
_lock = threading.Lock()


def env(k, d=""):
    return os.environ.get(k, d)


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


SITE = {
    "lat": float(env("SITE_LAT", "48.15")),
    "lon": float(env("SITE_LON", "11.58")),
    "name": env("SITE_NAME", "Ersatzneubau Brücke BW 7"),
    "client": env("SITE_CLIENT", "Bauherr / Auftraggeber"),
    "manager": env("SITE_MANAGER", "Bauleitung"),
}
