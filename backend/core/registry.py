"""Document-type registry (merged from APEX 2): backend/registry/doc_types/*.yaml + backend/registry/prompts/*.md.

Single source of document fields for the host (core.docs), the extractor (core.llm_extract), the rule fallback and the
reviewer. A new notice type = one YAML + one prompt (+ optional Word template). Field keys per entry:
  key, label_de, type (text|number|datetime|date|list), required, critical, derived (computed in Python), question_de
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

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


def all_specs() -> list[dict]:
    return [doc_spec(t) for t in doc_types()]


def related_fields(doc_type: str, field_key: str) -> list[str]:
    """`followup_related`: fields re-extracted together when this follow-up is answered."""
    return list((doc_spec(doc_type).get("followup_related") or {}).get(field_key, []))


@lru_cache
def prompt(name: str) -> str:
    return (REG / "prompts" / name).read_text(encoding="utf-8")
