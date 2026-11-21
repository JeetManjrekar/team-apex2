"""Evidence sources for extraction (merged from APEX 2 `modules/intake.py` + `modules/extraction.SourceChunk`).

Every piece of evidence the LLM may cite is a SourceChunk with a stable `ref`. A field value survives only if it cites
a ref that was in the request (enforced in core.llm_extract, not trusted to the model).

Ref formats (APEX 2, section 8.2):
  msg:<id>                 chat text                    audio:<id>@<start>-<end>   one dictation segment (Whisper)
  mail:<id>                imported e-mail (.eml)       cal:<uid>                  calendar entry (.ics)
  photo:<id>               uploaded photo               doc:project@p1             project master data
  doc:bgg@p<n>             Baugrundgutachten page       drill:<pile>               Polier's drilling list row
  sched:<activity>         Bauzeitenplan row            dr:<date>#personal|geraete last daily report section
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
from functools import lru_cache
from typing import Any

from pydantic import BaseModel

from .llm_settings import CFG
from .store import load, project as store_project

_PAGE_RE = re.compile(r"\[\[SEITE\s+(\d+)\]\]")
_PILE_RE = re.compile(r"\b(?:Bohr)?pfahl\s*(?:nr\.?\s*)?(\d+)\b|\bpile\s*(\d+)\b|\bP0?(\d{1,2})\b", re.I)

# chunk kind -> host source type (what the review panel / export label shows)
KIND_TO_SRC = {"text": "message", "audio": "voice", "email": "email", "calendar": "calendar", "photo": "photo",
               "document": "document", "drilling": "drilling", "schedule": "schedule", "daily_report": "diary",
               "project": "project", "weather": "weather"}


class SourceChunk(BaseModel):
    ref: str
    kind: str
    label_de: str
    locator: str | None = None
    text: str
    url: str | None = None
    aliases: list[str] = []          # e.g. ["drill:P07"] for an uploaded Bohrprotokoll page
    data: dict[str, Any] = {}        # structured values for Python derivations (drilling rows)


def mmss(s: float) -> str:
    return f"{int(s // 60):02d}:{int(s % 60):02d}"


def pages(text_with_markers: str) -> list[tuple[int, str]]:
    parts = _PAGE_RE.split(text_with_markers or "")
    if len(parts) == 1:
        return [(1, (text_with_markers or "").strip())]
    return [(int(parts[i]), parts[i + 1].strip()) for i in range(1, len(parts) - 1, 2)]


def pile_id(s: str) -> str | None:
    m = _PILE_RE.search(s or "")
    if not m:
        return None
    n = next(g for g in m.groups() if g)
    return f"P{int(n):02d}"


# ---------------------------------------------------------------- primary sources (this turn)
def message_chunk(msg_id: str, text: str, kind: str = "text", locator: str | None = None) -> SourceChunk:
    if kind == "email":
        return SourceChunk(ref=f"mail:{msg_id}", kind="email", label_de="E-Mail", locator=locator or "E-Mail", text=text.strip())
    if kind == "document":      # one page / sheet block of an imported client document (outlook.import_document)
        return SourceChunk(ref=f"msg:{msg_id}", kind="document", label_de="Dokument", locator=locator or "Dokument", text=text.strip())
    return SourceChunk(ref=f"msg:{msg_id}", kind="text", label_de="Chatnachricht",
                       locator=locator or f"Chat-Nachricht {dt.datetime.now():%H:%M}", text=text.strip())


def audio_chunks(audio_id: str, segments: list[dict], audio_file: str | None = None, transcript: str = "") -> list[SourceChunk]:
    """One chunk per Whisper segment, so a field can cite the exact moment: audio:<id>@4.0-11.0 -> 'Diktat 00:04–00:11'."""
    segs = [s for s in (segments or []) if (s.get("text") or "").strip()]
    if not segs and transcript.strip():
        segs = [{"start": 0.0, "end": 0.0, "text": transcript}]
    url = f"/data/{audio_file}" if audio_file else None
    return [SourceChunk(ref=f"audio:{audio_id}@{float(s['start']):.1f}-{float(s['end']):.1f}", kind="audio", label_de="Sprachnachricht",
                        locator=f"Diktat {mmss(float(s['start']))}–{mmss(float(s['end']))}", text=s["text"].strip(), url=url)
            for s in segs]


def _det_summary(dets: list[dict]) -> str:
    """'excavator ×2 (max 91 %), person ×1 (78 %)'. Detections are already filtered by the photos.MIN_CONF thresholds."""
    by = {}
    for d in dets:
        by.setdefault(d["class"], []).append(d["confidence"])
    return ", ".join(f"{c} ×{len(v)} ({'max ' if len(v) > 1 else ''}{max(v) * 100:.0f} %)" for c, v in sorted(by.items())) or "keine"


def photo_chunks(day: str | None = None, ids: list[str] | None = None) -> list[SourceChunk]:
    """Photos of `day` (class names only), or the photos the user attached (`ids`: counts + confidence per class)."""
    out = []
    for p in load("photos", []):
        if (p["id"] not in ids) if ids else p.get("taken_at", "")[:10] != day:
            continue
        taken = p["taken_at"][:16].replace("T", " ")
        if ids:      # attached by the user this turn: full detector output + citation hint
            text = (f"Vom Bauleiter angehängtes Foto. Objekterkennung (Anzahl, Konfidenz): {_det_summary(p.get('detections', []))}. "
                    f"Kategorie {p['category']}, aufgenommen {taken}. {p.get('caption_de', '')} "
                    f"Erkennungen sind Hinweise, kein Beweis; Angaben aus diesem Foto mit photo:{p['id']} belegen.")
        else:
            dets = ", ".join(sorted({d["class"] for d in p.get("detections", [])})) or "keine"
            text = f"Foto vom {taken}, Kategorie {p['category']}, erkannt: {dets}. {p.get('caption_de', '')}".strip()
        out.append(SourceChunk(ref=f"photo:{p['id']}", kind="photo", label_de=f"Foto vom {taken}", locator=f"Foto {p['original_name']}",
                               text=text, url=f"/data/{p['file']}"))
    return out


# ---------------------------------------------------------------- project context (seeded demo data, cited like any source)
def _demo(*parts):
    return CFG.demo_dir.joinpath(*parts)


def project() -> dict:
    """Loaded project master data only; {} on a fresh/reset instance (never falls back to the bundled demo)."""
    return store_project()


def context_chunks(today: dt.date) -> list[SourceChunk]:
    chunks: list[SourceChunk] = []
    proj = project()
    if not proj:        # no project loaded: nothing from the bundled demo may be cited
        return chunks
    if proj:
        chunks.append(SourceChunk(
            ref="doc:project@p1", kind="project", label_de="Projektstammdaten", locator="Seite 1",
            text=(f"Projekt: {proj.get('name_de')}. Bauherr: {proj.get('bauherr')}. Auftragnehmer: {proj.get('contractor')}. "
                  f"Bauleiter: {proj.get('site_manager')}. Polier: {proj.get('polier')}. "
                  f"Nachtragsmanager: {proj.get('nachtragsmanager')}. Vertrag: {proj.get('contract_ref')}.")))
    f = _demo("source_documents", "baugrundgutachten_auszug.md")
    if f.exists():
        for n, page in pages(f.read_text(encoding="utf-8")):
            chunks.append(SourceChunk(ref=f"doc:bgg@p{n}", kind="document", label_de=f"Baugrundgutachten, Seite {n}",
                                      locator=f"Seite {n}", text=page))
    zf = _demo("site_plan", "zones.json")
    zones = {z["id"]: z["label_de"] for z in json.loads(zf.read_text(encoding="utf-8"))} if zf.exists() else {}
    f = _demo("drilling", "drilling_times.csv")
    if f.exists():
        for row in csv.DictReader(f.open(encoding="utf-8")):
            if not row.get("start"):
                continue
            end = row["end"] or (re.search(r"Stand (\d{1,2}:\d{2})", row.get("note_de") or "") or [None, None])[1]
            data = {**row, "end": end, "depth_reached_m": float(row["depth_reached_m"] or 0),
                    "target_depth_m": float(row["target_depth_m"] or 0), "crew_count": int(row["crew_count"] or 0)}
            chunks.append(SourceChunk(
                ref=f"drill:{row['pile_id']}", kind="drilling", label_de=f"Bohrzeitenliste Polier, {row['pile_id']}",
                locator=f"Zeile {row['pile_id']}",
                text=(f"Bohrzeitenliste des Poliers (kein förmliches Bohrprotokoll). {zones.get(row['pile_id'], row['pile_id'])} "
                      f"({row['pile_id']}), Bauteil {zones.get(row['zone_id'], row['zone_id'])}, {row['date']}, {row['start']} bis "
                      f"{end or 'laufend'} Uhr, erreicht {row['depth_reached_m']} m von {row['target_depth_m']} m, "
                      f"Gerät {row['rig_id']}, {row['crew_count']} Personen. {row['note_de']}"), data=data))
    f = _demo("schedule", "bauzeitenplan.csv")
    if f.exists():
        for row in csv.DictReader(f.open(encoding="utf-8")):
            try:
                s, e = dt.date.fromisoformat(row["start_planned"]), dt.date.fromisoformat(row["end_planned"])
            except (KeyError, ValueError):
                continue
            if (s - today).days <= 2 and (today - e).days <= 2:
                chunks.append(SourceChunk(
                    ref=f"sched:{row['id']}", kind="schedule", label_de=f"Bauzeitenplan, {row['id']}", locator=row["id"],
                    text=f"{row['name_de']} (Zone {row['zone_id']}), {row['start_planned']} bis {row['end_planned']}, "
                         f"Rolle {row.get('crew_role', '')}. {row.get('assumption_note_de', '')}"))
    reports = sorted(p for p in _demo("daily_reports").glob("*.json") if p.stem < today.isoformat()) if _demo("daily_reports").exists() else []
    if reports:
        dr = json.loads(reports[-1].read_text(encoding="utf-8"))
        staff = ", ".join(f"{k}: {v}" for k, v in dr.get("staff_by_company", {}).items())
        chunks.append(SourceChunk(ref=f"dr:{dr['date']}#personal", kind="daily_report", label_de=f"Bautagesbericht {dr['date']}, Personal",
                                  locator="Personal", text=f"Personal: {staff}"))
        chunks.append(SourceChunk(ref=f"dr:{dr['date']}#geraete", kind="daily_report", label_de=f"Bautagesbericht {dr['date']}, Geräte",
                                  locator="Geräte", text="Geräte: " + "; ".join(dr.get("equipment", []))))
    return chunks


# ---------------------------------------------------------------- chunk(s) -> host field source
def field_source(refs: list[str], by_ref: dict[str, SourceChunk], quote: str | None = None) -> dict:
    """The `source` dict stored on a document field. Keeps every cited chunk so the reviewer and the export appendix
    can show exactly what the value rests on."""
    first = by_ref[refs[0]]
    return {"type": KIND_TO_SRC.get(first.kind, first.kind), "evidence_id": ",".join(refs),
            "locator": "; ".join(dict.fromkeys(f"{by_ref[r].label_de}" + (f" ({by_ref[r].locator})" if by_ref[r].locator else "") for r in refs)),
            "quote": (quote or first.text)[:300], "url": first.url,
            "chunks": [{"ref": r, "label_de": by_ref[r].label_de, "text": by_ref[r].text[:600]} for r in refs]}
