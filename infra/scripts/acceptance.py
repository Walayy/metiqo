"""Recette des 22 critères SFG §31 à partir des artefacts authentifiés du commit courant."""

import argparse
import hashlib
import io
import json
import re
import stat
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree

from infra.scripts.build_images import ROOT, code_revision


def criterion(
    number: int,
    title: str,
    backend: tuple[str, ...] = (),
    browser: tuple[str, ...] = (),
    *,
    startup: bool = False,
    manual: bool = False,
) -> dict[str, Any]:
    return dict(
        number=number, title=title, backend=backend, browser=browser, startup=startup, manual=manual
    )


INGESTION = (
    "tests.integration.test_ingestion_gate::test_ingestion_gate_demo_rebuilds_from_empty_database"
)
CRITERIA = (
    criterion(1, "Démarrage Compose en une commande", startup=True),
    criterion(
        2,
        "Écrans et scénarios mock critiques",
        ("tests.mock.test_scenarios::test_catalog_contains_and_addresses_each_normative_scenario",),
        (
            "opportunities.spec.ts::",
            "models.spec.ts::",
            "paper-trading.spec.ts::",
            "mapping-review.spec.ts::",
        ),
    ),
    criterion(
        3,
        "Backfill idempotent et reprenable",
        (
            INGESTION,
            "tests.integration.test_backfill::test_interrupted_backfill_resumes_without_replaying_completed_years",
        ),
    ),
    criterion(4, "Année courante validée, hash et manifeste", (INGESTION,)),
    criterion(5, "Quota : dernier snapshot valide préservé", (INGESTION,)),
    criterion(
        6,
        "Reconstruction canonique des séries et games",
        (
            "tests.integration.test_canonical_games::test_games_keep_quality_flags_provenance_and_explicit_missingness",
            "tests.integration.test_canonical_series::test_series_prefer_oe_support_bo2_draw_and_leave_ambiguity_unresolved",
        ),
    ),
    criterion(
        7,
        "Cutoff automatiquement vérifié",
        (
            "tests.leakage.",
            "tests.integration.test_temporal_features::test_as_of_repository_excludes_game_at_cutoff_and_records_max_input_time",
        ),
    ),
    criterion(
        8,
        "Baseline rating et game winner calibré enregistrés",
        (
            "tests.integration.test_baseline_runs::test_baseline_runs_roundtrip_are_comparable_and_append_only",
            "tests.integration.test_model_training_workflow::test_training_workflow_publishes_candidate_then_allows_gated_promotion",
        ),
    ),
    criterion(
        9,
        "Probabilités des formats de série supportés",
        (
            "tests.markets.test_series_pricing::test_analytical_bo1_bo3_bo5_and_bo2_draw_probabilities",
            "tests.markets.test_series_pricing::test_every_supported_format_is_normalized_over_full_probability_domain",
        ),
    ),
    criterion(
        10,
        "Contrat commun mock et import manuel",
        (
            "tests.providers.test_mock_odds_provider::test_mock_passes_the_exact_reusable_provider_contract",
            "tests.providers.test_manual_import_provider::test_valid_csv_is_committed_atomically_and_passes_provider_contract",
            "tests.providers.test_manual_import_provider::test_valid_json_uses_the_same_normalized_contract",
        ),
    ),
    criterion(
        11,
        "Mapping ambigu bloquant",
        (
            "tests.integration.test_resolved_odds_gate::test_ambiguous_event_with_resolved_market_never_reaches_pricing",
        ),
    ),
    criterion(
        12,
        "Probabilités, marge, cote juste, edge et EV prudente",
        (
            "tests.pricing.test_value::test_sfg_odds_four_example_reproduces_every_value_metric",
            "tests.pricing.test_no_vig::test_hand_calculated_two_way_market_removes_overround",
        ),
    ),
    criterion(
        13,
        "Abstention structurée persistée",
        (
            "tests.integration.test_value_pipeline::test_value_gate_refusals_are_persisted[stale]",
            "tests.integration.test_value_pipeline::test_value_gate_refusals_are_persisted[ambiguous]",
            "tests.integration.test_value_pipeline::test_value_gate_refusals_are_persisted[no_edge]",
        ),
    ),
    criterion(
        14,
        "Prédictions et cotes immuables",
        (
            "tests.integration.test_prematch_predictions::test_repeated_prematch_prediction_keeps_reproducible_inference_and_history",
            "tests.integration.test_odds_schema::test_odds_snapshot_requires_reliable_time_or_informational_status_and_is_immutable",
        ),
    ),
    criterion(
        15,
        "Enregistrement et règlement paper",
        ("tests.integration.test_paper_gate::test_paper_gate_emits_an_auditable_fixture_report",),
        ("paper-trading.spec.ts::",),
    ),
    criterion(
        16,
        "Fraîcheur, modèle et qualité visibles",
        (
            "tests.integration.test_system_observability::test_status_distinguishes_source_failure_reads_and_measured_job_metrics",
        ),
        ("admin-data.spec.ts::", "real-models.spec.ts::"),
    ),
    criterion(
        17,
        "Stabilité, console et hydratation",
        (),
        (
            "visual-stability.spec.ts::slow response keeps desktop /admin stable",
            "accessibility.spec.ts::keeps cumulative layout shift below 0.05 on key dashboards",
            "accessibility.spec.ts::has no WCAG A/AA axe violations "
            "or hydration errors on key pages",
        ),
    ),
    criterion(
        18,
        "Parcours critiques Playwright mock",
        (),
        tuple(
            name + ".spec.ts::"
            for name in (
                "opportunities",
                "event-detail",
                "signal-detail",
                "models",
                "paper-trading",
                "mapping-review",
                "admin-data",
                "network-resilience",
                "keyboard-accessibility",
            )
        ),
    ),
    criterion(
        19,
        "Sauvegarde et restauration réelles",
        (
            "tests.integration.test_backup_container::test_packaged_backup_and_restore_with_read_only_root",
            "tests.integration.test_restore::",
        ),
    ),
    criterion(
        20,
        "Stake, contournements et mise automatique inactifs",
        (
            "tests.providers.test_stake_provider_disabled::test_startup_still_rejects_enablement_without_an_authorized_implementation",
            "tests.providers.test_stake_provider_disabled::test_repository_compliance_scan_is_clean_and_wired_into_ci",
        ),
    ),
    criterion(
        21,
        "Absence de gain garanti affichée",
        ("tests.test_release_compliance::test_marketing_promises_block_the_compliance_scan",),
        (
            "release-compliance.spec.ts::shows release refusals and no guaranteed gain at 1440px",
            "release-compliance.spec.ts::shows release refusals and no guaranteed gain at 390px",
        ),
        manual=True,
    ),
    criterion(
        22,
        "Portes juridiques visibles et publication bloquée",
        (
            "tests.test_release_compliance::test_public_release_fails_without_manual_evidence[public]",
            "tests.test_release_compliance::test_public_release_fails_without_manual_evidence[commercial]",
            "tests.test_release_compliance::test_go_requires_complete_scoped_current_untampered_evidence",
        ),
        ("release-compliance.spec.ts::",),
        manual=True,
    ),
)


