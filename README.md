# typed-config

[![PyPI version](https://img.shields.io/pypi/v/trysac-typed-config)](https://pypi.org/project/trysac-typed-config/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-typed-config)](LICENSE)
[![CI](https://github.com/Trysac/u056-typed-config/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u056-typed-config/actions/workflows/ci.yml)

Typed configuration from environment, .env and JSON files into frozen dataclasses, with aggregated errors, masked secrets and generated docs

## Problem

Describe in two or three sentences the concrete problem this utility solves, who hits it, and what
they do today without it. Replace this paragraph when the first real feature lands.

## Install

```sh
pip install trysac-typed-config
# or
uv add trysac-typed-config
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
import typed_config

# normalize() trims surrounding whitespace and lower-cases the text.
print(typed_config.normalize("  Hello World "))  # -> "hello world"

# Blank input is rejected explicitly instead of returning an empty string.
try:
    typed_config.normalize("   ")
except ValueError as exc:
    print(f"rejected: {exc}")
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
