"""Merge tests: APEX 2 LLM pipeline on the repo's JSON store, chat and voice path. Offline (fake LLM), isolated data dir.

Run from backend/:  python -m pytest tests -q
"""
import dataclasses
import json
from types import SimpleNamespace

import pytest

from core import assistant, docs, llm_adapter, llm_bridge, llm_extract, review, sources, store
from core.llm_adapter import Usage


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    (tmp_path / "uploads").mkdir()
    monkeypatch.setattr(assistant.plan, "weather", lambda: None)   # no network
    monkeypatch.setattr(llm_bridge.METRICS, "_path", tmp_path / "metrics.jsonl")
    yield tmp_path


def llm_mode(monkeypatch, reviewer=False):
    cfg = dataclasses.replace(llm_extract.CFG, provider="openai", api_key="test", model_extract="fake-model",
                              model_review="fake-model", reviewer_enabled=reviewer, cache_mode="off")
    for mod in (llm_extract, review, llm_adapter, llm_bridge):
        monkeypatch.setattr(mod, "CFG", cfg)
    return cfg


class FakeLLM:
    """Answers extraction prompts with the given fields; records every prompt it saw."""

    def __init__(self, fields=None, followups=None, message="", intent="smalltalk"):
        self.fields, self.followups, self.message, self.intent, self.prompts = fields or {}, followups or [], message, intent, []

    def __call__(self, prompt, schema, model, **kw):
        self.prompts.append(prompt)
        if schema is llm_extract._IntentOut:
            return schema(intent=self.intent), Usage(input=10, output=2, model=model)
        if schema is llm_extract._ChatOut:
            return schema(reply="2 plus 1 ist 3. Sagen Sie mir z. B. „Pfahl 7, ab 4 Meter Fels“."), Usage(input=50, output=20, model=model)
        if schema is review._JudgeOut:
            return schema(verdicts=self.verdicts), Usage(input=10, output=5, model=model)
        return schema.model_validate({"fields": self.fields, "followups": self.followups, "assistant_message_de": self.message}), \
            Usage(input=100, output=50, model=model)


def ctx():
    return sources.context_chunks(sources.dt.date(2026, 11, 17))


# ---------------------------------------------------------------- registry
def test_registry_drives_doc_types():
    assert set(docs.DOC_TYPES) == {"nachtragsmeldung", "behinderungsanzeige", "mehrkostenanzeige", "maengelanzeige",
                                   "bautagesbericht", "bedenkenanmeldung", "aktennotiz"}
    keys = [f[0] for f in docs.DOC_TYPES["nachtragsmeldung"]["fields"]]
    assert {"depth_rock_m", "drilling_time_ratio", "expected_ground_ref", "drilling_log_ref"} <= set(keys)


# ---------------------------------------------------------------- extractor gates (APEX 2 guarantees)
def test_source_gate_confidence_gate_and_derived_numbers(monkeypatch):
    llm_mode(monkeypatch)
    msg = sources.message_chunk("m1", "Pfahl 7, ab 4 Meter Fels, Bohrgerät kommt kaum runter")
    fake = FakeLLM(fields={
        "location": {"value": "Widerlager 1, Pfahl 7", "source_refs": ["msg:m1", "drill:P07"], "confidence": 0.9},
        "found_ground": {"value": "Fels", "source_refs": ["msg:m1"], "confidence": 0.9},
        "depth_rock_m": {"value": "4 m", "source_refs": ["msg:m1"], "confidence": 0.95},
        "expected_ground": {"value": "Sand und Kies", "source_refs": ["doc:bgg@p14"], "confidence": 0.9},
        "ordered_by": {"value": "Herr Weber", "source_refs": ["mail:invented"], "confidence": 0.9},   # ref not in request
        "rig": {"value": "BG-01", "source_refs": ["drill:P07"], "confidence": 0.3},                    # below threshold
        "drilling_time_h": {"value": 99, "source_refs": ["msg:m1"], "confidence": 1.0},                # derived: LLM ignored
    })
    monkeypatch.setattr(llm_extract, "complete_json", fake)
    res = llm_extract.extract("nachtragsmeldung", [msg] + ctx(), run_id="t", focus={"pile_id": "P07"})
    f = res.fields
    assert f["location"].value == "Widerlager 1, Pfahl 7" and f["depth_rock_m"].value == 4.0
    assert f["ordered_by"].value is None and res.dropped["ordered_by"] == "no_valid_source"
    assert f["rig"].value is None and res.dropped["rig"] == "low_confidence"
    assert f["drilling_time_h"].derived and f["drilling_time_h"].value != 99
    assert f["drilling_time_ratio"].value == pytest.approx(3.0, abs=0.3)          # eval case_01 expectation
    assert {fu.field_key for fu in res.followups} >= {"drilling_log_ref", "ordered_by"}
    assert "drill:P07" in res.sources


