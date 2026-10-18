"""Generic, deterministic detectors.

Each detector takes the repo root plus parameters from rules.yaml and yields Hits.
Rules choose a detector by name, so most new rules need YAML only, not new code.
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Hit:
    file: str
    line: int | None
    evidence: str


SKIP_DIRS = {".git", "target", "build", "node_modules", ".idea", ".venv", ".gradle"}
MAX_EVIDENCE = 200


def _files(repo: Path, pattern: str) -> Iterator[Path]:
    """Yield files under repo matching the glob pattern, skipping build output folders."""
    for path in sorted(repo.rglob(pattern)):
        if path.is_file() and not SKIP_DIRS.intersection(path.relative_to(repo).parts):
            yield path


def _rel(repo: Path, path: Path) -> str:
    return path.relative_to(repo).as_posix()


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="ignore").splitlines()


def property_match(repo: Path, key: str, value: str) -> Iterator[Hit]:
    """Flag lines in application*.properties where the whole key matches `key`
    and the value contains a match for `value`. Both are regexes."""
    key_re, value_re = re.compile(key), re.compile(value)
    for f in _files(repo, "application*.properties"):
        for number, raw in enumerate(_lines(f), start=1):
            line = raw.strip()
            if not line or line.startswith(("#", "!")) or "=" not in line:
                continue
            k, v = (part.strip() for part in line.split("=", 1))
            if key_re.fullmatch(k) and value_re.search(v):
                yield Hit(_rel(repo, f), number, line[:MAX_EVIDENCE])


POM_NS = {"m": "http://maven.apache.org/POM/4.0.0"}
NON_RUNTIME_SCOPES = {"test", "provided"}


def dependency_present(repo: Path, artifact_id: str) -> Iterator[Hit]:
    """Flag a Maven dependency with this artifactId that ships at runtime.

    Optional dependencies and test/provided scopes are skipped: Spring Boot leaves
    optional ones (such as devtools) out of the production jar, so flagging them
    would be a false positive.
    """
    for pom in _files(repo, "pom.xml"):
        root = ET.parse(pom).getroot()
        for dep in root.iterfind(".//m:dependencies/m:dependency", POM_NS):
            if dep.findtext("m:artifactId", default="", namespaces=POM_NS) != artifact_id:
                continue
            optional = dep.findtext("m:optional", default="false", namespaces=POM_NS)
            scope = dep.findtext("m:scope", default="compile", namespaces=POM_NS)
            if optional.strip() == "true" or scope.strip() in NON_RUNTIME_SCOPES:
                continue
            group_id = dep.findtext("m:groupId", default="", namespaces=POM_NS)
            yield Hit(_rel(repo, pom), None, f"{group_id}:{artifact_id}")


def file_regex(repo: Path, glob: str, pattern: str) -> Iterator[Hit]:
    """Flag every line, in files matching glob, where the regex pattern is found."""
    regex = re.compile(pattern)
    for f in _files(repo, glob):
        for number, line in enumerate(_lines(f), start=1):
            if regex.search(line):
                yield Hit(_rel(repo, f), number, line.strip()[:MAX_EVIDENCE])


DETECTORS: dict[str, Callable[..., Iterator[Hit]]] = {
    "property_match": property_match,
    "dependency_present": dependency_present,
    "file_regex": file_regex,
}
