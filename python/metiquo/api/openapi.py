"""Génération sans effet de bord du contrat OpenAPI."""

import json

from metiquo.api.app import create_app
from metiquo.api.readiness import ReadinessCheck
from metiquo.config import Settings


class ContractReadinessProbe:
    """Sonde sans accès PostgreSQL utilisée uniquement pour le contrat."""

    def check(self) -> ReadinessCheck:
        return ReadinessCheck(available=False, reason_code="CONTRACT_GENERATION")


def _contract_settings() -> Settings:
    return Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "mock",
            "database_url": "postgresql+psycopg://metiquo@postgres:5432/metiquo",
            "odds_provider": "mock",
        }
    )


def render_openapi() -> str:
    """Rendre un JSON trié et reproductible sans dépendance externe."""

    app = create_app(settings=_contract_settings(), readiness_probe=ContractReadinessProbe())
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
