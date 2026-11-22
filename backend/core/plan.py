"""Plan vs actual, weather and early warnings."""
import csv, datetime as dt, json, time
import requests
from .llm_settings import today as demo_today
from .store import DATA, load, save, SITE, localized, pick
from .i18n import T, get_lang

WMO = {0: "klar", 1: "überwiegend klar", 2: "teilweise bewölkt", 3: "bedeckt", 45: "Nebel", 48: "Reifnebel",
       51: "leichter Niesel", 53: "Niesel", 55: "starker Niesel", 61: "leichter Regen", 63: "Regen", 65: "starker Regen",
       66: "gefrierender Regen", 67: "gefrierender Regen", 71: "leichter Schneefall", 73: "Schneefall", 75: "starker Schneefall",
       77: "Schneegriesel", 80: "Regenschauer", 81: "Regenschauer", 82: "starke Regenschauer", 85: "Schneeschauer",
       86: "Schneeschauer", 95: "Gewitter", 96: "Gewitter mit Hagel", 99: "Gewitter mit Hagel"}
WMO_EN = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "rime fog",
          51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
          66: "freezing rain", 67: "freezing rain", 71: "light snowfall", 73: "snowfall", 75: "heavy snowfall",
          77: "snow grains", 80: "rain showers", 81: "rain showers", 82: "heavy rain showers", 85: "snow showers",
          86: "snow showers", 95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail"}
_cache = {"t": 0, "data": None}


