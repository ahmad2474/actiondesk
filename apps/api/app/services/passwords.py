from functools import lru_cache
from importlib import import_module
from secrets import token_urlsafe
from typing import Protocol, cast

from app.core.auth_config import get_auth_settings


class PasswordEngine(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, hash: str, password: str) -> bool: ...
    def check_needs_rehash(self, hash: str) -> bool: ...


@lru_cache
def password_hasher() -> PasswordEngine:
    settings = get_auth_settings()
    try:
        argon2 = import_module("argon2")
        low_level = import_module("argon2.low_level")
    except ImportError:
        raise RuntimeError("Install the approved argon2-cffi dependency with uv sync") from None
    return cast(
        PasswordEngine,
        argon2.PasswordHasher(
            memory_cost=settings.argon_memory_kib,
            time_cost=settings.argon_time_cost,
            parallelism=settings.argon_parallelism,
            type=low_level.Type.ID,
        ),
    )


@lru_cache
def dummy_hash() -> str:
    return password_hasher().hash(token_urlsafe(32))


def verify_password(encoded: str | None, password: str) -> bool:
    target = encoded or dummy_hash()
    exceptions = import_module("argon2.exceptions")
    try:
        valid = password_hasher().verify(target, password)
    except (exceptions.VerificationError, exceptions.InvalidHashError):
        return False
    return valid and encoded is not None
