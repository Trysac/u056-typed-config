"""Behavior tests for the public API of typed_config."""

from __future__ import annotations

import pytest

import typed_config


def test_normalize_trims_and_lowercases() -> None:
    assert typed_config.normalize("  Hello World ") == "hello world"


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_normalize_rejects_blank_input(value: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        typed_config.normalize(value)


def test_version_is_semver() -> None:
    parts = typed_config.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
