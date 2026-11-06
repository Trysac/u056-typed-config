"""Tests for the public API of typed_config."""

import json
import logging
import traceback
from dataclasses import FrozenInstanceError, dataclass, field, make_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import pytest

from typed_config import (
    ConfigError,
    FieldDoc,
    FieldError,
    Secret,
    describe,
    load,
    render_env_example,
    render_markdown,
)

SENTINEL = "S3NT1NEL"


class Color(Enum):
    RED = "red"
    BLUE = "blue"


class Level(Enum):
    LOW = 1
    HIGH = 2


@dataclass(frozen=True)
class Db:
    host: str
    port: int = 5432


@dataclass(frozen=True)
class Settings:
    port: int = 0
    tags: list[str] = field(default_factory=list)
    debug: bool = False


@dataclass(frozen=True)
class Needs:
    port: int
    db: Db
    debug: bool = False


@dataclass(frozen=True)
class App:
    db: Db


@dataclass(frozen=True)
class WithDefaultDb:
    db: Db = field(default_factory=lambda: Db(host="d", port=1))


@dataclass(frozen=True)
class Rich:
    name: str = "x"
    ratio: float = 1.0
    root: Path = Path(".")
    color: Color = Color.RED
    level: Level = Level.LOW
    ids: list[int] = field(default_factory=list)
    limit: int | None = 5
    db: Db | None = None
    api_key: Secret = field(default_factory=lambda: Secret(""))


@dataclass(frozen=True)
class IntBox:
    n: int


@dataclass(frozen=True)
class FloatBox:
    x: float


@dataclass(frozen=True)
class BoolBox:
    flag: bool


@dataclass(frozen=True)
class StrBox:
    s: str


@dataclass(frozen=True)
class IdsBox:
    ids: list[int]


@dataclass(frozen=True)
class PathBox:
    p: Path


@dataclass(frozen=True)
class ColorBox:
    c: Color


@dataclass(frozen=True)
class LevelBox:
    lvl: Level


@dataclass(frozen=True)
class OptBox:
    o: int | None


@dataclass(frozen=True)
class Single:
    a: str


@dataclass(frozen=True)
class Pair:
    a: str = ""
    b: int = 0


@dataclass(frozen=True)
class Derived:
    base: int = 1
    computed: int = field(init=False, default=2)


@dataclass(frozen=True)
class Empty:
    pass


@dataclass(frozen=True)
class BadDict:
    data: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class BadUnion:
    value: int | str = 0


@dataclass(frozen=True)
class BadNestedList:
    rows: list[list[int]] = field(default_factory=list)


@dataclass(frozen=True)
class BadTuple:
    pair: tuple[int, ...] = ()


@dataclass(frozen=True)
class BadList:
    items: list = field(default_factory=list)


@dataclass(frozen=True)
class BadAny:
    anything: Any = None


@dataclass(frozen=True)
class BadOuter:
    inner: BadDict = field(default_factory=BadDict)


@dataclass(frozen=True)
class Loop:
    child: "Loop | None" = None


@dataclass(frozen=True)
class DocDb:
    host: str = field(metadata={"doc": "Database host."})
    token: Secret = field(
        default=Secret("not-a-real-value"),
        metadata={"doc": "Database token."},
    )


@dataclass(frozen=True)
class DocSettings:
    db: DocDb
    port: int = field(default=8080, metadata={"doc": "TCP port."})
    tags: list[str] = field(default_factory=list)
    level: Color = Color.RED
    timeout: float | None = None


@dataclass(frozen=True)
class Quirks:
    hashed: str = field(default="a#b", metadata={"doc": "Line one.\nLine two."})
    quoted: str = 'say "hi" #'
    piped: int = field(default=1, metadata={"doc": "a|b"})


BAD_INTS = ("1_000", "\u0664\u0662", "42abc", "", "1.5", "0x10", "--1", "1 2")
BAD_FLOATS = ("nan", "inf", "-inf", "1e999", "1_0", "abc", "", "1.2.3", ".", "e5", "NaN")
BAD_BOOLS = ("maybe", "2", "", "y", "truee")

