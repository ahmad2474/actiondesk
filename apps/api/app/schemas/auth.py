from datetime import datetime

from pydantic import Field, SecretStr, field_validator

from app.domain.email import canonical_email
from app.schemas.core import InputSchema, UserRead


class Login(InputSchema):
    email: str = Field(max_length=254)
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return canonical_email(value)


class AuthRead(InputSchema):
    user: UserRead
    session_expires_at: datetime
    csrf_token: str
