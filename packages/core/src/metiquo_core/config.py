from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="METIQUO_", extra="ignore")

    database_url: SecretStr
    artifact_dir: Path = Path(".cache/backend/artifacts")
    log_level: str = "INFO"
    odds_max_age_seconds: int = Field(default=900, ge=1)
    oracle_enabled: bool = True
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
    sofascore_max_events: int = Field(default=120, ge=1, le=500)
    # Discovery is deliberately incremental: a run must not open every day
    # and every event page in the J-7/J+7 window in one burst.
    sofascore_listing_days_per_run: int = Field(default=2, ge=1, le=4)
    sofascore_events_per_run: int = Field(default=12, ge=1, le=120)
    sofascore_min_delay_seconds: float = Field(default=2.0, ge=0.5, le=30.0)
    sofascore_max_delay_seconds: float = Field(default=5.0, ge=0.5, le=60.0)
    sofascore_listing_interval_seconds: int = Field(default=300, ge=60, le=3600)
    sofascore_scheduled_refresh_seconds: int = Field(default=300, ge=60, le=3600)
    sofascore_live_refresh_seconds: int = Field(default=60, ge=30, le=900)
    sofascore_block_cooldown_seconds: int = Field(default=900, ge=60, le=86_400)
    catalog_enabled: bool = True
    catalog_interval_seconds: int = Field(default=86400, ge=300)
    catalog_max_pages: int = Field(default=200, ge=1, le=2000)
    catalog_max_page_bytes: int = Field(default=15_000_000, ge=1024)
    catalog_max_image_bytes: int = Field(default=10_000_000, ge=1024)
    catalog_max_image_pixels: int = Field(default=80_000_000, ge=1, le=80_000_000)
    catalog_timeout_seconds: int = Field(default=60, ge=5, le=300)

    @property
    def oracle_folder_url(self) -> str:
        return f"https://drive.google.com/drive/folders/{self.oracle_folder_id}?hl=en"
