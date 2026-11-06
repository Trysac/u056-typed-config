"""Schema introspection shared by the loader and the documentation generators."""

from __future__ import annotations

import dataclasses
import enum
import types
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union, get_args, get_origin, get_type_hints

from .secret import Secret

# Sentinel meaning "no value"; ``None`` is a legitimate default.
NOTHING: Any = object()

MAX_SCHEMA_DEPTH = 8

_SCALARS: tuple[Any, ...] = (str, int, float, bool, Path, Secret)


@dataclass(frozen=True)
class Spec:
    """A resolved annotation: base type plus the list and optional flags."""

    base: Any
    is_list: bool
    optional: bool


@dataclass(frozen=True)
class Node:
    """One dataclass field of the schema; ``children`` is set for nested dataclasses."""

    name: str
    path: tuple[str, ...]
    spec: Spec
    field: dataclasses.Field[Any]
    children: tuple[Node, ...] | None


def is_dataclass_type(tp: Any) -> bool:
    """Return True when ``tp`` is a dataclass type (not an instance)."""
    return isinstance(tp, type) and dataclasses.is_dataclass(tp)


def _is_scalar(tp: Any) -> bool:
    if tp in _SCALARS:
        return True
    return isinstance(tp, type) and issubclass(tp, enum.Enum)


def _unsupported(location: str) -> TypeError:
    return TypeError(f"unsupported type for field '{location}'")


def resolve_spec(tp: Any, location: str) -> Spec:
    """Resolve an annotation into a ``Spec`` or raise ``TypeError`` naming the field."""
    optional = False
    origin = get_origin(tp)
    if origin is Union or origin is types.UnionType:
        args = get_args(tp)
        rest = [arg for arg in args if arg is not type(None)]
        if len(rest) != 1 or len(rest) == len(args):
            raise _unsupported(location)
        optional = True
        tp = rest[0]
    if get_origin(tp) is list:
        items = get_args(tp)
        if len(items) != 1 or not _is_scalar(items[0]):
            raise _unsupported(location)
        return Spec(items[0], True, optional)
    if _is_scalar(tp) or is_dataclass_type(tp):
        return Spec(tp, False, optional)
    raise _unsupported(location)


def build_nodes(schema: Any, path: tuple[str, ...] = (), depth: int = 0) -> tuple[Node, ...]:
    """Build the field tree of a dataclass schema.

    Raises:
        TypeError: if ``schema`` is not a dataclass, nests too deeply or uses an
            unsupported annotation (the message names the field).
    """
    if not is_dataclass_type(schema):
        raise TypeError("schema must be a dataclass type")
    if depth >= MAX_SCHEMA_DEPTH:
        raise TypeError("schema nesting is too deep")
    try:
        hints = get_type_hints(schema)
    except Exception:
        raise TypeError(f"cannot resolve type hints of {schema.__name__}") from None
    nodes: list[Node] = []
    for item in dataclasses.fields(schema):
        if not item.init:
            continue
        field_path = (*path, item.name)
        spec = resolve_spec(hints[item.name], ".".join(field_path))
        children: tuple[Node, ...] | None = None
        if is_dataclass_type(spec.base):
            children = build_nodes(spec.base, field_path, depth + 1)
        nodes.append(Node(item.name, field_path, spec, item, children))
    return tuple(nodes)


def type_name(spec: Spec) -> str:
    """Return a readable type name such as ``list[int]`` or ``str | None``."""
    name = str(spec.base.__name__)
    if spec.is_list:
        name = f"list[{name}]"
    if spec.optional:
        name = f"{name} | None"
    return name


def field_default(node: Node, parent: Any) -> Any:
    """Return the default of ``node`` or ``NOTHING`` when it is required.

    ``parent`` is the default instance of the enclosing group (or ``NOTHING``); when given,
    its attribute wins. An ``X | None`` field without a default defaults to ``None``.
    """
    if parent is not NOTHING:
        return getattr(parent, node.name)
    item = node.field
    if item.default is not dataclasses.MISSING:
        return item.default
    factory = item.default_factory
    if callable(factory):
        return factory()
    return None if node.spec.optional else NOTHING


def leaf_nodes(nodes: tuple[Node, ...]) -> Iterator[Node]:
    """Yield every non-group field in declaration order."""
    for node in nodes:
        if node.children is None:
            yield node
        else:
            yield from leaf_nodes(node.children)


def doc_leaves(nodes: tuple[Node, ...], parent: Any = NOTHING) -> Iterator[tuple[Node, Any]]:
    """Yield every leaf with its default (``NOTHING`` when required)."""
    for node in nodes:
        default = field_default(node, parent)
        if node.children is None:
            yield node, default
        else:
            group = NOTHING if default is NOTHING or default is None else default
            yield from doc_leaves(node.children, group)
