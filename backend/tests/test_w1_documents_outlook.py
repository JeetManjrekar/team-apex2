"""W1 tests: docxtpl export, PDF/soffice handling, Outlook .eml / .ics ingestion. Offline, isolated data dir, no OPENAI_API_KEY."""
import datetime as dt, json, os, shutil, sys, tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ["OPENAI_API_KEY"] = ""                 # deterministic rules mode
_TMP_METRICS = Path(tempfile.mkdtemp(prefix="w1_metrics_")) / "m.jsonl"
os.environ["LLM_METRICS_FILE"] = str(_TMP_METRICS)

import pytest                                      # noqa: E402
from docx import Document                          # noqa: E402
from fastapi.testclient import TestClient          # noqa: E402

from core import assistant, docs, export, llm_bridge, outlook, store   # noqa: E402

SAMPLE_EML = """From: "Klaus Weber" <k.weber@bauherr-musterstadt.de>
To: bauleitung@beispiel-bau.de
Subject: Pfahl 7 – weiteres Vorgehen
Date: Sat, 21 Nov 2026 08:12:00 +0100
Message-ID: <abc123@bauherr-musterstadt.de>
Content-Type: text/plain; charset=utf-8

Sehr geehrter Herr Manjrekar,

bitte führen Sie die Bohrarbeiten an Pfahl 7 mit Meißeleinsatz bis zur planmäßigen Tiefe von 12 m fort.
Bitte senden Sie uns bis Montag, 23.11.2026, eine Aufstellung der zusätzlichen Bohrzeiten.

Mit freundlichen Grüßen
Klaus Weber
Tel. 089 1234567
IBAN DE89 3704 0044 0532 0130 00
"""
TODAY = dt.date(2026, 11, 21)


@pytest.fixture()
def site(tmp_path, monkeypatch):
    """Fresh copy of the seed data (docs, photos, uploads) as the data dir."""
    shutil.copytree(BACKEND / "data" / "seed", tmp_path, dirs_exist_ok=True)
    monkeypatch.setattr(store, "DATA", tmp_path)
    monkeypatch.setattr(export, "DATA", tmp_path)
    return tmp_path


@pytest.fixture()
def client(site):
    from app import app
    return TestClient(app)


def pile7():
    return next(d for d in docs.all_docs() if d["type"] == "nachtragsmeldung")


def metrics_stages():
    return [json.loads(l)["stage"] for l in _TMP_METRICS.read_text().splitlines() if l.strip()]


def all_text(path):
    d = Document(path)
    cells = [c.text for t in d.tables for r in t.rows for c in r.cells]
    return "\n".join([p.text for p in d.paragraphs] + cells), d


# ---------- Word export ----------
def test_templates_exist_for_every_family():
    for name in ("notice.docx", "nachtrag.docx", "tagesbericht.docx"):
        assert (export.templates_dir() / name).is_file()
    assert {export.TEMPLATE_FOR[t] for t in docs.DOC_TYPES} <= {"notice.docx", "nachtrag.docx", "tagesbericht.docx"}


def test_docxtpl_render_with_photo_and_source_appendix(site):
    d = pile7()
    d["photos"] = [p["id"] for p in store.load("photos", [])][:2]
    docs.set_field(d, "material", "Beton\nC30/37 & <Zusatz>", {"type": "user", "quote": "manual edit"}, by="user")
    docs.set_field(d, "staff_hours", "3 Mann", {"type": "message", "evidence_id": None, "locator": "Antwort im Chat", "quote": "3 Mann"}, by="ai")
    ctx = export.build_context(d)
    assert [r["value"] for r in ctx["rows"] if r["label"].startswith("Anordnung")] == ["— (offen)"]
    filled = [k for k, *_ in docs.DOC_TYPES[d["type"]]["fields"] if d["fields"][k]["value"]]
    assert len(ctx["sources"]) == len(filled)                          # every filled field, incl. user source
    assert any(s["kind"] == "user" and s["evidence_id"] is None for s in ctx["sources"])
    assert all(len(s["excerpt"]) <= 300 for s in ctx["sources"])
    assert set(ctx["sources"][0]) >= {"label", "evidence_id", "kind", "locator", "excerpt"}

    path = export.docx(d)
    text, word = all_text(path)
    assert len(word.inline_shapes) == 2                                # annotated photos embedded
    assert "C30/37 & <Zusatz>" in text and "— (offen)" in text
    assert "Quellenanhang" in text and "msg-" in text and "manuell bearbeitet" in text
    assert "Entwurf" in ctx["footer"] or "ENTWURF" in ctx["footer"]
    assert any("original (1).jpg" in p.text for p in word.paragraphs)  # caption
    assert "ENTWURF" in word.sections[0].header._element.xml            # draft watermark


