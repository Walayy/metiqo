"""Identités UUID déterministes partagées par les adaptateurs de cotes."""

from uuid import NAMESPACE_URL, UUID, uuid5


def provider_entity_uuid(provider_code: str, kind: str, identity: str) -> UUID:
    """Dériver une identité stable sans confondre fournisseurs ni types d'entité."""

    normalized_provider = provider_code.strip()
    normalized_kind = kind.strip()
    normalized_identity = identity.strip()
    if not normalized_provider or not normalized_kind or not normalized_identity:
        raise ValueError("provider_code, kind et identity sont obligatoires")
    return uuid5(
        NAMESPACE_URL,
        f"metiquo:{normalized_provider}:{normalized_kind}:{normalized_identity}",
    )


def provider_market_uuid(
    provider_code: str,
    provider_event_id: str,
    provider_market_id: str,
) -> UUID:
    """Conserver un UUID fournisseur explicite ou dériver l'identité externe."""

    try:
        return UUID(provider_market_id)
    except ValueError:
        return provider_entity_uuid(
            provider_code,
            "market",
            f"{provider_event_id}:{provider_market_id}",
        )
