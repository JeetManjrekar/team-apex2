"""Read-only: compare the intended routes in commands/agent_commands.json (English set) with the real router. Prints mismatches.
Run from repo root: python synthetic_data_en/scripts/check_routes.py"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from core import agent  # noqa: E402

cases = json.loads((ROOT / "synthetic_data_en/commands/agent_commands.json").read_text())["cases"]
bad = 0
for c in cases:
    got = ["reported"] if agent.is_incident_report(c["text"]) else agent.route(c["text"])
    want = ["reported"] if "verbal_report" in c["tags"] else c["intended"]
    ok = set(got) == set(want)
    bad += not ok
    print(f"{'OK  ' if ok else 'DIFF'} {c['id']:4} want={want} got={got}  | {c['text'][:60]!r}")
print(f"\n{bad} mismatch(es) of {len(cases)}")
sys.exit(1 if bad else 0)
