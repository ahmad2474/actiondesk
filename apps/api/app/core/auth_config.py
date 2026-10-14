from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    """API-only settings. Import/schema export never requires runtime secrets."""

    model_config = SettingsConfigDict(
        env_prefix="ACTIONDESK_AUTH_", env_file=".env", extra="ignore"
    )
    secret: SecretStr | None = None
    organization_slug: str = ""
    allowed_origins: list[str] = Field(default_factory=list)
    cookie_secure: bool = True
    idle_seconds: int = Field(default=1800, ge=60)
    absolute_seconds: int = Field(default=28800, ge=60)
    touch_seconds: int = Field(default=300, ge=1)
    argon_memory_kib: int = Field(default=65536, ge=8192)
    argon_time_cost: int = Field(default=3, ge=1)
    argon_parallelism: int = Field(default=4, ge=1)
    ip_limit: int = Field(default=20, ge=1)
    ip_window_seconds: int = Field(default=60, ge=1)
    account_limit: int = Field(default=10, ge=1)
    account_window_seconds: int = Field(default=900, ge=1)

    @property
    def cookie_name(self) -> str:
        return "__Host-actiondesk_session" if self.cookie_secure else "actiondesk_session_local"

    def secret_key(self) -> bytes:
        try:
            key = bytes.fromhex(self.secret.get_secret_value() if self.secret else "")
        except ValueError:
            raise RuntimeError("Configure a random 32-byte hexadecimal auth secret") from None
        if len(key) != 32:
            raise RuntimeError("Configure a random 32-byte hexadecimal auth secret")
        return key

    def validate_runtime(self) -> None:
        self.secret_key()
        if not self.organization_slug or not self.allowed_origins:
            raise RuntimeError(
                "Configure the authentication organization and exact allowed origins"
            )
        if not self.touch_seconds < self.idle_seconds <= self.absolute_seconds:
            raise RuntimeError("Require touch interval < idle timeout <= absolute timeout")
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
            ):
                raise RuntimeError("Authentication origins must be exact HTTP(S) origins")
            if not self.cookie_secure and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise RuntimeError("Non-Secure authentication cookies require loopback origins")


@lru_cache
def get_auth_settings() -> AuthSettings:
    return AuthSettings()