def weather():
    """Daily weather for the site (7 past + 7 forecast days), keyed by ISO date. None if offline."""
    if _cache["data"] and time.time() - _cache["t"] < 1800:
        return _localized(_cache["data"])
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=8, params={
            "latitude": SITE["lat"], "longitude": SITE["lon"], "timezone": "Europe/Berlin", "past_days": 7, "forecast_days": 7,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code,wind_speed_10m_max"})
        r.raise_for_status()
        d = r.json()["daily"]
        out = {}
        for i, day in enumerate(d["time"]):
            out[day] = {"tmax": d["temperature_2m_max"][i], "tmin": d["temperature_2m_min"][i],
                        "rain": d["precipitation_sum"][i], "wind": d["wind_speed_10m_max"][i],
                        "code": d["weather_code"][i]}
        _cache.update(t=time.time(), data=out)
        return _localized(out)
    except Exception:
        return None


def _localized(data):
    """Weather rows with `text` in the current language (the cache keeps the language-free WMO code)."""
    wmo = WMO if get_lang() == "de" else WMO_EN
    return {day: dict(w, text=wmo.get(w["code"], "?")) for day, w in data.items()}


def weather_text(w):
    return T("v_weather_text", **w)


# ---------------------------------------------------------------- demo data: BW 12 Mühlbach (backend/data/demo)
# One dataset for the whole app: the same Bauzeitenplan, drilling list and Baugrundgutachten the LLM cites.
DEMO_DIR = DATA / "demo"
# activities shown in plan vs actual: measurable drilling output, plus the concreting days (frost check)
_PLAN_IDS = ("W1_BP", "A1_BP", "A2_BP", "W2_BP", "W1_BET", "A1_BET", "A2_BET", "W2_BET")


def demo_path(*parts):
    """A demo file in the request language: <name>_en.<ext> for English when it exists, else the German original."""
    return localized(DEMO_DIR.joinpath(*parts))


def _demo_schedule():
    rows = []
    with demo_path("schedule", "bauzeitenplan.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["id"] not in _PLAN_IDS:
                continue
            per_day, days = float(r["planned_output_per_day"] or 0), int(r["duration_days"] or 1)
            qty = per_day * days if per_day else 1
            rows.append({"id": r["id"], "name": pick(r, "name"), "unit": r["unit"] or ("activity" if get_lang() == "en" else "Vorgang"), "total": qty,
                         "start": r["start_planned"], "end": r["end_planned"], "concrete": r["weather_sensitive"] == "1",
                         "zone": r["zone_id"], "crew_role": r["crew_role"]})
    return rows


def _demo_progress():
    """Drilling metres per pile and day from the Polier's drilling list (activity = W1_BP etc. by zone)."""
    act = {"W1": "W1_BP", "A1": "A1_BP", "A2": "A2_BP", "W2": "W2_BP"}
    out = []
    with demo_path("drilling", "drilling_times.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            m = float(r["depth_reached_m"] or 0)
            if m and r["zone_id"] in act:
                out.append({"date": r["date"], "activity": act[r["zone_id"]], "qty": m, "note": f"{r['pile_id']}: {pick(r, 'note')}"})
    return out


def _demo_client_docs():
    from .sources import pages
    md = demo_path("source_documents", "baugrundgutachten_auszug.md").read_text(encoding="utf-8")
    loc = "Geotechnical report BW 12, page {n}" if get_lang() == "en" else "Baugrundgutachten BW 12, Seite {n}"
    return [{"id": f"doc:bgg@p{n}", "locator": loc.format(n=n), "excerpt": t} for n, t in pages(md)]


def load_demo():
    save("project", json.loads(demo_path("project.json").read_text(encoding="utf-8")))
    save("client_docs", _demo_client_docs())
    save("schedule", _demo_schedule())
    save("progress", _demo_progress())


def _d(s):
    return dt.date.fromisoformat(s)


def status(as_of=None, with_weather=True):
    sched, prog = load("schedule", []), load("progress", [])
    if not as_of:
        as_of = demo_today().isoformat()     # DEMO_TODAY pins the demo day; empty = real date
    a = _d(as_of)
    rows, alerts = [], []
    for s in sched:
        start, end = _d(s["start"]), _d(s["end"])
        days = (end - start).days + 1
        per_day = s["total"] / days
        elapsed = max(0, min(days, (a - start).days + 1))
        planned = round(per_day * elapsed, 2)
        actual = round(sum(p["qty"] for p in prog if p["activity"] == s["id"] and p["date"] <= as_of), 2)
        delay = round((planned - actual) / per_day, 1) if per_day else 0
        light = "green" if delay < 0.5 else ("yellow" if delay < 2 else "red")
        if elapsed == 0:
            light = "grey"
        row = dict(s, planned=planned, actual=actual, per_day=round(per_day, 2), delay_days=delay, light=light)
        rows.append(row)
        if light == "red":
            alerts.append({"kind": "delay", "level": "red", "activity": s["id"],
                           "text": T("al_delay", name=s["name"], delay=delay, p=planned, a=actual, unit=s["unit"]),
                           "suggest": "behinderung", "suggest_label": "Draft Behinderungsanzeige"})
        elif light == "yellow":
            alerts.append({"kind": "delay", "level": "yellow", "activity": s["id"],
                           "text": T("al_delay_watch", name=s["name"], delay=delay), "suggest": None})
    w = weather() if with_weather else None
    if w:
        for s in sched:
            if not s.get("concrete"):
                continue
            cold = [(d, v) for d, v in w.items() if s["start"] <= d <= s["end"] and v["tmin"] <= 2]
            if cold:
                d, v = min(cold, key=lambda x: x[1]["tmin"])
                alerts.append({"kind": "frost", "level": "yellow", "activity": s["id"],
                               "text": T("al_frost", name=s["name"], start=s["start"], end=s["end"], d=d, tmin=v["tmin"]),
                               "suggest": "bedenken", "suggest_label": "Draft Bedenkenanzeige (winter measures)",
                               "weather_date": d, "tmin": v["tmin"]})
    return {"as_of": as_of, "activities": rows, "alerts": alerts, "weather_available": w is not None,
            "weather_today": (w or {}).get(as_of)}


def add_progress(date, activity, qty, note=""):
    prog = load("progress", [])
    prog.append({"date": date, "activity": activity, "qty": float(qty), "note": note})
    save("progress", prog)
