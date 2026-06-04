from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass
class BlockingReasonDTO:
    id: UUID
    code: str
    title: str
    description: str | None
    hard_block: bool
    is_active: bool


class ReasonCodeExistsError(Exception):
    """A reason with the same code already exists."""


class ReasonNotFoundError(Exception):
    """No reason with the given id."""