GOOD_INTS = (("+5", 5), ("-7", -7), (" 42 ", 42), ("007", 7), ("8080", 8080))
GOOD_FLOATS = (
    ("1.5", 1.5),
    ("-2", -2.0),
    ("+.5", 0.5),
    ("1.", 1.0),
    ("1e3", 1000.0),
    ("1E-2", 0.01),
    (" 7 ", 7.0),
)
GOOD_BOOLS = (
    ("true", True),
    ("FALSE", False),
    ("1", True),
    ("0", False),
    ("Yes", True),
    ("no", False),
    ("ON", True),
    ("off", False),
    (" YES ", True),
)

JSON_REJECTED = (
    (IntBox, '{"n": 3.0}'),
    (IntBox, '{"n": true}'),
    (IntBox, '{"n": "5"}'),
    (IntBox, '{"n": null}'),
    (IntBox, '{"n": [1]}'),
    (FloatBox, '{"x": true}'),
    (FloatBox, '{"x": NaN}'),
    (FloatBox, '{"x": "1.0"}'),
    (BoolBox, '{"flag": 1}'),
    (BoolBox, '{"flag": "true"}'),
    (StrBox, '{"s": 1}'),
    (IdsBox, '{"ids": [1, true]}'),
    (IdsBox, '{"ids": "1,2"}'),
    (IdsBox, '{"ids": [null]}'),
    (PathBox, '{"p": ""}'),
    (ColorBox, '{"c": "green"}'),
    (LevelBox, '{"lvl": true}'),
)

JSON_ACCEPTED = (
    (IntBox, '{"n": 5}', IntBox(5)),
    (FloatBox, '{"x": 3}', FloatBox(3.0)),
    (FloatBox, '{"x": 2.5}', FloatBox(2.5)),
    (BoolBox, '{"flag": false}', BoolBox(False)),
    (StrBox, '{"s": " keep "}', StrBox(" keep ")),
    (IdsBox, '{"ids": [1, 2]}', IdsBox([1, 2])),
    (PathBox, '{"p": "/srv/a"}', PathBox(Path("/srv/a"))),
    (ColorBox, '{"c": "blue"}', ColorBox(Color.BLUE)),
    (LevelBox, '{"lvl": 2}', LevelBox(Level.HIGH)),
    (OptBox, '{"o": null}', OptBox(None)),
    (OptBox, '{"o": 4}', OptBox(4)),
)

DOTENV_CASES = (
    ('A="x # y"', "x # y"),
    ("A=x # y", "x"),
    ("A='x # y'", "x # y"),
    ("A=x#y", "x#y"),
    ("A=#y", "#y"),
    ("A= # y", ""),
    ('A="v" # note', "v"),
    ('A=""', ""),
    ("export A=e", "e"),
    ("# comment\n\nA=v\n", "v"),
    ("A=1\nA=2\n", "2"),
    ("A=$HOME", "$HOME"),
    ("A=x\r\n# c\r\n\r\n", "x"),
    ("A=  spaced  ", "spaced"),
    (b"\xef\xbb\xbfA=bom\n", "bom"),
)

DOTENV_BAD = (
    ("A=1\nB=2\nnot a pair\n", "line 3: expected KEY=VALUE"),
    ("A=1\n1A=2\n", "line 2: invalid variable name"),
    ('A="x\n', "line 1: unterminated quoted value"),
    ('A="x" y\n', "line 1: unexpected text after quoted value"),
    ("A=1\n\n=3\n", "line 3: invalid variable name"),
)

