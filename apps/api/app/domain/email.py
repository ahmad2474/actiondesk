import re


def canonical_email(email: str) -> str:
    """ASCII identifiers: trim outer ASCII spaces (PostgreSQL btrim) and lowercase."""
    value = email.strip(" ")
    if (
        not value.isascii()
        or len(value) > 254
        or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value)
    ):
        raise ValueError("Invalid email identifier")
    return value.lower()
