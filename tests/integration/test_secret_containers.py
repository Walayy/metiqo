"""Frontières des secrets de production et contrôle réel du processus non-root."""

import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_production_compose_keeps_secrets_off_web_and_removes_trust(tmp_path: Path) -> None:
    credential = tmp_path / "fixture-secret"
    credential.write_text("private-fixture-value", encoding="utf-8")
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.production.yml",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        env={
            **os.environ,
            "APP_PUBLIC_ORIGIN": "https://localhost:8443",
            "POSTGRES_PASSWORD_SECRET_FILE": str(credential),
            "DATABASE_URL_SECRET_FILE": str(credential),
        },
    )
    assert "private-fixture-value" not in result.stdout
    services = json.loads(result.stdout)["services"]
    database = services["postgres"]
    assert "POSTGRES_HOST_AUTH_METHOD" not in database["environment"]
    assert database["environment"]["POSTGRES_PASSWORD_FILE"] == "/run/secrets/postgres_password"
    assert database["user"] == "postgres" and database["read_only"] is True
    for name in ("api", "worker"):
        environment = services[name]["environment"]
        assert "DATABASE_URL" not in environment
        assert environment["DATABASE_URL_FILE"] == "/run/secrets/database_url"
        assert environment["AUTH_MODE"] == "owner"
    for name in ("api", "worker", "web", "gateway", "postgres"):
        assert services[name]["cap_drop"] == ["ALL"]
        assert services[name]["security_opt"] == ["no-new-privileges:true"]
    for name in ("web", "gateway"):
        assert not services[name].get("secrets")
    assert not services["api"].get("ports") and not services["web"].get("ports")
    assert len(services["gateway"]["ports"]) == 1


@pytest.mark.integration
def test_python_image_reads_mounted_secret_with_no_extra_privileges(tmp_path: Path) -> None:
    image = os.environ.get("TEST_SECURITY_IMAGE")
    if not image:
        pytest.skip("TEST_SECURITY_IMAGE requis pour le test réel de permissions")
    credential = tmp_path / "database_url"
    credential.write_text(
        "postgresql+psycopg://metiquo:fixture-mounted-password@postgres:5432/metiquo",
        encoding="utf-8",
    )
    raw = tmp_path / "raw"
    raw.mkdir()
    script = """
import json, os
from pathlib import Path
from metiquo.config import load_settings
settings = load_settings()
assert 'fixture-mounted-password' in settings.database_url.get_secret_value()
assert 'fixture-mounted-password' not in repr(settings)
assert 'DATABASE_URL' not in os.environ
assert os.geteuid() == 10001
status = Path('/proc/self/status').read_text()
assert 'CapEff:\\t0000000000000000' in status
assert 'NoNewPrivs:\\t1' in status
for path in ('/app/forbidden', '/data/raw/forbidden', '/run/secrets/database_url'):
    try:
        Path(path).write_text('must not write')
    except OSError:
        pass
    else:
        raise AssertionError('readonly boundary failed')
Path('/tmp/allowed').write_text('temporary')
print(json.dumps({'uid': os.geteuid(), 'secretFileLoaded': True, 'readonlyVerified': True}))
"""
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--read-only",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--tmpfs",
            "/tmp:rw,mode=1777",
            "--mount",
            f"type=bind,source={credential},target=/run/secrets/database_url,readonly",
            "--mount",
            f"type=bind,source={raw},target=/data/raw,readonly",
            "-e",
            "APP_ENV=production",
            "-e",
            "APP_DATA_MODE=mock",
            "-e",
            "AUTH_MODE=owner",
            "-e",
            "APP_PUBLIC_ORIGIN=https://localhost:8443",
            "-e",
            "DATABASE_URL_FILE=/run/secrets/database_url",
            image,
            "python",
            "-c",
            script,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "fixture-mounted-password" not in result.stdout + result.stderr
    assert json.loads(result.stdout)["readonlyVerified"] is True


@pytest.mark.integration
def test_web_image_is_nonroot_with_no_server_credentials() -> None:
    image = os.environ.get("TEST_SECURITY_WEB_IMAGE")
    if not image:
        pytest.skip("TEST_SECURITY_WEB_IMAGE requis")
    script = """
const fs = require('node:fs');
if (process.getuid() === 0) throw new Error('root process');
for (const name of ['DATABASE_URL', 'DATABASE_URL_FILE', 'OE_GOOGLE_DRIVE_BEARER']) {
  if (process.env[name]) throw new Error('server credential available');
}
for (const path of ['/app/forbidden', '/run/secrets/database_url']) {
  let refused = false;
  try { fs.writeFileSync(path, 'must not write'); } catch { refused = true; }
  if (!refused) throw new Error('readonly boundary failed');
}
fs.writeFileSync('/tmp/allowed', 'temporary');
console.log(JSON.stringify({uid: process.getuid(), readonlyVerified: true}));
"""
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--read-only",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--tmpfs",
            "/tmp:rw,mode=1777",
            image,
            "node",
            "-e",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["uid"] == 1000


@pytest.mark.integration
def test_production_postgres_starts_nonroot_and_requires_password(tmp_path: Path) -> None:
    if not os.environ.get("TEST_SECURITY_IMAGE"):
        pytest.skip("TEST_SECURITY_IMAGE requis pour la stack éphémère")
    credential = tmp_path / "postgres_password"
    password = "fixture-postgres-" + uuid4().hex
    credential.write_text(password, encoding="utf-8")
    project = "metiquo-sec004-" + uuid4().hex[:12]
    environment = {
        **os.environ,
        "APP_PUBLIC_ORIGIN": "https://localhost:8443",
        "POSTGRES_PASSWORD_SECRET_FILE": str(credential),
        "DATABASE_URL_SECRET_FILE": str(credential),
    }
    compose = [
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.production.yml",
    ]
    try:
        started = subprocess.run(
            [*compose, "up", "-d", "--wait", "--wait-timeout", "60", "postgres"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=90,
        )
        assert started.returncode == 0, started.stderr
        container = subprocess.run(
            [*compose, "ps", "-q", "postgres"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        uid = subprocess.run(
            ["docker", "exec", container, "id", "-u"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert uid.stdout.strip() != "0"
        refused = subprocess.run(
            [
                "docker",
                "exec",
                container,
                "psql",
                "-h",
                "127.0.0.1",
                "-U",
                "metiquo",
                "-d",
                "metiquo",
                "--no-password",
                "-c",
                "SELECT 1",
            ],
            capture_output=True,
            text=True,
        )
        assert refused.returncode != 0
        authenticated = subprocess.run(
            [
                "docker",
                "exec",
                container,
                "sh",
                "-ec",
                'export PGPASSWORD="$(cat /run/secrets/postgres_password)"; '
                "exec psql -h 127.0.0.1 -U metiquo -d metiquo --no-password -Atc 'SELECT 1'",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert authenticated.stdout.strip() == "1"
        assert password not in authenticated.stdout + authenticated.stderr
    finally:
        # Seules les ressources du projet UUID créé par ce test sont supprimées.
        assert project.startswith("metiquo-sec004-") and len(project) == 27
        subprocess.run(
            [*compose, "down", "--volumes", "--remove-orphans"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            check=True,
            timeout=60,
        )