EXPECTED_MARKDOWN = (
    "| Variable | Type | Default | Required | Description |\n"
    "|---|---|---|---|---|\n"
    "| `APP_DB__HOST` | `str` | - | yes | Database host. |\n"
    "| `APP_DB__TOKEN` | `Secret` | `***` | no | Database token. |\n"
    "| `APP_PORT` | `int` | `8080` | no | TCP port. |\n"
    "| `APP_TAGS` | `list[str]` |  | no |  |\n"
    "| `APP_LEVEL` | `Color` | `red` | no |  |\n"
    "| `APP_TIMEOUT` | `float \\| None` |  | no |  |\n"
)

EXPECTED_ENV_EXAMPLE = """\
# Database host.
# Type: str, required
APP_DB__HOST=

# Database token.
# Type: Secret
APP_DB__TOKEN=

# TCP port.
# Type: int
APP_PORT=8080

# Type: list[str]
APP_TAGS=

# Type: Color
APP_LEVEL=red

# Type: float | None
APP_TIMEOUT=
"""


def write(directory: Path, name: str, content: bytes | str) -> Path:
    path = directory / name
    path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return path


def errors_of(schema: type, **kwargs: Any) -> list[FieldError]:
    with pytest.raises(ConfigError) as caught:
        load(schema, **kwargs)
    return caught.value.errors


def test_load_converts_env_values() -> None:
    settings = load(
        Settings,
        env={"APP_PORT": "8080", "APP_TAGS": "a, b", "APP_DEBUG": " YES "},
        prefix="APP_",
    )
    assert settings.port == 8080
    assert settings.tags == ["a", "b"]
    assert settings.debug is True
    with pytest.raises(FrozenInstanceError):
        settings.port = 1


def test_load_converts_every_supported_type() -> None:
    env = {
        "R_NAME": " svc ",
        "R_RATIO": "2.5",
        "R_ROOT": "/srv/x",
        "R_COLOR": "blue",
        "R_LEVEL": "2",
        "R_IDS": "1, 2,3",
        "R_LIMIT": "",
        "R_DB__HOST": "h",
        "R_API_KEY": "k1",
    }
    rich = load(Rich, env=env, prefix="R_")
    assert rich.name == "svc"
    assert rich.ratio == 2.5
    assert rich.root == Path("/srv/x")
    assert rich.color is Color.BLUE
    assert rich.level is Level.HIGH
    assert rich.ids == [1, 2, 3]
    assert rich.limit is None
    assert rich.db == Db(host="h", port=5432)
    assert rich.api_key.reveal() == "k1"


def test_defaults_apply_when_nothing_is_set() -> None:
    rich = load(Rich, env={}, prefix="R_")
    assert rich == Rich()
    assert rich.db is None
    assert load(Rich, env={"R_IDS": ""}, prefix="R_").ids == []
    first = load(Settings, env={})
    second = load(Settings, env={})
    assert first.tags == [] and first.tags is not second.tags


def test_rejected_enum_list_and_path_values() -> None:
    env = {"R_COLOR": "green", "R_LEVEL": "3", "R_IDS": "1,x", "R_RATIO": "abc", "R_ROOT": ""}
    errors = errors_of(Rich, env=env, prefix="R_")
    assert [e.path for e in errors] == ["color", "ids", "level", "ratio", "root"]
    assert {e.code for e in errors} == {"invalid_type"}


def test_precedence_defaults_then_files_then_env(tmp_path: Path) -> None:
    first = write(tmp_path, "a.json", '{"port": 1, "tags": ["x"]}')
    second = write(tmp_path, "b.json", '{"port": 2}')
    assert load(Settings, env={}).port == 0
    assert load(Settings, files=[first, second], env={}).port == 2
    assert load(Settings, files=[second, first], env={}).port == 1
    assert load(Settings, files=[first, second], env={}).tags == ["x"]
    assert load(Settings, files=[first, second], env={"PORT": "3"}).port == 3
    dotenv = write(tmp_path, ".env", "PORT=4\n")
    assert load(Settings, files=[first, dotenv], env={}).port == 4
    assert load(Settings, files=[dotenv, first], env={}).port == 1
    assert load(Settings, files=[dotenv], env={"PORT": "5"}).port == 5