def test_checked_document_has_no_watermark_and_review_footer(site):
    d = pile7()
    for k in docs.missing(d):
        docs.set_field(d, k, "x", {"type": "user", "quote": "x"}, by="user")
    docs.set_status(d, "checked", "Jeet Manjrekar")
    _, word = all_text(export.docx(d))
    assert "ENTWURF" not in word.sections[0].header._element.xml
    assert "geprüft von Jeet Manjrekar" in "\n".join(p.text for p in word.paragraphs)


def test_fallback_when_template_missing(site, tmp_path, monkeypatch):
    monkeypatch.setenv("EXPORT_TEMPLATES_DIR", str(tmp_path / "no_templates"))
    text, word = all_text(export.docx(pile7()))
    assert "Nachtragsmeldung" in text and "— (offen)" in text and "Nachweise je Feld" in text
    assert "ENTWURF" in word.sections[0].header._element.xml


def test_export_docx_is_timed(site):
    export.docx(pile7())
    assert "export_docx" in metrics_stages()


# ---------- PDF ----------
def test_soffice_resolution_order(tmp_path, monkeypatch):
    def fake(name):
        p = tmp_path / name
        p.write_text("#!/bin/sh\n")
        p.chmod(0o755)
        return str(p)
    a, b, c = fake("a"), fake("b"), fake("c")
    monkeypatch.setattr(export, "SOFFICE_PATHS", (c,))
    monkeypatch.setattr(export.shutil, "which", lambda n: b)
    monkeypatch.setenv("SOFFICE_BIN", a)
    assert export.find_soffice() == a                                   # env wins
    monkeypatch.setenv("SOFFICE_BIN", str(tmp_path / "missing"))
    assert export.find_soffice() == b                                   # then PATH
    monkeypatch.setattr(export.shutil, "which", lambda n: None)
    assert export.find_soffice() == c                                   # then fixed paths
    monkeypatch.setattr(export, "SOFFICE_PATHS", ())
    assert export.find_soffice() is None


def test_pdf_route_returns_503_without_soffice(client, monkeypatch):
    monkeypatch.setattr(export, "find_soffice", lambda: None)
    r = client.get(f"/api/docs/{pile7()['id']}/pdf")
    assert r.status_code == 503
    assert "/print" in r.json()["detail"]
    assert client.get(f"/api/docs/{pile7()['id']}/print").status_code == 200   # print view still works
    assert client.get("/api/docs/nope/pdf").status_code == 404


def test_pdf_route_503_when_conversion_fails(client, monkeypatch, tmp_path):
    bad = tmp_path / "soffice"
    bad.write_text("#!/bin/sh\nexit 1\n")
    bad.chmod(0o755)
    monkeypatch.setenv("SOFFICE_BIN", str(bad))
    assert client.get(f"/api/docs/{pile7()['id']}/pdf").status_code == 503


