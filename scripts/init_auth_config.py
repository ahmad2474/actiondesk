"""Fill missing local .env authentication settings without printing or replacing secrets."""

import argparse
import secrets
from pathlib import Path


def initialize(path: Path) -> None:
    lines = path.read_text().splitlines()
    values = {
        "ACTIONDESK_AUTH_SECRET": secrets.token_hex(32),
        "ACTIONDESK_AUTH_ORGANIZATION_SLUG": "synthetic-demo",
        "ACTIONDESK_AUTH_COOKIE_SECURE": "false",
        "ACTIONDESK_AUTH_ALLOWED_ORIGINS": '["http://127.0.0.1:3000","http://127.0.0.1:8000"]',
    }
    positions = {
        line.split("=", 1)[0]: index
        for index, line in enumerate(lines)
        if "=" in line and not line.lstrip().startswith("#")
    }
    for key, value in values.items():
        if key in positions:
            index = positions[key]
            if not lines[index].split("=", 1)[1].strip():
                lines[index] = f"{key}={value}"
        else:
            lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize local auth configuration")
    parser.add_argument("--file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    initialize(arguments.file)