def test_pii_is_masked_in_prompt_and_restored(monkeypatch):
    llm_mode(monkeypatch)
    msg = sources.message_chunk("m2", "Bagger steht seit 10 Uhr. Rückruf an k.weber@bauherr.de oder 089 1234567.")
    fake = FakeLLM(fields={"measures": {"value": "Rückruf an EMAIL_1 erbeten", "source_refs": ["msg:m2"], "confidence": 0.9}})
    monkeypatch.setattr(llm_extract, "complete_json", fake)
    res = llm_extract.extract("behinderungsanzeige", [msg], run_id="t")
    assert "k.weber@bauherr.de" not in fake.prompts[0] and "1234567" not in fake.prompts[0]
    assert res.fields["measures"].value == "Rückruf an k.weber@bauherr.de erbeten"


# ---------------------------------------------------------------- chat + voice (rules mode, no key)
def test_hero_text_rules_mode_cites_sources():
    r = assistant.handle("Pfahl 7, ab 4 Meter Fels, Bohrgerät kommt kaum runter")
    d = docs.get(r["active"])
    assert d["type"] == "nachtragsmeldung" and d["extraction_mode"] == "rules"
    assert d["fields"]["depth_rock_m"]["value"] == "4"
    assert d["fields"]["location"]["source"]["evidence_id"].startswith("msg:")
    assert d["fields"]["drilling_time_ratio"]["value"]                              # Python-derived, no LLM needed
    assert d["fields"]["expected_ground_ref"]["source"]["evidence_id"] == "doc:bgg@p14"
    assert d["fields"]["project"]["source"]["evidence_id"] == "doc:project@p1"


def test_voice_fields_cite_whisper_segments():
    meta = {"audio_file": "uploads/a1.webm", "duration_s": 9.0, "stt_model": "faster-whisper-small",
            "segments": [{"start": 0.0, "end": 3.2, "text": "Pfahl 7."}, {"start": 3.2, "end": 9.0, "text": "Ab 4 Meter Fels."}]}
    r = assistant.handle("Pfahl 7. Ab 4 Meter Fels.", voice=True, evidence_meta=meta)
    d = docs.get(r["active"])
    loc, depth = d["fields"]["location"]["source"], d["fields"]["depth_rock_m"]["source"]
    assert loc["evidence_id"].startswith("audio:") and loc["type"] == "voice"
    assert "@0.0-3.2" in loc["evidence_id"] and "Diktat 00:00–00:03" in loc["locator"]
    assert "@3.2-9.0" in depth["evidence_id"]