def evaluate_criteria(
    backend: set[str],
    browser: set[str],
    *,
    startup_ok: bool,
    manual_ok: bool,
) -> list[dict[str, Any]]:
    result = []
    for rule in CRITERIA:
        evidence: list[dict[str, str]] = []
        missing = []
        for kind, cases in (("backend", backend), ("browser", browser)):
            for prefix in rule[kind]:
                matches = sorted(name for name in cases if name.startswith(prefix))
                evidence.extend({"suite": kind, "test": name} for name in matches)
                if not matches:
                    missing.append(prefix)
        if rule["startup"] and not startup_ok:
            missing.append("démarrage Compose neuf")
        if rule["manual"] and not manual_ok:
            missing.append("revue visuelle liée aux sources")
        result.append(
            {**rule, "status": "FAIL" if missing else "PASS", "tests": evidence, "missing": missing}
        )
    return result


def junit_cases(path: Path) -> set[str]:
    cases = ElementTree.parse(path).findall(".//testcase")
    identities = {case.get("classname", "") + "::" + case.get("name", "") for case in cases}
    if (
        not cases
        or len(identities) != len(cases)
        or any(
            case.find(tag) is not None for case in cases for tag in ("skipped", "failure", "error")
        )
    ):
        raise ValueError("Rapport JUnit absent, incomplet, dupliqué ou non vert")
    return identities


