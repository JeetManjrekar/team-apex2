"""Document-type registry (merged from APEX 2): backend/registry/doc_types/*.yaml + backend/registry/prompts/*.md.

Single source of document fields for the host (core.docs), the extractor (core.llm_extract), the rule fallback and the
reviewer. A new notice type = one YAML + one prompt (+ optional Word template). Field keys per entry:
  key, label_de, type (text|number|datetime|date|list), required, critical, derived (computed in Python), question_de
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .i18n import get_lang

REG = Path(__file__).resolve().parent.parent / "registry"


@lru_cache
def doc_spec(doc_type: str) -> dict:
    spec = yaml.safe_load((REG / "doc_types" / f"{doc_type}.yaml").read_text(encoding="utf-8"))
    if spec.get("key") != doc_type:
        raise ValueError(f"registry mismatch: {doc_type}.yaml has key {spec.get('key')!r}")
    return spec


@lru_cache
def doc_types() -> tuple[str, ...]:
    return tuple(p.stem for p in sorted((REG / "doc_types").glob("*.yaml")))


def tr(obj: dict, base: str, lang: str | None = None, default: str = "") -> str:
    """Language-aware text from a registry dict: `<base>_<lang>`, falling back to `<base>_de`."""
    return obj.get(f"{base}_{lang or get_lang()}") or obj.get(f"{base}_de") or default


def all_specs() -> list[dict]:
    return [doc_spec(t) for t in doc_types()]


def related_fields(doc_type: str, field_key: str) -> list[str]:
    """`followup_related`: fields re-extracted together when this follow-up is answered."""
    return list((doc_spec(doc_type).get("followup_related") or {}).get(field_key, []))


@lru_cache
def _prompt_raw(name: str) -> str:
    return (REG / "prompts" / name).read_text(encoding="utf-8")


EN_RULE = ("\n\nSPRACHE / LANGUAGE: The user works in English. Write EVERY free-text output in English (field values, questions, "
           "notes, explanations, messages), translating German source text where needed. Keep JSON keys, field keys, enum values, "
           "names, numbers and quoted evidence unchanged. This rule overrides any German wording above.")


def prompt(name: str) -> str:
    """Prompt file; with English selected an English-output rule is appended (the prompts themselves stay German)."""
    p = _prompt_raw(name)
    return (EN_RULE.lstrip() + "\n\n" + p) if get_lang() == "en" and name not in ("chat.md", "extraction_rules.md") else p
