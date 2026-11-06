"""Typed errors raised by the library."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

MAX_TEXT = 200

FieldErrorCode = Literal[
    "missing",
    "invalid_type",
    "unknown_key",
    "parse_error",
    "too_large",
    "too_deep",
    "unsupported_file",
]


def clip(text: str) -> str:
    """Return ``text`` truncated to ``MAX_TEXT`` characters."""
    return text[:MAX_TEXT]


@dataclass(frozen=True)
class FieldError:
    """One problem found while loading configuration.

    Attributes:
        path: Dotted field path (``db.host``), a file name, or ``$`` for the overflow marker.
        code: Machine-readable error code.
        message: Human-readable explanation; it never contains the offending value.
    """

    path: str
    code: FieldErrorCode
    message: str


class ConfigError(ValueError):
    """Raised by ``load`` when the configuration is invalid.

    Attributes:
        code: Always ``"invalid_config"``.
        errors: Every problem found, sorted by path and capped at 100 entries.
    """

    code = "invalid_config"

    def __init__(self, errors: Sequence[FieldError]) -> None:
        self.errors: list[FieldError] = list(errors)
        details = "; ".join(f"{e.path}: {e.code}: {e.message}" for e in self.errors)
        super().__init__(f"invalid configuration ({len(self.errors)} error(s)): {details}")
