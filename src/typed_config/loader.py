"""Loading of typed configuration from environment variables, ``.env`` and JSON files."""

from __future__ import annotations

import logging
import math
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar, cast

from .errors import ConfigError, FieldError, FieldErrorCode, clip
from .files import SourceError, read_file
from .schema import NOTHING, Node, Spec, build_nodes, field_default, leaf_nodes, type_name
from .secret import Secret

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

T = TypeVar("T")

MAX_ERRORS = 100
_MAX_COLLECTED = 1000
_INT_RE = re.compile(r"[+-]?[0-9]+")
_FLOAT_RE = re.compile(r"[+-]?([0-9]+[.]?[0-9]*|[.][0-9]+)([eE][+-]?[0-9]+)?")
_BOOLS = {
    "true": True,
    "1": True,
    "yes": True,
    "on": True,
    "false": False,
    "0": False,
    "no": False,
    "off": False,
}
_FAIL: Any = object()


class _Invalid(Exception):
    """Internal signal: a raw value cannot be converted to the declared type."""


class _Errors:
    """Collects field errors with a hard cap so hostile input cannot grow memory."""

    def __init__(self) -> None:
        self.items: list[FieldError] = []
        self.overflow = False

    def add(self, path: str, code: FieldErrorCode, message: str) -> None:
        if len(self.items) >= _MAX_COLLECTED:
            self.overflow = True
            return
        self.items.append(FieldError(path, code, message))

    def extend(self, other: _Errors) -> None:
        for item in other.items:
            self.add(item.path, item.code, item.message)
        self.overflow = self.overflow or other.overflow

    def finalize(self) -> list[FieldError]:
        items = sorted(self.items, key=lambda error: error.path)
        if len(items) > MAX_ERRORS or self.overflow:
            items = items[:MAX_ERRORS]
            message = f"too many errors; showing the first {MAX_ERRORS}"
            items.append(FieldError("$", "too_large", message))
        return items


@dataclass(frozen=True)
class _Source:
    label: str
    kind: str
    data: Mapping[str, Any]

    def lookup(self, path: tuple[str, ...], env_name: str) -> Any:
        if self.kind != "json":
            return self.data.get(env_name, NOTHING)
        current: Any = self.data
        for part in path:
            if not isinstance(current, dict) or part not in current:
                return NOTHING
            current = current[part]
        return current


@dataclass(frozen=True)
class _Context:
    sources: tuple[_Source, ...]
    prefix: str


def _try_int(text: str) -> int | None:
    if not _INT_RE.fullmatch(text):
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _parse_float(text: str) -> float:
    if not _FLOAT_RE.fullmatch(text):
        raise _Invalid
    result = float(text)
    if not math.isfinite(result):
        raise _Invalid
    return result


def _scalar_from_text(base: Any, text: str) -> Any:
    if base is str:
        return text
    if base is Secret:
        return Secret(text)
    if base is bool:
        flag = _BOOLS.get(text.lower())
        if flag is None:
            raise _Invalid
        return flag
    if base is int:
        number = _try_int(text)
        if number is None:
            raise _Invalid
        return number
    if base is float:
        return _parse_float(text)
    if base is Path:
        if not text:
            raise _Invalid
        return Path(text)
    parsed = _try_int(text)
    for member in base:
        value = member.value
        if isinstance(value, str) and value == text:
            return member
        if type(value) is int and parsed is not None and value == parsed:
            return member
    raise _Invalid


def _scalar_from_json(base: Any, value: Any) -> Any:
    if base is bool and type(value) is bool:
        return value
    if base is int and type(value) is int:
        return value
    if base is float and type(value) in (int, float):
        try:
            result = float(value)
        except OverflowError:
            raise _Invalid from None
        if math.isfinite(result):
            return result
    if base is str and isinstance(value, str):
        return value
    if base is Secret and isinstance(value, str):
        return Secret(value)
    if base is Path and isinstance(value, str) and value:
        return Path(value)
    if isinstance(base, type) and issubclass(base, Enum):
        for member in base:
            if type(member.value) is type(value) and member.value == value:
                return member
    raise _Invalid


def _convert(spec: Spec, raw: Any, from_json: bool) -> Any:
    if from_json:
        if raw is None:
            if spec.optional:
                return None
            raise _Invalid
        if spec.is_list:
            if not isinstance(raw, list):
                raise _Invalid
            return [_scalar_from_json(spec.base, item) for item in raw]
        return _scalar_from_json(spec.base, raw)
    if not isinstance(raw, str):
        raise _Invalid
    text = raw.strip()
    if text == "" and spec.optional:
        return None
    if spec.is_list:
        if text == "":
            return []
        return [_scalar_from_text(spec.base, part.strip()) for part in text.split(",")]
    return _scalar_from_text(spec.base, text)


def _resolve_leaf(
    node: Node,
    context: _Context,
    errors: _Errors,
    parent: Any,
) -> tuple[Any, bool]:
    dotted = ".".join(node.path)
    env_name = context.prefix + "__".join(node.path).upper()
    for source in context.sources:
        raw = source.lookup(node.path, env_name)
        if raw is NOTHING:
            continue
        try:
            return _convert(node.spec, raw, source.kind == "json"), True
        except _Invalid:
            message = f"expected {type_name(node.spec)} (source: {source.label})"
            errors.add(dotted, "invalid_type", message)
            return _FAIL, True
    default = field_default(node, parent)
    if default is NOTHING:
        errors.add(dotted, "missing", f"required; set {env_name} or provide it in a file")
        return _FAIL, False
    return default, False


