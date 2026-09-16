from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator
from pydantic.alias_generators import to_camel


class Contract(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class LeagueData(Contract):
    id: str = Field(min_length=1)
    slug: str
    name: str
    region: str
    image: str
    source_image: str
    tier: Literal["major", "regional", "international"]


class TeamData(Contract):
    id: str = Field(min_length=1)
    name: str
    code: str
    slug: str
    league_id: str
    image: str
    source_image: str


class Catalog(Contract):
    retrieved_at: date
    source: HttpUrl
    leagues: list[LeagueData]
    teams: list[TeamData]

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        leagues = {item.id for item in self.leagues}
        if len(leagues) != len(self.leagues) or len({t.id for t in self.teams}) != len(self.teams):
            raise ValueError("Duplicate catalog identity")
        if any(team.league_id not in leagues for team in self.teams):
            raise ValueError("Unknown team league")
        return self


class Quote(Contract):
    recorded_at: AwareDatetime
    odds: float = Field(gt=1, lt=1_000_000_000, allow_inf_nan=False)


class Opportunity(Contract):
    id: str
    league_id: str
    home_id: str
    away_id: str
    pick_id: str
    starts_at: AwareDatetime
    format: Literal["BO1", "BO3", "BO5"]
    market: Literal["winner", "map1"]
    probability: float = Field(gt=0, lt=1, allow_inf_nan=False)
    bookmaker: Literal["stake"] = "stake"
    history: list[Quote] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_market(self) -> Self:
        if self.home_id == self.away_id or self.pick_id not in (self.home_id, self.away_id):
            raise ValueError("Invalid match selection")
        dates = [point.recorded_at for point in self.history]
        if any(a >= b for a, b in zip(dates, dates[1:], strict=False)):
            raise ValueError("Quote timestamps must increase strictly")
        return self


class Opportunities(Contract):
    generated_at: datetime
    reference_date: datetime
    items: list[Opportunity]


def value_percent(probability: Decimal, odds: Decimal) -> Decimal:
    if not probability.is_finite() or not Decimal(0) < probability < Decimal(1):
        raise ValueError("Probability must be finite and between zero and one")
    if not odds.is_finite() or odds <= 1:
        raise ValueError("Decimal odds must be finite and greater than one")
    return (probability * odds - 1) * 100
