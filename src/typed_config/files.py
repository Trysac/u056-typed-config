"""Reading and parsing of ``.json`` and ``.env`` configuration files."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .errors import FieldErrorCode, clip

MAX_JSON_DEPTH = 32

_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_EXPORT_RE = re.compile(r"export\s+")
_COMMENT_RE = re.compile(r"\s#")


class SourceError(Exception):
    """Internal: a file cannot be used; carries the field error code and message."""

    def __init__(self, code: FieldErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ParsedFile:
    """A successfully parsed configuration file."""

    name: str
    kind: Literal["json", "dotenv"]
    data: Mapping[str, Any]


def _kind_of(path: Path) -> Literal["json", "dotenv"]:
    lowered = path.name.lower()
    if lowered.endswith(".json"):
        return "json"
    if lowered.endswith(".env"):
        return "dotenv"
    raise SourceError("unsupported_file", "unsupported file type; use .json or .env")


def read_file(path: Path, max_bytes: int) -> ParsedFile:
    """Read and parse ``path``, reading at most ``max_bytes + 1`` bytes.

    Raises:
        SourceError: with a field error code when the file cannot be used.
    """
    path = Path(path)
    kind = _kind_of(path)
    try:
        with path.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
    except FileNotFoundError:
        raise SourceError("missing", "file not found") from None
    except OSError:
        raise SourceError("parse_error", "file could not be read") from None
    if len(raw) > max_bytes:
        raise SourceError("too_large", f"file exceeds {max_bytes} bytes")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SourceError("parse_error", "file is not valid UTF-8") from None
    data = parse_json(text) if kind == "json" else parse_dotenv(text)
    return ParsedFile(clip(path.name), kind, data)


def _depth_within_limit(text: str) -> bool:
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                return False
        elif char in "]}":
            depth = max(0, depth - 1)
    return True


def parse_json(text: str) -> dict[str, Any]:
    """Parse a JSON object after checking nesting depth iteratively."""
    if not _depth_within_limit(text):
        raise SourceError("too_deep", f"JSON nesting exceeds {MAX_JSON_DEPTH} levels")
    try:
        data = json.loads(text)
    except ValueError:
        raise SourceError("parse_error", "invalid JSON") from None
    if not isinstance(data, dict):
        raise SourceError("parse_error", "top-level JSON value must be an object")
    return data


def _parse_value(rest: str, number: int) -> str:
    lead = rest.lstrip()
    if lead[:1] in ("'", '"'):
        quote = lead[0]
        end = lead.find(quote, 1)
        if end == -1:
            raise SourceError("parse_error", f"line {number}: unterminated quoted value")
        tail = lead[end + 1 :].strip()
        if tail and not tail.startswith("#"):
            message = f"line {number}: unexpected text after quoted value"
            raise SourceError("parse_error", message)
        return lead[1:end]
    match = _COMMENT_RE.search(rest)
    value = rest[: match.start()] if match else rest
    return value.strip()


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines; no interpolation, duplicate keys keep the last value."""
    result: dict[str, str] = {}
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        prefix = _EXPORT_RE.match(stripped)
        if prefix:
            stripped = stripped[prefix.end() :]
        key, separator, rest = stripped.partition("=")
        if not separator:
            raise SourceError("parse_error", f"line {number}: expected KEY=VALUE")
        key = key.strip()
        if not _KEY_RE.fullmatch(key):
            raise SourceError("parse_error", f"line {number}: invalid variable name")
        result[key] = _parse_value(rest, number)
    return result