def test_voice_llm_mode_end_to_end(monkeypatch):
    llm_mode(monkeypatch)
    seg_ref = None

    def fake(prompt, schema, model, **kw):
        nonlocal seg_ref
        seg_ref = next(line[2:].split(">>")[0] for line in prompt.splitlines() if line.startswith("<<audio:"))
        return schema.model_validate({"fields": {"occurred_at": {"value": "10:00", "source_refs": [seg_ref], "confidence": 0.9},
                                                 "cause": {"value": "Hydraulikschaden", "source_refs": [seg_ref], "confidence": 0.9}},
                                      "followups": [{"field_key": "expected_duration", "question_de": "Wie lange dauert die Reparatur?"}],
                                      "assistant_message_de": "Behinderungsanzeige vorbereitet."}), Usage(input=1, output=1, model=model)
    monkeypatch.setattr(llm_extract, "complete_json", fake)
    meta = {"audio_file": "uploads/a2.webm", "segments": [{"start": 0.0, "end": 4.1, "text": "Bagger steht seit 10 Uhr wegen Hydraulikschaden"}]}
    r = assistant.handle("Bagger steht seit 10 Uhr wegen Hydraulikschaden", voice=True, evidence_meta=meta)
    d = docs.get(r["active"])
    assert d["type"] == "behinderungsanzeige" and d["extraction_mode"] == "llm"
    assert d["fields"]["cause"]["source"]["evidence_id"] == seg_ref and d["fields"]["occurred_at"]["value"].endswith("10:00")
    assert d["fields"]["addressee"]["value"] == "Staatliches Bauamt (fiktiv)"          # host field from doc:project@p1
    assert "Wie lange dauert die Reparatur?" in r["replies"][0]["text"] or "Empfänger" in r["replies"][0]["text"]


def test_followup_answer_is_reextracted_not_invented(monkeypatch):
    llm_mode(monkeypatch)
    monkeypatch.setattr(llm_extract, "complete_json", FakeLLM(fields={
        "occurred_at": {"value": "10:00", "source_refs": ["msg:x"], "confidence": 0.9}}))
    r = assistant.handle("Bagger steht seit 10 Uhr wegen Hydraulikschaden")
    d = docs.get(r["active"])
    state = store.load("chat_state", {})
    pending = state["pending"]["field"]
    # an answer without the value -> question stays open, nothing written
    monkeypatch.setattr(llm_extract, "complete_json", FakeLLM(fields={}))
    r2 = assistant.handle("weiß ich gerade nicht genau, frag den Polier")
    assert "bleibt offen" in r2["replies"][0]["text"] and not docs.get(d["id"])["fields"][pending]["value"]
    # an answer with the value -> filled, cited to the answer message
    ans = {pending: {"value": "zwei Tage", "source_refs": [], "confidence": 0.9}}

    def fake(prompt, schema, model, **kw):
        ref = next(line[2:].split(">>")[0] for line in prompt.splitlines() if line.startswith("<<msg:"))
        ans[pending]["source_refs"] = [ref]
        return schema.model_validate({"fields": ans, "followups": [], "assistant_message_de": ""}), Usage()
    monkeypatch.setattr(llm_extract, "complete_json", fake)
    assistant.handle("Die Reparatur dauert zwei Tage")
    f = docs.get(d["id"])["fields"][pending]
    assert f["value"] == "zwei Tage" and f["source"]["evidence_id"].startswith("msg:")


def test_user_lock_survives_new_ai_input(monkeypatch):
    llm_mode(monkeypatch)
    monkeypatch.setattr(llm_extract, "complete_json", FakeLLM(fields={
        "location": {"value": "Pfahl 7", "source_refs": ["drill:P07"], "confidence": 0.9},
        "found_ground": {"value": "Fels", "source_refs": ["drill:P07"], "confidence": 0.9}}))
    d = docs.get(assistant.handle("Pfahl 7 ab 4 m Fels")["active"])
    docs.set_field(d, "found_ground", "Kalkstein, angewittert", {"type": "user"}, by="user")
    docs.put(d)
    d2 = docs.get(assistant.handle("Pfahl 7 nochmal: Fels ab 4 m")["active"])
    assert d2["id"] == d["id"] and d2["fields"]["found_ground"]["value"] == "Kalkstein, angewittert"
    assert d2["fields"]["found_ground"]["locked"]


