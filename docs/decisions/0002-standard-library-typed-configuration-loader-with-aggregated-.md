# Standard-library typed configuration loader with aggregated, value-free errors

Status: accepted (generated, pending human review)

## Context

Services read os.environ in scattered places, fail late on a missing variable, print secrets in tracebacks and keep no list of variables. Pydantic-settings solves this but pulls Pydantic as a dependency. TOML and YAML are out of scope (tomllib needs Python 3.11).

## Decision

Load once into a user-defined dataclass using only the standard library. Resolve annotations with typing.get_type_hints into a small field tree shared by the loader and the doc generators. Convert text with strict regexes (int() and float() alone accept underscores and non-ASCII digits) and keep JSON types exact. Collect all problems into one ConfigError sorted by path and capped at 100, with messages that name the expected type and source but never the received value, raised outside any except block so no chained exception can show it. Bound every untrusted input: file size, iterative JSON depth check before json.loads, schema depth, and collected errors. Secret wraps strings with a masked repr and constant-time equality.

## Consequences

No runtime dependencies and one definition for loading and documentation. Only a fixed set of annotations is supported and anything else fails fast with TypeError. Validation is limited to type conversion; there are no custom validators. Strict .env unknown-key detection is prefix based, and a missing file is reported as an error rather than skipped.
