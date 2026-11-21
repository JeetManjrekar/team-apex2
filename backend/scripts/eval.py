"""Field-accuracy eval over data/eval/cases (text-only, single-message cases).
Runs each case through assistant.apply_text on a throw-away data dir and writes data/eval/report.json.
Usage (from backend/):  python scripts/eval.py"""
import json, re, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core import assistant, llm_bridge, store  # noqa: E402

EVAL = ROOT / "data" / "eval"
DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})|(\d{1,2})\.(\d{1,2})\.(\d{4})")


def _iso(s):
    m = DATE.search(str(s))
    return None if not m else (m.group(0) if m.group(1) else f"{m.group(6)}-{int(m.group(5)):02d}-{int(m.group(4)):02d}")


def _ok(exp, field):
    val, src = (field or {}).get("value"), ((field or {}).get("source") or {})
    if val in (None, ""):
        return False
    m = exp["match"]
    if m == "contains_all":
        return all(t.lower() in str(val).lower() for t in exp["terms"])
    if m == "numeric_tol":
        try:
            return abs(float(val) - float(exp["value"])) <= exp.get("tol", 0)
        except (TypeError, ValueError):
            return False
    if m == "date":
        return _iso(val) == _iso(exp["value"])
    if m == "source_ref":
        return exp["value"] in json.dumps(src, ensure_ascii=False) or exp["value"] in str(val)
    return str(val).strip().lower() == str(exp["value"]).strip().lower()


def main():
    cases = [json.loads(p.read_text()) for p in sorted((EVAL / "cases").glob("case_*.json"))]
    cases = [c for c in cases if c["input"].get("text") and not c["input"].get("audio") and not any(
        k in c for k in ("setup", "followup_answer", "expected_no_document"))]
    tmp = Path(tempfile.mkdtemp())
    store.DATA, store.UPLOADS = tmp, tmp / "uploads"
    store.UPLOADS.mkdir()
    llm_bridge.METRICS._path = tmp / "llm_metrics.jsonl"        # eval runs must not pollute real metrics
    assistant.plan.DATA = tmp
    assistant.plan.load_demo()
    per_case, hit, total, dropped = [], 0, 0, 0
    for c in cases:
        doc, *_ , gaps, mode = assistant.apply_text(c["doc_type"], c["input"]["text"])
        res = {k: _ok(e, doc["fields"].get(k)) for k, e in c["expected_fields"].items()}
        empty_ok = all((doc["fields"].get(k) or {}).get("value") in (None, "") for k in c.get("must_be_empty", []))
        hit += sum(res.values()); total += len(res); dropped += len(gaps)
        per_case.append({"id": c["id"], "mode": mode, "fields": res, "must_be_empty_ok": empty_ok})
    report = {"accuracy": round(hit / total, 3) if total else None, "fields_correct": hit, "fields_total": total,
              "gaps_asked": dropped, "cases": per_case}
    (EVAL / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}), f"({len(cases)} cases, mode={per_case[0]['mode'] if per_case else '-'})")


if __name__ == "__main__":
    main()
