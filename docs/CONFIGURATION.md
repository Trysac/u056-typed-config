# Configuration guide

`typed_config` loads configuration once into a frozen dataclass, reports every problem at
once, masks secrets and generates the documentation from the same definition.

## Defining a schema

A schema is a dataclass. Supported field types: `str`, `int`, `float`, `bool`, `pathlib.Path`,
`Enum` (matched by value), `Secret`, `list[T]` of those scalars, `X | None`, and nested
dataclasses. Any other annotation raises `TypeError` naming the field when `load`, `describe` or
a renderer is called. Describe a field with `field(metadata={"doc": "..."})`.

## Sources and precedence

Defaults, then `files` in the given order, then `env`. `env` defaults to `os.environ` only when
it is `None`.

- Environment variable names are `prefix + "__".join(field path).upper()`; the prefix is used
  verbatim, so field `db.host` with prefix `APP_` reads `APP_DB__HOST`.
- `.json` files are objects whose keys are field names (nested objects for nested dataclasses).
- `.env` files use `KEY=VALUE` lines, `#` comments, an optional `export` prefix and no
  interpolation. An unquoted value ends at ` #`; single or double quotes keep `#`; duplicate keys
  keep the last; CRLF line endings and a UTF-8 BOM are accepted.
- Any other suffix is reported as `unsupported_file`; a file that does not exist is `missing`.

## Conversion rules

Text values are trimmed first. `int` must match `^[+-]?[0-9]+$` (no `1_000`, no non-ASCII
digits); `float` must match a plain decimal form and be finite; `bool` accepts
`true/false/1/0/yes/no/on/off` in any case. JSON values keep their decoded type: an `int` field
takes a JSON integer only, `float` takes an integer or a float, `bool` only `true` or `false`.
Lists are comma-separated in text sources and JSON arrays in JSON. An empty string for
`X | None` is `None`; an `X | None` field without a default is `None` when unset. An optional
nested group that is not mentioned anywhere stays at its default (or `None`).

## Errors

`ConfigError` (a `ValueError`, `code == "invalid_config"`) carries `errors`, a list of
`FieldError(path, code, message)` sorted by path and capped at 100 entries (a final entry with
path `$` and code `too_large` marks the cap). Codes: `missing`, `invalid_type`, `unknown_key`,
`parse_error`, `too_large`, `too_deep`, `unsupported_file`. Messages name the expected type and the
source (`env` or the file name) but never the received value.

With `strict=True` unknown JSON keys are errors. In `.env` files a key is unknown when it starts
with the prefix (or any key when the prefix is empty) and is not a known variable.

## Generated documentation

`describe(schema, prefix)` returns `FieldDoc` records, `render_markdown` a table and
`render_env_example` an example `.env`. Secret defaults are shown as `***` in the table and
left blank in the example file. Required means the field has no default; inside an optional
group the variable is needed only when the group is used.

## Threat model

- Secrets: `Secret` masks `repr`/`str`, compares in constant time and is never printed by the
  error type; error messages never include received values, and conversion failures are not
  chained to the underlying exception.
- Hostile files: size is capped (`max_file_bytes`, default 1 MiB, read as at most
  `max_file_bytes + 1` bytes), JSON nesting is limited to 32 levels with an iterative check before
  parsing, schema nesting to 8 levels, and error collection is bounded.
- Out of scope: TOML, YAML, hot reload, remote stores, command-line parsing. A `Secret` is not
  encrypted memory: `reveal()` returns the plain string.
