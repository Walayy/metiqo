"""Frontières interchangeables des fournisseurs de données externes."""

from metiquo.providers.contracts import OddsProvider
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

__all__ = [
    "MANUAL_IMPORT_COLUMNS",
    "LicensedFeedActivationError",
    "LicensedOddsFeedConfiguration",
    "LicensedOddsFeedProvider",
    "ManualImportIssue",
    "ManualImportOddsProvider",
    "ManualImportResult",
    "OddsProvider",
]
