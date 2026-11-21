"""Fields beyond the registry schema: the Bautagesbericht has an Ort field, and the user can add / remove own fields on
any draft (chat commands, API, editor). Offline (fake LLM), isolated data dir.

Run from backend/:  python -m pytest tests -q
"""
import dataclasses

import pytest
from fastapi.testclient import TestClient

from core import assistant, docs, export, llm_adapter, llm_bridge, llm_extract, review, store
from core.llm_adapter import Usage


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    (tmp_path / "uploads").mkdir()
    monkeypatch.setattr(assistant.plan, "weather", lambda: None)   # no network
    monkeypatch.setattr(llm_bridge.METRICS, "_path", tmp_path / "metrics.jsonl")
    monkeypatch.setattr(assistant.plan, "DATA", tmp_path)
    monkeypatch.setattr(export, "DATA", tmp_path)
    assistant.plan.load_demo()
    yield tmp_path


def rules_mode(monkeypatch):
    cfg = dataclasses.replace(llm_extract.CFG, api_key="")
    for mod in (llm_extract, review, llm_adapter, llm_bridge):
        monkeypatch.setattr(mod, "CFG", cfg)


def llm_mode(monkeypatch):
    cfg = dataclasses.replace(llm_extract.CFG, provider="openai", api_key="test", model_extract="fake-model",
                              model_review="fake-model", reviewer_enabled=False, cache_mode="off")
    for mod in (llm_extract, review, llm_adapter, llm_bridge):
        monkeypatch.setattr(mod, "CFG", cfg)


class FakeLLM:
    def __init__(self, fields=None):
        self.fields, self.prompts = fields or {}, []

    def __call__(self, prompt, schema, model, **kw):
        self.prompts.append(prompt)
        if schema is llm_extract._IntentOut:
            return schema(intent="smalltalk"), Usage(model=model)
        ref = next((line[2:].split(">>")[0] for line in prompt.splitlines() if line.startswith("<<msg:")), "msg:x")
        fields = {k: {"value": v, "source_refs": [ref], "confidence": 0.9} for k, v in self.fields.items()}
        return schema.model_validate({"fields": fields, "followups": [], "assistant_message_de": ""}), Usage(model=model)


def say(text):
    return assistant.handle(text)["replies"][0]["text"]


def daily(monkeypatch):
    rules_mode(monkeypatch)
    say("Tagesbericht")
    return docs.get(store.load("chat_state", {})["active"])


# ---------------------------------------------------------------- Ort on the Bautagesbericht (the reported bug)
def test_daily_report_has_an_optional_location_field():
    meta = docs.field_meta("bautagesbericht", "location")
    assert meta and meta["label"] == "Ort / Bauabschnitt" and not meta["required"]


def test_daily_location_from_followup_answer_llm(monkeypatch):
    llm_mode(monkeypatch)
    monkeypatch.setattr(llm_extract, "complete_json", FakeLLM())
    say("Tagesbericht")
    d = store.load("chat_state", {})["active"]
    fake = FakeLLM({"location": "Achse 3, Widerlager Süd"})
    monkeypatch.setattr(llm_extract, "complete_json", fake)
    r = say("Wir waren heute an Achse 3, Widerlager Süd")
    assert docs.get(d)["fields"]["location"]["value"] == "Achse 3, Widerlager Süd" and "Ort / Bauabschnitt" in r
    assert "location" in fake.prompts[-1]                       # the model was offered the field
    assert "nicht entnehmen" not in r


def test_daily_location_as_label_value_rules(monkeypatch):
    d = daily(monkeypatch)
    r = say("Ort: Zufahrt Nord")
    f = docs.get(d["id"])["fields"]["location"]
    assert f["value"] == "Zufahrt Nord" and f["locked"] and "Ort / Bauabschnitt" in r


# ---------------------------------------------------------------- own fields via chat
def test_add_field_with_value(monkeypatch):
    d = daily(monkeypatch)
    r = say("Füge Feld Kranführer hinzu: Herr Maier")
    d = docs.get(d["id"])
    key = docs.find_field(d, "Kranführer")
    assert key.startswith("custom_") and d["fields"][key]["value"] == "Herr Maier" and "hinzugefügt" in r
    meta = next(m for m in docs.public(d)["meta"]["fields"] if m["key"] == key)
    assert meta["custom"] and not meta["required"] and key not in docs.missing(d)


