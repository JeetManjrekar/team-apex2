"""Follow-up answers are read against the whole draft, for every document type: fields in any order, several per
answer, an answer naming the draft type completes the open draft. Offline (fake LLM), isolated data dir.

Run from backend/:  python -m pytest tests -q
"""
import dataclasses

import pytest

from core import assistant, docs, llm_adapter, llm_bridge, llm_extract, review, store
from core.llm_adapter import Usage


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    (tmp_path / "uploads").mkdir()
    monkeypatch.setattr(assistant.plan, "weather", lambda: None)   # no network
    monkeypatch.setattr(llm_bridge.METRICS, "_path", tmp_path / "metrics.jsonl")
    monkeypatch.setattr(assistant.plan, "DATA", tmp_path)
    assistant.plan.load_demo()
    yield tmp_path


def rules_mode(monkeypatch):
    cfg = dataclasses.replace(llm_extract.CFG, api_key="")
    for mod in (llm_extract, review, llm_adapter, llm_bridge):
        monkeypatch.setattr(mod, "CFG", cfg)
    assert not cfg.llm_ready


def llm_mode(monkeypatch):
    cfg = dataclasses.replace(llm_extract.CFG, provider="openai", api_key="test", model_extract="fake-model",
                              model_review="fake-model", reviewer_enabled=False, cache_mode="off")
    for mod in (llm_extract, review, llm_adapter, llm_bridge):
        monkeypatch.setattr(mod, "CFG", cfg)


class FakeLLM:
    """Extraction answers: `fields` cited to the chat message of the prompt (the only source of a follow-up)."""

    def __init__(self, fields=None):
        self.fields, self.prompts = fields or {}, []

    def __call__(self, prompt, schema, model, **kw):
        self.prompts.append(prompt)
        if schema is llm_extract._IntentOut:
            return schema(intent="smalltalk"), Usage(model=model)
        ref = next((line[2:].split(">>")[0] for line in prompt.splitlines() if line.startswith("<<msg:")), "msg:x")
        fields = {k: {"value": v, "source_refs": [ref], "confidence": 0.9} for k, v in self.fields.items()}
        return schema.model_validate({"fields": fields, "followups": [], "assistant_message_de": ""}), Usage(model=model)


def pending():
    return store.load("chat_state", {}).get("pending") or {}


def value(doc_id, key):
    return docs.get(doc_id)["fields"][key]["value"]


def drafts(dtype):
    return [d for d in docs.all_docs() if d["type"] == dtype]


# ---------------------------------------------------------------- rules mode (no model)
def test_rules_answer_with_another_field_than_asked(monkeypatch):
    rules_mode(monkeypatch)
    d = assistant.handle("Nachtrag: Bohrgerät kommt kaum runter, Fels angetroffen")["active"]
    assert pending()["field"] == "location"
    r = assistant.handle("das war um 10:30")
    assert "10:30" in value(d, "occurred_at") and not value(d, "location")     # not stored verbatim as Ort
    assert "Datum und Uhrzeit" in r["replies"][0]["text"] and pending()["field"] == "location"


def test_rules_time_and_location_in_one_answer(monkeypatch):
    rules_mode(monkeypatch)
    d = assistant.handle("Nachtrag: Bohrgerät kommt kaum runter, Fels angetroffen")["active"]
    r = assistant.handle("heute 10:30 an Pfahl 7")
    assert value(d, "location") == "Pfahl 7" and "10:30" in value(d, "occurred_at")
    assert "Ort / Bauteil, Datum und Uhrzeit" in r["replies"][0]["text"]
    assert pending()["field"] not in ("location", "occurred_at")


def test_rules_answer_naming_the_draft_type_completes_it(monkeypatch):
    rules_mode(monkeypatch)
    d = assistant.handle("Nachtrag: Bohrgerät kommt kaum runter, Fels angetroffen")["active"]
    assistant.handle("heute 10:30 an Pfahl 7")
    r = assistant.handle("Nachtrag: ab 4 Meter Fels, war bei Pfahl 7")
    assert r["active"] == d and len(drafts("nachtragsmeldung")) == 1 and value(d, "depth_rock_m") == "4"
    assert value(d, "found_ground") == "Fels angetroffen"          # rules never overwrite or propose on filled fields


def test_rules_new_incident_still_gets_its_own_draft(monkeypatch):
    rules_mode(monkeypatch)
    assistant.handle("Nachtrag: Bohrgerät kommt kaum runter, Fels angetroffen")
    assistant.handle("heute 10:30 an Pfahl 7")
    assistant.handle("Nachtrag bei Pfahl 9: Fels ab 3 m")                   # other location
    assistant.handle("Neuer Nachtrag: Fels ab 2 m")                         # explicit new
    assert len(drafts("nachtragsmeldung")) == 3


