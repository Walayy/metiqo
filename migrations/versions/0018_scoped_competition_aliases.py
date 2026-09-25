"""Scoped, reviewed tournament aliases and EMEA Masters source identities.

Revision ID: 0018
Revises: 0017
"""

import hashlib
import json
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

STAKE_KEY = "/fr/sports/league-of-legends/international-1/em-2026-summer-swiss-t5"
STAKE_SOURCE = f"https://stake.bet{STAKE_KEY}"
LOLTV_SOURCE = "https://loltv.gg/matches"
VALID_FROM = datetime(2026, 9, 25, tzinfo=UTC)
VALID_UNTIL = datetime(2026, 11, 1, tzinfo=UTC)
TEAM_ALIASES = (
    ("BIG", "clpz8g6c901goakxlu3z0ahw4"),
    ("FC Barcelona", "clpz8g66h015xakxleja0nupz"),
    ("Senshi eSports (Benelux Team)", "clqovtlft0153t1c3kb8ql3tr"),
    ("Team Secret Club", "404f65e22b05da1713d17c69"),
)
WSCI_KEY = (
    "/fr/sports/league-of-legends/international-1/2026-world-star-challengers-invitational-t8"
)
CBLOL_KEY = "/fr/sports/league-of-legends/international-1/cblol-2026-split-2-playoffs-t5"
EXTRA_TEAM_ALIASES = (
    (
        "Keyd Academy",
        "clpz8g6bv01fbakxlifhqtdwk",
        WSCI_KEY,
        datetime(2026, 9, 20, tzinfo=UTC),
        datetime(2026, 10, 3, tzinfo=UTC),
        (
            "https://stake.bet/fr/sports/league-of-legends/international-1/2026-world-star-challengers-invitational-t8/850860-fennel-keyd-stars-academy",
            "https://loltv.gg/match/2026-09-25-fennel-vs-vivo-keyd-stars-academy",
            "https://stake.bet/fr/sports/league-of-legends/international-1/2026-world-star-challengers-invitational-t8/850867-cupid-esports-keyd-stars-academy",
            "https://loltv.gg/match/2026-09-25-cupid-esports-vs-vivo-keyd-stars-academy",
        ),
    ),
    (
        "LOS",
        "clpz8g6da01kxakxl4k32fiwd",
        CBLOL_KEY,
        datetime(2026, 9, 25, tzinfo=UTC),
        datetime(2026, 10, 1, tzinfo=UTC),
        (
            "https://stake.bet/fr/sports/league-of-legends/international-1/cblol-2026-split-2-playoffs-t5/836114-loud-los",
            "https://loltv.gg/match/2026-09-27-round-4-1-cblol-split-2-2026",
        ),
    ),
)


def _record(
    name: str,
    target_id: str,
    *,
    competition: bool = False,
    competition_key: str = STAKE_KEY,
    valid_from: datetime = VALID_FROM,
    valid_until: datetime = VALID_UNTIL,
    sources: tuple[str, ...] = (STAKE_SOURCE, LOLTV_SOURCE),
) -> dict[str, object]:
    record: dict[str, object] = {
        "provider": "stake",
        "game": "league-of-legends",
        "name": name,
        "competition_key": competition_key,
        "target_provider": "loltv",
        "target_id": target_id,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "evidence": {
            "sources": list(sources),
            "reason": (
                "Source tournament labels and edition, independently corroborated by unique "
                "two-team pairs and UTC starts in the retained 2026-09-25 captures."
                if competition
                else "Source team labels in the same tournament edition, corroborated by the "
                "same opponent, tournament and compatible UTC schedule in the "
                "retained source captures."
            ),
        },
        "active": True,
    }
    canonical = {
        **record,
        "valid_from": valid_from.isoformat().replace("+00:00", "Z"),
        "valid_until": valid_until.isoformat().replace("+00:00", "Z"),
    }
    canonical.pop("active")
    identity = {"kind": "competition", "record": canonical} if competition else canonical
    raw = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    record["id"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return record


def _team_records() -> list[dict[str, object]]:
    return [
        *[_record(name, target_id) for name, target_id in TEAM_ALIASES],
        *[
            _record(
                name,
                target_id,
                competition_key=competition_key,
                valid_from=valid_from,
                valid_until=valid_until,
                sources=sources,
            )
            for name, target_id, competition_key, valid_from, valid_until, sources in (
                EXTRA_TEAM_ALIASES
            )
        ],
    ]


def upgrade() -> None:
    op.create_table(
        "match_competition_aliases",
        sa.Column("id", sa.String(64), primary_key=True),
        *[
            sa.Column(name, sa.String(), nullable=False)
            for name in (
                "provider",
                "game",
                "name",
                "competition_key",
                "target_provider",
                "target_id",
            )
        ],
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", JSONB(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("valid_until > valid_from"),
    )
    competition_record = _record(
        "EM 2026 Summer Swiss", "emea-masters-summer-2026", competition=True
    )
    op.execute(
        sa.text(
            """INSERT INTO match_competition_aliases
            (id, provider, game, name, competition_key, target_provider, target_id,
             valid_from, valid_until, evidence, active)
            VALUES (:id, :provider, :game, :name, :competition_key, :target_provider,
                    :target_id, :valid_from, :valid_until, CAST(:evidence AS jsonb), :active)"""
        ).bindparams(
            **{**competition_record, "evidence": json.dumps(competition_record["evidence"])}
        )
    )
    for record in _team_records():
        op.execute(
            sa.text(
                """INSERT INTO match_identity_aliases
                (id, provider, game, name, competition_key, target_provider, target_id,
                 valid_from, valid_until, evidence, active)
                VALUES (:id, :provider, :game, :name, :competition_key, :target_provider,
                        :target_id, :valid_from, :valid_until, CAST(:evidence AS jsonb), :active)
                ON CONFLICT (id) DO NOTHING"""
            ).bindparams(**{**record, "evidence": json.dumps(record["evidence"])})
        )
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT FROM pg_roles WHERE rolname='metiquo_api') THEN
        GRANT SELECT ON match_competition_aliases TO metiquo_api;
      END IF;
      IF EXISTS (SELECT FROM pg_roles WHERE rolname='metiquo_worker') THEN
        GRANT SELECT, INSERT, UPDATE ON match_competition_aliases TO metiquo_worker;
        REVOKE DELETE ON match_competition_aliases FROM metiquo_worker;
      END IF;
    END $$""")


def downgrade() -> None:
    for record in _team_records():
        op.execute(
            sa.text("UPDATE match_identity_aliases SET active = false WHERE id = :id").bindparams(
                id=record["id"]
            )
        )
    op.drop_table("match_competition_aliases")
