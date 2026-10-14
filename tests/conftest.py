import secrets

import pytest

from app.core.auth_config import get_auth_settings
from app.services.passwords import dummy_hash, password_hasher


@pytest.fixture(autouse=True)
def auth_test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit ephemeral test config, never a runtime authentication bypass."""
    monkeypatch.setenv("ACTIONDESK_AUTH_SECRET", secrets.token_hex(32))
    monkeypatch.setenv("ACTIONDESK_AUTH_ORGANIZATION_SLUG", "synthetic-demo")
    monkeypatch.setenv("ACTIONDESK_AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("ACTIONDESK_AUTH_ALLOWED_ORIGINS", '["http://127.0.0.1:8000"]')
    get_auth_settings.cache_clear()
    password_hasher.cache_clear()
    dummy_hash.cache_clear()


@pytest.fixture(autouse=True)
def isolated_startup_warmup(monkeypatch: pytest.MonkeyPatch) -> None:
    # Runtime calls the real Argon2 warmup. Unit/API tests isolate startup cost;
    # cryptographic verification and startup validation are tested independently.
    monkeypatch.setattr("app.main.dummy_hash", lambda: "test-only-warmup")