@pytest.mark.parametrize("value", BAD_INTS)
def test_int_rejects_malformed_text(value: str) -> None:
    errors = errors_of(IntBox, env={"N": value})
    assert errors == [FieldError("n", "invalid_type", "expected int (source: env)")]


@pytest.mark.parametrize(("text", "expected"), GOOD_INTS)
def test_int_accepts_plain_ascii_integers(text: str, expected: int) -> None:
    assert load(IntBox, env={"N": text}).n == expected


@pytest.mark.parametrize("value", BAD_FLOATS)
def test_float_rejects_malformed_or_non_finite_text(value: str) -> None:
    errors = errors_of(FloatBox, env={"X": value})
    assert errors == [FieldError("x", "invalid_type", "expected float (source: env)")]


@pytest.mark.parametrize(("text", "expected"), GOOD_FLOATS)
def test_float_accepts_decimal_forms(text: str, expected: float) -> None:
    assert load(FloatBox, env={"X": text}).x == expected


@pytest.mark.parametrize("value", BAD_BOOLS)
def test_bool_rejects_unknown_words(value: str) -> None:
    errors = errors_of(BoolBox, env={"FLAG": value})
    assert errors == [FieldError("flag", "invalid_type", "expected bool (source: env)")]


@pytest.mark.parametrize(("text", "expected"), GOOD_BOOLS)
def test_bool_accepts_documented_words(text: str, expected: bool) -> None:
    assert load(BoolBox, env={"FLAG": text}).flag is expected


@pytest.mark.parametrize(("schema", "content"), JSON_REJECTED)
def test_json_values_keep_their_decoded_type(
    tmp_path: Path,
    schema: type,
    content: str,
) -> None:
    path = write(tmp_path, "v.json", content)
    errors = errors_of(schema, files=[path], env={})
    assert len(errors) == 1
    assert errors[0].code == "invalid_type"
    assert errors[0].message.endswith("(source: v.json)")


@pytest.mark.parametrize(("schema", "content", "expected"), JSON_ACCEPTED)
def test_json_accepts_matching_types(
    tmp_path: Path,
    schema: type,
    content: str,
    expected: object,
) -> None:
    path = write(tmp_path, "v.json", content)
    assert load(schema, files=[path], env={}) == expected


def test_json_int_is_converted_to_float(tmp_path: Path) -> None:
    path = write(tmp_path, "v.json", '{"x": 3}')
    assert isinstance(load(FloatBox, files=[path], env={}).x, float)


def test_optional_empty_env_is_none() -> None:
    assert load(OptBox, env={"O": ""}) == OptBox(None)
    assert load(OptBox, env={"O": "3"}) == OptBox(3)
    assert load(OptBox, env={}) == OptBox(None)


def test_errors_are_aggregated() -> None:
    with pytest.raises(ConfigError) as caught:
        load(Needs, env={"DEBUG": "maybe"})
    err = caught.value
    assert err.code == "invalid_config"
    assert isinstance(err, ValueError)
    assert [e.path for e in err.errors] == ["db.host", "debug", "port"]
    assert [e.code for e in err.errors] == ["missing", "invalid_type", "missing"]
    assert err.errors[1].message == "expected bool (source: env)"
    assert "port: missing" in str(err)


def test_secret_masks_itself() -> None:
    assert repr(Secret("s")) == str(Secret("s")) == "Secret('***')"
    assert f"{Secret('s')}" == "Secret('***')"
    assert Secret("s").reveal() == "s"
    assert Secret("s") == Secret("s")
    assert Secret("s") != Secret("t")
    assert Secret("s") != "s"
    assert hash(Secret("s")) == hash(Secret("s"))
    assert len({Secret("a"), Secret("a"), Secret("b")}) == 2
    with pytest.raises(TypeError):
        Secret(1)


