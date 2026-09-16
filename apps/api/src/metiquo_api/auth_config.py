from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="METIQUO_", extra="ignore")

    auth_secret: SecretStr = Field(min_length=32)
    auth_origins: list[str] = ["http://127.0.0.1:8080", "http://localhost:8080"]
    auth_cookie_secure: bool = True
    auth_trust_proxy: bool = False
    smtp_host: str = "127.0.0.1"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_security: Literal["none", "starttls", "tls"] = "none"
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str = "connexion@metiquo.fr"

    @model_validator(mode="after")
    def validate_transport(self) -> Self:
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError("SMTP username and password must be configured together")
        if self.smtp_username and self.smtp_security == "none":
            raise ValueError("SMTP credentials require TLS")
        if not self.auth_origins:
            raise ValueError("At least one explicit auth origin is required")
        for origin in self.auth_origins:
            url = urlsplit(origin)
            if (
                url.scheme not in ("http", "https")
                or not url.netloc
                or url.path
                or url.query
                or url.fragment
                or url.username
                or url.password
            ):
                raise ValueError("Auth origins must be explicit HTTP(S) origins without paths")
            if not self.auth_cookie_secure and url.hostname not in (
                "localhost",
                "127.0.0.1",
                "::1",
            ):
                raise ValueError("Insecure auth cookies are only allowed on loopback origins")
        return self

    @property
    def session_cookie(self) -> str:
        return "__Host-metiquo_session" if self.auth_cookie_secure else "metiquo_session"

    @property
    def challenge_cookie(self) -> str:
        return "__Host-metiquo_challenge" if self.auth_cookie_secure else "metiquo_challenge"
