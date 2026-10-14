import importlib.util
import os
import secrets

import pytest

from app.core.auth_config import get_auth_settings
from app.services.passwords import password_hasher, verify_password

available = importlib.util.find_spec("argon2") is not None
pytestmark = pytest.mark.skipif(
    not available and os.environ.get("CI") != "true",
    reason="BLOCKED: approved argon2-cffi dependency could not be installed",
)


def test_real_argon2id_roundtrip_and_profile() -> None:
    password = secrets.token_urlsafe(24)
    encoded = password_hasher().hash(password)
    assert encoded.startswith("$argon2id$")
    settings = get_auth_settings()
    assert (
        f"m={settings.argon_memory_kib},t={settings.argon_time_cost},p={settings.argon_parallelism}"
    ) in encoded
    assert verify_password(encoded, password)
    assert not verify_password(encoded, secrets.token_urlsafe(24))
    assert not password_hasher().check_needs_rehash(encoded)


def test_unknown_and_passwordless_use_real_dummy_verification() -> None:
    assert not verify_password(None, secrets.token_urlsafe(24))
    assert not verify_password("malformed-hash", secrets.token_urlsafe(24))