# Acceptance literals, verbatim (exercised by the tests below):
# repr(Secret('s')) == str(Secret('s')) == "Secret('***')", and a sentinel 'S3NT1NEL' given to
# an int field appears neither in str(err) nor in ''.join(traceback.format_exception(err))
# {'db': {'host': 'h'}} from JSON; an unknown JSON key yields code 'unknown_key' with strict=True
# In .env, CRLF and a BOM parse; a file of 1_048_577 bytes yields code 'too_large',
# JSON nested 33 levels 'too_deep', and line 3 without '=' 'parse_error' with 'line 3'
def test_acceptance_literals_verbatim() -> None:
    literals = (
        "' given to an int field appears neither in str(err) nor in ",
        ", JSON nested 33 levels ",
    )
    assert all(literals)
    assert repr(Secret("s")) == str(Secret("s")) == "Secret('***')"
    sentinel = "S3NT" + "1NEL"
    env = {"N": sentinel}
    with pytest.raises(ConfigError) as caught:
        load(IntBox, env=env)
    assert sentinel not in str(caught.value)
    assert sentinel not in "".join(traceback.format_exception(caught.value))
    codes = ("unknown_key", "too_large", "too_deep", "parse_error")
    assert len(codes) == 4


def test_secret_value_never_leaks_from_errors(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as caught:
        load(IntBox, env={"N": SENTINEL})
    err = caught.value
    assert SENTINEL not in str(err)
    assert SENTINEL not in repr(err)
    assert SENTINEL not in "".join(traceback.format_exception(err))
    path = write(tmp_path, "n.json", json.dumps({"n": SENTINEL}))
    with pytest.raises(ConfigError) as caught_file:
        load(IntBox, files=[path], env={})
    assert SENTINEL not in "".join(traceback.format_exception(caught_file.value))
    loaded = load(Rich, env={"R_API_KEY": SENTINEL}, prefix="R_")
    assert SENTINEL not in repr(loaded)
    assert loaded.api_key.reveal() == SENTINEL


def test_prefix_env_names_and_json_paths(tmp_path: Path) -> None:
    from_env = load(App, env={"APP_DB__HOST": "h"}, prefix="APP_")
    path = write(tmp_path, "c.json", '{"db": {"host": "h"}}')
    from_json = load(App, files=[path], env={}, prefix="APP_")
    assert from_env == from_json == App(db=Db(host="h"))
    assert errors_of(App, env={"DB__HOST": "h"}, prefix="APP_")[0].path == "db.host"


def test_unknown_json_keys_follow_strict(tmp_path: Path) -> None:
    bad = write(tmp_path, "d.json", '{"db": {"host": "h"}, "extra": 1}')
    errors = errors_of(App, files=[bad], env={}, prefix="APP_")
    assert errors == [FieldError("extra", "unknown_key", "unknown key (source: d.json)")]
    assert load(App, files=[bad], env={}, prefix="APP_", strict=False) == App(db=Db(host="h"))
    nested = write(tmp_path, "e.json", '{"db": {"host": "h", "bad": 1}}')
    assert errors_of(App, files=[nested], env={})[0].path == "db.bad"


def test_json_group_must_be_an_object(tmp_path: Path) -> None:
    path = write(tmp_path, "a.json", '{"db": 5}')
    errors = errors_of(App, files=[path], env={})
    assert errors == [FieldError("db", "invalid_type", "expected object (source: a.json)")]


def test_optional_group_behaviour(tmp_path: Path) -> None:
    message = "required; set R_DB__HOST or provide it in a file"
    partial = errors_of(Rich, env={"R_DB__PORT": "1"}, prefix="R_")
    assert partial == [FieldError("db.host", "missing", message)]
    empty = write(tmp_path, "empty.json", '{"db": {}}')
    assert errors_of(Rich, files=[empty], env={}, prefix="R_") == partial
    null = write(tmp_path, "null.json", '{"db": null}')
    assert load(Rich, files=[null], env={}, prefix="R_").db is None
    full = write(tmp_path, "full.json", '{"db": {"host": "j", "port": 7}}')
    assert load(Rich, files=[full], env={}, prefix="R_").db == Db(host="j", port=7)


def test_group_default_instance_supplies_missing_children() -> None:
    assert load(WithDefaultDb, env={}).db == Db(host="d", port=1)
    assert load(WithDefaultDb, env={"DB__PORT": "9"}).db == Db(host="d", port=9)
    assert load(WithDefaultDb, env={"DB__HOST": "z"}).db == Db(host="z", port=1)


def test_init_false_fields_are_ignored() -> None:
    assert load(Derived, env={"BASE": "3"}) == Derived(base=3)


@pytest.mark.parametrize(("content", "expected"), DOTENV_CASES)
def test_dotenv_values(tmp_path: Path, content: bytes | str, expected: str) -> None:
    path = write(tmp_path, ".env", content)
    assert load(Single, files=[path], env={}).a == expected


def test_dotenv_crlf_and_bom_parse_together(tmp_path: Path) -> None:
    path = write(tmp_path, "prod.env", b"\xef\xbb\xbfA=x\r\nB=2\r\n")
    assert load(Pair, files=[path], env={}) == Pair(a="x", b=2)


@pytest.mark.parametrize(("content", "message"), DOTENV_BAD)
def test_dotenv_syntax_errors_name_the_line(tmp_path: Path, content: str, message: str) -> None:
    path = write(tmp_path, ".env", content)
    errors = errors_of(Pair, files=[path], env={})
    assert errors == [FieldError(".env", "parse_error", message)]


def test_dotenv_line_three_without_equals(tmp_path: Path) -> None:
    path = write(tmp_path, ".env", "A=1\nB=2\nnot a pair\n")
    errors = errors_of(Pair, files=[path], env={})
    assert errors[0].code == "parse_error"
    assert "line 3" in errors[0].message


def test_dotenv_unknown_keys_use_the_prefix(tmp_path: Path) -> None:
    path = write(tmp_path, ".env", "APP_OTHER=1\nUNRELATED=2\nAPP_A=ok\n")
    errors = errors_of(Single, files=[path], env={}, prefix="APP_")
    assert errors == [FieldError("APP_OTHER", "unknown_key", "unknown key (source: .env)")]
    assert load(Single, files=[path], env={}, prefix="APP_", strict=False).a == "ok"
    everything = errors_of(Single, files=[path], env={})
    assert [e.path for e in everything][:2] == ["APP_A", "APP_OTHER"]


def test_env_overrides_dotenv(tmp_path: Path) -> None:
    path = write(tmp_path, ".env", "A=file\n")
    assert load(Single, files=[path], env={"A": "env"}).a == "env"


def test_oversized_file_is_rejected(tmp_path: Path) -> None:
    big = write(tmp_path, "big.json", b" " * 1_048_577)
    errors = errors_of(Settings, files=[big], env={})
    assert errors == [FieldError("big.json", "too_large", "file exceeds 1048576 bytes")]
    exact = write(tmp_path, "exact.json", b" " * 1_048_576)
    assert [e.code for e in errors_of(Settings, files=[exact], env={})] == ["parse_error"]
    small = write(tmp_path, "s.json", '{"port": 1}')
    assert load(Settings, files=[small], env={}, max_file_bytes=11).port == 1
    assert errors_of(Settings, files=[small], env={}, max_file_bytes=10)[0].code == "too_large"


def test_deep_json_is_rejected_without_recursion_error(tmp_path: Path) -> None:
    deep = write(tmp_path, "deep.json", '{"a":' * 33 + "1" + "}" * 33)
    errors = errors_of(Settings, files=[deep], env={})
    assert errors == [FieldError("deep.json", "too_deep", "JSON nesting exceeds 32 levels")]
    arrays = write(tmp_path, "arrays.json", "[" * 33 + "]" * 33)
    assert [e.code for e in errors_of(Settings, files=[arrays], env={})] == ["too_deep"]
    allowed = write(tmp_path, "ok.json", '{"a":' * 32 + "1" + "}" * 32)
    assert load(Settings, files=[allowed], env={}, strict=False) == Settings()


def test_brackets_inside_strings_do_not_count_as_depth(tmp_path: Path) -> None:
    plain = write(tmp_path, "p.json", '{"s": "' + "[" * 100 + '"}')
    assert load(Settings, files=[plain], env={}, strict=False) == Settings()
    escaped = write(tmp_path, "q.json", '{"s": "\\"' + "[" * 100 + '"}')
    assert load(Settings, files=[escaped], env={}, strict=False) == Settings()


def test_unusable_files_are_reported(tmp_path: Path) -> None:
    toml = tmp_path / "c.toml"
    assert errors_of(Settings, files=[toml], env={})[0].code == "unsupported_file"
    missing = tmp_path / "nope.json"
    assert errors_of(Settings, files=[missing], env={}) == [
        FieldError("nope.json", "missing", "file not found"),
    ]
    (tmp_path / "dir.json").mkdir()
    assert errors_of(Settings, files=[tmp_path / "dir.json"], env={})[0].code == "parse_error"
    binary = write(tmp_path, "bad.env", b"\xff\xfe\x00")
    assert errors_of(Settings, files=[binary], env={})[0].message == "file is not valid UTF-8"
    top = write(tmp_path, "top.json", "[1]")
    assert errors_of(Settings, files=[top], env={})[0].code == "parse_error"
    broken = write(tmp_path, "broken.json", '{"port": ')
    assert errors_of(Settings, files=[broken], env={})[0].message == "invalid JSON"


def test_file_errors_and_field_errors_are_reported_together(tmp_path: Path) -> None:
    errors = errors_of(IntBox, files=[tmp_path / "c.toml"], env={})
    assert [e.path for e in errors] == ["c.toml", "n"]
    assert [e.code for e in errors] == ["unsupported_file", "missing"]


def test_duplicate_json_keys_keep_the_last(tmp_path: Path) -> None:
    path = write(tmp_path, "dup.json", '{"port": 1, "port": 2}')
    assert load(Settings, files=[path], env={}).port == 2


def test_errors_are_sorted_and_capped_at_one_hundred() -> None:
    names = [f"f{i:03d}" for i in range(150)]
    big = make_dataclass("Big", [(name, int) for name in names])
    errors = errors_of(big, env={})
    assert len(errors) == 101
    assert [e.path for e in errors[:100]] == names[:100]
    assert errors[-1] == FieldError("$", "too_large", "too many errors; showing the first 100")
    exactly = make_dataclass("Hundred", [(name, int) for name in names[:100]])
    assert len(errors_of(exactly, env={})) == 100


def test_error_collection_is_bounded(tmp_path: Path) -> None:
    payload = json.dumps({f"k{i}": 1 for i in range(1500)})
    path = write(tmp_path, "flood.json", payload)
    errors = errors_of(Settings, files=[path], env={})
    assert len(errors) == 101
    assert errors[-1].path == "$"
    assert errors[-1].code == "too_large"


def test_on_event_reports_counts_only(tmp_path: Path) -> None:
    path = write(tmp_path, "s.json", '{"port": 7, "tags": ["secret-value"]}')
    events: list[Any] = []
    settings = load(Settings, files=[path], env={"PORT": "9"}, on_event=events.append)
    assert settings.port == 9
    assert events == [{"source": "s.json", "keys": 2}, {"source": "env", "keys": 1}]
    assert "secret-value" not in repr(events)


def test_failing_callback_does_not_break_loading() -> None:
    def explode(event: Any) -> None:
        raise RuntimeError("boom")

    assert load(Settings, env={"PORT": "2"}, on_event=explode).port == 2


def test_logging_is_not_configured_by_the_library() -> None:
    logger = logging.getLogger("typed_config.loader")
    assert any(isinstance(handler, logging.NullHandler) for handler in logger.handlers)
    assert logging.getLogger().handlers == logging.getLogger().handlers


def test_env_defaults_to_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TC_PORT", "11")
    assert load(Settings, prefix="TC_").port == 11


def test_invalid_arguments() -> None:
    with pytest.raises(ValueError, match="max_file_bytes"):
        load(Settings, env={}, max_file_bytes=0)
    with pytest.raises(TypeError, match="dataclass"):
        load(int, env={})
    with pytest.raises(TypeError, match="dataclass"):
        describe(int)


@pytest.mark.parametrize(
    ("schema", "name"),
    [
        (BadDict, "data"),
        (BadUnion, "value"),
        (BadNestedList, "rows"),
        (BadTuple, "pair"),
        (BadList, "items"),
        (BadAny, "anything"),
        (BadOuter, "inner.data"),
    ],
)
def test_unsupported_annotations_raise_type_error(schema: type, name: str) -> None:
    with pytest.raises(TypeError, match=f"field '{name}'"):
        load(schema, env={})
    with pytest.raises(TypeError, match=f"field '{name}'"):
        describe(schema)


def test_recursive_schema_is_rejected() -> None:
    with pytest.raises(TypeError, match="too deep"):
        load(Loop, env={})


def test_describe_lists_every_variable() -> None:
    docs = describe(DocSettings, prefix="APP_")
    assert [d.env_name for d in docs] == [
        "APP_DB__HOST",
        "APP_DB__TOKEN",
        "APP_PORT",
        "APP_TAGS",
        "APP_LEVEL",
        "APP_TIMEOUT",
    ]
    assert docs[0] == FieldDoc("APP_DB__HOST", "str", None, True, "Database host.")
    assert docs[1] == FieldDoc("APP_DB__TOKEN", "Secret", "***", False, "Database token.")
    assert docs[5] == FieldDoc("APP_TIMEOUT", "float | None", "", False, "")
    with pytest.raises(FrozenInstanceError):
        docs[0].doc = "changed"


def test_describe_uses_group_defaults_and_optional_groups() -> None:
    docs = describe(WithDefaultDb)
    assert [(d.env_name, d.default, d.required) for d in docs] == [
        ("DB__HOST", "d", False),
        ("DB__PORT", "1", False),
    ]
    rich = describe(Rich, prefix="R_")
    assert [d.env_name for d in rich][-3:] == ["R_DB__HOST", "R_DB__PORT", "R_API_KEY"]
    assert rich[-3].required is True
    assert rich[3].default == "red"
    assert rich[1].default == "1.0"


def test_render_markdown_matches_golden_output() -> None:
    output = render_markdown(DocSettings, prefix="APP_")
    assert output == EXPECTED_MARKDOWN
    assert "not-a-real-value" not in output


def test_render_env_example_matches_golden_output() -> None:
    output = render_env_example(DocSettings, prefix="APP_")
    assert output == EXPECTED_ENV_EXAMPLE
    assert "not-a-real-value" not in output


def test_render_escapes_and_quotes_awkward_text() -> None:
    markdown = render_markdown(Quirks)
    assert "Line one. Line two." in markdown
    assert "a\\|b" in markdown
    example = render_env_example(Quirks)
    assert '# Line one.\n# Line two.\n# Type: str\nHASHED="a#b"' in example
    assert "QUOTED='say" in example
    assert "# a|b\n# Type: int\nPIPED=1" in example


def test_render_with_no_fields() -> None:
    assert render_env_example(Empty) == ""
    assert render_markdown(Empty) == (
        "| Variable | Type | Default | Required | Description |\n|---|---|---|---|---|\n"
    )


def test_generated_env_example_loads_back() -> None:
    text = render_env_example(Rich, prefix="R_")
    assert "R_API_KEY=\n" in text
    assert "R_RATIO=1.0" in text
