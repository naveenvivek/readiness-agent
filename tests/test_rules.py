"""Each rule must fire on the problem it targets and stay quiet on the safe variant."""

import pytest
from conftest import JAVA, PROPS, dependency, make_app, pom

from readiness_agent.engine import scan


def rule_ids(findings) -> list[str]:
    return sorted({f.rule_id for f in findings})


def test_clean_app_has_no_findings(tmp_path, rules):
    app = make_app(
        tmp_path,
        {
            PROPS: "server.port=${PORT:8080}\nspring.datasource.password=${DB_PASS}\n"
            "management.endpoints.web.exposure.include=health\n",
            "pom.xml": pom(dependency("org.postgresql", "postgresql")),
            JAVA: 'class App { void run() { System.out.println("hi"); } }\n',
        },
    )
    assert scan(app, rules) == []


# ------------------------------------------------------------------ dependencies


def test_h2_runtime_dependency_is_a_blocker(tmp_path, rules):
    app = make_app(tmp_path, {"pom.xml": pom(dependency("com.h2database", "h2"))})
    [finding] = scan(app, rules)
    assert finding.rule_id == "STATE-001"
    assert finding.evidence == "com.h2database:h2"


@pytest.mark.parametrize(
    "extra",
    ["<scope>test</scope>", "<optional>true</optional>", "<scope>provided</scope>"],
)
def test_dependencies_not_shipped_at_runtime_are_ignored(tmp_path, rules, extra):
    app = make_app(tmp_path, {"pom.xml": pom(dependency("com.h2database", "h2", extra))})
    assert scan(app, rules) == []


def test_eureka_client_is_flagged(tmp_path, rules):
    eureka = dependency("org.springframework.cloud", "spring-cloud-starter-netflix-eureka-client")
    app = make_app(tmp_path, {"pom.xml": pom(eureka)})
    assert rule_ids(scan(app, rules)) == ["DISC-001"]


# ------------------------------------------------------------------ properties


def test_hardcoded_port_is_flagged_with_line_number(tmp_path, rules):
    app = make_app(tmp_path, {PROPS: "# comment\nserver.port=9090\n"})
    [finding] = scan(app, rules)
    assert finding.rule_id == "PORT-001"
    assert finding.line == 2


@pytest.mark.parametrize(
    "line, expected",
    [
        ("spring.datasource.password=petclinic", ["SEC-001"]),
        ("app.smtp.PASSWORD = secret123", ["SEC-001"]),
        ("spring.datasource.password=${MYSQL_PASS:petclinic}", ["SEC-002"]),
        ("spring.datasource.password=${DB_PASS}", []),
        ("spring.datasource.password=", []),
    ],
)
def test_password_detection(tmp_path, rules, line, expected):
    app = make_app(tmp_path, {PROPS: line + "\n"})
    assert rule_ids(scan(app, rules)) == expected


@pytest.mark.parametrize(
    "line, expected",
    [
        ("management.endpoints.web.exposure.include=*", ["SEC-003"]),
        ("spring.sql.init.mode=always", ["DB-001"]),
        ("spring.sql.init.mode=embedded", []),
        ("logging.file = /var/log/app.log", ["LOG-001"]),
        ("logging.file.name=app.log", ["LOG-001"]),
        ("spring.sleuth.enabled=true", ["OBS-001"]),
        ("logging.level.root=INFO", []),
    ],
)
def test_property_rules(tmp_path, rules, line, expected):
    app = make_app(tmp_path, {PROPS: line + "\n"})
    assert rule_ids(scan(app, rules)) == expected


def test_value_containing_equals_sign_is_parsed_correctly(tmp_path, rules):
    url = "spring.datasource.url=jdbc:postgresql://db/app?ssl=true&password=x\n"
    app = make_app(tmp_path, {PROPS: url})
    assert scan(app, rules) == []


def test_files_in_build_output_are_ignored(tmp_path, rules):
    app = make_app(tmp_path, {"target/classes/application.properties": "server.port=9090\n"})
    assert scan(app, rules) == []


# ------------------------------------------------------------------ source code and scripts


def test_scheduled_job_is_flagged(tmp_path, rules):
    java = (
        "package demo;\n\nclass Reports {\n"
        '    @Scheduled(cron = "0 0 * * * *")\n    void run() {}\n}\n'
    )
    app = make_app(tmp_path, {"src/main/java/demo/Reports.java": java})
    [finding] = scan(app, rules)
    assert finding.rule_id == "JOB-001"
    assert finding.file == "src/main/java/demo/Reports.java"
    assert finding.line == 4
    assert finding.evidence == '@Scheduled(cron = "0 0 * * * *")'


@pytest.mark.parametrize(
    "code, expected",
    [
        ("Thread t = new Thread(() -> poll());", ["STATE-002"]),
        ("byte[] k = Files.readAllBytes(Paths.get(path));", ["FS-001"]),
        ("cache = CacheBuilder.newBuilder().build();", ["CACHE-001"]),
        ("@EnableCaching", ["CACHE-001"]),
        ("String s = Files.readString(tmp);", []),
    ],
)
def test_java_rules(tmp_path, rules, code, expected):
    app = make_app(tmp_path, {JAVA: f"class App {{\n  {code}\n}}\n"})
    assert rule_ids(scan(app, rules)) == expected


@pytest.mark.parametrize(
    "script, expected",
    [
        ('echo "host all all 0.0.0.0/0 password" >> pg_hba.conf', ["NET-001"]),
        ("apt-get install -y postgresql-15", ["DB-002"]),
        ("apt-install postgresql-${POSTGRES_VERSION}", ["DB-002"]),
        ("apt-get install -y postgresql-client-15 wget", []),
    ],
)
def test_shell_script_rules(tmp_path, rules, script, expected):
    app = make_app(tmp_path, {"init/install.sh": script + "\n"})
    assert rule_ids(scan(app, rules)) == expected


@pytest.mark.parametrize(
    "line, flagged",
    [
        ('POSTGRES_PASSWORD="password"', True),
        ("export DB_PASSWORD=hunter2", True),
        ('POSTGRES_PASSWORD="${FROM_SECRET}"', False),
        ("POSTGRES_PASSWORD=", False),
    ],
)
def test_env_file_passwords(tmp_path, rules, line, flagged):
    app = make_app(tmp_path, {"init/app.env": line + "\n"})
    assert (rule_ids(scan(app, rules)) == ["SEC-004"]) is flagged
