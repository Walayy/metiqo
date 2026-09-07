"""État publiable des portes sans exposer leurs pièces confidentielles."""

from typing import Literal

from pydantic import Field

from metiquo.contracts.base import ContractModel
from metiquo.foundation.release_compliance import GateStatus, ReleaseAudience


class ReleaseCompliance(ContractModel):
    audience: ReleaseAudience
    gates: dict[str, GateStatus]
    public_release_allowed: bool = Field(alias="publicReleaseAllowed")
    stake_provider_enabled: Literal[False] = Field(default=False, alias="stakeProviderEnabled")
