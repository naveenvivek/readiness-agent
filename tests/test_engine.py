"""Engine behaviour, rules catalog integrity and the CLI."""

import json

import pytest
from conftest import PROPS, dependency, make_app, pom

from readiness_agent.cli import main
from readiness_agent.detectors import DETECTORS
from readiness_agent.engine import scan
from readiness_agent.models import Rule, Severity


def test_rule_ids_are_unique(rules):
    ids = [r.id for r in rules]
    assert len(ids) == len(set(ids))


def test_every_rule_uses_a_known_detector(rules):
    assert {r.detector for r in rules} <= DETECTORS.keys()


def test_unknown_detector_raises(tmp_path):
    bad = Rule(id="X-001", title="t", severity="info", detector="nope", params={}, fix="f")
    with pytest.raises(ValueError, match="unknown detector"):
        scan(tmp_path, [bad])


def test_missing_repo_folder_raises(tmp_path, rules):
    with pytest.raises(FileNotFoundError):
        scan(tmp_path / "does-not-exist", rules)


def test_findings_are_sorted_blockers_first(tmp_path, rules):
    app = make_app(
        tmp_path,
        {
            PROPS: "management.endpoints.web.exposure.include=*\n",
            "pom.xml": pom(dependency("com.h2database", "h2")),
        },
    )
    severities = [f.severity for f in scan(app, rules)]
    assert severities == [Severity.BLOCKER, Severity.WARNING]


def test_cli_json_output(tmp_path, capsys):
    app = make_app(tmp_path, {PROPS: "server.port=9090\n"})
    assert main([str(app), "--json"]) == 0
    [finding] = json.loads(capsys.readouterr().out)
    assert finding["rule_id"] == "PORT-001"
    assert finding["severity"] == "blocker"


def test_cli_fail_on_blocker_sets_exit_code(tmp_path, capsys):
    app = make_app(tmp_path, {PROPS: "server.port=9090\n"})
    assert main([str(app), "--fail-on-blocker"]) == 1
    assert "1 finding(s): 1 blocker" in capsys.readouterr().out
