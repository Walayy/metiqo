"""Cache court des URL publiques ; les prix sont toujours relus dans le navigateur."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import Field, ValidationError

from metiquo.contracts.base import ContractModel, UtcDateTime
from metiquo.foundation.time import Clock
from metiquo.providers.stake_parser import public_url


class DiscoveryCache(ContractModel):
    observed_at: UtcDateTime
    urls: tuple[str, ...] = Field(min_length=1, max_length=1000)


def read_discovery(path: Path, clock: Clock, max_age_seconds: int = 300) -> tuple[str, ...]:
    try:
        with path.open("rb") as stream:
            payload = stream.read(256 * 1024 + 1)
        if len(payload) > 256 * 1024:
            return ()
        cache = DiscoveryCache.model_validate_json(payload)
        age = (clock.now().value - cache.observed_at).total_seconds()
        if not 0 <= age < max_age_seconds:
            return ()
        return tuple(dict.fromkeys(public_url(url, event_only=True) for url in cache.urls))
    except (OSError, ValueError, ValidationError):
        return ()


def write_discovery(path: Path, clock: Clock, urls: tuple[str, ...]) -> None:
    cache = DiscoveryCache(observed_at=clock.now().value, urls=urls)
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(cache.model_dump(mode="json"), stream)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
