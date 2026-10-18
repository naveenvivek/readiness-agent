"""Loads the rules catalog and runs each rule's detector against a repo."""

from pathlib import Path

import yaml

from .detectors import DETECTORS
from .models import SEVERITY_ORDER, Finding, Rule

DEFAULT_RULES = Path(__file__).resolve().parents[2] / "rules" / "rules.yaml"


def load_rules(path: Path = DEFAULT_RULES) -> list[Rule]:
    # safe_load, never yaml.load: plain load can construct arbitrary Python objects.
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Rule(**r) for r in data["rules"]]


def scan(repo: Path, rules: list[Rule]) -> list[Finding]:
    """Run every rule against the repo. Findings are sorted blockers first."""
    if not repo.is_dir():
        raise FileNotFoundError(f"Repo folder not found: {repo}")
    findings: list[Finding] = []
    for rule in rules:
        detect = DETECTORS.get(rule.detector)
        if detect is None:
            raise ValueError(f"Rule {rule.id}: unknown detector '{rule.detector}'")
        for hit in detect(repo, **rule.params):
            findings.append(
                Finding(
                    rule_id=rule.id,
                    title=rule.title,
                    severity=rule.severity,
                    file=hit.file,
                    line=hit.line,
                    evidence=hit.evidence,
                    fix=rule.fix,
                )
            )
    return sorted(findings, key=lambda f: (SEVERITY_ORDER[f.severity], f.rule_id, f.file))
