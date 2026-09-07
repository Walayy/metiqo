"""Serve the real production Node and Caddy builds through verified local TLS."""

import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.integration
def test_rebuilt_gateway_serves_web_and_api_with_verified_tls(tmp_path: Path) -> None:
    api = os.environ.get("TEST_SECURITY_IMAGE")
    web = os.environ.get("TEST_SECURITY_WEB_IMAGE")
    gateway = os.environ.get("TEST_SECURITY_GATEWAY_IMAGE")
    if not api or not web or not gateway:
        pytest.skip("TEST_SECURITY_{IMAGE,WEB_IMAGE,GATEWAY_IMAGE} requis")
    prefix = "metiquo-sec005-" + uuid4().hex[:12]

    def docker(*arguments: str) -> str:
        result = subprocess.run(
            ["docker", *arguments],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        return (result.stdout + (result.stderr if arguments[0] == "logs" else "")).strip()

    docker("network", "create", prefix)
    created = []
    common = ["--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true"]
    try:
        for service, arguments in (
            (
                "api",
                [
                    "-e",
                    "APP_DATA_MODE=mock",
                    "-e",
                    "APP_ENV=test",
                    "-e",
                    "DATABASE_URL=postgresql+psycopg://metiquo@postgres:5432/metiquo",
                    "-e",
                    "AUTH_MODE=disabled",
                    "-e",
                    "APP_PUBLIC_ORIGIN=https://localhost:8443",
                    api,
                    "uvicorn",
                    "metiquo.api.app:create_app",
                    "--factory",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8000",
                ],
            ),
            (
                "web",
                [
                    "-e",
                    "APP_DATA_MODE=mock",
                    "-e",
                    "API_BASE_URL=http://api:8000",
                    "-e",
                    "APP_PUBLIC_ORIGIN=https://localhost:8443",
                    web,
                ],
            ),
            (
                "gateway",
                [
                    "--user",
                    "1000:1000",
                    "--tmpfs",
                    "/data:uid=1000,gid=1000",
                    "--tmpfs",
                    "/config:uid=1000,gid=1000",
                    "--mount",
                    f"type=bind,source={ROOT / 'infra/gateway/Caddyfile'},"
                    "target=/etc/caddy/Caddyfile,readonly",
                    "-p",
                    "127.0.0.1::8443",
                    gateway,
                ],
            ),
        ):
            name = prefix + "-" + service
            docker(
                "run",
                "-d",
                "--name",
                name,
                "--network",
                prefix,
                "--network-alias",
                service,
                *common,
                "--tmpfs",
                "/tmp:mode=1777",
                *arguments,
            )
            created.append(name)
        port = docker("port", prefix + "-gateway", "8443/tcp").rsplit(":", 1)[1]
        certificate = tmp_path / "caddy-root.crt"
        deadline = time.monotonic() + 30
        while True:
            copied = subprocess.run(
                [
                    "docker",
                    "exec",
                    prefix + "-gateway",
                    "cat",
                    "/data/caddy/pki/authorities/local/root.crt",
                ],
                capture_output=True,
                timeout=10,
            )
            if copied.returncode == 0:
                certificate.write_bytes(copied.stdout)
                break
            assert time.monotonic() < deadline, copied.stderr.decode(errors="replace") + docker(
                "logs", prefix + "-gateway"
            )
            time.sleep(0.25)
        context = ssl.create_default_context(cafile=str(certificate))
        for route, expected in (
            ("/health", b""),
            ("/api/v1/auth/session", b"disabled"),
            ("/", b"html"),
        ):
            while True:
                try:
                    with urllib.request.urlopen(
                        f"https://localhost:{port}{route}", context=context, timeout=5
                    ) as response:
                        body = response.read()
                        assert response.status == 200
                        assert expected in body
                        break
                except (urllib.error.URLError, TimeoutError) as error:
                    assert time.monotonic() < deadline, (
                        f"Production route not ready: {route}: {error}\n"
                        + docker("logs", prefix + "-api")[-3000:]
                        + docker("logs", prefix + "-gateway")[-3000:]
                    )
                    time.sleep(0.25)
    finally:
        for name in reversed(created):
            docker("rm", "-f", name)
        docker("network", "rm", prefix)
