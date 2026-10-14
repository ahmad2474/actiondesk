from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Principal:
    """Trusted server identity; never construct from client IDs or headers."""

    organization_id: UUID
    user_id: UUID