@pytest.mark.skipif(not export.find_soffice(), reason="LibreOffice not installed")
def test_pdf_route_with_real_soffice(client):
    r = client.get(f"/api/docs/{pile7()['id']}/pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert {"export_docx", "export_pdf"} <= set(metrics_stages())


# ---------- .eml ----------
def test_eml_masked_before_llm_and_proposals_never_overwrite_locked(client, monkeypatch):
    d = pile7()
    docs.set_field(d, "instruction_by", "Hr. Weber (Bauherr)", {"type": "user", "quote": "manual edit"}, by="user")   # locked, mail would fill it
    docs.put(d)
    seen = []
    real_extract, real_summarize = assistant.extract, outlook.summarize.summarize
    monkeypatch.setattr(assistant, "extract", lambda dtype, text, evidence, *a, **k: (seen.append((text, json.dumps(evidence, ensure_ascii=False))),
                                                                                  real_extract(dtype, text, evidence, *a, **k))[1])
    monkeypatch.setattr(outlook.summarize, "summarize", lambda text: (seen.append((text, "")), real_summarize(text))[1])
    n_docs = len(docs.all_docs())

    r = client.post("/api/inbox/import", files=[("files", ("pfahl7.eml", SAMPLE_EML.encode(), "message/rfc822"))])
    assert r.status_code == 200, r.text
    res = r.json()
    assert seen, "extraction and summarize were never called"
    for text, ev in seen:                                               # nothing private reaches the LLM layer
        for secret in ("k.weber@bauherr-musterstadt.de", "beispiel-bau.de", "1234567", "DE89 3704"):
            assert secret not in text and secret not in ev
    mail = res["emails"][0]
    assert mail["evidence_id"].startswith("mail-") and mail["masked"]
    assert mail["subject"] == "Pfahl 7 – weiteres Vorgehen" and len(mail["open_items"]) == 2

    assert len(docs.all_docs()) == n_docs                               # merged into the existing draft, none created
    entry = res["drafts"][0]
    assert entry["id"] == d["id"] and entry["merged"] and entry["url"] == f"/api/docs/{d['id']}"
    after = docs.get(d["id"])
    locked = after["fields"]["instruction_by"]
    assert locked["value"] == "Hr. Weber (Bauherr)" and locked["locked"] and locked["by"] == "user"   # lock wins
    assert "instruction_by" not in entry["filled"]
    f = after["fields"]["description"]                                   # filled, unlocked: the mail may only propose
    assert f["value"] == "Bohrpfahl 7: bei 4 m auf Fels gestoßen"
    assert f["proposal"]["source"]["evidence_id"] == mail["evidence_id"]                 # proposal with mail- evidence
    assert "description" in entry["proposals"]
    assert after["status"] == "draft"
    ev_ids = {(v["source"] or {}).get("evidence_id") for v in after["fields"].values()}
    assert mail["evidence_id"] in ev_ids
    assert "E-Mail Klaus Weber" in f["proposal"]["source"]["locator"] and "@" not in f["proposal"]["source"]["locator"]
    assert res["notifications"] and res["notifications"][0]["doc"] == d["id"]
    assert "outlook_import" in metrics_stages()


def test_eml_import_is_idempotent(client):
    files = [("files", ("a.eml", SAMPLE_EML.encode(), "message/rfc822"))]
    first = client.post("/api/inbox/import", files=files).json()
    snapshot = json.dumps(docs.all_docs(), sort_keys=True)
    second = client.post("/api/inbox/import", files=files).json()
    assert second["emails"][0]["duplicate"] is True and not second["notifications"]
    assert json.dumps(docs.all_docs(), sort_keys=True) == snapshot
    assert second["emails"][0]["evidence_id"] == first["emails"][0]["evidence_id"]


def test_checked_draft_drops_back_to_draft_when_mail_adds_content(site):
    d = pile7()
    for k in docs.missing(d):
        docs.set_field(d, k, "x", {"type": "user", "quote": "x"}, by="user")
    docs.set_status(d, "checked", "Jeet Manjrekar")
    docs.put(d)
    outlook.import_files([("a.eml", SAMPLE_EML.encode())])
    assert docs.get(d["id"])["status"] == "draft"                       # never stays "checked" with unreviewed AI content


def test_eml_html_only_body_is_converted_to_text():
    raw = (b"From: a@b.de\nSubject: Test\nMessage-ID: <h1@x>\nContent-Type: text/html; charset=utf-8\n\n"
           b"<html><head><style>p{color:red}</style></head><body><p>Hallo&nbsp;Welt</p><p>Pfahl 7 &amp; Achse 2</p><script>x()</script></body></html>")
    m = outlook.parse_eml(raw)
    assert m["body"] == "Hallo Welt\n\nPfahl 7 & Achse 2" and "color" not in m["body"] and "x()" not in m["body"]


def test_unsupported_and_broken_files_are_skipped_not_fatal(client):
    r = client.post("/api/inbox/import", files=[("files", ("notes.txt", b"hi", "text/plain")), ("files", ("bad.ics", b"garbage", "text/calendar"))])
    assert r.status_code == 200
    assert {s["file"] for s in r.json()["skipped"]} == {"notes.txt", "bad.ics"}


# ---------- .ics ----------
def _ics(*events):
    body = "".join(events)
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//\r\n{body}END:VCALENDAR\r\n".encode()


def _event(uid, day, summary="Termin", hhmm="100000", desc="", extra=""):
    d = f"DESCRIPTION:{desc}\r\n" if desc else ""
    return (f"BEGIN:VEVENT\r\nUID:{uid}\r\nSUMMARY:{summary}\r\nDTSTART:{day:%Y%m%d}T{hhmm}\r\nDTEND:{day:%Y%m%d}T{int(hhmm[:2]) + 1:02d}0000\r\n{d}{extra}END:VEVENT\r\n")


def test_ics_lookahead_window_and_reminders(site, monkeypatch):
    monkeypatch.setenv("OUTLOOK_LOOKAHEAD_DAYS", "7")
    desc = ("Pfahl 7 Fels bei 4 m.\\n- Prüfung der Pfahllänge | Verantwortlich: Fr. Schulz | bis 24.11.2026"
            "\\n- Entscheidung Meißeleinsatz | Verantwortlich: Hr. Weber | bis 23.11.2026 mail k.weber@bauherr.de")
    raw = _ics(_event("today-1", TODAY, "Baubesprechung", desc=desc),
               _event("in7", TODAY + dt.timedelta(days=7), "Abnahme"),
               _event("in8", TODAY + dt.timedelta(days=8), "Zu spät"),
               _event("past", TODAY - dt.timedelta(days=1), "Gestern"),
               _event("cx", TODAY + dt.timedelta(days=1), "Abgesagt", extra="STATUS:CANCELLED\r\n"),
               _event("weekly", TODAY - dt.timedelta(days=7), "Jour fixe", extra="RRULE:FREQ=WEEKLY;COUNT=4\r\n"))
    n_docs = len(docs.all_docs())
    res = outlook.import_files([("termine.ics", raw)], today=TODAY)
    ids = {r["evidence_id"] for r in res["reminders"]}
    assert ids == {"cal-today-1", "cal-in7", "cal-weekly-20261121", "cal-weekly-20261128"}
    assert all(r["kind"] == "calendar" for r in res["reminders"])
    rem = next(r for r in res["reminders"] if r["evidence_id"] == "cal-today-1")
    assert rem["message"] == "Baubesprechung 10:00 – 2 offene Punkte zu Pfahl 7"
    assert len(docs.all_docs()) == n_docs and not res["drafts"]         # calendar alone creates no document
    msgs = [m["text"] for m in store.load("messages", [])]
    assert "Baubesprechung 10:00 – 2 offene Punkte zu Pfahl 7" in msgs
    assert any(t.startswith("Abnahme am 28.11. 10:00") for t in msgs)
    again = outlook.import_files([("termine.ics", raw)], today=TODAY)  # notifications are not repeated
    assert not again["notifications"]


def test_ics_lookahead_env_is_respected(monkeypatch):
    monkeypatch.setenv("OUTLOOK_LOOKAHEAD_DAYS", "2")
    raw = _ics(_event("a", TODAY + dt.timedelta(days=2)), _event("b", TODAY + dt.timedelta(days=3)))
    assert [e["uid"] for e in outlook.parse_ics(raw, TODAY)] == ["a"]


def test_ics_all_day_and_utc_events():
    raw = (b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//\r\n"
           b"BEGIN:VEVENT\r\nUID:allday\r\nSUMMARY:Baustopp\r\nDTSTART;VALUE=DATE:20261121\r\nDTEND;VALUE=DATE:20261122\r\nEND:VEVENT\r\n"
           b"BEGIN:VEVENT\r\nUID:utc\r\nSUMMARY:Call\r\nDTSTART:20261122T090000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
    ev = {e["uid"]: e for e in outlook.parse_ics(raw, TODAY, 7)}
    assert ev["allday"]["all_day"] and set(ev) == {"allday", "utc"}
    assert outlook.reminder(ev["allday"], TODAY)["message"] == "Baustopp"


def test_inbox_route_registered(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/inbox/import" in paths and "/api/docs/{doc_id}/pdf" in paths


# ---------- one-click sync ----------
@pytest.fixture()
def samples(tmp_path, monkeypatch):
    d = tmp_path / "samples"
    d.mkdir()
    (d / "mail.eml").write_text(SAMPLE_EML, encoding="utf-8")
    (d / "cal.ics").write_bytes(_ics(_event("s1", dt.date.today(), "Baubesprechung")))
    (d / "ignore.txt").write_text("x")
    monkeypatch.setattr(outlook, "SAMPLES_DIR", d)
    monkeypatch.delenv("ICS_FEED_URL", raising=False)
    return d


def test_sync_ingests_sample_folder(client, samples):
    r = client.post("/api/inbox/sync", json={})
    assert r.status_code == 200
    j = r.json()
    assert [e["evidence_id"] for e in j["emails"]][0].startswith("mail-")
    assert [x["evidence_id"] for x in j["reminders"]] == ["cal-s1"]
    assert j["sources_synced"] == [{"source": "samples", "ok": True, "files": ["cal.ics", "mail.eml"]}]
    assert "IBAN" not in json.dumps(j) or "DE89" not in json.dumps(j)         # masked before it reaches the response
    assert "outlook_import" in metrics_stages()
    assert client.post("/api/inbox/sync", json={"include_samples": False}).json()["created"] == []


def test_sync_fetches_mocked_ics_url(client, samples, monkeypatch):
    seen = []
    feed = _ics(_event("remote-1", dt.date.today(), "Extern"))
    monkeypatch.setattr(outlook, "fetch_ics", lambda url: seen.append(url) or feed)
    j = client.post("/api/inbox/sync", json={"ics_url": "https://cal.example.com/f.ics", "include_samples": False}).json()
    assert seen == ["https://cal.example.com/f.ics"]
    assert [r["evidence_id"] for r in j["reminders"]] == ["cal-remote-1"]
    assert j["sources_synced"][0]["source"] == "ics_url"


def test_sync_uses_env_feed_and_reports_network_failure(client, samples, monkeypatch):
    monkeypatch.setenv("ICS_FEED_URL", "https://cal.example.com/f.ics")
    def boom(url):
        raise outlook.SyncError(502, "calendar feed could not be fetched (URLError)")
    monkeypatch.setattr(outlook, "fetch_ics", boom)
    j = client.post("/api/inbox/sync", json={}).json()                       # samples still imported, failure reported
    assert j["emails"] and j["sources_synced"][-1] == {"source": "ics_url", "ok": False, "error": "calendar feed could not be fetched (URLError)", "files": []}
    r = client.post("/api/inbox/sync", json={"include_samples": False})      # nothing else to import -> error
    assert r.status_code == 502 and "could not be fetched" in r.json()["detail"]


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://x.example.com/a.ics", "javascript:alert(1)", "webcal://x/a.ics", "not a url"])
def test_sync_rejects_invalid_url_scheme(client, samples, monkeypatch, url):
    monkeypatch.setattr(outlook, "fetch_ics", lambda u: pytest.fail("must not fetch"))
    r = client.post("/api/inbox/sync", json={"ics_url": url})
    assert r.status_code == 400 and "http" in r.json()["detail"]


def test_sync_does_not_poll_without_opt_in(client, samples, monkeypatch):
    monkeypatch.setattr(outlook, "fetch_ics", lambda u: pytest.fail("no URL given, must not fetch"))
    assert client.post("/api/inbox/sync").status_code == 200
