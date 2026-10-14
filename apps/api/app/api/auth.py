from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.dependencies import authenticated_context, require_origin
from app.api.requests import problem_response
from app.core.auth_config import get_auth_settings
from app.db.session import get_engine
from app.domain.errors import DomainError
from app.schemas.auth import AuthRead, Login
from app.services import auth
from app.services.login_limits import LoginLimiter, login_limiter

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    responses={
        401: problem_response("Invalid or unavailable authentication"),
        403: problem_response("Origin or CSRF check failed"),
        422: problem_response("Invalid input"),
        503: problem_response("Authentication temporarily unavailable"),
    },
)


def login_request(request: Request) -> None:
    require_origin(request)
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise DomainError(415, "Unsupported Media Type", "Login requires application/json.")


@router.post(
    "/login",
    response_model=AuthRead,
    operation_id="login",
    dependencies=[Depends(login_request)],
    responses={
        429: problem_response("Login temporarily rate limited"),
        415: problem_response("Login requires JSON"),
    },
)
def login(
    credentials: Login,
    request: Request,
    response: Response,
    limiter: Annotated[LoginLimiter, Depends(login_limiter)],
) -> AuthRead:
    # Uvicorn proxy interpretation is disabled in Compose. Ignore forwarded headers here.
    limiter.check(request.client.host if request.client else "unknown", credentials.email)
    settings = get_auth_settings()
    token, result = auth.login(get_engine(), credentials, request.cookies.get(settings.cookie_name))
    response.set_cookie(
        settings.cookie_name,
        token,
        max_age=settings.absolute_seconds,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return result


@router.get("/me", response_model=AuthRead, operation_id="current_user")
def me(context: Annotated[auth.AuthContext, Depends(authenticated_context)]) -> AuthRead:
    return context.response


@router.post("/logout", status_code=204, operation_id="logout")
def logout(request: Request, response: Response) -> None:
    require_origin(request)
    settings = get_auth_settings()
    token = request.cookies.get(settings.cookie_name)
    try:
        authenticated_context(request)
    except DomainError as error:
        if error.status != 401:
            raise
        # No valid session remains to mutate; origin check still protects cookie clearing.
    auth.logout(get_engine(), token)
    response.delete_cookie(
        settings.cookie_name, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax"
    )