# ---------------------------------------------------------------- reviewer
def test_reviewer_double_judge_unanimous_and_edit_guard(monkeypatch):
    llm_mode(monkeypatch, reviewer=True)
    monkeypatch.setattr(review, "CFG", dataclasses.replace(review.CFG, reviewer_mode="double_judge"))
    monkeypatch.setattr(llm_extract, "complete_json", FakeLLM(fields={
        "location": {"value": "Widerlager 1, Pfahl 7", "source_refs": ["drill:P07"], "confidence": 0.9},
        "depth_rock_m": {"value": 5, "source_refs": ["drill:P07"], "confidence": 0.9},
        "found_ground": {"value": "Fels", "source_refs": ["drill:P07"], "confidence": 0.9}}))
    started = []
    fake_thread = lambda target, args, daemon: started.append((target, args)) or type("T", (), {"start": lambda s: None})()
    monkeypatch.setattr(review, "threading", SimpleNamespace(Thread=fake_thread))   # run the background job by hand
    d = docs.get(assistant.handle("Pfahl 7, ab 4 Meter Fels")["active"])
    assert d["fields"]["depth_rock_m"]["review"]["status"] == "being_verified"
    # the user edits found_ground while the judges run -> its verdict must not be written
    docs.set_field(d, "found_ground", "Fels (Kalkstein)", {"type": "user"}, by="user")
    docs.put(d)
    verdicts = {"a": [review.Verdict(field_key="location", supported=True), review.Verdict(field_key="depth_rock_m", supported=False, note_de="Liste nennt 4,0 m"),
                      review.Verdict(field_key="found_ground", supported=False)],
                "b": [review.Verdict(field_key="location", supported=True), review.Verdict(field_key="depth_rock_m", supported=True),
                      review.Verdict(field_key="found_ground", supported=False)]}
    monkeypatch.setattr(review, "_judge", lambda model, provider, items, run_id, tag: [v.model_copy(update={"judges": {tag: v.supported}}) for v in verdicts[tag]])
    target, args = started[0]
    target(*args)
    d = docs.get(d["id"])
    assert d["review"]["status"] == "done", d["review"]["error"]
    assert d["fields"]["location"]["review"]["status"] == "verified"
    assert d["fields"]["depth_rock_m"]["review"]["status"] == "flagged"            # judges disagree -> not verified
    assert d["fields"]["found_ground"]["value"] == "Fels (Kalkstein)" and d["fields"]["found_ground"]["review"] is None
    assert d["review"]["status"] == "done" and [x["field_name"] for x in d["review"]["findings"]] == ["depth_rock_m"]


def test_metrics_rows_carry_tokens(monkeypatch, isolated):
    llm_mode(monkeypatch)
    monkeypatch.setattr(llm_extract, "complete_json", FakeLLM(fields={}))
    assistant.handle("Pfahl 7, ab 4 Meter Fels")
    rows = [json.loads(x) for x in (isolated / "metrics.jsonl").read_text().splitlines()]
    ext = next(r for r in rows if r["stage"] == "llm_extraction")
    assert ext["tokens_in"] == 100 and ext["model"] == "fake-model"
    assert any(r["stage"] == "chat_turn_end_to_end" for r in rows)


# ---------------------------------------------------------------- one dataset (BW 12) + metrics cost
def test_demo_dataset_is_bw12(isolated):
    from core import plan
    plan.load_demo()
    st = plan.status("2026-11-17", with_weather=False)
    w1 = next(a for a in st["activities"] if a["id"] == "W1_BP")
    assert w1["total"] == 96 and w1["actual"] == pytest.approx(76.6)        # P01-P06 à 12 m + P07 at 4.6 m
    assert {"W1_BET", "A1_BET"} <= {a["id"] for a in st["activities"] if a["concrete"]}
    assert store.load("client_docs", [])[1]["id"] == "doc:bgg@p14"
    assert "BW 12" in store.SITE["name"] and store.SITE["client"] == "Staatliches Bauamt (fiktiv)"


