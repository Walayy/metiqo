"""Emplacement Stake non opérationnel, sans transport ni logique de collecte."""

from metiquo.foundation.time import Clock
from metiquo.providers.disabled import DisabledProvider

STAKE_DISABLED_REASON = (
    "L'autorisation écrite du fournisseur, une juridiction licite et la validation juridique "
    "de l'usage et de la redistribution sont requises ; aucune implémentation autorisée "
    "n'est livrée."
)


class StakeAuthorizedProvider(DisabledProvider):
    """Squelette durablement désactivé jusqu'à une future implémentation autorisée."""

    provider_code = "stake-authorized"

    def __init__(self, clock: Clock | None = None) -> None:
        super().__init__(self.provider_code, STAKE_DISABLED_REASON, clock)
