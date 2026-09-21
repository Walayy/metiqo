from pathlib import Path
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
    # Docker enables it explicitly; local commands stay opt-in to avoid an
    # unexpected browser launch during unrelated worker tests and tooling.
    sofascore_enabled: bool = False
    sofascore_timeout_seconds: int = Field(default=45, ge=10, le=180)
    sofascore_browser_profile_dir: Path = Path(".cache/backend/sofascore-browser")
    # All due pages in the window are visited sequentially, without a count cap.
    sofascore_min_delay_seconds: float = Field(default=15.0, ge=10, le=300)
    sofascore_max_delay_seconds: float = Field(default=30.0, ge=10, le=600)
    sofascore_listing_interval_seconds: int = Field(default=180, ge=60, le=86400)
    sofascore_past_listing_interval_seconds: int = Field(default=3600, ge=300, le=604800)
    sofascore_future_listing_interval_seconds: int = Field(default=900, ge=300, le=604800)
    sofascore_scheduled_refresh_seconds: int = Field(default=180, ge=60, le=3600)
    sofascore_live_refresh_seconds: int = Field(default=120, ge=60, le=900)
    sofascore_upcoming_refresh_seconds: int = Field(default=900, ge=300, le=86400)
    sofascore_finished_refresh_seconds: int = Field(default=3600, ge=300, le=604800)
    sofascore_incomplete_refresh_seconds: int = Field(default=300, ge=60, le=86400)
    sofascore_block_cooldown_seconds: int = Field(default=900, ge=60, le=86_400)
    catalog_enabled: bool = True
    catalog_interval_seconds: int = Field(default=86400, ge=300)
    catalog_max_pages: int = Field(default=200, ge=1, le=2000)
    catalog_max_page_bytes: int = Field(default=15_000_000, ge=1024)
    catalog_max_image_bytes: int = Field(default=10_000_000, ge=1024)
    catalog_max_image_pixels: int = Field(default=80_000_000, ge=1, le=80_000_000)
    catalog_timeout_seconds: int = Field(default=60, ge=5, le=300)

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
