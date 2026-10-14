import hashlib
import hmac
from collections.abc import Callable
from typing import Protocol, cast

from redis import Redis
from redis.exceptions import RedisError

from app.core.auth_config import get_auth_settings
from app.core.config import get_settings
from app.domain.errors import DomainError

# Atomic fixed-window counters; callers cannot race INCR against expiry assignment.
COUNTER_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return {count, redis.call('TTL', KEYS[1])}
"""


class LoginLimiter(Protocol):
    def check(self, address: str, email: str) -> None: ...


class RedisLoginLimiter:
    def check(self, address: str, email: str) -> None:
        settings = get_auth_settings()
        scope = settings.organization_slug
        limits = [
            ("ip", address, settings.ip_limit, settings.ip_window_seconds),
            (
                "account",
                f"{scope}:{email}",
                settings.account_limit,
                settings.account_window_seconds,
            ),
        ]
        try:
            with Redis.from_url(
                get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2
            ) as client:
                for kind, identifier, maximum, window in limits:
                    digest = hmac.new(
                        settings.secret_key(), f"{kind}:{identifier}".encode(), hashlib.sha256
                    ).hexdigest()
                    evaluate = cast(Callable[[str, int, str, int], list[int]], client.eval)
                    count, ttl = evaluate(COUNTER_SCRIPT, 1, f"actiondesk:login:{digest}", window)
                    if count > maximum:
                        raise DomainError(
                            429,
                            "Too Many Requests",
                            "Try login again later.",
                            headers={"Retry-After": str(max(1, ttl))},
                        )
        except RedisError:
            raise DomainError(
                503, "Service Unavailable", "Login is temporarily unavailable."
            ) from None


def login_limiter() -> LoginLimiter:
    return RedisLoginLimiter()
