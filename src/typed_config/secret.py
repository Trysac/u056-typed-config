"""A string wrapper that never reveals its value by accident."""

from __future__ import annotations

import hmac


class Secret:
    """Wrap a sensitive string so that ``repr``, ``str`` and logging show only ``***``.

    Use :meth:`reveal` to read the wrapped value deliberately. Equality uses a
    constant-time comparison.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("Secret value must be a string")
        self._value = value

    def reveal(self) -> str:
        """Return the wrapped value."""
        return self._value

    def __repr__(self) -> str:
        return "Secret('***')"

    def __str__(self) -> str:
        return "Secret('***')"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Secret):
            return NotImplemented
        mine = self._value.encode("utf-8", "surrogatepass")
        theirs = other._value.encode("utf-8", "surrogatepass")
        return hmac.compare_digest(mine, theirs)

    def __hash__(self) -> int:
        return hash(("typed_config.Secret", self._value))