def test_non_token_cost_lands_in_cost_eur(isolated):
    with llm_bridge.timed("stt", "stt", model="groq:whisper-large-v3") as t:
        t.add_cost(0.0123)
    row = json.loads((isolated / "metrics.jsonl").read_text().splitlines()[-1])
    assert row["stage"] == "stt" and row["cost_eur"] == pytest.approx(0.0123)


def test_bare_audio_ref_resolves_to_its_segments_only(monkeypatch):
    llm_mode(monkeypatch)
    segs = [{"start": 0.0, "end": 2.0, "text": "Pfahl 7."}, {"start": 2.0, "end": 4.4, "text": "Ab 4 Meter Fels."}]
    chunks = sources.audio_chunks("rec1", segs)
    monkeypatch.setattr(llm_extract, "complete_json", FakeLLM(fields={
        "found_ground": {"value": "Fels", "source_refs": ["audio:rec1"], "confidence": 0.9},        # segment part dropped
        "depth_rock_m": {"value": 4, "source_refs": ["audio:other"], "confidence": 0.9}}))         # recording not in request
    res = llm_extract.extract("nachtragsmeldung", chunks, run_id="t")
    assert res.fields["found_ground"].source_refs == ["audio:rec1@0.0-2.0", "audio:rec1@2.0-4.4"]
    assert res.fields["depth_rock_m"].value is None and res.dropped["depth_rock_m"] == "no_valid_source"


# ---------------------------------------------------------------- chat vs diary note
def test_question_gets_help_not_diary_rules_mode():
    r = assistant.handle("So we are testing if you are working properly or not. What is 2 plus 1?")
    txt = r["replies"][0]["text"]
    assert "Bautagebuch" not in txt and "site assistant" in txt and r["replies"][0]["kind"] == "chat"
    assert store.load("notes", []) == []


def test_question_gets_llm_answer_and_notes_still_work(monkeypatch):
    llm_mode(monkeypatch)
    monkeypatch.setattr(llm_extract, "complete_json", FakeLLM(intent="smalltalk"))
    r = assistant.handle("Was ist 2 plus 1?")
    assert r["replies"][0]["text"].startswith("2 plus 1 ist 3") and store.load("notes", []) == []
    monkeypatch.setattr(llm_extract, "complete_json", FakeLLM(intent="diary_note"))
    r = assistant.handle("Schalungstafeln für Achse 1 um 14:30 angekommen")
    assert "Bautagebuch" in r["replies"][0]["text"] and len(store.load("notes", [])) == 1


def test_question_during_open_followup_keeps_question_open():
    assistant.handle("Bagger steht seit 10 Uhr wegen Hydraulikschaden")
    pending = store.load("chat_state", {})["pending"]
    r = assistant.handle("hello, are you there?")
    assert "Noch offen" in r["replies"][0]["text"] and store.load("chat_state", {})["pending"] == pending


# ---------------------------------------------------------------- photo attach rule
def _photo(pid, cat, minutes_ago):
    now = sources.dt.datetime.now()
    return {"id": pid, "file": f"uploads/{pid}.jpg", "original_name": f"{pid}.jpg", "category": cat, "detections": [],
            "taken_at": now.isoformat(timespec="seconds"), "location_source": "site_default", "lat": 48.3, "lon": 11.9,
            "uploaded_at": (now - sources.dt.timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")}


def test_recent_uncategorized_photo_is_attached_and_marked():
    store.save("photos", [_photo("rock", "uncategorized", 5), _photo("old", "uncategorized", 300),
                          _photo("ev", "Nachtrag evidence", 300), _photo("truck", "delivery", 5)])
    d = docs.get(assistant.handle("Pfahl 7, ab 4 Meter Fels")["active"])
    assert set(d["photos"]) == {"rock", "ev"}                       # old upload and wrong category stay out
    assert "rock.jpg (Kategorie nicht geprüft" in d["fields"]["photos"]["value"]
    d2 = docs.get(assistant.handle("Bagger steht seit 10 Uhr wegen Hydraulikschaden")["active"])
    assert "rock" not in d2["photos"]                               # already attached to the open Nachtrag draft