def verify_runs(
    positive: dict[str, Any], negative: dict[str, Any], revision: str, negative_log: str
) -> None:
    if positive.get("headSha") != revision or negative.get("headSha") != revision:
        raise ValueError("Les deux runs doivent tester le commit courant")
    jobs = {job["name"]: job for job in positive.get("jobs", [])}
    required = {
        "Qualité",
        "Migrations PostgreSQL",
        "Interface Playwright",
        "Build Docker",
        "Gate MVP",
    }
    if (
        positive.get("status") != "completed"
        or positive.get("conclusion") != "success"
        or not required.issubset(jobs)
        or any(job.get("conclusion") != "success" for job in jobs.values())
    ):
        raise ValueError("CI normale incomplète ou non verte")
    negative_jobs = {job["name"]: job for job in negative.get("jobs", [])}
    steps = negative_jobs.get("Qualité", {}).get("steps", [])
    injected = any(
        step["name"].startswith("Injecter la faute temporelle") and step["conclusion"] == "success"
        for step in steps
    )
    refused = any(
        step["name"].startswith("Vérifier le cutoff critique") and step["conclusion"] == "failure"
        for step in steps
    )
    if (
        negative.get("status") != "completed"
        or negative.get("conclusion") != "failure"
        or negative_jobs.get("Gate MVP", {}).get("conclusion") != "failure"
        or not injected
        or not refused
        or "FAILED tests/leakage/" not in negative_log
        or "test_property_every_nonnegative_event_offset_is_rejected" not in negative_log
    ):
        raise ValueError("Exercice négatif critique non démontré")


def extract_verified_archive(payload: bytes, digest: str, destination: Path) -> None:
    if digest != "sha256:" + hashlib.sha256(payload).hexdigest():
        raise ValueError("L'empreinte de l'artefact ne correspond pas à GitHub")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if sum(item.file_size for item in archive.infolist()) > 512 * 1024 * 1024:
            raise ValueError("Artefact trop volumineux")
        for item in archive.infolist():
            target = (destination / item.filename).resolve()
            if not target.is_relative_to(destination.resolve()) or stat.S_ISLNK(
                item.external_attr >> 16
            ):
                raise ValueError("Artefact refusé : chemin hors destination ou lien")
        archive.extractall(destination)


def verify_manual_review(root: Path) -> dict[str, Any]:
    report = json.loads((root / "docs/evidence/qa-006/report.json").read_text(encoding="utf-8"))
    review = report["manualReview"]
    if report["status"] != "passed" or not all(
        review.get(k) for k in ("reviewer", "reviewedAt", "scope", "captures", "sourceHashes")
    ):
        raise ValueError("La revue visuelle est incomplète")
    for item in [*review["captures"], *review["sourceHashes"]]:
        path = (root / item["path"]).resolve()
        if (
            not path.is_relative_to(root.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]
        ):
            raise ValueError("Sources ou images modifiées depuis la revue visuelle")
    return dict(review)


def gh(*arguments: str) -> bytes:
    return subprocess.run(
        ["gh", *arguments], cwd=ROOT, capture_output=True, check=True, timeout=180
    ).stdout


def read_json(path: Path) -> dict[str, Any]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


