"""Site layout generation from site documents + photo GPS, driven by the generated fixtures in /site_documents.

Ground truth: site_documents/ground_truth/expected_layout.json (regenerate the folder with `python site_documents/generate.py`).
Runs on a temp data dir: no server, no LLM, no detector (seed detections are replayed).
"""
import json
import math
from pathlib import Path

import pytest

from core import agent, geo, layout_suggest, llm_bridge, photos, site_twin, store

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "site_documents" / "upload"
EXP = json.loads((ROOT / "site_documents" / "ground_truth" / "expected_layout.json").read_text(encoding="utf-8"))
SEED_PHOTOS = {p["id"]: p for p in json.loads((ROOT / "backend/data/seed/photos.json").read_text())}
DOC_FILES = ["project_reference.json", "vermessung_punkte.csv", "bauzeitenplan.xlsx", "baugrundgutachten.pdf",
             "baugrundgutachten.docx", "lageplan.geojson"]


@pytest.fixture
def tmpdata(tmp_path, monkeypatch):
    (tmp_path / "uploads").mkdir()
    for m in (store, site_twin):
        monkeypatch.setattr(m, "DATA", tmp_path, raising=False)
    for m in (store, photos):
        monkeypatch.setattr(m, "UPLOADS", tmp_path / "uploads", raising=False)
    monkeypatch.setattr(llm_bridge, "classify_photo", lambda *a, **k: None)
    monkeypatch.delenv("MAGNETIC_DECLINATION_DEG", raising=False)
    return tmp_path


def _ingest_photos(monkeypatch, ids=None):
    """Upload the geotagged copies through the real ingest (EXIF path); the detector replays the seed detections."""
    files = sorted((DOCS / "photos").glob("site_*.jpg"))
    current = {}
    monkeypatch.setattr(photos, "detect", lambda raw: [{k: d[k] for k in ("class", "confidence", "x", "y", "width", "height")}
                                                       for d in SEED_PHOTOS[current["id"]]["detections"]])
    out = {}
    for f in files:
        pid = f.stem.removeprefix("site_")
        if ids and pid not in ids:
            continue
        current["id"] = pid
        rec = photos.ingest([(f.name, "image/jpeg", f.read_bytes())])[0]
        out[pid] = rec["id"]
    return out                                   # seed id -> new photo id


def _add_docs(names=DOC_FILES):
    return layout_suggest.add_sources([(n, (DOCS / n).read_bytes()) for n in names])


def _centroid(poly):
    return [sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)]


# ---------------------------------------------------------------- parsing
def test_utm_round_trip_and_known_value():
    for lat, lon in [(48.2935, 11.8890), (47.4, 10.1), (54.9, 8.3), (50.1, 14.2)]:
        e, n, z = geo.wgs84_to_utm(lat, lon)
        lat2, lon2 = geo.utm_to_wgs84(e, n, z)
        assert math.hypot((lat2 - lat) * 110540, (lon2 - lon) * 111320 * math.cos(math.radians(lat))) < 0.01
    # analytic references: central meridian of zone 32 is 9° E (easting 500 000); WGS84 meridian arc to 45° is
    # 4 984 944.378 m, times k0 = 0.9996 -> northing 4 982 950.40; the projection is symmetric about the meridian
    e, n, z = geo.wgs84_to_utm(45.0, 9.0)
    assert z == 32 and abs(e - 500000) < 1e-6 and abs(n - 4982950.40) < 0.01
    assert abs((geo.wgs84_to_utm(48, 10.5)[0] - 500000) - (500000 - geo.wgs84_to_utm(48, 7.5)[0])) < 1e-6


@pytest.mark.parametrize("s,v", [("48,2935", 48.2935), ("48.2935° N", 48.2935), ("11,889 E", 11.889), ("48°17'36.6\"N", 48.2935),
                                 ("11°53'20.4\" W", -11.889), ("abc", None)])