def _resolve_group(
    node: Node,
    children: tuple[Node, ...],
    context: _Context,
    errors: _Errors,
    parent: Any,
) -> tuple[Any, bool]:
    present = False
    for source in context.sources:
        if source.kind != "json":
            continue
        raw = source.lookup(node.path, "")
        if raw is NOTHING or (raw is None and node.spec.optional):
            continue
        if not isinstance(raw, dict):
            message = f"expected object (source: {source.label})"
            errors.add(".".join(node.path), "invalid_type", message)
            return _FAIL, True
        present = True
    default = field_default(node, parent)
    child_parent = NOTHING if default is NOTHING or default is None else default
    local = _Errors()
    instance, hit = _build(node.spec.base, children, context, local, child_parent)
    if hit or present:
        errors.extend(local)
        return instance, True
    if default is not NOTHING:
        return default, False
    errors.extend(local)
    return instance, False


def _build(
    cls: Any,
    nodes: tuple[Node, ...],
    context: _Context,
    errors: _Errors,
    parent: Any,
) -> tuple[Any, bool]:
    kwargs: dict[str, Any] = {}
    provided = False
    failed = False
    for node in nodes:
        if node.children is None:
            value, hit = _resolve_leaf(node, context, errors, parent)
        else:
            value, hit = _resolve_group(node, node.children, context, errors, parent)
        provided = provided or hit
        if value is _FAIL:
            failed = True
        else:
            kwargs[node.name] = value
    if failed:
        return _FAIL, provided
    return cls(**kwargs), provided


def _unknown_json(
    data: Mapping[str, Any],
    nodes: tuple[Node, ...],
    parent_path: tuple[str, ...],
    label: str,
    errors: _Errors,
) -> None:
    by_name = {node.name: node for node in nodes}
    for key, value in data.items():
        node = by_name.get(key)
        if node is None:
            path = clip(".".join((*parent_path, key)))
            errors.add(path, "unknown_key", f"unknown key (source: {label})")
        elif node.children is not None and isinstance(value, dict):
            _unknown_json(value, node.children, (*parent_path, key), label, errors)


def _check_unknown(
    source: _Source,
    nodes: tuple[Node, ...],
    prefix: str,
    known: set[str],
    errors: _Errors,
) -> None:
    if source.kind == "json":
        _unknown_json(source.data, nodes, (), source.label, errors)
        return
    for key in source.data:
        if key.startswith(prefix) and key not in known:
            errors.add(clip(key), "unknown_key", f"unknown key (source: {source.label})")


def _emit(
    on_event: Callable[[Mapping[str, str | int]], None] | None,
    source: str,
    keys: int,
) -> None:
    logger.debug("loaded configuration source: keys=%d", keys)
    if on_event is None:
        return
    payload: dict[str, str | int] = {"source": source, "keys": keys}
    try:
        on_event(payload)
    except Exception:
        logger.debug("on_event callback raised; ignoring")


def load(
    schema: type[T],
    *,
    env: Mapping[str, str] | None = None,
    files: Sequence[Path] = (),
    prefix: str = "",
    strict: bool = True,
    max_file_bytes: int = 1_048_576,
    on_event: Callable[[Mapping[str, str | int]], None] | None = None,
) -> T:
    """Load ``schema`` (a dataclass) from files and environment variables.

    Precedence is defaults, then ``files`` in order, then ``env``. Every problem is collected
    and reported at once in a single :class:`ConfigError`.

    Args:
        schema: Dataclass type describing the configuration.
        env: Mapping used as the environment; ``os.environ`` only when ``None``.
        files: ``.json`` or ``.env`` files, lowest precedence first.
        prefix: Prepended verbatim to every environment variable name.
        strict: Report unknown keys in files as ``unknown_key`` errors.
        max_file_bytes: Largest accepted file size in bytes.
        on_event: Optional callback receiving ``{"source": ..., "keys": ...}`` per source.

    Raises:
        ConfigError: if any value is missing, malformed or a file cannot be used.
        TypeError: if ``schema`` is not a dataclass or uses an unsupported annotation.
        ValueError: if ``max_file_bytes`` is not positive.
    """
    if max_file_bytes < 1:
        raise ValueError("max_file_bytes must be a positive integer")
    nodes = build_nodes(schema)
    env_map: Mapping[str, str] = os.environ if env is None else env
    known = {prefix + "__".join(node.path).upper() for node in leaf_nodes(nodes)}
    errors = _Errors()
    file_sources: list[_Source] = []
    for file in files:
        name = clip(Path(file).name)
        try:
            parsed = read_file(Path(file), max_file_bytes)
        except SourceError as exc:
            errors.add(name, exc.code, exc.message)
            continue
        source = _Source(name, parsed.kind, parsed.data)
        if strict:
            _check_unknown(source, nodes, prefix, known, errors)
        file_sources.append(source)
        _emit(on_event, name, len(parsed.data))
    _emit(on_event, "env", sum(1 for name in known if name in env_map))
    env_source = _Source("env", "env", env_map)
    context = _Context((env_source, *reversed(file_sources)), prefix)
    instance, _ = _build(schema, nodes, context, errors, NOTHING)
    if errors.items:
        raise ConfigError(errors.finalize())
    return cast(T, instance)
