"""Projection des vainqueurs observés vers le port de cotes existant."""

import json
import re

from metiquo.contracts.stake_scraping import ScrapedMarket, StakeEventCapture
from metiquo.foundation.time import Clock
from metiquo.providers.manual_import import ManualImportOddsProvider
from metiquo.providers.stake_parser import PARSER_VERSION, PROVIDER_CODE


def winner_provider(capture: StakeEventCapture, clock: Clock) -> ManualImportOddsProvider:
    """Conserver tous les autres marchés dans la capture brute, sans inventer leur contrat."""
    provider = ManualImportOddsProvider(PROVIDER_CODE, clock=clock)
    winners: dict[str, ScrapedMarket] = {}
    for market in capture.markets:
        if market.label == "Vainqueur du match - Two options":
            period = "SERIES"
        elif match := re.fullmatch(r"Map ([1-5]) Gagnant - Two options", market.label):
            period = f"GAME_{match[1]}"
        else:
            continue
        previous = winners.get(period)
        if previous is None or market.captured_at >= previous.captured_at:
            winners[period] = market
    rows = []
    event = capture.event
    for period, market in sorted(winners.items()):
        # Choisir d'abord l'observation la plus récente, même sans prix : revenir
        # à l'ancien onglet publierait à tort une cote désormais indisponible.
        if len(market.outcomes) != 2 or any(o.decimal_odds is None for o in market.outcomes):
            continue
        if {o.label for o in market.outcomes} != set(event.participants):
            continue
        for outcome in market.outcomes:
            side = event.participants.index(outcome.label)
            rows.append(
                {
                    "provider": PROVIDER_CODE,
                    "provider_event_id": event.provider_event_id,
                    "game_title": "lol",
                    "competition": event.competition,
                    "participant_a": event.participants[0],
                    "participant_b": event.participants[1],
                    "starts_at": event.starts_at.isoformat(),
                    "best_of": event.best_of,
                    "event_status": event.status.value,
                    "provider_market_id": f"dom:winner:{period}",
                    "market_label": market.label,
                    "market_type": "MATCH_WINNER",
                    "period": period,
                    "line": None,
                    "unit": "match",
                    "provider_selection_id": f"dom:team-{side}",
                    "selection": "TEAM_A" if side == 0 else "TEAM_B",
                    "selection_label": outcome.label,
                    "decimal_odds": str(outcome.decimal_odds),
                    "market_status": "open"
                    if all(o.status == "open" for o in market.outcomes)
                    else "suspended",
                    "captured_at": market.captured_at.isoformat(),
                    "timestamp_reliable": False,
                    "settlement_rules_version": PARSER_VERSION,
                    "remake_policy": "review",
                    "forfeit_policy": "review",
                    "cancelled_policy": "review",
                    "provenance_reference": f"{PARSER_VERSION}:event:{event.provider_event_id}",
                }
            )
    if rows:
        result = provider.import_document(json.dumps(rows).encode(), document_format="json")
        if not result.committed:
            raise ValueError("La projection de la capture Stake est incohérente")
    return provider
