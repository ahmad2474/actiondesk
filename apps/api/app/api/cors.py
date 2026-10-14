from starlette.middleware.cors import CORSMiddleware

from app.core.auth_config import get_auth_settings


class AuthCORSMiddleware(CORSMiddleware):
    def is_allowed_origin(self, origin: str) -> bool:
        # Runtime-only configuration keeps OpenAPI export independent of secrets/settings.
        return origin in get_auth_settings().allowed_origins
