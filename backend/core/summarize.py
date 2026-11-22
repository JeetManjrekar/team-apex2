"""Summaries of minutes, diary entries and emails: open items with owner and deadline, decisions, Nachtrag candidates."""
import re
from . import llm, sanitizer
from .i18n import T

I = re.I
OPEN_KW = re.compile(r"\bbis\b|until|\bby\b|deadline|frist|offen|\bopen\b|todo|to do|soll|muss|klären|liefern|prüf|senden|einholen|"
                     r"entscheid|freigabe|bitte|please|needs? to|will\b", I)
DECIDE_KW = re.compile(r"beschlossen|vereinbart|festgelegt|decided|agreed|beibehalten|\bkept\b|retained|confirmed", I)
DATE = re.compile(r"\b\d{1,2}\.\d{1,2}\.(?:\d{2,4})?|\b\d{4}-\d{2}-\d{2}|\bKW\s?\d{1,2}\b|"
                  r"\b(?:montag|dienstag|mittwoch|donnerstag|freitag|monday|tuesday|wednesday|thursday|friday)\b", I)
OWNER = re.compile(r"(?:verantwortlich|verantw\.|zuständig|responsible|owner|wer)\s*:\s*([^|;\n]+)|@(\w+)|\(([A-ZÄÖÜ][\w. ]+)\)\s*$", I)
NACHTRAG = re.compile(r"bitte führen sie|please (?:proceed|continue|carry out)|ordnen (?:wir )?an|anordnung|instruct|zusätzlich|"
                      r"additional|abweichend|geänderte|change order", I)


def _lines(text):
    out = []
    for raw in text.splitlines():
        for s in ([raw] if "|" in raw else re.split(r"(?<=[a-zäöüß0-9]{3}[.!?])\s+(?=[A-ZÄÖÜ])", raw)):
            s = s.strip(" -•*\t")
            if len(s) > 3:
                out.append(s)
    return out


def rules(text):
    is_email = bool(re.search(r"^(?:von|from|betreff|subject)\s*:", text, I | re.M))
    subject = re.search(r"^(?:betreff|subject)\s*:\s*(.+)$", text, I | re.M)
    items, decisions, nachtrag = [], [], []
    for s in _lines(text):
        if re.match(r"^(?:von|an|from|to|cc|datum|date|betreff|subject|teilnehmer)\s*:", s, I):
            continue
        if DECIDE_KW.search(s):
            decisions.append(s)
            continue
        if NACHTRAG.search(s):
            nachtrag.append(s)
        dl = DATE.search(s)
        if OPEN_KW.search(s) and (dl or OWNER.search(s) or re.search(r"bitte|please|offen|open", s, I)):
            m = OWNER.search(s)
            owner = next((g for g in m.groups() if g), "").strip() if m else (T("sm_we") if is_email and re.search(r"bitte|please", s, I) else "")
            item = re.split(r"\s*\|\s*", s)[0]
            items.append({"item": item, "owner": owner, "deadline": dl.group(0) if dl else "", "quote": s})
    head = subject.group(1) if subject else (_lines(text)[0] if _lines(text) else "")
    summary = [head] + ([T("sm_counts", n=len(items), m=len(decisions))] if items or decisions else [])
    return {"kind": "email" if is_email else "minutes", "summary": summary, "open_items": items,
            "decisions": decisions, "nachtrag_candidates": nachtrag}


SYSTEM = """Summarize construction site minutes, diary entries or emails in German.
Use only what the text says. Every open item and decision needs "quote": a verbatim substring of the text.
Return JSON: {"kind":"minutes|email|diary","summary":["..."],"open_items":[{"item":"","owner":"","deadline":"","quote":""}],
"decisions":["..."],"nachtrag_candidates":["verbatim sentence where the client orders additional or changed work"]}"""


def summarize(text):
    masked, mapping = sanitizer.mask(text)
    res = rules(masked)
    if llm.provider():
        try:
            r = llm.chat_json(SYSTEM, masked)
            if r:
                r["open_items"] = [i for i in r.get("open_items", []) if i.get("quote") and i["quote"].lower() in masked.lower()]
                res = {**res, **{k: v for k, v in r.items() if v}}
        except Exception:
            pass
    res = sanitizer.unmask(res, mapping)
    res["masked"] = sorted(mapping.keys())
    return res


SAMPLE_MINUTES = """Baubesprechung Nr. 7 – Ersatzneubau Brücke BW 12 – 20.11.2026
Teilnehmer: Bauherr (Hr. Weber), Bauleitung (J. Manjrekar), Tragwerksplanung (Fr. Schulz), NU Bohrarbeiten (Hr. Kaya)

1. Bohrpfähle Achse 10: Pfahl 7 bei 4 m auf Fels gestoßen, laut Baugrundgutachten erst ab 9 m erwartet. Weiteres Vorgehen offen.
- Prüfung, ob die Pfahllänge reduziert werden kann | Verantwortlich: Fr. Schulz | bis 24.11.2026
- Entscheidung über Meißeleinsatz | Verantwortlich: Hr. Weber | bis 23.11.2026
2. Bewehrungspläne Pfahlkopfbalken: Freigabe Rev. C fehlt noch.
- Freigabe der Bewehrungspläne Rev. C | Verantwortlich: Fr. Schulz | bis 22.11.2026
3. Betonage Pfahlkopfbalken: Termin 26.–28.11. beibehalten.
- Angebot Winterbaumaßnahmen einholen | Verantwortlich: J. Manjrekar | bis 25.11.2026
Beschlossen: Nächste Baubesprechung am 27.11.2026, 10:00 Uhr."""

SAMPLE_EMAIL = """Von: k.weber@bauherr-musterstadt.de
An: bauleitung@beispiel-bau.de
Betreff: Pfahl 7 – weiteres Vorgehen
Datum: 21.11.2026 08:12

Sehr geehrter Herr Manjrekar,

bitte führen Sie die Bohrarbeiten an Pfahl 7 mit Meißeleinsatz bis zur planmäßigen Tiefe von 12 m fort. Die Tragwerksplanung bestätigt die ursprüngliche Pfahllänge.
Bitte senden Sie uns bis Montag, 23.11.2026, eine Aufstellung der zusätzlichen Bohrzeiten.

Mit freundlichen Grüßen
Klaus Weber
Tel. 089 1234567"""


def samples() -> dict:
    """Sample minutes + email for the Summaries tab in the request language. German: the texts above; English: their
    translations, kept as their own files (backend/data/demo/samples/*_en.*)."""
    from .i18n import get_lang
    from .plan import DEMO_DIR
    if get_lang() == "en":
        d = DEMO_DIR / "samples"
        try:
            return {"minutes": (d / "sample_minutes_en.md").read_text(encoding="utf-8").strip(),
                    "email": (d / "sample_email_en.txt").read_text(encoding="utf-8").strip()}
        except OSError:
            pass
    return {"minutes": SAMPLE_MINUTES, "email": SAMPLE_EMAIL}