def fingerprint(path: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def verify_runtime(
    security: dict[str, Any],
    performance: dict[str, Any],
    startup: dict[str, Any],
    revision: str,
) -> None:
    for proof in (security, performance, startup):
        if proof.get("commit") != revision or proof.get("passed") is not True:
            raise ValueError("Une preuve runtime est invalide ou provient d'un autre commit")
    if security.get("blocking") or not performance.get("sourceUnchanged"):
        raise ValueError("Gate sécurité ou provenance du benchmark refusé")
    scanned = {name: item["id"] for name, item in security.get("images", {}).items()}
    if (
        set(scanned) != {"api", "worker", "web", "postgres", "gateway"}
        or startup.get("images") != scanned
    ):
        raise ValueError("Les images scannées diffèrent des images du dernier démarrage")


def collect(ci_run: str, negative_run: str, output: Path) -> dict[str, Any]:
    revision = code_revision(ROOT)
    if revision is None:
        raise ValueError("La recette exige un checkout Git propre")
    fields = "status,conclusion,headSha,url,jobs"
    positive = json.loads(gh("run", "view", ci_run, "--json", fields))
    negative = json.loads(gh("run", "view", negative_run, "--json", fields))
    negative_log = gh("run", "view", negative_run, "--log-failed").decode("utf-8")
    verify_runs(positive, negative, revision, negative_log)
    repository = json.loads(gh("repo", "view", "--json", "nameWithOwner"))["nameWithOwner"]
    metadata = json.loads(gh("api", f"repos/{repository}/actions/runs/{ci_run}/artifacts"))[
        "artifacts"
    ]
    artifacts = []
    for name in ("runtime-evidence", "browser-evidence"):
        matches = [item for item in metadata if item["name"] == name and not item["expired"]]
        if len(matches) != 1:
            raise ValueError("Artefact requis absent, expiré ou ambigu")
        item = matches[0]
        payload = gh("api", f"repos/{repository}/actions/artifacts/{item['id']}/zip")
        extract_verified_archive(payload, item["digest"], output / name)
        artifacts.append({key: item[key] for key in ("id", "name", "digest", "size_in_bytes")})
    runtime = output / "runtime-evidence/data"
    backend_path = runtime / "ci/backend.xml"
    browser_path = output / "browser-evidence/data/ci/playwright.xml"
    backend, browser = junit_cases(backend_path), junit_cases(browser_path)
    if len(backend) < 616 or len(browser) < 106:
        raise ValueError("Les suites complètes attendues n'ont pas été exécutées")
    (security_path,) = runtime.glob("security/*/summary.json")
    (performance_path,) = runtime.glob("performance/*/report.json")
    (startup_path,) = runtime.glob("acceptance/startup-*/report.json")
    security, performance, startup = map(read_json, (security_path, performance_path, startup_path))
    verify_runtime(security, performance, startup, revision)
    manual = verify_manual_review(ROOT)
    startup_ok = (
        startup.get("command") == ["make", "mock-demo"]
        and startup.get("startedWithNoResources") is True
        and startup.get("cleanupConfirmed") is True
        and startup.get("sourceUnchanged") is True
    )
    rows = evaluate_criteria(backend, browser, startup_ok=startup_ok, manual_ok=True)
    if code_revision(ROOT) != revision:
        raise ValueError("Le checkout a changé pendant la recette")
    return {
        "ticket": "QA-007",
        "commit": revision,
        "passed": all(row["status"] == "PASS" for row in rows),
        "criteria": rows,
        "generatedAt": datetime.now(UTC).isoformat(),
        "positiveRun": positive,
        "negativeRun": negative,
        "artifacts": artifacts,
        "tests": {"backend": len(backend), "browser": len(browser), "skipped": 0},
        "proofs": [
            fingerprint(path)
            for path in (backend_path, browser_path, security_path, performance_path, startup_path)
        ],
        "manualReview": manual,
        "versions": {"startup": startup["versions"], "benchmark": performance["versions"]},
        "commands": [
            f"gh run view {ci_run}",
            f"gh run view {negative_run}",
            "make mock-demo",
            "uv run --frozen python -m pytest",
            "pnpm exec playwright test --grep-invert 'authenticates the Owner'",
            "make scan-security",
            "make check",
        ],
        "scope": (
            "MVP personnel sur fixtures identifiées et services réels. Aucune validation "
            "financière, autorisation de source, ouverture publique ou fonctionnalité "
            "P10/P11 n'est déduite."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ci-run", required=True)
    parser.add_argument("--negative-ci-run", required=True)
    args = parser.parse_args()
    if not all(re.fullmatch(r"[0-9]+", value) for value in (args.ci_run, args.negative_ci_run)):
        parser.error("Les identifiants de run doivent être numériques")
    output = (
        ROOT / "data/acceptance" / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8])
    )
    output.mkdir(parents=True)
    try:
        report = collect(args.ci_run, args.negative_ci_run, output)
    except (
        OSError,
        ValueError,
        KeyError,
        ElementTree.ParseError,
        subprocess.SubprocessError,
        zipfile.BadZipFile,
    ) as error:
        report = {
            "ticket": "QA-007",
            "passed": False,
            "error": str(error),
            "criteria": evaluate_criteria(set(), set(), startup_ok=False, manual_ok=False),
        }
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Recette du MVP personnel",
        "",
        f"Commit : `{report.get('commit', 'non vérifié')}`",
        "",
        "| N° | Critère | Résultat |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| {row['number']} | {row['title']} | {row['status']} |" for row in report["criteria"]
    )
    lines.extend(
        [
            "",
            "Les commandes, versions, cas exécutés et empreintes figurent "
            "dans le rapport JSON joint.",
            "",
            str(report.get("error", report.get("scope", ""))),
        ]
    )
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "report": str(output / "report.json")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
