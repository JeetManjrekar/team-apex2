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


def project() -> dict:
    """Master data of the LOADED project (data/project.json, written by plan.load_demo / cleared by demo.reset).
    Empty on a fresh install or after a reset, so nothing project-specific leaks into prompts, greetings or exports."""
    p = load("project", {})
    return p if isinstance(p, dict) else {}


class _Site(dict):
    """Site header data, resolved at access time from the loaded project (env SITE_* overrides win). Neutral when none is loaded."""
    def _resolve(self):
        P = project()
        return {
            "lat": float(env("SITE_LAT") or P.get("lat", 48.3069)),
            "lon": float(env("SITE_LON") or P.get("lon", 11.9081)),
            "name": env("SITE_NAME") or P.get("name_de", ""),
            "client": env("SITE_CLIENT") or P.get("bauherr", ""),
            "manager": env("SITE_MANAGER") or (f"{P['site_manager']}, Bauleitung" if P.get("site_manager") else ""),
        }
    def __getitem__(self, k): return self._resolve()[k]
    def get(self, k, d=None): return self._resolve().get(k, d)
    def keys(self): return self._resolve().keys()
    def items(self): return self._resolve().items()
    def values(self): return self._resolve().values()
    def __iter__(self): return iter(self._resolve())
    def __len__(self): return len(self._resolve())
    def copy(self): return self._resolve()


SITE = _Site()
