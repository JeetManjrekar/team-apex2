"""Geld & Zeit: cost exposure and savings, computed from measured data times configured internal rates.

Specification: COST_MODEL.md. Four metrics, each a transparent rule on data the system already holds:
  nachtrag_exposure  drilling list (drill:Pxx)        -> extra rig/crew hours measured + predicted to target depth
  idle_cost          Behinderungsanzeige (doc-…)       -> standby + idle crew, and what a crew reassignment avoids
  delay_risk         schedule + progress + weather      -> projected slip per milestone x site overhead
  doc_time_saved     documents + llm_metrics.jsonl      -> manual baseline vs measured minutes, AI cost per document
Rules of the house (enforced here, tested in tests/test_cost_model.py):
  * every result: expected/low/high, band, German explanation with the real numbers, assumptions, source refs,
    label "Schätzung, intern"; missing input -> {"status": "nicht genug Daten", "reason": …}, never a guess
  * all rates/thresholds/probabilities come from env (COST_*), each with its source label ("Annahme …")
  * no euro value ever reaches an outgoing document: this module is read only by the dashboard / AI Manager
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import os
import re
from statistics import mean

from . import store
from .i18n import get_lang


def _t(en, de):
    """Follows the request language (X-Lang): English by default, German when the user chose Deutsch."""
    return de if get_lang() == "de" else en


def label():
    return _t("Estimate, internal", "Schätzung, intern")


NO_DATA = "no_data"
WD_START_H, WD_END_H = 7.0, 16.0
WD_HOURS = WD_END_H - WD_START_H


# ---------------------------------------------------------------- configuration
_DEFAULTS = {   # env name: (default, unit en, unit de, source en, source de)
    "COST_RIG_EUR_H": (420.0, "€/h", "€/h", "Drilling rig incl. operator · assumption, partner confirmation pending", "Bohrgerät inkl. Bediener · Annahme, Bestätigung durch Partnerin offen"),
    "COST_CREW_EUR_H": (58.0, "€/h per person", "€/h je Person", "Wage incl. overhead · assumption, partner confirmation pending", "Lohn inkl. Zuschläge · Annahme, Bestätigung durch Partnerin offen"),
    "COST_STANDBY_EUR_H": (150.0, "€/h", "€/h", "Idle machine · assumption, partner confirmation pending", "Stillstand Gerät · Annahme, Bestätigung durch Partnerin offen"),
    "COST_SITE_MANAGER_EUR_H": (75.0, "€/h", "€/h", "Site manager, for time saved · assumption", "Bauleitung, für gesparte Zeit · Annahme"),
    "COST_SITE_OVERHEAD_EUR_DAY": (2500.0, "€/working day", "€/Arbeitstag", "Site overhead per extra day · assumption", "Baustellengemeinkosten je Mehrtag · Annahme"),
    "COST_BAND_MEDIUM_EUR": (5000.0, "€", "€", "Band limit low/medium · assumption", "Grenze niedrig/mittel · Annahme"),
    "COST_BAND_HIGH_EUR": (25000.0, "€", "€", "Band limit medium/high · assumption", "Grenze mittel/hoch · Annahme"),
    "COST_BASELINE_NACHTRAGSMELDUNG_MIN": (90.0, "min", "min", "Manual time change order notice · assumption, partner confirmation pending", "Handzeit Nachtragsmeldung · Annahme, Bestätigung durch Partnerin offen"),
    "COST_BASELINE_MEHRKOSTENANZEIGE_MIN": (90.0, "min", "min", "Manual time additional cost notice · assumption", "Handzeit Mehrkostenanzeige · Annahme"),
    "COST_BASELINE_BAUTAGESBERICHT_MIN": (45.0, "min", "min", "Manual time daily report · assumption, partner confirmation pending", "Handzeit Bautagesbericht · Annahme, Bestätigung durch Partnerin offen"),
    "COST_BASELINE_BEHINDERUNGSANZEIGE_MIN": (30.0, "min", "min", "Manual time delay notice · assumption, partner confirmation pending", "Handzeit Behinderungsanzeige · Annahme, Bestätigung durch Partnerin offen"),
    "COST_BASELINE_BEDENKENANMELDUNG_MIN": (30.0, "min", "min", "Manual time notice of concern · assumption", "Handzeit Bedenkenanmeldung · Annahme"),
    "COST_BASELINE_MAENGELANZEIGE_MIN": (30.0, "min", "min", "Manual time defect notice · assumption", "Handzeit Mängelanzeige · Annahme"),
    "COST_BASELINE_AKTENNOTIZ_MIN": (15.0, "min", "min", "Manual time file note · assumption", "Handzeit Aktennotiz · Annahme"),
    "COST_REVIEW_MIN": (3.0, "min", "min", "Review time per draft until measured · assumption", "Prüfzeit je Entwurf, solange nicht gemessen · Annahme"),
    "COST_REPAIR_DEFAULT_DAYS": (1.0, "working days", "Arbeitstage", "Repair time when none is given · assumption", "Reparaturdauer ohne Angabe · Annahme"),
    "COST_REACTION_H": (1.0, "h", "h", "Time until the reassignment takes effect · assumption", "Zeit bis die Umsetzung greift · Annahme"),
    "COST_FROST_P_BELOW_0": (0.8, "", "", "Probability concreting moves at Tmin < 0 °C · schedule assumption, not material science", "Wahrscheinlichkeit Betonage verschieben bei Tmin < 0 °C · Terminannahme, keine Materialaussage"),
    "COST_FROST_P_0_TO_5": (0.5, "", "", "Probability at Tmin 0…5 °C · schedule assumption", "Wahrscheinlichkeit bei Tmin 0…5 °C · Terminannahme"),
    "COST_FROST_P_ABOVE_5": (0.1, "", "", "Probability at Tmin > 5 °C · schedule assumption", "Wahrscheinlichkeit bei Tmin > 5 °C · Terminannahme"),
    "COST_FROST_SLIP_DAYS": (2.0, "working days", "Arbeitstage", "Shift of a concreting day in frost · schedule assumption", "Verschiebung einer Betonage bei Frost · Terminannahme"),
    "COST_ROCK_HARDER_PCT": (20.0, "%", "%", "Rock gets slower with depth (upper range) · assumption", "Felsgeschwindigkeit wird mit der Tiefe langsamer (obere Spanne) · Annahme"),
}


def settings() -> dict:
    out = {}
    for k, (d, unit_en, unit_de, src_en, src_de) in _DEFAULTS.items():
        try:
            v = float(os.environ.get(k, "") or d)
        except ValueError:
            v = d
        src = _t(src_en, src_de)
        out[k] = {"value": v, "unit": _t(unit_en, unit_de),
                  "source": src if v == d else f"{src.split(' · ')[0]} · " + _t("set in configuration", "gesetzt in der Konfiguration")}
    return out


def _v(cfg, k):
    return cfg[k]["value"]


# ---------------------------------------------------------------- formatting (number format follows the language)
def num(x, d=1) -> str:
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") if get_lang() == "de" else s


def eur(x) -> str:
    return f"{num(x, 0)} €"


BAND_LABEL = {"low": ("low", "niedrig"), "medium": ("medium", "mittel"), "high": ("high", "hoch")}


def _band(cfg, x):
    return "high" if x >= _v(cfg, "COST_BAND_HIGH_EUR") else "medium" if x >= _v(cfg, "COST_BAND_MEDIUM_EUR") else "low"


def _result(cfg, key, kind, title, exp, low, high, explanation, assumptions, sources, **extra):
    low, exp, high = sorted((round(low), round(exp), round(high)))[0], round(exp), max(round(low), round(exp), round(high))
    return {"key": key, "kind": kind, "title": title, "status": "ok", "expected_eur": exp, "low_eur": low, "high_eur": high,
            "band": _band(cfg, exp), "band_label": _t(*BAND_LABEL[_band(cfg, exp)]), "explanation": explanation,
            "assumptions": assumptions, "sources": sources, "label": label(), **extra}


def _no_data(key, kind, title, reason):
    return {"key": key, "kind": kind, "title": title, "status": NO_DATA, "status_text": _t("not enough data", "nicht genug Daten"),
            "reason": reason, "label": label(),
            "expected_eur": None, "low_eur": None, "high_eur": None, "band": None, "sources": []}


# ---------------------------------------------------------------- calendar (working days Mon-Fri, 07:00-16:00)
def _is_wd(d: dt.date) -> bool:
    return d.weekday() < 5


def add_wd(d: dt.date, n: int) -> dt.date:
    step = 1 if n >= 0 else -1
    while n:
        d += dt.timedelta(days=step)
        if _is_wd(d):
            n -= step
    return d


def wd_between(a: dt.date, b: dt.date) -> int:
    """Working days from a to b (b later: positive; counts days after a up to and including b)."""
    if b == a:
        return 0
    sign, (x, y) = (1, (a, b)) if b > a else (-1, (b, a))
    n, d = 0, x
    while d < y:
        d += dt.timedelta(days=1)
        n += _is_wd(d)
    return sign * n


def _today() -> dt.date:
    from .llm_settings import today
    return today()


def _hhmm(s) -> float | None:
    m = re.match(r"^\s*(\d{1,2}):(\d{2})", s or "")
    return int(m.group(1)) + int(m.group(2)) / 60 if m else None


# ---------------------------------------------------------------- inputs
def _demo_dir():
    from .plan import DEMO_DIR
    return DEMO_DIR


def drilling_rows() -> list[dict]:
    p = _demo_dir() / "drilling" / "drilling_times.csv"
    if not p.exists():
        return []
    rows = []
    with p.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            start, end = _hhmm(r.get("start")), _hhmm(r.get("end"))
            stand = re.search(r"Stand\s*(\d{1,2}):(\d{2})", r.get("note_de") or "")
            until = end if end is not None else (int(stand.group(1)) + int(stand.group(2)) / 60 if stand else None)
            rock = re.search(r"ab\s*(\d+(?:[.,]\d+)?)\s*m\s*Fels", r.get("note_de") or "", re.I)
            reached, target = float(r.get("depth_reached_m") or 0), float(r.get("target_depth_m") or 0)
            rows.append({"pile": r["pile_id"], "zone": r["zone_id"], "date": r["date"], "start": start, "until": until,
                         "until_label": r.get("end") or (f"{stand.group(1)}:{stand.group(2)}" if stand else ""),
                         "hours": (until - start) if start is not None and until is not None else None,
                         "reached": reached, "target": target, "crew": int(r.get("crew_count") or 0) or None,
                         "rock_from": float(rock.group(1).replace(",", ".")) if rock else None,
                         "done": bool(end) and reached >= target > 0, "note": r.get("note_de") or "", "ref": f"drill:{r['pile_id']}"})
    return rows


def schedule_rows() -> list[dict]:
    p = _demo_dir() / "schedule" / "bauzeitenplan.csv"
    if not p.exists():
        return []
    out = []
    with p.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append({"id": r["id"], "name": r["name_de"], "zone": r["zone_id"], "start": dt.date.fromisoformat(r["start_planned"]),
                        "end": dt.date.fromisoformat(r["end_planned"]), "preds": [x for x in (r["predecessors"] or "").split(";") if x],
                        "per_day": float(r["planned_output_per_day"] or 0), "unit": r["unit"], "days": int(r["duration_days"] or 0),
                        "sensitive": r["weather_sensitive"] == "1", "milestone": r["is_milestone"] == "1"})
    return out


def weather() -> dict:
    """{iso date: tmin} from the live forecast, gaps filled from the demo fixture. Source ref: wx:<date>."""
    out = {}
    try:
        import json
        for w in json.loads((_demo_dir() / "weather" / "weather_fixture.json").read_text(encoding="utf-8")):
            out[w["date"]] = float(w["t_min"])
    except Exception:
        pass
    try:
        from .plan import weather as live
        for d, w in (live() or {}).items():
            if w.get("tmin") is not None:
                out[d] = float(w["tmin"])
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- 4.1 Nachtrag exposure
def _ref_speed(rows):
    refs = [r for r in rows if r["done"] and r["hours"] and r["reached"]]
    return (mean(r["hours"] / r["reached"] for r in refs), refs) if refs else (None, [])


def nachtrag_exposure(cfg=None, rows=None) -> list[dict]:
    cfg, rows = cfg or settings(), rows if rows is not None else drilling_rows()
    ref_hpm, refs = _ref_speed(rows)
    out = []
    for p in rows:
        if p["done"] or not p["reached"]:
            continue
        key, title = f"nachtrag:{p['pile']}", _t(f"Change order {p['pile']} ({p['zone']})", f"Nachtrag {p['pile']} ({p['zone']})")
        if ref_hpm is None:
            out.append(_no_data(key, "nachtrag", title, _t("no completed reference piles in the drilling list", "keine abgeschlossenen Referenzpfähle in der Bohrliste")))
            continue
        if p["hours"] is None or not p["crew"]:
            out.append(_no_data(key, "nachtrag", title, _t(f"{p['pile']}: drilling time or crew size missing in the drilling list", f"{p['pile']}: Bohrzeit oder Personalstärke fehlt in der Bohrliste")))
            continue
        normal_h = p["reached"] * ref_hpm
        extra = p["hours"] - normal_h
        if extra < 0.5 and p["hours"] / normal_h < 1.3:
            continue                                     # drilling at normal speed: no exposure
        rate = _v(cfg, "COST_RIG_EUR_H") + p["crew"] * _v(cfg, "COST_CREW_EUR_H")
        if p["rock_from"] and p["reached"] > p["rock_from"]:
            cur_hpm = (p["hours"] - p["rock_from"] * ref_hpm) / (p["reached"] - p["rock_from"])
            speed_txt = _t(f"the current rock speed of {num(cur_hpm)} h/m (rock from {num(p['rock_from'])} m)",
                           f"aktueller Felsgeschwindigkeit {num(cur_hpm)} h/m (ab {num(p['rock_from'])} m Fels)")
        else:
            cur_hpm = p["hours"] / p["reached"]
            speed_txt = _t(f"the current speed of {num(cur_hpm)} h/m", f"aktueller Geschwindigkeit {num(cur_hpm)} h/m")
        harder = 1 + _v(cfg, "COST_ROCK_HARDER_PCT") / 100
        rem = max(0.0, p["target"] - p["reached"])
        pred_h = {"low": 0.0, "exp": rem * max(0.0, cur_hpm - ref_hpm), "high": rem * max(0.0, cur_hpm * harder - ref_hpm)}
        measured = extra * rate
        tot = {k: measured + h * rate for k, h in pred_h.items()}
        ref_ids = ", ".join(r["pile"] for r in refs)
        until = p["until_label"] or _t("now", "jetzt")
        expl = _t(
            f"{p['pile']}: {num(extra)} extra hours until {until} ({num(p['reached'])} m in {num(p['hours'])} h instead of "
            f"{num(normal_h)} h at {num(ref_hpm, 2)} h/m from {ref_ids}) × {eur(rate)}/h (rig {eur(_v(cfg, 'COST_RIG_EUR_H'))}/h + "
            f"{p['crew']} people × {eur(_v(cfg, 'COST_CREW_EUR_H'))}/h) = {eur(measured)} measured. Remaining {num(rem)} m to "
            f"{num(p['target'])} m at {speed_txt}: probably another {eur(tot['exp'] - measured)} "
            f"(range {eur(tot['low'])} to {eur(tot['high'])} in total).",
            f"{p['pile']}: {num(extra)} Mehrstunden bis Stand {until} ({num(p['reached'])} m in {num(p['hours'])} h statt "
            f"{num(normal_h)} h bei {num(ref_hpm, 2)} h/m aus {ref_ids}) × {eur(rate)}/h (Bohrgerät {eur(_v(cfg, 'COST_RIG_EUR_H'))}/h + "
            f"{p['crew']} Personen × {eur(_v(cfg, 'COST_CREW_EUR_H'))}/h) = {eur(measured)} gemessen. Restliche {num(rem)} m bis "
            f"{num(p['target'])} m bei {speed_txt}: voraussichtlich weitere {eur(tot['exp'] - measured)} "
            f"(Spanne {eur(tot['low'])} bis {eur(tot['high'])} gesamt).")
        docs = _claim_docs(p["pile"])
        doc = docs[0] if docs else None
        missing_log = bool(doc) and not ((doc.get("fields") or {}).get("drilling_log_ref") or {}).get("value")
        action = ((_t("Request drilling log", "Bohrprotokoll anfordern") if missing_log else _t("Pass to change order manager", "An Nachtragsmanager weitergeben"))
                  if doc else _t("Draft change order notice", "Nachtragsmeldung erstellen"))
        out.append(_result(cfg, key, "nachtrag", title, tot["exp"], tot["low"], tot["high"], expl,
                           [cfg["COST_RIG_EUR_H"]["source"], cfg["COST_CREW_EUR_H"]["source"], _t("Reference = mean of the completed piles", "Referenz = Mittel der abgeschlossenen Pfähle"),
                            _t("Lower range: the rock ends now", "untere Spanne: Fels endet jetzt"),
                            _t(f"Upper range: rock {num(_v(cfg, 'COST_ROCK_HARDER_PCT'), 0)} % slower · assumption", f"obere Spanne: Fels +{num(_v(cfg, 'COST_ROCK_HARDER_PCT'), 0)} % langsamer · Annahme")],
                           [p["ref"]] + [r["ref"] for r in refs],
                           zone=p["zone"], pile=p["pile"], measured_eur=round(measured), extra_hours=round(extra, 2), rate_eur_h=rate,
                           remaining_hours={k: round(rem * v, 2) for k, v in {"low": ref_hpm, "exp": cur_hpm, "high": cur_hpm * harder}.items()},
                           documented=bool(doc), doc_id=doc["id"] if doc else None, action=action))
    return out


def _claim_docs(pile):
    n = int(re.sub(r"\D", "", pile) or 0)
    rx = re.compile(rf"\b(?:{re.escape(pile)}|P0?{n}|pfahl\s*0?{n}|pile\s*0?{n})\b", re.I)
    hits = []
    for d in store.load("docs", []):
        if d.get("type") not in ("nachtragsmeldung", "mehrkostenanzeige"):
            continue
        text = " ".join(str((f or {}).get("value") or "") for f in (d.get("fields") or {}).values())
        if rx.search(text):
            hits.append(d)
    return hits


# ---------------------------------------------------------------- 4.2 idle cost (machine breakdown)
_BREAKDOWN = re.compile(r"bagger|excavator|hydraul|defekt|ausgefallen|ausfall|breakdown|broken|stillstand|idle|steht|gerät|machine|maschine", re.I)
_CREW = re.compile(r"(?:crew of|team of)\s*(\d+)|(\d+)\s*(?:mann|personen|person|leute|arbeiter|workers|people|crew)\b", re.I)


def _repair_days(text):
    t = (text or "").lower()
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:arbeits)?(?:tag|tage|tagen|day|days|working days)\b", t)
    if m:
        return float(m.group(1).replace(",", ".")), _t("as stated", "aus der Angabe")
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:h|std|stunden?|hours?)\b", t)
    if m:
        return float(m.group(1).replace(",", ".")) / WD_HOURS, _t("as stated", "aus der Angabe")
    if re.search(r"halbe[nr]? tag|half a day", t):
        return 0.5, _t("as stated", "aus der Angabe")
    if re.search(r"morgen|tomorrow", t):
        return 1.0, _t("as stated", "aus der Angabe")
    return None, None


def _start_hour(text):
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(uhr|am|pm|h)\b", text or "", re.I) or re.search(r"\b(\d{1,2}):(\d{2})\b", text or "")
    if not m:
        return None
    h = int(m.group(1)) + (int(m.group(2)) / 60 if m.group(2) else 0)
    if len(m.groups()) >= 3 and (m.group(3) or "").lower() == "pm" and h < 12:
        h += 12
    return h if 0 <= h < 24 else None


def idle_cost(cfg=None, docs=None) -> list[dict]:
    cfg = cfg or settings()
    docs = docs if docs is not None else store.load("docs", [])
    decisions = store.load("cost_decisions", {})
    out = []
    for d in docs:
        if d.get("type") != "behinderungsanzeige":
            continue
        f = {k: (v or {}).get("value") or "" for k, v in (d.get("fields") or {}).items()}
        quotes = {((v or {}).get("source") or {}).get("quote") or "" for v in (d.get("fields") or {}).values()}
        text = " ".join(str(x) for x in list(f.values()) + sorted(quotes))     # the original message is quoted as each field's source
        if not _BREAKDOWN.search(text):
            continue
        key, title = f"idle:{d['id']}", (_t("Idle: ", "Stillstand: ") + str(f.get('location') or f.get('cause') or d.get('title', '')))[:80]
        start_h = _start_hour(f.get("occurred_at"))
        days, how = _repair_days(f.get("expected_duration"))
        assumptions = [cfg["COST_STANDBY_EUR_H"]["source"], cfg["COST_CREW_EUR_H"]["source"], cfg["COST_REACTION_H"]["source"]]
        if days is None:
            days, how = _v(cfg, "COST_REPAIR_DEFAULT_DAYS"), _t("default", "Standard")
            assumptions.append(cfg["COST_REPAIR_DEFAULT_DAYS"]["source"])
        m = _CREW.search(text)
        if m:
            crew, crew_src = int(m.group(1) or m.group(2)), _t("from the report", "aus der Meldung")
        else:
            crew, crew_src = 1, _t("operator only (not stated)", "nur Maschinenführer (keine Angabe)")
            assumptions.append(_t("Crew size not stated: 1 operator · assumption", "Personalstärke ohne Angabe: 1 Maschinenführer · Annahme"))
        if start_h is None and not f.get("occurred_at"):
            out.append(_no_data(key, "idle", title, _t("start of the stoppage missing", "Beginn des Stillstands fehlt")))
            continue
        hours = {k: days * WD_HOURS * x for k, x in (("low", 0.5), ("exp", 1.0), ("high", 2.0))}
        without = {k: h * _v(cfg, "COST_STANDBY_EUR_H") + h * crew * _v(cfg, "COST_CREW_EUR_H") for k, h in hours.items()}
        avoided = {k: max(0.0, h - _v(cfg, "COST_REACTION_H")) * crew * _v(cfg, "COST_CREW_EUR_H") for k, h in hours.items()}
        accepted = (decisions.get(key) or {}).get("accepted") is True
        hhmm = f"{int(start_h):02d}:{int(round((start_h % 1) * 60)):02d}" if start_h is not None else None
        start_txt = _t(f"since {hhmm}", f"seit {hhmm} Uhr") if hhmm else _t(f"since {f.get('occurred_at')}", f"seit {f.get('occurred_at')}")
        expl = _t(
            f"Stoppage {start_txt}, repair {num(days)} working days ({how}) = {num(hours['exp'])} h: "
            f"{num(hours['exp'])} h × {eur(_v(cfg, 'COST_STANDBY_EUR_H'))}/h machine + {crew} person(s) ({crew_src}) × {num(hours['exp'])} h × "
            f"{eur(_v(cfg, 'COST_CREW_EUR_H'))}/h = {eur(without['exp'])}. Reassigning the crew after "
            f"{num(_v(cfg, 'COST_REACTION_H'))} h {'avoids' if accepted else 'would avoid'} about {eur(avoided['exp'])}.",
            f"Stillstand {start_txt}, Reparatur {num(days)} Arbeitstage ({how}) = {num(hours['exp'])} h: "
            f"{num(hours['exp'])} h × {eur(_v(cfg, 'COST_STANDBY_EUR_H'))}/h Gerät + {crew} Person(en) ({crew_src}) × {num(hours['exp'])} h × "
            f"{eur(_v(cfg, 'COST_CREW_EUR_H'))}/h = {eur(without['exp'])}. Umsetzung der Mannschaft nach "
            f"{num(_v(cfg, 'COST_REACTION_H'))} h {'vermeidet' if accepted else 'würde vermeiden'} ca. {eur(avoided['exp'])}.")
        src = [f"doc-{d['id']}"] + [x for x in [((d.get("fields") or {}).get(k) or {}).get("source", {}) and
                                                ((d["fields"][k].get("source") or {}).get("evidence_id")) for k in ("occurred_at", "expected_duration", "cause")] if x]
        out.append(_result(cfg, key, "idle", title, without["exp"], without["low"], without["high"], expl, assumptions, list(dict.fromkeys(src)),
                           doc_id=d["id"], idle_hours=round(hours["exp"], 1), crew=crew, repair_days=days,
                           avoided_eur=round(avoided["exp"]), avoided_low_eur=round(avoided["low"]), avoided_high_eur=round(avoided["high"]),
                           with_reassignment_eur=round(without["exp"] - avoided["exp"]), accepted=accepted,
                           action=None if accepted else _t("Accept reassignment", "Umsetzung annehmen")))
    return out


# ---------------------------------------------------------------- 4.3 delay risk
def _frost_p(cfg, tmin):
    if tmin is None:
        return None
    return _v(cfg, "COST_FROST_P_BELOW_0") if tmin < 0 else _v(cfg, "COST_FROST_P_0_TO_5") if tmin <= 5 else _v(cfg, "COST_FROST_P_ABOVE_5")


def _drilling_finish(zone, rows, exposures, today):
    """Projected finish of the drilling in a zone from the remaining pile hours (rig works WD_HOURS per day)."""
    ref_hpm, _ = _ref_speed(rows)
    piles = [r for r in rows if r["zone"] == zone and not r["done"]]
    if not piles or ref_hpm is None:
        return None
    expo = {e["pile"]: e for e in exposures if e.get("status") == "ok" and e.get("zone") == zone}
    used_today = max((r["until"] for r in piles if r["date"] == today.isoformat() and r["until"]), default=WD_START_H)
    left_today = max(0.0, WD_END_H - used_today)
    res = {}
    for k in ("low", "exp", "high"):
        rem = 0.0
        for p in piles:
            if p["pile"] in expo:
                rem += expo[p["pile"]]["remaining_hours"][k]
            else:
                rem += max(0.0, p["target"] - p["reached"]) * ref_hpm
        days = 0 if rem <= left_today else math.ceil((rem - left_today) / WD_HOURS)
        res[k] = (add_wd(today, days), rem)
    return res


def delay_risk(cfg=None, rows=None, sched=None, wx=None, progress=None, exposures=None) -> list[dict]:
    cfg = cfg or settings()
    rows = rows if rows is not None else drilling_rows()
    sched = sched if sched is not None else schedule_rows()
    if not sched:
        return [_no_data("delay", "delay", _t("Delay risk", "Terminrisiko"), _t("no schedule loaded", "kein Bauzeitenplan geladen"))]
    wx = wx if wx is not None else weather()
    progress = progress if progress is not None else store.load("progress", [])
    exposures = exposures if exposures is not None else nachtrag_exposure(cfg, rows)
    today = _today()
    by_id = {a["id"]: a for a in sched}
    slip, why, frost_note = {}, {}, {}
    for a in sched:                                       # CSV is in dependency order
        inh = {k: max([slip[p][k] for p in a["preds"] if p in slip] or [0.0]) for k in ("low", "exp", "high")}
        own = {"low": 0.0, "exp": 0.0, "high": 0.0}
        reasons = []
        if a["per_day"] and a["start"] <= today <= a["end"] + dt.timedelta(days=14):
            fin = _drilling_finish(a["zone"], rows, exposures, today) if "BP" in a["id"] else None
            if fin:
                own = {k: max(0, wd_between(a["end"], fin[k][0])) for k in fin}
                if own["exp"] > 0:
                    reasons.append(_t(f"{a['name']}: {num(fin['exp'][1])} h of drilling left → done {fin['exp'][0].strftime('%d.%m.')} instead of {a['end'].strftime('%d.%m.')}",
                                      f"{a['name']}: Rest {num(fin['exp'][1])} h Bohrzeit → fertig {fin['exp'][0].strftime('%d.%m.')} statt {a['end'].strftime('%d.%m.')}"))
            else:
                actual = sum(e["qty"] for e in progress if e.get("activity") == a["id"] and e.get("date", "") <= today.isoformat())
                elapsed = max(1, wd_between(a["start"] - dt.timedelta(days=1), min(today, a["end"])))
                rate = actual / elapsed if elapsed else 0
                total = a["per_day"] * max(1, a["days"])
                if rate > 0 and actual < total:
                    fin_d = add_wd(today, math.ceil((total - actual) / rate))
                    s = max(0, wd_between(a["end"], fin_d))
                    own = {"low": s * 0.5, "exp": float(s), "high": s * 1.5}
                    if s:
                        reasons.append(_t(f"{a['name']}: {num(rate)} {a['unit']}/day instead of {num(a['per_day'])} → +{s} working days",
                                          f"{a['name']}: {num(rate)} {a['unit']}/AT statt {num(a['per_day'])} → +{s} AT"))
        base = {k: max(own[k], inh[k]) for k in own}
        if a["sensitive"]:
            day = add_wd(a["start"], round(base["exp"])) if base["exp"] else a["start"]
            tmin = wx.get(day.isoformat())
            p = _frost_p(cfg, tmin)
            if p is not None:
                fd = _v(cfg, "COST_FROST_SLIP_DAYS")
                base = {"low": base["low"] + max(0.0, p - 0.15) * fd, "exp": base["exp"] + p * fd, "high": base["high"] + min(1.0, p + 0.15) * fd}
                frost_note[a["id"]] = {"date": day.isoformat(), "tmin": tmin, "p": p, "ref": f"wx:{day.isoformat()}"}
                if tmin is not None and tmin <= 5:
                    reasons.append(_t(f"{a['name']} on {day.strftime('%d.%m.')}: forecast Tmin {num(tmin, 0)} °C → frost probability {num(p * 100, 0)} %",
                                      f"{a['name']} am {day.strftime('%d.%m.')}: Prognose Tmin {num(tmin, 0)} °C → Frostwahrscheinlichkeit {num(p * 100, 0)} %"))
        slip[a["id"]] = base
        why[a["id"]] = reasons + [r for pid in a["preds"] for r in why.get(pid, []) if r not in reasons]
    out = []
    od = _v(cfg, "COST_SITE_OVERHEAD_EUR_DAY")
    for a in sched:
        if not a["milestone"] or slip[a["id"]]["exp"] <= 0:
            continue
        s = slip[a["id"]]
        chain = list(dict.fromkeys(why[a["id"]]))[:4]
        frost_used = [frost_note[x] for x in frost_note if any(x == y or x in _ancestors(y, by_id) for y in [a["id"]])]
        sources = [f"sched:{x}" for x in sorted(_ancestors(a["id"], by_id) | {a["id"]}) if slip.get(x, {}).get("exp", 0) > 0][:8]
        sources += [r["ref"] for r in rows if r["zone"] in {by_id[x]["zone"] for x in _ancestors(a["id"], by_id) if x in by_id} and not r["done"] and r["reached"]]
        sources += [f["ref"] for f in frost_used]
        action = (_t("Check moving the concreting", "Betonage verschieben prüfen") if any(f["tmin"] is not None and f["tmin"] <= 5 for f in frost_used)
                  else _t("Check drilling order / second rig", "Bohrreihenfolge / zweites Gerät prüfen"))
        why_txt = "; ".join(c.rstrip(".") for c in chain)
        expl = _t(f"{a['name']}: probably +{num(s['exp'])} working days (range {num(s['low'])} to {num(s['high'])}) × "
                  f"{eur(od)}/day site overhead = {eur(s['exp'] * od)}. Reasons: {why_txt}.",
                  f"{a['name']}: voraussichtlich +{num(s['exp'])} Arbeitstage (Spanne {num(s['low'])} bis {num(s['high'])}) × "
                  f"{eur(od)}/AT Baustellengemeinkosten = {eur(s['exp'] * od)}. Gründe: {why_txt}.")
        out.append(_result(cfg, f"delay:{a['id']}", "delay", _t(f"Delay risk {a['name']}", f"Terminrisiko {a['name']}"), s["exp"] * od, s["low"] * od, s["high"] * od, expl,
                           [cfg["COST_SITE_OVERHEAD_EUR_DAY"]["source"], cfg["COST_FROST_SLIP_DAYS"]["source"],
                            _t("Frost probability: ", "Frostwahrscheinlichkeit: ") + cfg["COST_FROST_P_BELOW_0"]["source"],
                            _t("No float between activities · assumption", "kein Puffer zwischen Vorgängen · Annahme")],
                           list(dict.fromkeys(sources)), milestone=a["id"], zone=a["zone"] or _zone_of_chain(a["id"], by_id),
                           slip_days={k: round(v, 1) for k, v in s.items()}, action=action))
    return out


def _ancestors(aid, by_id, seen=None):
    seen = set() if seen is None else seen
    for p in by_id.get(aid, {}).get("preds", []):
        if p not in seen:
            seen.add(p)
            _ancestors(p, by_id, seen)
    return seen


def _zone_of_chain(aid, by_id):
    zs = [by_id[x]["zone"] for x in _ancestors(aid, by_id) if by_id.get(x, {}).get("zone")]
    return zs[0] if zs else None


# ---------------------------------------------------------------- 4.4 documentation time saved
def _metrics_rows():
    import json
    p = store.DATA / "llm_metrics.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _ts(s):
    try:
        t = dt.datetime.fromisoformat(s)
        return t.astimezone().replace(tzinfo=None) if t.tzinfo else t
    except Exception:
        return None


def doc_time_saved(cfg=None, docs=None, metrics=None) -> list[dict]:
    cfg = cfg or settings()
    docs = docs if docs is not None else store.load("docs", [])
    metrics = metrics if metrics is not None else _metrics_rows()
    mrows = [(r, _ts(r.get("started_at"))) for r in metrics]
    out = []
    for d in docs:
        k = f"COST_BASELINE_{d.get('type', '').upper()}_MIN"
        if k not in cfg:
            continue
        created = _ts(d.get("created_at") or "")
        if not created:
            continue
        last = max([_ts(e.get("at") or "") or created for e in d.get("log") or []] + [created])
        lo, hi = created - dt.timedelta(seconds=90), last + dt.timedelta(seconds=10)
        win = [r for r, t in mrows if t and lo <= t <= hi]
        turns = [r for r in win if r.get("stage") in ("chat_turn_end_to_end", "voice_to_draft_end_to_end")] or \
                [r for r in win if str(r.get("run_id", "")).endswith(d["id"]) and not str(r.get("stage", "")).startswith("export")]
        ai_s = sum(float(r.get("duration_ms") or 0) for r in turns) / 1000
        ai_cost = sum(float(r.get("cost_eur") or 0) for r in win if (r.get("tokens_in") or 0) + (r.get("tokens_out") or 0) > 0)
        review = _v(cfg, "COST_REVIEW_MIN")
        minutes = ai_s / 60 + review
        base = _v(cfg, k)
        saved_min = max(0.0, base - minutes)
        money = saved_min / 60 * _v(cfg, "COST_SITE_MANAGER_EUR_H")
        cost_txt = _t(f"; AI cost {num(ai_cost, 3)} €." if ai_cost else "; AI cost not recorded.",
                      f"; KI-Kosten {num(ai_cost, 3)} €." if ai_cost else "; KI-Kosten nicht erfasst.")
        expl = _t(f"{d.get('title')}: by hand {num(base, 0)} min, with the assistant {num(ai_s, 0)} s processing + {num(review, 0)} min review = "
                  f"{num(minutes)} min → {num(saved_min)} min saved × {eur(_v(cfg, 'COST_SITE_MANAGER_EUR_H'))}/h = {eur(money)}" + cost_txt,
                  f"{d.get('title')}: von Hand {num(base, 0)} min, mit Assistent {num(ai_s, 0)} s Verarbeitung + {num(review, 0)} min Prüfung = "
                  f"{num(minutes)} min → {num(saved_min)} min gespart × {eur(_v(cfg, 'COST_SITE_MANAGER_EUR_H'))}/h = {eur(money)}" + cost_txt)
        out.append(_result(cfg, f"time:{d['id']}", "time", _t(f"Time saved: {d.get('title')}", f"Zeit gespart: {d.get('title')}"), money, money, money, expl,
                           [cfg[k]["source"], cfg["COST_REVIEW_MIN"]["source"], cfg["COST_SITE_MANAGER_EUR_H"]["source"]],
                           [f"doc-{d['id']}"] + [f"metric:{r.get('stage')}" for r in turns[:3]],
                           doc_id=d["id"], manual_min=base, assisted_min=round(minutes, 2), ai_seconds=round(ai_s, 1),
                           saved_min=round(saved_min, 1), ai_cost_eur=round(ai_cost, 4) if ai_cost else None))
    return out


# ---------------------------------------------------------------- ranking + summary


def summary() -> dict:
    cfg = settings()
    rows = drilling_rows()
    expo = nachtrag_exposure(cfg, rows)
    idle = idle_cost(cfg)
    delay = delay_risk(cfg, rows=rows, exposures=expo)
    times = doc_time_saved(cfg)
    ok = lambda xs: [x for x in xs if x.get("status") == "ok"]  # noqa: E731

    def total(xs, f="expected_eur"):
        return sum(x[f] for x in xs) if xs else 0

    documented = [x for x in ok(expo) if x.get("documented")]
    accepted = [x for x in ok(idle) if x.get("accepted")]
    open_delay = max(ok(delay), key=lambda x: x["expected_eur"], default=None)   # site overhead accrues once: largest milestone
    manual = sum(x["manual_min"] for x in ok(times))
    assisted = sum(x["assisted_min"] for x in ok(times))
    saved_eur = total(ok(times))
    ai_costs = [x["ai_cost_eur"] for x in ok(times) if x.get("ai_cost_eur")]
    ai_total = sum(ai_costs) if ai_costs else None
    gains = total(documented) + sum(x["avoided_eur"] for x in accepted) + saved_eur
    events = sorted([x for x in ok(expo) + ok(idle) if x.get("action")] + ([open_delay] if open_delay else []),
                    key=lambda x: -x["expected_eur"])
    result = {
        "label": label(), "as_of": _today().isoformat(), "generated_at": store.now(),
        "nachtrag_documented": {"expected_eur": total(documented), "low_eur": total(documented, "low_eur"), "high_eur": total(documented, "high_eur"),
                                "count": len(documented)},
        "nachtrag_open": {"expected_eur": total([x for x in ok(expo) if not x.get("documented")]), "count": len([x for x in ok(expo) if not x.get("documented")])},
        "idle_avoided": {"expected_eur": sum(x["avoided_eur"] for x in accepted), "count": len(accepted)},
        "idle_avoidable": {"expected_eur": sum(x["avoided_eur"] for x in ok(idle) if not x.get("accepted")),
                           "cost_eur": total(ok(idle)), "count": len(ok(idle))},
        "delay_open": ({"expected_eur": open_delay["expected_eur"], "low_eur": open_delay["low_eur"], "high_eur": open_delay["high_eur"],
                        "slip_days": open_delay["slip_days"], "title": open_delay["title"]} if open_delay else None),
        "documentation": {"docs": len(ok(times)), "manual_min": round(manual), "assisted_min": round(assisted, 1), "saved_eur": round(saved_eur),
                          "ai_cost_total_eur": round(ai_total, 4) if ai_total else None,
                          "ai_cost_per_doc_eur": round(ai_total / len(ai_costs), 4) if ai_total else None},
        "return_ratio": round(gains / ai_total) if ai_total and gains else None,
        "top": events[:3],
        "items": {"nachtrag": expo, "idle": idle, "delay": delay, "time": times},
        "footer": _t("Estimate, internal · assumptions in the settings · not a claim amount",
                     "Schätzung, intern · Annahmen in den Einstellungen · kein Nachtragsbetrag"),
    }
    _remember(result)
    return result


# ---------------------------------------------------------------- decisions + calibration hook
def decide(key: str, accepted: bool) -> dict:
    d = store.load("cost_decisions", {})
    d[key] = {"accepted": bool(accepted), "at": store.now()}
    store.save("cost_decisions", d)
    return d[key]


def _remember(res):
    """Keep the latest estimate (with its inputs) per event so a real outcome can be compared later."""
    est = store.load("cost_estimates", {})
    for kind, xs in res["items"].items():
        for x in xs:
            if x.get("status") == "ok" and kind != "time":
                est[x["key"]] = {"expected_eur": x["expected_eur"], "low_eur": x["low_eur"], "high_eur": x["high_eur"],
                                 "inputs": {k: x.get(k) for k in ("extra_hours", "rate_eur_h", "remaining_hours", "idle_hours", "crew",
                                                                  "repair_days", "slip_days") if x.get(k) is not None},
                                 "sources": x["sources"], "at": res["generated_at"]}
    store.save("cost_estimates", est)


def record_outcome(key: str, actual_eur: float, note: str = "") -> dict:
    out = store.load("cost_outcomes", {})
    out[key] = {"actual_eur": float(actual_eur), "note": note[:200], "at": store.now()}
    store.save("cost_outcomes", out)
    return out[key]


def calibration() -> dict:
    est, outc = store.load("cost_estimates", {}), store.load("cost_outcomes", {})
    rows = []
    for k, o in outc.items():
        e = est.get(k)
        if e and o.get("actual_eur"):
            rows.append({"key": k, "estimate_eur": e["expected_eur"], "actual_eur": o["actual_eur"],
                         "error_pct": round(100 * (e["expected_eur"] - o["actual_eur"]) / o["actual_eur"], 1),
                         "inside_range": e["low_eur"] <= o["actual_eur"] <= e["high_eur"]})
    return {"pairs": rows, "mean_abs_error_pct": round(mean(abs(r["error_pct"]) for r in rows), 1) if rows else None}
