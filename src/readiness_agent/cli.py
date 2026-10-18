"""Command line entry point.

uv run readiness-scan samples/spring-petclinic
uv run readiness-scan samples/bank-of-anthos/src/ledgermonolith --json
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .engine import DEFAULT_RULES, load_rules, scan
from .models import Finding, Severity


def _print_text(findings: list[Finding]) -> None:
    for f in findings:
        where = f"{f.file}:{f.line}" if f.line else f.file
        print(f"[{f.severity.value.upper():7}] {f.rule_id}  {f.title}")
        print(f"          {where}")
        print(f"          {f.evidence}")
        print(f"          fix: {f.fix}\n")
    counts = Counter(f.severity for f in findings)
    summary = ", ".join(f"{counts[s]} {s.value}" for s in Severity if counts[s])
    print(f"{len(findings)} finding(s)" + (f": {summary}" if summary else ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a repo for Cloud Run readiness issues.")
    parser.add_argument("repo", type=Path, help="path to the application's source folder")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES, help="rules YAML file")
    parser.add_argument("--json", action="store_true", help="print findings as JSON")
    parser.add_argument(
        "--fail-on-blocker",
        action="store_true",
        help="exit with code 1 if any blocker is found (useful in CI)",
    )
    args = parser.parse_args(argv)

    findings = scan(args.repo, load_rules(args.rules))
    if args.json:
        print(json.dumps([f.model_dump(mode="json") for f in findings], indent=2))
    else:
        _print_text(findings)

    has_blocker = any(f.severity is Severity.BLOCKER for f in findings)
    return 1 if args.fail_on_blocker and has_blocker else 0


if __name__ == "__main__":
    sys.exit(main())