def test_parse_coord(s, v):
    got = geo.parse_coord(s)
    assert (got is None and v is None) or abs(got - v) < 1e-4


@pytest.mark.parametrize("name,n,kinds", [
    ("vermessung_punkte.csv", 26, {"anchor", "boundary", "zone"}),
    ("bauzeitenplan.xlsx", 8, {"point"}),
    ("baugrundgutachten.pdf", 4, {"marker"}),
    ("baugrundgutachten.docx", 4, {"marker"}),
    ("lageplan.geojson", 21, {"zone", "marker"}),
    ("project_reference.json", 1, {"anchor"}),
])
def test_each_document_yields_points_with_locators(name, n, kinds):
    r = geo.extract_points(name, (DOCS / name).read_bytes())
    assert len(r["points"]) == n
    assert {p["kind"] for p in r["points"]} == kinds
    assert all(p["locator"] and p["source"] == name for p in r["points"])


def test_unsupported_and_empty_files_are_reported(tmpdata):
    res = layout_suggest.add_sources([("notes.txt", b"hello"), ("empty.csv", b"a;b\n1;2\n")])
    reasons = {s["file"]: s["reason"] for s in res["skipped"]}
    assert "unsupported" in reasons["notes.txt"] and reasons["empty.csv"] == "no coordinates found"


# ---------------------------------------------------------------- integration: all documents + seed photos
def test_full_layout_from_documents_and_photos(tmpdata, monkeypatch):
    ids = _ingest_photos(monkeypatch)
    added = _add_docs()
    assert len(added["added"]) == len(DOC_FILES) and not added["skipped"]
    assert _add_docs()["duplicates"] == DOC_FILES                      # accumulated store de-duplicates

    res = layout_suggest.suggest()
    lay, rep = res["layout"], res["report"]

    # origin = the anchor of the synthetic set, not backend/data
    assert abs(lay["origin"]["lat"] - EXP["origin"]["lat"]) < 1e-5 and abs(lay["origin"]["lon"] - EXP["origin"]["lon"]) < 1e-5
    assert "anchor" in rep["origin_source"]

    zones = {z["id"]: z for z in lay["zones"]}
    assert set(zones) == set(EXP["zones"])
    for zid, ez in EXP["zones"].items():
        c = _centroid(zones[zid]["polygon"])
        assert math.dist(c, ez["centroid"]) < 3, zid
        assert zones[zid]["name"] == ez["name"]
        assert zones[zid]["activities"] == ez["activities"]
        assert zones[zid]["estimated"] and zones[zid]["source"]
    assert zones["be"]["kind"] == "facilities"
    assert rep["unmatched_activities"] == EXP["unmatched_activities"]

    # boundary from the survey's boundary points, markers from the reports / plan (BK1 found in PDF and DOCX -> one marker)
    assert "boundary points" in rep["boundary_source"]
    assert max(math.dist(p, q) for p in lay["boundary"] for q in EXP["boundary"] if math.dist(p, q) < 3) < 0.1
    names = sorted(s["name"] for s in lay["structures"])
    assert names == sorted(EXP["markers"])
    for s in lay["structures"]:
        assert math.dist([s["x"], s["y"]], EXP["markers"][s["name"]]) < 0.2

    # the Tokyo photo is an outlier, every other photo is inside the boundary
    out = [o for o in rep["outliers"] if o["kind"] == "photo"]
    assert [o["photo"] for o in out] == [ids["4d007fe8"]]
    assert rep["photos_on_site"] == 6
    assert not [w for w in rep["warnings"] if "outside the boundary" in w]

    # save -> twin places every photo in its expected zone, distances are real
    site_twin.save_layout(lay)
    tw = site_twin.twin()
    by_seed = {seed: next(p for p in tw["photos"] if p["id"] == new) for seed, new in ids.items()}
    for seed, ep in EXP["photos"].items():
        p = by_seed[seed]
        if ep["outlier"]:
            assert p["position_method"] == "outside_site" and p["plan_xy"] is None
        else:
            assert p["position_method"] == "gps" and p["zone"] == ep["zone"], seed
            assert math.dist(p["plan_xy"], ep["xy"]) < 0.1
    for d in EXP["distances"]:
        a, b = by_seed[d["a"]], by_seed[d["b"]]
        nb = next(n for n in a["neighbours"] if n["id"] == b["id"])
        assert abs(nb["distance_m"] - d["m"]) < 0.5 and nb["within_accuracy"] is d["within_accuracy"]

    # zones make the zone-based safety rule work: the excavator photo inside the site facilities is flagged
    hits = [(i["rule"], i["zone"]) for i in agent.detect_incidents(tw)]
    assert ("machine_in_restricted_zone", "be") in hits

    # EXIF extras: accuracy stored, magnetic heading corrected to true north (270° M + 3.5° declination)
    assert by_seed["07179547"]["gps_accuracy_m"] == 3.0
    assert by_seed["1c92357b"]["heading"] == 273.5


