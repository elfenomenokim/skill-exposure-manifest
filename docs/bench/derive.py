#!/usr/bin/env python3
"""Measure derive and resolve cost and print the result as JSON.

Run from the repository root: python3 docs/bench/derive.py
Set SKILLS_DIR to a skills tree that holds atlas-flow/references/skill-exposure-policy.json.
Only an explicit --write replaces the committed docs/bench/derive.json, so a contributor
who just wants the numbers never dirties the tree.
"""
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# The skills tree is a caller input, never a guess about the checkout's parents: an
# exported repository has no atlas-flow sibling, so the default is this repo itself.
SKILLS = Path(os.environ.get("SKILLS_DIR") or ROOT)


def module():
    path = ROOT / "src/skill_exposure_manifest/core.py"
    spec = importlib.util.spec_from_file_location("sem", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def bench(call, runs=9):
    """Return (min, median) milliseconds; the host is shared, so both are reported."""
    values = []
    for _ in range(runs):
        start = time.perf_counter()
        call()
        values.append((time.perf_counter() - start) * 1000)
    values.sort()
    return values[0], values[len(values) // 2]


def main():
    policy = SKILLS / "atlas-flow/references/skill-exposure-policy.json"
    if not policy.is_file():
        raise SystemExit(f"no policy at {policy}; set SKILLS_DIR to a tree holding skills/atlas-flow")
    sem = module()
    derive_low, derive_mid = bench(lambda: sem.canonical_policy_manifest(str(SKILLS), str(policy)))
    resolve_low, resolve_mid = bench(lambda: sem.resolve_canonical_skill(
        "atlas-flow", project_root=str(SKILLS), policy_path=str(policy)))
    entries = sem.canonical_policy_manifest(str(SKILLS), str(policy))[0]["entries"]
    data = {
        "schema": "skill-exposure-manifest-bench/1",
        "date": time.strftime("%Y-%m-%d"),
        "host": "macOS arm64 (Apple M5 Pro)",
        "python": ".".join(map(str, __import__("sys").version_info[:3])),
        "method": "9 runs, perf_counter, warm page cache; min and median reported because the host is shared",
        "registrations": len(entries),
        "canonical_policy_manifest_ms_min": round(derive_low, 1),
        "canonical_policy_manifest_ms_median": round(derive_mid, 1),
        "resolve_canonical_skill_ms_min": round(resolve_low, 1),
        "resolve_canonical_skill_ms_median": round(resolve_mid, 1),
        "sources_read_per_resolve": len(entries),
    }
    # Only an explicit --write replaces the committed measurement.
    if "--write" in sys.argv[1:]:
        (ROOT / "docs/bench/derive.json").write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
