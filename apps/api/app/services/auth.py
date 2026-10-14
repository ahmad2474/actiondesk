import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.auth_config import get_auth_settings
from app.db.models import AuthSession, Organization, RoleAssignment, User
from app.domain.email import canonical_email
from app.domain.errors import DomainError
from app.domain.identity import Principal
from app.domain.types import UserStatus
from app.schemas.auth import AuthRead, Login
from app.schemas.core import UserRead
from app.services.passwords import password_hasher, verify_password


def utc_now() -> datetime:
    return datetime.now(UTC)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def valid_token_shape(token: str | None) -> bool:
    return token is not None and re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is not None


def csrf_token(token: str) -> str:
    return hmac.new(
        get_auth_settings().secret_key(), b"csrf:" + token.encode("ascii"), hashlib.sha256
    ).hexdigest()


def unauthorized() -> DomainError:
    return DomainError(401, "Unauthorized", "Valid authentication is required.")


@dataclass(frozen=True)
class AuthContext:
    principal: Principal
    response: AuthRead


def user_read(session: Session, user: User, now: datetime) -> UserRead:
    roles = session.scalars(
        select(RoleAssignment.role).where(
            RoleAssignment.organization_id == user.organization_id,
            RoleAssignment.user_id == user.id,
            RoleAssignment.revoked_at.is_(None),
            RoleAssignment.granted_at <= now,
        )
    )
    return UserRead(
        id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        name=user.name,
        department_id=user.department_id,
        status=UserStatus(user.status),
        created_at=user.created_at,
        roles=frozenset(roles),
    )


def login(engine: Engine, credentials: Login, previous_token: str | None) -> tuple[str, AuthRead]:
    settings = get_auth_settings()
    now = utc_now()
    try:
        # Read without holding a transaction/row lock during expensive password verification.
        with Session(engine) as session:
            user = session.scalar(
                select(User)
                .join(Organization)
                .where(
                    Organization.slug == settings.organization_slug,
                    func.lower(func.trim(User.email)) == credentials.email,
                )
            )
            encoded = user.password_hash if user else None
            user_id = user.id if user else None
        verified = verify_password(encoded, credentials.password.get_secret_value())
        if not verified or user_id is None:
            raise unauthorized()
        token = secrets.token_urlsafe(32)
        with Session(engine) as session, session.begin():
            # Recheck under a user lock: disable/credential changes cannot race session issuance.
            user = session.scalar(
                select(User)
                .join(Organization)
                .where(
                    Organization.slug == settings.organization_slug,
                    User.id == user_id,
                    User.status == UserStatus.ACTIVE,
                )
                .with_for_update(of=User)
            )
            if user is None or user.password_hash != encoded:
                raise unauthorized()
            assert encoded is not None
            if password_hasher().check_needs_rehash(encoded):
                user.password_hash = password_hasher().hash(credentials.password.get_secret_value())
            if valid_token_shape(previous_token):
                assert previous_token is not None
                session.execute(
                    update(AuthSession)
                    .where(
                        AuthSession.token_hash == token_digest(previous_token),
                        AuthSession.organization_id == user.organization_id,
                        AuthSession.revoked_at.is_(None),
                    )
                    .values(revoked_at=now)
                )
            expires = now + timedelta(seconds=settings.absolute_seconds)
            session.add(
                AuthSession(
                    token_hash=token_digest(token),
                    organization_id=user.organization_id,
                    user_id=user.id,
                    created_at=now,
                    last_seen_at=now,
                    expires_at=expires,
                )
            )
            result = AuthRead(
                user=user_read(session, user, now),
                session_expires_at=expires,
                csrf_token=csrf_token(token),
            )
        return token, result
    except SQLAlchemyError:
        raise DomainError(
            503, "Service Unavailable", "Authentication is temporarily unavailable."
        ) from None


