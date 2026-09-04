"""Publication des DTO métier dans les composants OpenAPI."""

from fastapi import FastAPI
from pydantic.json_schema import models_json_schema

from metiquo.contracts import DOMAIN_CONTRACT_MODELS


def _domain_component_schemas() -> dict[str, object]:
    _, root_schema = models_json_schema(
        [(model, "serialization") for model in DOMAIN_CONTRACT_MODELS],
        ref_template="#/components/schemas/{model}",
    )
    definitions = root_schema.get("$defs")
    if not isinstance(definitions, dict):
        raise RuntimeError("Les schémas des contrats métier n'ont pas été générés")
    return {str(name): definition for name, definition in definitions.items()}


def install_domain_contract_schemas(app: FastAPI) -> None:
    """Ajouter les contrats partagés sans créer de route prématurée."""

    openapi_schema = app.openapi()
    components = openapi_schema.setdefault("components", {})
    if not isinstance(components, dict):
        raise RuntimeError("La section OpenAPI components est invalide")
    schemas = components.setdefault("schemas", {})
    if not isinstance(schemas, dict):
        raise RuntimeError("La section OpenAPI components.schemas est invalide")

    for name, definition in _domain_component_schemas().items():
        # Les schémas produits par FastAPI pour une route sont prioritaires :
        # Pydantic peut ordonner ou développer différemment leurs références,
        # tout en décrivant le même contrat.
        schemas.setdefault(name, definition)

    app.openapi_schema = openapi_schema
