"""Documentation generators derived from the same schema used for loading."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .schema import NOTHING, build_nodes, doc_leaves, type_name
from .secret import Secret


@dataclass(frozen=True)
class FieldDoc:
    """Documentation of one environment variable.

    Attributes:
        env_name: Full variable name including the prefix.
        type_name: Readable type, for example ``list[int]`` or ``str | None``.
        default: Display form of the default, ``None`` when the field is required.
            Secret defaults are shown as ``***``.
        required: True when the field has no default.
        doc: Description taken from ``field(metadata={"doc": ...})``.
    """

    env_name: str
    type_name: str
    default: str | None
    required: bool
    doc: str


def _display(value: Any) -> str:
    if isinstance(value, Secret):
        return "***"
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, list | tuple):
        return ",".join(_display(item) for item in value)
    return str(value)


def _rows(schema: Any, prefix: str) -> list[tuple[FieldDoc, bool]]:
    rows: list[tuple[FieldDoc, bool]] = []
    for node, default in doc_leaves(build_nodes(schema)):
        entry = FieldDoc(
            env_name=prefix + "__".join(node.path).upper(),
            type_name=type_name(node.spec),
            default=None if default is NOTHING else _display(default),
            required=default is NOTHING,
            doc=str(node.field.metadata.get("doc", "")),
        )
        rows.append((entry, node.spec.base is Secret))
    return rows


def describe(schema: type, prefix: str = "") -> list[FieldDoc]:
    """Return one ``FieldDoc`` per environment variable of ``schema``.

    Raises:
        TypeError: if ``schema`` is not a dataclass or uses an unsupported annotation.
    """
    return [entry for entry, _ in _rows(schema, prefix)]


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(schema: type, prefix: str = "") -> str:
    """Render a Markdown table: Variable, Type, Default, Required, Description.

    Secret defaults are shown as ``***``.
    """
    lines = [
        "| Variable | Type | Default | Required | Description |",
        "|---|---|---|---|---|",
    ]
    for entry, _ in _rows(schema, prefix):
        if entry.default is None:
            default = "-"
        elif entry.default == "":
            default = ""
        else:
            default = f"`{_cell(entry.default)}`"
        cells = [
            f"`{_cell(entry.env_name)}`",
            f"`{_cell(entry.type_name)}`",
            default,
            "yes" if entry.required else "no",
            _cell(entry.doc),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _quote(value: str) -> str:
    needs_quotes = value != value.strip() or "#" in value or value[:1] in ("'", '"')
    if not needs_quotes:
        return value
    if '"' not in value:
        return f'"{value}"'
    return f"'{value}'"


def render_env_example(schema: type, prefix: str = "") -> str:
    """Render an example ``.env`` file; secret values are left blank."""
    blocks: list[str] = []
    for entry, is_secret in _rows(schema, prefix):
        lines = [f"# {line}" for line in entry.doc.strip().splitlines()]
        suffix = ", required" if entry.required else ""
        lines.append(f"# Type: {entry.type_name}{suffix}")
        value = "" if is_secret or entry.default is None else _quote(entry.default)
        lines.append(f"{entry.env_name}={value}")
        blocks.append("\n".join(lines))
    if not blocks:
        return ""
    return "\n\n".join(blocks) + "\n"
