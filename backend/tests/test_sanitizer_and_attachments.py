"""PII masking toggle, proposal-only apply_text, photo attachment in exports. Run from backend/: python -m pytest tests -q"""
from core import assistant, docs, llm_adapter, llm_extract, sanitizer, store

TEXT = "Mail an max@bau.de, IBAN DE89 3704 0044 0532 0130 00, Tel +49 170 1234567"


def test_mask_on_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_PII_MASKING", raising=False)
    out, m = sanitizer.mask(TEXT)
    assert "max@bau.de" not in out and m and sanitizer.unmask(out, m) == TEXT


def test_mask_toggle_off(monkeypatch):
    monkeypatch.setenv("ENABLE_PII_MASKING", "false")
    out, m = sanitizer.mask(TEXT)
    assert out == TEXT and m == {}
    monkeypatch.setenv("ENABLE_PII_MASKING", "true")
    assert sanitizer.mask(TEXT)[0] != TEXT


def test_llm_prompt_is_masked_when_enabled(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(llm_extract, "complete_json", lambda p, *a, **k: (seen.append(p), (_ for _ in ()).throw(RuntimeError))[1])
    monkeypatch.setattr(llm_extract.CFG.__class__, "llm_ready", property(lambda s: True))
    for flag, leaked in (("true", False), ("false", True)):
        monkeypatch.setenv("ENABLE_PII_MASKING", flag)
        seen.clear()
        try:
            llm_extract.converse("kontakt max@bau.de", "Projekt: X\n")
        except RuntimeError:
            pass
        assert ("max@bau.de" in seen[0]) is leaked


def test_attached_photo_is_embedded_in_exports(monkeypatch, tmp_path):
    from PIL import Image
    from core import export, sources
    monkeypatch.setattr(store, "DATA", tmp_path); monkeypatch.setattr(export, "DATA", tmp_path)
    (tmp_path / "uploads").mkdir()
    Image.new("RGB", (40, 30), "gray").save(tmp_path / "uploads/p1.jpg")
    now = sources.dt.datetime.now().isoformat(timespec="seconds")
    store.save("photos", [{"id": "p1", "file": "uploads/p1.jpg", "original_name": "p1.jpg", "category": "uncategorized",
                           "detections": [], "taken_at": now, "uploaded_at": now, "location_source": "site_default", "lat": 48.3, "lon": 11.9}])
    doc = docs.create("aktennotiz")
    doc["photos"].append("p1")
    docs.put(doc)
    assert "p1.jpg" in export.print_html(doc)
    from docx import Document
    d = Document(str(export.docx(doc)))
    assert len(d.inline_shapes) == 1


def test_ai_never_overwrites_locked_field():
    doc = docs.create("aktennotiz")
    k = next(iter(doc["fields"]))
    docs.set_field(doc, k, "Nutzertext", {"type": "user"}, by="user")
    assert docs.set_field(doc, k, "KI-Text", None, by="ai") == "proposal"
    assert doc["fields"][k]["value"] == "Nutzertext" and doc["fields"][k]["proposal"]["value"] == "KI-Text"
