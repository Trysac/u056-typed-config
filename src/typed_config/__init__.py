"""Typed configuration from environment variables, .env and JSON files into dataclasses."""

from __future__ import annotations

from .docs import FieldDoc, describe, render_env_example, render_markdown
from .errors import ConfigError, FieldError
from .loader import load
from .secret import Secret

__all__ = [
    "ConfigError",
    "FieldDoc",
    "FieldError",
    "Secret",
    "__version__",
    "describe",
    "load",
    "render_env_example",
    "render_markdown",
]

__version__ = "0.1.0"
