from pathlib import Path

import pytest

from readiness_agent.engine import load_rules
from readiness_agent.models import Rule

PROPS = "src/main/resources/application.properties"
JAVA = "src/main/java/demo/App.java"


def make_app(root: Path, files: dict[str, str]) -> Path:
    """Write a fake repo: {relative path: file content}."""
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def pom(*dependencies: str) -> str:
    """A minimal Maven POM containing the given <dependency> blocks."""
    deps = "\n".join(dependencies)
    return (
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        f"  <dependencies>\n{deps}\n  </dependencies>\n</project>\n"
    )


def dependency(group_id: str, artifact_id: str, extra: str = "") -> str:
    return (
        f"    <dependency><groupId>{group_id}</groupId>"
        f"<artifactId>{artifact_id}</artifactId>{extra}</dependency>"
    )


@pytest.fixture(scope="session")
def rules() -> list[Rule]:
    return load_rules()