def authenticate(engine: Engine, token: str | None) -> AuthContext:
    if not valid_token_shape(token):
        raise unauthorized()
    assert token is not None
    settings = get_auth_settings()
    now = utc_now()
    cutoff = now - timedelta(seconds=settings.idle_seconds)
    try:
        with Session(engine) as session, session.begin():
            row = session.execute(
                select(AuthSession, User)
                .join(
                    User,
                    (User.id == AuthSession.user_id)
                    & (User.organization_id == AuthSession.organization_id),
                )
                .join(Organization, Organization.id == AuthSession.organization_id)
                .where(
                    AuthSession.token_hash == token_digest(token),
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > now,
                    AuthSession.last_seen_at > cutoff,
                    User.status == UserStatus.ACTIVE,
                    Organization.slug == settings.organization_slug,
                )
            ).first()
            if row is None:
                raise unauthorized()
            record, user = row
            seen = record.last_seen_at
            if seen.tzinfo is None:  # SQLite unit adapter; PostgreSQL values are timezone-aware.
                seen = seen.replace(tzinfo=UTC)
            if seen < now - timedelta(seconds=settings.touch_seconds):
                # Recheck validity in the update; never revive a revoked session.
                touched = session.execute(
                    update(AuthSession)
                    .where(
                        AuthSession.id == record.id,
                        AuthSession.revoked_at.is_(None),
                        AuthSession.expires_at > now,
                        AuthSession.last_seen_at > cutoff,
                        AuthSession.last_seen_at < now - timedelta(seconds=settings.touch_seconds),
                    )
                    .values(last_seen_at=now)
                    .returning(AuthSession.id)
                    .execution_options(synchronize_session=False)
                ).scalar_one_or_none()
                if touched is None:
                    # Another request may have touched it; distinguish that from revocation.
                    live = session.scalar(
                        select(AuthSession.id).where(
                            AuthSession.id == record.id,
                            AuthSession.revoked_at.is_(None),
                            AuthSession.expires_at > now,
                            AuthSession.last_seen_at > cutoff,
                        )
                    )
                    if live is None:
                        raise unauthorized()
            return AuthContext(
                Principal(user.organization_id, user.id),
                AuthRead(
                    user=user_read(session, user, now),
                    session_expires_at=record.expires_at,
                    csrf_token=csrf_token(token),
                ),
            )
    except SQLAlchemyError:
        raise DomainError(
            503, "Service Unavailable", "Authentication is temporarily unavailable."
        ) from None


def logout(engine: Engine, token: str | None) -> None:
    if not valid_token_shape(token):
        return
    assert token is not None
    try:
        with Session(engine) as session, session.begin():
            session.execute(
                update(AuthSession)
                .where(
                    AuthSession.token_hash == token_digest(token),
                    AuthSession.organization_id.in_(
                        select(Organization.id).where(
                            Organization.slug == get_auth_settings().organization_slug
                        )
                    ),
                    AuthSession.revoked_at.is_(None),
                )
                .values(revoked_at=utc_now())
            )
    except SQLAlchemyError:
        raise DomainError(
            503, "Service Unavailable", "Logout is temporarily unavailable."
        ) from None


def set_initial_password(engine: Engine, email: str, password: str) -> None:
    """Explicit local CLI only; never called by normal bootstrap or request endpoints."""
    encoded = password_hasher().hash(password)
    with Session(engine) as session, session.begin():
        user = session.scalar(
            select(User)
            .join(Organization)
            .where(
                Organization.slug == get_auth_settings().organization_slug,
                func.lower(func.trim(User.email)) == canonical_email(email),
            )
            .with_for_update(of=User)
        )
        if user is None or user.password_hash is not None:
            raise ValueError("Select an existing account without initialized credentials")
        replace_password(session, user, encoded)
        user.status = UserStatus.ACTIVE


def replace_password(session: Session, user: User, encoded: str) -> None:
    """Credential changes revoke all devices in the caller's transaction. No reset HTTP flow."""
    user.password_hash = encoded
    session.execute(
        update(AuthSession)
        .where(
            AuthSession.organization_id == user.organization_id,
            AuthSession.user_id == user.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=utc_now())
    )
