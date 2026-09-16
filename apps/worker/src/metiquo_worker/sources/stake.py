from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from metiquo_core.contracts import Quote


@dataclass(frozen=True)
class SourceQuote:
    """Source identities must be resolved to internal match/market IDs before persistence."""

    match_source_id: str
    market_source_id: str
    selection_source_id: str
    quote: Quote


class OddsSource(Protocol):
    def collect(self) -> Iterator[SourceQuote]: ...


class StakeSource:
    """Reserved extension point. No URL, navigation, account or network request."""

    def collect(self) -> Iterator[SourceQuote]:
        raise NotImplementedError("Stake collection is not implemented or enabled")
