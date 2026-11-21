"""Plan vs actual, weather and early warnings."""
import datetime as dt, time
import requests
from .store import load, save, SITE

WMO = {0: "klar", 1: "überwiegend klar", 2: "teilweise bewölkt", 3: "bedeckt", 45: "Nebel", 48: "Reifnebel",
       51: "leichter Niesel", 53: "Niesel", 55: "starker Niesel", 61: "leichter Regen", 63: "Regen", 65: "starker Regen",
       66: "gefrierender Regen", 67: "gefrierender Regen", 71: "leichter Schneefall", 73: "Schneefall", 75: "starker Schneefall",
       77: "Schneegriesel", 80: "Regenschauer", 81: "Regenschauer", 82: "starke Regenschauer", 85: "Schneeschauer",
       86: "Schneeschauer", 95: "Gewitter", 96: "Gewitter mit Hagel", 99: "Gewitter mit Hagel"}
_cache = {"t": 0, "data": None}


def weather():
    """Daily weather for the site (7 past + 7 forecast days), keyed by ISO date. None if offline."""
    if _cache["data"] and time.time() - _cache["t"] < 1800:
        return _cache["data"]
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
                        "text": WMO.get(d["weather_code"][i], "?")}
        _cache.update(t=time.time(), data=out)
        return out
    except Exception:
        return None


def weather_text(w):
    return f"{w['text']}, {w['tmin']:.0f} bis {w['tmax']:.0f} °C, Niederschlag {w['rain']:.1f} mm, Wind bis {w['wind']:.0f} km/h"


DEMO_SCHEDULE = [
    {"id": "piles", "name": "Bohrpfähle Achse 10", "unit": "Stk", "total": 10, "start": "2026-11-13", "end": "2026-11-22", "concrete": False},
    {"id": "rebar", "name": "Bewehrung Pfahlkopfbalken", "unit": "t", "total": 12, "start": "2026-11-19", "end": "2026-11-26", "concrete": False},
    {"id": "formwork", "name": "Schalung Widerlager Süd", "unit": "m²", "total": 240, "start": "2026-11-17", "end": "2026-11-28", "concrete": False},
    {"id": "concrete", "name": "Betonage Pfahlkopfbalken", "unit": "m³", "total": 85, "start": "2026-11-26", "end": "2026-11-28", "concrete": True},
]
DEMO_PROGRESS = [
    ("2026-11-13", "piles", 1, "Pfahl 1"), ("2026-11-14", "piles", 1, "Pfahl 2"), ("2026-11-16", "piles", 1, "Pfahl 3"),
    ("2026-11-17", "piles", 1, "Pfahl 4"), ("2026-11-18", "piles", 1, "Pfahl 5"), ("2026-11-19", "piles", 1, "Pfahl 6"),
    ("2026-11-20", "piles", 0, "Pfahl 7: Fels bei 4 m, Bohrfortschritt gering"),
    ("2026-11-17", "formwork", 20, ""), ("2026-11-18", "formwork", 20, ""), ("2026-11-19", "formwork", 15, ""), ("2026-11-20", "formwork", 15, ""),
    ("2026-11-19", "rebar", 1.5, ""), ("2026-11-20", "rebar", 1.5, ""),
]


DEMO_CLIENT_DOCS = [
    {"id": "gutachten-14", "locator": "Baugrundgutachten BW 7, Seite 14",
     "excerpt": "Bohrung BK 3 (Achse 10): 0,0 bis ca. 9,2 m unter GOK Sand und Kies, mitteldicht gelagert; ab ca. 9,2 m Kalkstein (Fels), angewittert."},
    {"id": "lv-02-110", "locator": "Leistungsverzeichnis Pos. 02.110",
     "excerpt": "Bohrpfähle d = 90 cm herstellen, Bodenklasse BK 3 bis 5, Pfahllänge 12 m, Fels nicht enthalten."},
]


def load_demo():
    save("client_docs", DEMO_CLIENT_DOCS)
    save("schedule", DEMO_SCHEDULE)
    save("progress", [{"date": d, "activity": a, "qty": q, "note": n} for d, a, q, n in DEMO_PROGRESS])


def _d(s):
    return dt.date.fromisoformat(s)


def status(as_of=None, with_weather=True):
    sched, prog = load("schedule", []), load("progress", [])
    if not as_of:
        as_of = dt.date.today().isoformat()
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
                           "text": f"{s['name']}: {delay} Arbeitstage Verzug (Soll {planned:g} {s['unit']}, Ist {actual:g} {s['unit']}).",
                           "suggest": "behinderung", "suggest_label": "Draft Behinderungsanzeige"})
        elif light == "yellow":
            alerts.append({"kind": "delay", "level": "yellow", "activity": s["id"],
                           "text": f"{s['name']}: {delay} Tage hinter Plan. Beobachten.", "suggest": None})
    w = weather() if with_weather else None
    if w:
        for s in sched:
            if not s.get("concrete"):
                continue
            cold = [(d, v) for d, v in w.items() if s["start"] <= d <= s["end"] and v["tmin"] <= 2]
            if cold:
                d, v = min(cold, key=lambda x: x[1]["tmin"])
                alerts.append({"kind": "frost", "level": "yellow", "activity": s["id"],
                               "text": f"Frostgefahr: {s['name']} geplant {s['start']} bis {s['end']}, Prognose am {d} Tmin {v['tmin']:.0f} °C.",
                               "suggest": "bedenken", "suggest_label": "Draft Bedenkenanzeige (winter measures)",
                               "weather_date": d, "tmin": v["tmin"]})
    return {"as_of": as_of, "activities": rows, "alerts": alerts, "weather_available": w is not None,
            "weather_today": (w or {}).get(dt.date.today().isoformat())}


def add_progress(date, activity, qty, note=""):
    prog = load("progress", [])
    prog.append({"date": date, "activity": activity, "qty": float(qty), "note": note})
    save("progress", prog)
