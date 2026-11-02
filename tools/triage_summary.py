"""Beta triage summary (M11): counts issues by severity, reproducibility and state, and applies
the release-readiness rules of docs/beta/TRIAGE.md. Read-only (``gh issue list``).
Usage:  python tools/triage_summary.py [--repo owner/name] [--json issues.json]
``--json`` reads a saved ``gh issue list --json number,title,state,labels`` output instead.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter

SEVERITIES = ("S1", "S2", "S3", "S4")
REPRO = ("R-always", "R-often", "R-sometimes", "R-once")


def load(repo: str | None, path: str | None) -> list[dict[str, object]]:
    if path:
        with open(path, encoding="utf-8") as stream:
            return list(json.load(stream))
    cmd = ["gh", "issue", "list", "--label", "beta", "--state", "all", "--limit", "1000",
           "--json", "number,title,state,labels"]  # fmt: skip
    if repo:
        cmd += ["--repo", repo]
    return list(json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout))


def labels_of(issue: dict[str, object]) -> set[str]:
    return {str(label["name"]) for label in issue.get("labels", [])}  # type: ignore[union-attr]


def summarise(issues: list[dict[str, object]]) -> dict[str, object]:
    open_issues = [i for i in issues if str(i["state"]).upper() == "OPEN"]
    by_severity = Counter(
        next((s for s in SEVERITIES if s in labels_of(i)), "untriaged") for i in open_issues
    )
    by_repro = Counter(next((r for r in REPRO if r in labels_of(i)), "unknown") for i in open_issues)
    untriaged = [i for i in open_issues if "needs-triage" in labels_of(i)]
    blockers = [
        i for i in open_issues
        if "S1" in labels_of(i) or ("S2" in labels_of(i) and "accepted-by-owner" not in labels_of(i))
    ]  # fmt: skip
    return {
        "total": len(issues),
        "open": len(open_issues),
        "open_by_severity": dict(by_severity),
        "open_by_reproducibility": dict(by_repro),
        "needs_triage": [f"#{i['number']} {i['title']}" for i in untriaged],
        "release_blockers": [f"#{i['number']} {i['title']}" for i in blockers],
        # No reports is no evidence, not a clean result (M11: readiness is decided from evidence).
        "ready": bool(issues) and not blockers and not untriaged,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo")
    parser.add_argument("--json")
    args = parser.parse_args()
    summary = summarise(load(args.repo, args.json))
    for key, value in summary.items():
        print(f"{key}: {value}")
    print("Also required before 1.0: regression tests for fixed S1/S2, and the test scenarios")
    print("passed on a fresh Windows 10 and a fresh Windows 11 PC (docs/beta/TRIAGE.md).")
    return 0 if summary["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
