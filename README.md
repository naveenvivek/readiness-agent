# readiness-agent

An agent that checks whether a Spring Boot application is ready to run on **Google Cloud Run**,
explains what will break, and (in later phases) plans and generates the changes.

It follows the pattern Google describes for its own large-scale code migrations:
**deterministic checks first, an LLM only where judgment is needed, and code that verifies
the LLM's claims.** This repository currently contains the deterministic layer: a YAML rules
catalog and a small rules engine.

## Why deterministic rules first

| | Rules (this repo) | LLM alone |
|---|---|---|
| Same answer every run | Yes | Can vary between runs and model versions |
| Completeness | Checks every file and line | Can skim or miss things in large repos |
| Evidence | Exact file, line and rule ID | Can cite the wrong place or invent issues |
| Testing | Unit tests per rule | Statistical evals |
| Prompt injection | Repo content is only data | Reads hostile content directly |

The LLM layer (planned) handles what rules cannot: architectural judgment, trade-offs and
context, such as whether an in-process cache actually matters.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14.

```bash
git clone https://github.com/naveenvivek/readiness-agent
cd readiness-agent
uv sync

# sample applications to scan (ignored by git)
git clone --depth 1 https://github.com/spring-projects/spring-petclinic samples/spring-petclinic
git clone --depth 1 https://github.com/GoogleCloudPlatform/bank-of-anthos samples/bank-of-anthos

uv run readiness-scan samples/bank-of-anthos/src/ledgermonolith
uv run readiness-scan samples/spring-petclinic --json
uv run pytest
```

Options: `--json` prints machine-readable findings, `--fail-on-blocker` exits with code 1 when
a blocker is found (for CI), and `--rules path.yaml` uses a different catalog.

## What it finds on real applications

**Bank of Anthos ledger monolith** (Google's VM-hosted Spring Boot sample): 4 blockers,
7 warnings, 2 info.

| Rule | Evidence | Why it matters on Cloud Run |
|---|---|---|
| STATE-002 | `LedgerReader.java:85` starts `new Thread` that polls the database | CPU is only allocated during requests by default, so the poller stalls and balances go stale |
| SEC-004 | `init/ledgermonolith.env` sets `POSTGRES_PASSWORD="password"` | Literal credentials in the repo |
| NET-001 | `init/install-script.sh` opens Postgres to `0.0.0.0/0` | Database reachable from any address |
| FS-001 | `JWTVerifierGenerator.java:51` reads the JWT key from a local path | The file will not exist in a container |
| LOG-001 | `logging.file = /var/log/ledgermonolith.log` | Container disk is temporary; Cloud Logging reads stdout |
| OBS-001 | `spring.sleuth.*` properties | Sleuth was removed in Spring Boot 3, so tracing config is ignored |
| DB-002 | Install script installs PostgreSQL on the app VM | Move the database to Cloud SQL |

**Spring PetClinic**: 5 blockers, 1 warning, 1 info, including `spring.sql.init.mode=always`
(every new instance re-runs the schema scripts) and `${MYSQL_PASS:petclinic}` (a placeholder
that silently falls back to a known password). Its `spring-boot-devtools` dependency is
correctly *not* flagged, because it is optional and excluded from the production jar.

## Rules

Rules live in [`rules/rules.yaml`](rules/rules.yaml). Each one selects a generic detector and
passes it parameters, so most new rules need no Python code:

| Detector | Checks |
|---|---|
| `dependency_present` | A Maven dependency that ships at runtime (optional, test and provided scopes are skipped) |
| `property_match` | A key/value regex pair in `application*.properties` |
| `file_regex` | A regex in files matching a glob (Java sources, shell scripts, env files) |

Current catalog: STATE-001/002, PORT-001, SEC-001/002/003/004, NET-001, DB-001/002, JOB-001,
DISC-001, LOG-001, FS-001, OBS-001, CACHE-001. Every rule has tests for the cases where it
must fire and the cases where it must stay quiet.

## Project layout

```
rules/rules.yaml              rules catalog
src/readiness_agent/
  models.py                   Rule, Finding, Severity (Pydantic)
  detectors.py                generic deterministic detectors
  engine.py                   loads rules, runs detectors, sorts findings
  cli.py                      readiness-scan command
tests/                        pytest suite (fake repos built in tmp_path)
```

## Roadmap

1. **Rules engine** (done): deterministic findings with evidence.
2. **More coverage**: `application.yml` support, Gradle builds, `property_absent` and
   `file_absent` detectors, Spring Boot version-aware rules.
3. **Plan node**: Gemini turns verified findings into a target design (Cloud Run service,
   Cloud Run job or GKE), migration order and effort. Every plan item must cite a finding ID;
   a validator rejects any that do not.
4. **LLM review node**: Gemini proposes findings the rules missed; code checks that each
   quoted piece of evidence exists before it is accepted. Confirmed patterns become new rules.
   This can also ingest the JSON output of Google Cloud's App Modernization CLI (`codmod`).
5. **ADK 2.0 graph** wiring the nodes, with a human approval step before any pull request.
6. **Generate and validate**: Dockerfile, `cloudbuild.yaml` and `service.yaml` from templates,
   checked cheapest first (schema, lint, policy, build).
7. **Deploy**: the agent itself on Cloud Run, Cloud Build CI/CD with an eval gate, Cloud Trace.
8. **Verify**: build and boot the migrated app in a gVisor sandbox (GKE Agent Sandbox) and
   compare its responses with the original, a small-scale version of a dual run.

## Sample applications

The sample applications referenced above are separate projects under their own licenses and
are not included in this repository.
