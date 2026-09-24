from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="METIQUO_", extra="ignore")

    database_url: SecretStr
    artifact_dir: Path = Path(".cache/backend/artifacts")
    log_level: str = "INFO"
    odds_max_age_seconds: int = Field(default=900, ge=1)
    oracle_enabled: bool = True
    oracle_date_timezone: str | None = None
    oracle_folder_id: str = Field(default="1gLSw0RLjBbtaNy0dgnGQDAZOHIgCe-HH", pattern=r"^[\w-]+$")
    oracle_interval_seconds: int = Field(default=21600, ge=300)
    oracle_full_refresh_seconds: int = Field(default=604800, ge=300)
    oracle_export_timeout_seconds: int = Field(default=600, ge=30, le=1800)
    oracle_max_archive_bytes: int = Field(default=1_500_000_000, ge=1024)
    oracle_max_expanded_bytes: int = Field(default=5_000_000_000, ge=1024)
    browser_headless: bool = True
    worker_status_id: int = Field(default=1, ge=1)
    worker_stop_file: Path | None = None
    stake_enabled: bool = False
    settlements_enabled: bool = False
    stake_games: list[str] = ["league-of-legends"]
    stake_profile_dir: Path = Path(".cache/stake-audit/chrome-profile")
    stake_min_delay_seconds: float = Field(default=5, ge=2, le=60)
    stake_timeout_seconds: int = Field(default=45, ge=10, le=120)
    stake_cycle_seconds: int = Field(default=600, ge=60, le=1800)
    stake_max_actions: int = Field(default=300, ge=10, le=1000)
    stake_request_budget: int = Field(default=30000, ge=1000, le=60000)
    stake_budget_window_seconds: int = Field(default=1200, ge=300, le=3600)
    stake_block_cooldown_seconds: int = Field(default=3600, ge=60, le=86400)
    stake_start_guard_seconds: int = Field(default=60, ge=0, le=600)
    # Docker enables it explicitly; local commands stay opt-in to avoid an
    # unexpected browser launch during unrelated worker tests and tooling.
    loltv_enabled: bool = False
    loltv_timeout_seconds: int = Field(default=30, ge=5, le=120)
    loltv_browser_profile_dir: Path = Path(".cache/backend/loltv-browser")
    loltv_browser_channel: Literal["chromium", "chrome"] = "chromium"
    loltv_feed_enabled: bool = True
    loltv_render_live: bool = False
    loltv_min_delay_seconds: float = Field(default=2, ge=1, le=60)
    loltv_max_delay_seconds: float = Field(default=4, ge=1, le=120)
    loltv_listing_interval_seconds: int = Field(default=60, ge=30, le=3600)
    loltv_results_interval_seconds: int = Field(default=300, ge=60, le=86400)
    loltv_future_listing_interval_seconds: int = Field(default=900, ge=300, le=86400)
    loltv_live_refresh_seconds: int = Field(default=30, ge=30, le=900)
    loltv_finished_refresh_seconds: int = Field(default=21600, ge=900, le=604800)
    loltv_incomplete_refresh_seconds: int = Field(default=900, ge=300, le=86400)
    loltv_block_cooldown_seconds: int = Field(default=900, ge=60, le=86400)
    loltv_request_budget: int = Field(default=120, ge=10, le=600)
    loltv_browser_request_budget: int = Field(default=600, ge=50, le=3000)
    loltv_budget_window_seconds: int = Field(default=600, ge=60, le=3600)
    loltv_cycle_seconds: int = Field(default=90, ge=15, le=600)
    catalog_enabled: bool = True
    catalog_interval_seconds: int = Field(default=86400, ge=300)
    catalog_max_pages: int = Field(default=200, ge=1, le=2000)
    catalog_max_page_bytes: int = Field(default=15_000_000, ge=1024)
    catalog_max_image_bytes: int = Field(default=10_000_000, ge=1024)
    catalog_max_image_pixels: int = Field(default=80_000_000, ge=1, le=80_000_000)
    catalog_timeout_seconds: int = Field(default=60, ge=5, le=300)

    @field_validator("stake_games")
    @classmethod
    def validate_stake_games(cls, value: list[str]) -> list[str]:
        import re

        if (
            not value
            or len(set(value)) != len(value)
            or any(not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) for slug in value)
        ):
            raise ValueError("Stake games must be distinct public sport slugs")
        return value

    @field_validator("oracle_date_timezone", mode="before")
    @classmethod
    def validate_oracle_timezone(cls, value: str | None) -> str | None:
        if not value:
            return None
        try:
            ZoneInfo(value)
        except (KeyError, ValueError) as error:
            raise ValueError("Oracle timezone must be an IANA timezone") from error
        return value

    @property
    def oracle_folder_url(self) -> str:
        return f"https://drive.google.com/drive/folders/{self.oracle_folder_id}?hl=en"