def test_layout_from_photos_only(tmpdata, monkeypatch):
    _ingest_photos(monkeypatch)
    res = layout_suggest.suggest()
    lay, rep = res["layout"], res["report"]
    assert "median GPS of 7 photos" in rep["origin_source"]
    # 6 on-site photos -> W1 pair groups together, the others stand alone
    assert len(lay["zones"]) == 5 and all(z["id"].startswith("area") for z in lay["zones"])
    assert len([o for o in rep["outliers"] if o["kind"] == "photo"]) == 1
    site_twin.save_layout(lay)
    placed = [p for p in site_twin.twin()["photos"] if p["plan_xy"]]
    assert len(placed) == 6 and all(p["zone"] for p in placed)


def test_schedule_only_gives_placeholder_boxes(tmpdata):
    _add_docs(["bauzeitenplan.xlsx"])
    res = layout_suggest.suggest()
    zones = {z["id"]: z for z in res["layout"]["zones"]}
    assert set(zones) == {"w1", "a1", "a2", "w2"}
    assert all("placeholder" in z["source"] for z in zones.values())
    assert sum("only a centre point" in w for w in res["report"]["warnings"]) == 4
    assert math.dist(_centroid(zones["a2"]["polygon"]), EXP["zones"]["a2"]["centroid"]) < 1


def test_no_data_returns_empty_layout_with_reason(tmpdata):
    res = layout_suggest.suggest()
    assert res["layout"]["zones"] == [] and res["layout"]["origin"] is None
    assert res["report"]["origin_source"] is None and "No anchor" in res["report"]["warnings"][0]


def test_conflicting_anchor_is_reported(tmpdata):
    _add_docs(["project_reference.json", "vermessung_punkte.csv"])
    other = {"anchor": {"lat": EXP["origin"]["lat"] + 0.005, "lon": EXP["origin"]["lon"]}}      # ~550 m north
    layout_suggest.add_sources([("alter_bezugspunkt.json", json.dumps(other).encode())])
    rep = layout_suggest.suggest()["report"]
    assert any("from the chosen origin" in w and "alter_bezugspunkt.json" in w for w in rep["warnings"])


def test_rotation_is_applied_to_detection_bearing():
    lay = {"origin": EXP["origin"], "rotation_deg": 30, "zones": []}
    p = {"heading": 90.0, "img_w": 1000, "img_h": 800, "detections": [{"class": "person", "confidence": 0.9, "x": 500, "y": 400, "width": 50, "height": 200}]}
    d = site_twin.place_detections(p, [0.0, 0.0], lay)[0]
    assert d["bearing_deg"] == 60.0


