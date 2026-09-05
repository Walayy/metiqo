"""Frontières interchangeables des fournisseurs de données externes."""

from metiquo.providers.contracts import OddsProvider
from metiquo.providers.disabled import DisabledProvider, ProviderDisabledError
from metiquo.providers.licensed_feed import (
    LicensedFeedActivationError,
    LicensedOddsFeedConfiguration,
    LicensedOddsFeedProvider,
)
from metiquo.providers.manual_import import (
    MANUAL_IMPORT_COLUMNS,
    ManualImportIssue,
    ManualImportOddsProvider,
    ManualImportResult,
)
from metiquo.providers.stake_authorized import (
    STAKE_DISABLED_REASON,
    StakeAuthorizedProvider,
)

__all__ = [
    "MANUAL_IMPORT_COLUMNS",
    "STAKE_DISABLED_REASON",
    "DisabledProvider",
    "LicensedFeedActivationError",
    "LicensedOddsFeedConfiguration",
    "LicensedOddsFeedProvider",
    "ManualImportIssue",
    "ManualImportOddsProvider",
    "ManualImportResult",
    "OddsProvider",
    "ProviderDisabledError",
    "StakeAuthorizedProvider",
]