@pytest.mark.parametrize("cmd", ["Neues Feld Kranführer: Herr Maier", "add field crane operator: Mr Maier",
                                 "Füge das Feld Kranführer zum Tagesbericht hinzu: Herr Maier"])
def test_add_field_phrasings(monkeypatch, cmd):
    d = daily(monkeypatch)
    say(cmd)
    d = docs.get(d["id"])
    assert len(d["custom_fields"]) == 1 and d["fields"][d["custom_fields"][0]["key"]]["value"].endswith("Maier")


def test_add_field_without_value_asks_for_it(monkeypatch):
    d = daily(monkeypatch)
    r = say("Füge Feld Besucherzahl hinzu")
    key = docs.find_field(docs.get(d["id"]), "Besucherzahl")
    assert "Was soll dort stehen" in r and store.load("chat_state", {})["pending"]["field"] == key
    say("12 Personen")
    assert docs.get(d["id"])["fields"][key]["value"] == "12 Personen"


def test_set_unknown_field_creates_it(monkeypatch):
    d = daily(monkeypatch)
    r = say("setze Sicherheitsunterweisung auf erledigt 7 Uhr")
    d = docs.get(d["id"])
    assert "Neues Feld" in r and d["fields"][docs.find_field(d, "Sicherheitsunterweisung")]["value"] == "erledigt 7 Uhr"


def test_existing_field_is_reused_not_duplicated(monkeypatch):
    d = daily(monkeypatch)
    say("Füge Feld Ort hinzu: Achse 3")
    d = docs.get(d["id"])
    assert not d.get("custom_fields") and d["fields"]["location"]["value"] == "Achse 3"


def test_remove_own_field_but_not_a_standard_one(monkeypatch):
    d = daily(monkeypatch)
    say("Füge Feld Kranführer hinzu: Herr Maier")
    assert "entfernt" in say("entferne Feld Kranführer")
    d = docs.get(d["id"])
    assert not d["custom_fields"] and not docs.find_field(d, "Kranführer")
    assert "Standardfeld" in say("entferne Feld Wetter") and "weather" in docs.get(d["id"])["fields"]
    docs.undo(d, next(i for i, e in enumerate(d["log"]) if e.get("field", "").startswith("custom_")))   # no crash


def test_unknown_label_value_gives_a_hint_and_adds_nothing(monkeypatch):
    rules_mode(monkeypatch)
    d = assistant.handle("Nachtrag: Fels an Pfahl 7")["active"]
    r = say("Schalung: 40 m2 gestellt")
    assert "Füge Feld Schalung hinzu" in r and not docs.get(d).get("custom_fields")


def test_field_names_match_whole_words():
    d = docs.create("bautagesbericht")
    assert docs.find_field(d, "ort") == "location" and docs.find_field(d, "Personal") == "staff_by_company"
    assert docs.find_field(d, "ord") is None                     # no substring hit in "Anordnungen"


# ---------------------------------------------------------------- export and API
def test_own_fields_are_exported(monkeypatch):
    d = daily(monkeypatch)
    say("Füge Feld Kranführer hinzu: Herr Maier")
    d = docs.get(d["id"])
    ctx = export.build_context(d)
    assert {"label": "Kranführer", "value": "Herr Maier"} in ctx["rows"] and any(r["label"] == "Kranführer" for r in ctx["sources"])
    assert "Kranführer" in export.print_html(d)
    from docx import Document
    text = "\n".join(c.text for t in Document(str(export.docx(d))).tables for row in t.rows for c in row.cells)
    assert "Kranführer" in text and "Herr Maier" in text


def test_api_add_and_remove_field():
    from app import app
    c = TestClient(app)
    d = docs.create("bautagesbericht")
    r = c.post(f"/api/docs/{d['id']}/fields", json={"label": "Kranführer", "value": "Herr Maier"})
    assert r.status_code == 200
    m = next(m for m in r.json()["meta"]["fields"] if m["custom"])
    assert r.json()["fields"][m["key"]]["value"] == "Herr Maier"
    assert c.patch(f"/api/docs/{d['id']}/fields/{m['key']}", json={"value": "Frau Huber"}).status_code == 200
    assert c.delete(f"/api/docs/{d['id']}/fields/weather").status_code == 400
    r = c.delete(f"/api/docs/{d['id']}/fields/{m['key']}")
    assert r.status_code == 200 and not any(x["custom"] for x in r.json()["meta"]["fields"])
    assert c.post(f"/api/docs/{d['id']}/fields", json={"label": ""}).status_code == 400