# ---------------------------------------------------------------- agent zone words
def test_agent_zone_words_seed_and_generated_layouts():
    seed = site_twin.normalise(json.loads((ROOT / "backend/data/seed/site_layout.json").read_text()))
    assert agent._zone_from_text("Fly to the north abutment", seed) == "wln"
    assert agent._zone_from_text("Zeig mir die Bohrpfähle", seed) == "a10"
    assert agent._zone_from_text("Show me the excavation", seed) == "erd"
    gen = {"zones": [{"id": z, "name": v["name"], "polygon": v["polygon"]} for z, v in EXP["zones"].items()]}
    assert agent._zone_from_text("Show me Achse 2", gen) == "a2"
    assert agent._zone_from_text("Show me the piles", gen) == "w1"
    assert agent._zone_from_text("Fly to W2 in 3D", gen) == "w2"
    assert agent._zone_from_text("Show the site facilities", gen) == "be"
    assert agent._zone_from_text("Fly to the north abutment", gen) is None     # no north section here: ask, don't substitute W1


# ---------------------------------------------------------------- AI manager: chat uploads + "generate the site layout"
def test_unlabelled_points_are_reported_not_drawn(tmpdata):
    _add_docs(["project_reference.json", "vermessung_punkte.csv"])
    rows = "breite;laenge\n48,29351;11,88905\n48,29352;11,88906\n"
    layout_suggest.add_sources([("ohne_namen.csv", rows.encode())])
    rep = layout_suggest.suggest()
    assert [s["name"] for s in rep["layout"]["structures"]] == []
    assert len(rep["report"]["unlabelled_points"]) == 2 and any("without a name" in w for w in rep["report"]["warnings"])


def test_chat_upload_feeds_layout_sources(tmpdata, monkeypatch):
    from fastapi.testclient import TestClient
    from app import app
    from core import llm
    monkeypatch.setattr(llm, "provider", lambda *a, **k: None)          # inbox summaries stay rule-based: no network in tests
    c = TestClient(app)
    names = ["vermessung_punkte.csv", "bauzeitenplan.xlsx", "baugrundgutachten.pdf", "baugrundgutachten.docx",
             "lageplan.geojson", "project_reference.json"]
    r = c.post("/api/inbox/import", files=[("files", (n, (DOCS / n).read_bytes())) for n in names])
    assert r.status_code == 200, r.text
    body = r.json()
    site = body["site"]
    assert sorted(site["new_files"]) == sorted(names) and site["points_total"] == 26 + 8 + 4 + 4 + 21 + 1 and site["layout_empty"]
    assert not [x for x in body["skipped"] if x["file"].endswith((".geojson", ".json"))]      # no "unsupported" for plans
    assert {d["file"] for d in body["documents"]} == {n for n in names if not n.endswith(("json", "geojson"))}   # inbox still runs
    again = c.post("/api/inbox/import", files=[("files", (n, (DOCS / n).read_bytes())) for n in names]).json()["site"]
    assert again["new_files"] == [] and sorted(again["known_files"]) == sorted(names)
    # an office document without coordinates is not stored as a site source
    c.post("/api/inbox/import", files=[("files", ("notiz.csv", b"Datum;Text\n2026-11-18;Beton geliefert\n"))])
    assert "notiz.csv" not in [s["file"] for s in layout_suggest.sources()]


def test_agent_generates_layout_draft(tmpdata, monkeypatch):
    _ingest_photos(monkeypatch)
    _add_docs()
    r = agent.run("Generate the site layout from the uploaded documents", {}, "en")
    assert r["intents"] == ["layout"] and r["actions"] == [{"type": "layout.offer"}]
    card = r["cards"][0]
    assert card["kind"] == "layout" and {z["id"] for z in card["layout"]["zones"]} == set(EXP["zones"])
    assert "Widerlager 1" in r["speech"] and "not saved" in r["speech"]
    assert site_twin.get_layout()["zones"] == []                          # nothing saved by the agent


def test_agent_layout_without_data_says_what_to_upload(tmpdata):
    r = agent.run("Erstelle den Lageplan aus den Dokumenten", {}, "de")
    assert r["intents"] == ["layout"] and r["actions"] == [] and "Koordinaten" in r["speech"]