def test_rules_site_note_goes_to_diary_and_question_stays(monkeypatch):
    rules_mode(monkeypatch)
    d = assistant.handle("Nachtrag: Bohrgerät kommt kaum runter, Fels angetroffen")["active"]
    before = pending()
    r = assistant.handle("Beton für Achse 2 geliefert")
    assert "Bautagebuch" in r["replies"][0]["text"] and not value(d, "location") and pending() == before


def test_rules_unrecognised_answer_is_the_asked_value(monkeypatch):
    rules_mode(monkeypatch)
    d = assistant.handle("Nachtrag: Bohrgerät kommt kaum runter, Fels angetroffen")["active"]
    assistant.handle("Zufahrt Nord, vor dem Kran")
    f = docs.get(d)["fields"]["location"]
    assert f["value"] == "Zufahrt Nord, vor dem Kran" and f["source"]["type"] == "answer"


def test_rules_behinderung_two_fields_in_one_answer(monkeypatch):
    rules_mode(monkeypatch)
    d = assistant.handle("Behinderung: Bagger steht still")["active"]
    assistant.handle("seit 10 Uhr, dauert voraussichtlich 2 Tage")
    assert "10" in value(d, "occurred_at") and "2 Tage" in value(d, "expected_duration")


def test_skip_skips_the_whole_question(monkeypatch):
    llm_mode(monkeypatch)
    monkeypatch.setattr(llm_extract, "complete_json", FakeLLM())
    d = assistant.handle("Bagger steht seit 10 Uhr wegen Hydraulikschaden")["active"]
    asked = pending()["fields"]
    assistant.handle("skip")
    assert store.load("chat_state", {})["skipped"][d] == asked and not set(asked) & set(pending().get("fields", []))


# ---------------------------------------------------------------- model mode, every flow type
START = {"nachtragsmeldung": "Pfahl 7, ab 4 Meter Fels", "behinderungsanzeige": "Bagger steht wegen Hydraulikschaden",
         "bautagesbericht": "Tagesbericht"}


@pytest.mark.parametrize("dtype", list(START))
def test_llm_asks_several_fields_and_fills_any_of_them(monkeypatch, dtype):
    llm_mode(monkeypatch)
    monkeypatch.setattr(llm_extract, "complete_json", FakeLLM())
    d = assistant.handle(START[dtype])["active"]
    assert docs.get(d)["type"] == dtype
    asked = pending()["fields"]
    assert len(asked) > 1 and "beliebiger Reihenfolge" in store.load("messages", [])[-1]["text"]
    # the answer gives the 2nd and 3rd asked field but not the main one
    given = asked[1:3]
    fake = FakeLLM({k: "10:30" if "time" in k or k.endswith("_at") else "Achse 3" for k in given})
    monkeypatch.setattr(llm_extract, "complete_json", fake)
    r = assistant.handle("Achse 3, um 10:30, und noch was dazu")
    assert all(value(d, k) for k in given) and not value(d, asked[0])
    assert "Übernommen" in r["replies"][0]["text"] and asked[0] in pending()["fields"]
    # the model saw every empty field, not only the asked one, and the any-order note
    empty = [k for k, v in docs.get(d)["fields"].items() if not v["value"]]
    assert all(k in fake.prompts[-1] for k in empty)
    assert "beliebiger Reihenfolge" in fake.prompts[-1]
    assert len(drafts(dtype)) == 1


def test_llm_correction_of_a_filled_field_is_a_proposal(monkeypatch):
    llm_mode(monkeypatch)
    monkeypatch.setattr(llm_extract, "complete_json", FakeLLM({"location": "Pfahl 7", "found_ground": "Fels"}))
    d = assistant.handle("Pfahl 7, ab 4 Meter Fels")["active"]
    monkeypatch.setattr(llm_extract, "complete_json", FakeLLM({"found_ground": "Kalkstein"}))
    r = assistant.handle("Korrektur: das war Kalkstein, kein Fels")
    f = docs.get(d)["fields"]["found_ground"]
    assert f["value"] == "Fels" and f["proposal"]["value"] == "Kalkstein" and "Vorschlag" in r["replies"][0]["text"]


def test_llm_locked_field_is_never_touched(monkeypatch):
    llm_mode(monkeypatch)
    monkeypatch.setattr(llm_extract, "complete_json", FakeLLM())
    d = assistant.handle("Bagger steht seit 10 Uhr wegen Hydraulikschaden")["active"]
    key = pending()["fields"][0]
    doc = docs.get(d)
    docs.set_field(doc, key, "vom Nutzer", {"type": "user"}, by="user")
    docs.put(doc)
    fake = FakeLLM({key: "von der KI"})
    monkeypatch.setattr(llm_extract, "complete_json", fake)
    assistant.handle("noch eine Angabe dazu")
    assert value(d, key) == "vom Nutzer"
