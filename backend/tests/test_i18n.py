"""App-wide language: registry, drafting replies, daily report, export and prompts follow the request language
(de | en); nothing of the other language leaks in. Offline, isolated data dir."""
import re

import pytest
from fastapi.testclient import TestClient

from core import assistant, docs, export, i18n, llm_bridge, registry, store
from core.i18n import set_lang
from test_custom_fields import isolated, rules_mode  # noqa: F401  (fixtures / helpers)

DE_MARK = re.compile(r"[äöüß]|\b(bitte|angabe|angaben|entwurf|feld|foto|fotos|erstellt|übernommen|noch offen|nicht|oder|und)\b", re.I)


def test_catalog_complete():
    for k, e in i18n.CATALOG.items():
        assert e.get("de") and e.get("en"), k


@pytest.mark.parametrize("dtype", registry.doc_types())
def test_registry_fully_translated(dtype):
    spec = registry.doc_spec(dtype)
    assert spec.get("label_en") and "static_text_en" in spec
    for f in spec["fields"]:
        assert f.get("label_en"), (dtype, f["key"])
        assert not f.get("question_de") or f.get("question_en"), (dtype, f["key"])
    for c in spec["checklist"]:
        assert c.get("label_en"), (dtype, c["key"])
    set_lang("en")
    t = docs.DOC_TYPES[dtype]
    texts = [t["title"], t["description"], t["basis"], t["closing"]] + [f[1] for f in t["fields"]] + [f[4] for f in t["fields"]] \
        + [c["label"] for c in t["checklist"]]
    assert not any(DE_MARK.search(x or "") for x in texts), [x for x in texts if DE_MARK.search(x or "")]


def test_language_switches_titles_on_read(isolated, monkeypatch):  # noqa: F811
    rules_mode(monkeypatch)
    set_lang("de")
    d = docs.create("bautagesbericht")
    assert docs.get(d["id"])["title"] == "Bautagesbericht"
    set_lang("en")
    assert docs.get(d["id"])["title"] == "Daily site report"
    assert docs.public(docs.get(d["id"]))["meta"]["fields"][0]["label"] == "Date"


def test_daily_report_english_has_no_german(isolated, monkeypatch):  # noqa: F811
    rules_mode(monkeypatch)
    r = assistant.handle("daily report", lang="en")
    reply = r["replies"][0]["text"]
    doc = docs.get(r["active"])
    assert not DE_MARK.search(reply.replace("Bautagesbericht", "")), reply
    assert doc["title"] == "Daily site report"
    for k, f in doc["fields"].items():
        if f["source"] and f["source"].get("locator"):
            assert not DE_MARK.search(f["source"]["locator"]), (k, f["source"]["locator"])


def test_drafting_reply_english(isolated, monkeypatch):  # noqa: F811
    rules_mode(monkeypatch)
    r = assistant.handle("Change order: rock at pile 7 from 4 m, drilling rig stuck", lang="en")
    reply = r["replies"][0]["text"]
    assert reply.startswith("✓ Draft ready: Change order notice"), reply
    assert not DE_MARK.search(reply), reply
    doc = docs.get(r["active"])
    for k, f in doc["fields"].items():
        loc = (f["source"] or {}).get("locator") or ""
        assert not re.search(r"Seite|Zeile|Bohrzeitenliste|Projektstammdaten|Chat-Nachricht|Antwort im", loc), (k, loc)


def test_export_follows_language(isolated, monkeypatch):  # noqa: F811
    rules_mode(monkeypatch)
    set_lang("de")
    d = docs.create("nachtragsmeldung")
    set_lang("en")
    h = export.print_html(docs.get(d["id"]))
    assert '<html lang="en">' in h and "Formal completeness" in h and "Formale" not in h and "offen" not in h
    set_lang("de")
    h = export.print_html(docs.get(d["id"]))
    assert '<html lang="de">' in h and "Formale Vollständigkeit" in h


def test_prompt_gets_english_rule_only_in_english():
    set_lang("de")
    assert "LANGUAGE" not in registry.prompt("nachtragsmeldung.md")
    set_lang("en")
    assert registry.prompt("nachtragsmeldung.md").startswith("SPRACHE / LANGUAGE")


def test_middleware_sets_language(isolated):  # noqa: F811
    from app import app
    c = TestClient(app)
    assert c.get("/api/config", headers={"X-Lang": "en"}).json()["doc_types"]["maengelanzeige"]["title"] == "Defect notice"
    assert c.get("/api/config", headers={"X-Lang": "de"}).json()["doc_types"]["maengelanzeige"]["title"] == "Mängelanzeige"
