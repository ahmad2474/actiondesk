"""Explicit interactive local credential initialization; no seed passwords or reset flow."""

import argparse
import getpass
import sys
from time import perf_counter

from sqlalchemy.engine import make_url

from app.core.auth_config import get_auth_settings
from app.core.config import get_settings
from app.db.session import get_engine
from app.services.auth import set_initial_password
from app.services.passwords import password_hasher


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize an existing local synthetic account")
    parser.add_argument("--email", help="Existing account in the configured local organization")
    parser.add_argument(
        "--benchmark", action="store_true", help="Measure configured Argon2 profile"
    )
    args = parser.parse_args()
    if (
        get_settings().environment != "local"
        or not sys.stdin.isatty()
        or make_url(get_settings().database_url).host
        not in {"postgres", "localhost", "127.0.0.1", "::1"}
    ):
        raise SystemExit("Account initialization requires an interactive local terminal")
    get_auth_settings().validate_runtime()
    if args.benchmark:
        import secrets

        start = perf_counter()
        password_hasher().hash(secrets.token_urlsafe(32))
        print(f"Configured Argon2 hash took {perf_counter() - start:.3f}s")
        return
    if not args.email:
        raise SystemExit("Select an existing account with --email")
    password = getpass.getpass("New local password: ")
    confirmation = getpass.getpass("Confirm local password: ")
    if password != confirmation or not 12 <= len(password) <= 1024:
        raise SystemExit("Passwords must match and contain 12–1024 characters")
    try:
        set_initial_password(get_engine(), args.email, password)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    print("Selected local account initialized. Normal seeds remain unchanged.")


if __name__ == "__main__":
    main()
