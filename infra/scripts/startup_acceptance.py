"""Démarrer la démo complète sur des volumes neufs puis supprimer ce seul projet."""

import json
import os
import subprocess
from datetime import UTC, datetime
from urllib.request import urlopen
from uuid import uuid4

from infra.scripts.build_images import ROOT, code_revision


def compose_services(output: str) -> list[dict[str, object]]:
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        parsed = [json.loads(line) for line in output.splitlines() if line.strip()]
    return [parsed] if isinstance(parsed, dict) else list(parsed)


def main() -> int:
    revision = code_revision(ROOT)
    if revision is None:
        print("Le démarrage de recette exige un commit propre.")
        return 1
    identifier = uuid4().hex[:12]
    project = "metiquo-acceptance-" + identifier
    output = ROOT / "data/acceptance" / ("startup-" + identifier)
    output.mkdir(parents=True)
    empty_env = output / "empty.env"
    empty_env.write_text("", encoding="utf-8")
    isolated_prefixes = (
        "APP_",
        "AUTH_",
        "OE_",
        "ODDS_",
        "RELEASE_",
        "STAKE_",
        "COMPOSE_",
        "DATABASE_",
        "OBJECT_STORE_",
        "BACKUP_",
        "PAPER_",
        "WORKER_",
        "SIGNAL_",
        "MODEL_",
        "ALERT_",
    )
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith(isolated_prefixes)
    }
    environment.update(
        {
            "COMPOSE_PROJECT_NAME": project,
            "COMPOSE_ENV_FILES": str(empty_env),
            "APP_ENV": "development",
            "APP_DATA_MODE": "mock",
            "AUTH_MODE": "disabled",
            "APP_PUBLIC_ORIGIN": "http://localhost:3000",
            "APP_PUBLISH_HOST": "127.0.0.1",
            "DATABASE_URL": "postgresql+psycopg://metiquo@postgres:5432/metiquo",
            "ODDS_PROVIDER": "mock",
            "RELEASE_AUDIENCE": "personal",
            "OE_COMMERCIAL_GATE": "NO-GO",
            "RIOT_PRODUCT_GATE": "NO-GO",
            "STAKE_PROVIDER_ENABLED": "false",
        }
    )

    def command(arguments: list[str], *, timeout: int = 60) -> str:
        result = subprocess.run(
            arguments,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        with (output / "commands.log").open("a", encoding="utf-8") as log:
            log.write(json.dumps(arguments) + "\n" + result.stdout + result.stderr + "\n")
        if result.returncode:
            raise ValueError(f"Commande en échec ({result.returncode}) : {' '.join(arguments[:4])}")
        return result.stdout

    def resources() -> list[str]:
        found = []
        for kind in ("container", "volume", "network"):
            found.extend(
                command(
                    [
                        "docker",
                        kind,
                        "ls",
                        *(["--all"] if kind == "container" else []),
                        "-q",
                        "--filter",
                        "label=com.docker.compose.project=" + project,
                    ]
                ).splitlines()
            )
        return found

    def get(url: str) -> tuple[int, bytes]:
        with urlopen(url, timeout=15) as response:
            return response.status, response.read(2 * 1024 * 1024)

    report: dict[str, object] = {
        "commit": revision,
        "project": project,
        "command": ["make", "mock-demo"],
        "passed": False,
        "startedAt": datetime.now(UTC).isoformat(),
    }
    created = False
    try:
        if resources():
            raise ValueError("Le projet de recette doit être réellement neuf")
        report["startedWithNoResources"] = True
        created = True
        command(["make", "mock-demo"], timeout=1200)
        services = compose_services(command(["docker", "compose", "ps", "--format", "json"]))
        states = {
            service["Service"]: {"state": service["State"], "health": service.get("Health")}
            for service in services
        }
        for name in ("api", "worker", "web", "postgres"):
            if states.get(name) != {"state": "running", "health": "healthy"}:
                raise ValueError(f"Service non sain : {name}")
        report["services"] = states
        status, payload = get("http://127.0.0.1:8000/ready")
        if status != 200 or json.loads(payload)["status"] != "ready":
            raise ValueError("Readiness ou migrations incomplètes")
        report["readiness"] = json.loads(payload)
        status, payload = get("http://127.0.0.1:3000/api/backend/api/v1/system/compliance")
        compliance = json.loads(payload)
        if status != 200 or compliance != {
            "audience": "personal",
            "gates": {"OE-COMMERCIAL": "NO-GO", "RIOT-PRODUCT": "NO-GO"},
            "publicReleaseAllowed": False,
            "stakeProviderEnabled": False,
        }:
            raise ValueError("Le build personnel doit conserver ses portes NO-GO")
        report["compliance"] = compliance
        pages = {}
        for path in ("/", "/events", "/models", "/data", "/admin", "/paper-trading", "/settings"):
            status, content = get("http://127.0.0.1:3000" + path)
            if status != 200 or b"Metiquo" not in content:
                raise ValueError(f"Page de la stack indisponible : {path}")
            pages[path] = status
        report["pages"] = pages
        report["images"] = {
            name: command(
                ["docker", "image", "inspect", f"metiquo-{name}:local", "--format", "{{.Id}}"]
            ).strip()
            for name in ("api", "worker", "web", "postgres", "gateway")
        }
        for name in ("api", "worker"):
            image_revision = command(
                [
                    "docker",
                    "image",
                    "inspect",
                    f"metiquo-{name}:local",
                    "--format",
                    '{{index .Config.Labels "org.opencontainers.image.revision"}}',
                ]
            ).strip()
            if image_revision != revision:
                raise ValueError("Provenance des images Python incorrecte")
        report["versions"] = {
            "compose": command(["docker", "compose", "version", "--short"]).strip(),
            "python": command(
                ["docker", "compose", "exec", "-T", "api", "python", "--version"]
            ).strip(),
            "postgres": command(
                ["docker", "compose", "exec", "-T", "postgres", "postgres", "--version"]
            ).strip(),
            "node": command(
                ["docker", "compose", "exec", "-T", "web", "node", "--version"]
            ).strip(),
        }
        report["passed"] = True
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report["error"] = str(error)
    finally:
        if created:
            try:
                command(
                    [
                        "docker",
                        "compose",
                        "--project-name",
                        project,
                        "--profile",
                        "*",
                        "down",
                        "--volumes",
                        "--remove-orphans",
                    ],
                    timeout=180,
                )
                report["cleanupConfirmed"] = not resources()
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                report["cleanupError"] = str(error)
        report["sourceUnchanged"] = code_revision(ROOT) == revision
        report["passed"] = bool(
            report["passed"] and report.get("cleanupConfirmed") and report["sourceUnchanged"]
        )
        report["completedAt"] = datetime.now(UTC).isoformat()
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({"passed": report["passed"], "report": str(output / "report.json")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
