"""Masks private data before any LLM call. Placeholders are reversible and restored afterwards."""
import re

PATTERNS = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b")),
    ("PHONE", re.compile(r"(?:\+|00)\d[\d \-/]{7,}\d|\b0\d{2,5}[ \-/]?\d{3,}[\d \-]*\d\b")),
]


def mask(text: str):
    mapping, counters = {}, {}
    for label, rx in PATTERNS:
        def rep(m):
            val = m.group(0)
            for k, v in mapping.items():
                if v == val:
                    return k
            counters[label] = counters.get(label, 0) + 1
            key = f"{label}_{counters[label]}"
            mapping[key] = val
            return key
        text = rx.sub(rep, text)
    return text, mapping


def unmask(obj, mapping):
    if not mapping:
        return obj
    if isinstance(obj, str):
        for k in sorted(mapping, key=len, reverse=True):
            obj = obj.replace(k, mapping[k])
        return obj
    if isinstance(obj, list):
        return [unmask(x, mapping) for x in obj]
    if isinstance(obj, dict):
        return {k: unmask(v, mapping) for k, v in obj.items()}
    return obj
