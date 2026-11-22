"""Regressions found while building the "day in the life" story mode."""
from core import agent, stt


def test_spoken_change_order_goes_to_drafting_not_changes_query():
    said = ("Attention, change order. Pile 7 at abutment 1, hit rock at 4 meters depth. "
            "The drill rig takes three times as long as usual.")
    assert agent.route(said) == ["chat"]
    assert agent.route("Show me what has changed since yesterday.")[0] == "changes"


def test_whisper_merged_rock_at_is_split_again():
    assert stt._fix("hit rocket 4 meters depth") == "hit rock at 4 meters depth"
    assert stt._fix("the rocket launch") == "the rocket launch"       # only before a number


def test_result_applies_domain_fixes_per_segment():
    r = stt._result([{"start": 0.0, "end": 3.0, "text": "hit rocket 4 m"}], "groq", "whisper", 3.0)
    assert r["text"] == "hit rock at 4 m" and r["segments"][0]["text"] == "hit rock at 4 m"


def test_english_voice_hears_achse_as_aches():
    assert stt._fix("tipped over near Aches 2") == "tipped over near Achse 2"
    assert stt._fix("my back aches badly") == "my back aches badly"


def test_english_place_words_find_german_zones():
    lay = {"zones": [{"id": "a2", "name": "Achse 2"}, {"id": "w1", "name": "Widerlager 1"}]}
    assert agent._zone_from_text("truck tipped over near axis 2", lay) == "a2"
    assert agent._zone_from_text("accident at abutment 1", lay) == "w1"
