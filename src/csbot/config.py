from contextlib import contextmanager
from enum import Enum
from functools import partial
import inspect
import io
import logging
import os
import re
from typing import (
    cast,
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Mapping,
    TextIO,
    Type,
    TypeVar,
    Union,
)

import attr
from schematics import Model, types
import schematics.exceptions
import toml
from toml.encoder import _dump_str


_LOG = logging.getLogger(__name__)

_METADATA_KEY = 'csbot_config'


class Config(Model):
    """Base class for configuration schemas.

    Use :func:`option`, :func:`option_list` and :func:`option_map` to create fields in the schema.
    Schemas are also valid option types, so deeper structures can be defined.

    >>> class MyConfig(Config):
    ...     delay = option(float, default=0.5, help="Number of seconds to wait")
    ...     notify = option_list(str, help="Users to notify")
    """
    def __repr__(self):
        return f"{self.__class__.__name__}({', '.join(f'{a.name}={repr(a.value)}' for a in self.atoms())})"


#: Raised when configuration fails to validate
ConfigError = schematics.exceptions.DataError


_example_mode = False


@contextmanager
def example_mode():
    """For the duration of this context manager, try to use example values before default values."""
    global _example_mode
    old = _example_mode
    _example_mode = True
    yield
    _example_mode = old


class WordList(types.ListType):
    """A list of strings that also accepts a space-separated string instead."""
    def __init__(self, min_size=None, max_size=None, **kwargs):
        super().__init__(types.StringType, min_size, max_size, **kwargs)

    def convert(self, value, context=None):
        if isinstance(value, str):
            value = value.split()
        return super().convert(value, context)


_T = TypeVar("_T")
# Mapping of Python types to Schematics field types
_TYPE_MAP = {
    str: types.StringType,
    int: types.IntType,
    float: types.FloatType,
    bool: types.BooleanType,
    WordList: WordList,
}
# Basic option types available to the developer
_B = TypeVar("_B", Config, str, int, float, bool, WordList)
# Type of default value for an option
_DefaultValue = Union[None, _T]
# Type of callable to create a default value for an option
_DefaultCall = Callable[[], _DefaultValue[_T]]
# Type of a "default" or "example" argument
_DefaultArg = Union[_DefaultValue[_T], _DefaultCall[_T]]


def is_config(obj: Any) -> bool:
    """Is *obj* a configuration class or instance?"""
    if inspect.isclass(obj):
        return issubclass(obj, Config)
    else:
        return isinstance(obj, Config)


def is_allowable_type(cls: Type) -> bool:
    """Is *cls* allowed as a configuration option type?"""
    return cls in _TYPE_MAP or is_config(cls)


def structure(data: Mapping[str, Any], cls: Type[Config]) -> Config:
    """Create an instance of *cls* from plain Python structure *data*."""
    o = cls(data)
    o.validate()
    return o


def unstructure(obj: Config) -> Mapping[str, Any]:
    """Get plain Python structured data from *obj*."""
    return obj.to_native()


def loads(s: str, cls: Type[Config]) -> Config:
    """Create an instance of *cls* from the TOML in *s*."""
    return structure(toml.loads(s), cls)


def dumps(obj: Config) -> str:
    """Get TOML string representation of *obj*."""
    return toml.dumps(unstructure(obj))


def load(f: TextIO, cls: Type[Config]) -> Config:
    """Create an instance of *cls* from the TOML in *f*."""
    return structure(toml.load(f), cls)


def dump(obj: Config, f: TextIO):
    """Write TOML representation of *obj* to *f*."""
    return toml.dump(unstructure(obj), f)


class _Default(Generic[_T]):
    """A callable to get a default or example value.

    Both *default* and *example* can be either a value or a callable that returns a value.
    Returns *default* (or the result of calling it, if callable) when called.

    When called "normally", returns the value of the first environment variable in *env* that exists, or returns
    *default* if no environment variable is used.

    When called inside ``with example_mode()``, returns *example* if non-None, otherwise returns *default* (but without
    environment variable behaviour). This allows configuration to define required fields without default values that can
    still generate a useful example (see :class:`TomlExampleGenerator`) without otherwise supplying data.
    """
    def __init__(self, default: _DefaultArg = None, example: _DefaultArg = None, env: List[str] = None):
        self._default: _DefaultCall = default if callable(default) else lambda: default
        self._example: _DefaultCall = example if callable(example) else lambda: example
        self._env: List[str] = env or []

    def __call__(self) -> Union[str, _DefaultValue[_T]]:
        global _example_mode
        if _example_mode:
            return self._get_example()
        else:
            return self._get_default()

    def _get_default(self, use_env: bool = True) -> Union[str, _DefaultValue[_T]]:
        if use_env:
            for var in self._env:
                if var in os.environ:
                    return os.environ[var]
        return self._default()

    def _get_example(self) -> Union[str, _DefaultValue[_T]]:
        example = self._example()
        if example is None:
            example = self._get_default(use_env=False)
        return example


class _OptionKind(Enum):
    SIMPLE = "simple"
    STRUCTURE = "structure"
    SIMPLE_LIST = "simple_list"
    SIMPLE_MAP = "simple_map"
    STRUCTURE_LIST = "structure_list"
    STRUCTURE_MAP = "structure_map"

    @property
    def is_simple(self):
        return self in {self.SIMPLE, self.SIMPLE_LIST, self.SIMPLE_MAP}


@attr.s(frozen=True)
class _OptionMetadata(Generic[_B]):
    type: Type[_B] = attr.ib()
    kind: _OptionKind = attr.ib(validator=attr.validators.in_(_OptionKind))
    help: str = attr.ib(default="", validator=attr.validators.instance_of(str))


def option(cls: Type[_B], *,
           required: bool = None,
           default: _DefaultArg[_B] = None,
           example: _DefaultArg[_B] = None,
           env: Union[str, List[str]] = None,
           help: str):
    """Create a configuration option that contains a value of type *cls*.

    :param cls:         Option type (see :func:`is_allowable_type`)
    :param required:    A non-None value is required? (default: False if default is None, otherwise True)
    :param default:     Default value if no value is supplied (default: None)
    :param example:     Default value when generating example configuration (default: None)
    :param env:         Environment variables to try if no value is supplied, before using default (default: [])
    :param help:        Description of option, included when generating example configuration
    """
    if not is_allowable_type(cls):
        raise TypeError(f"cls must be subclass of Config or one of {_TYPE_MAP.keys()}")

    if required is None:
        required = default is not None

    if isinstance(env, str):
        env = [env]

    if is_config(cls):
        field = partial(types.ModelType, cls)
    else:
        field = _TYPE_MAP[cls]

    field_kwargs = {
        "required": required,
        "default": _Default(default, example, env),
        "metadata": {
            _METADATA_KEY: _OptionMetadata(
                type=cls,
                kind=_OptionKind.STRUCTURE if is_config(cls) else _OptionKind.SIMPLE,
                help=help,
            ),
        },
    }
    return field(**field_kwargs)


def option_list(cls: Type[_B], *,
                default: _DefaultArg[List[_B]] = None,
                example: _DefaultArg[List[_B]] = None,
                help: str):
    """Create a configuration option that contains a list of *cls* values.

    :param cls:         Option type (see :func:`is_allowable_type`)
    :param default:     Default value if no value is supplied (default: empty list)
    :param example:     Default value when generating example configuration (default: empty list)
    :param help:        Description of option, included when generating example configuration
    """
    if not is_allowable_type(cls):
        raise TypeError(f"cls must be subclass of Config or one of {_TYPE_MAP.keys()}")

    if default is None:
        default = list

    if is_config(cls):
        inner_field = types.ModelType(cls, required=True)
    else:
        inner_field = _TYPE_MAP[cls](required=True)

    field_kwargs = {
        "required": True,   # Disallow None as a value, empty list is fine
        "default": _Default(default, example),
        "metadata": {
            _METADATA_KEY: _OptionMetadata(
                type=cls,
                kind=_OptionKind.STRUCTURE_LIST if is_config(cls) else _OptionKind.SIMPLE_LIST,
                help=help,
            ),
        },
    }
    return types.ListType(inner_field, **field_kwargs)


def option_map(cls: Type[_B], *,
               default: _DefaultArg[Dict[str, _B]] = None,
               example: _DefaultArg[Dict[str, _B]] = None,
               help: str):
    """Create a configuration option that contains a mapping of string keys to *cls* values.

    :param cls:         Option type (see :func:`is_allowable_type`)
    :param default:     Default value if no value is supplied (default: empty list)
    :param example:     Default value when generating example configuration (default: empty list)
    :param help:        Description of option, included when generating example configuration
    """
    if not is_allowable_type(cls):
        raise TypeError(f"cls must be subclass of Config or one of {_TYPE_MAP.keys()}")

    if default is None:
        default = dict

    if is_config(cls):
        inner_field = types.ModelType(cls, required=True)
    else:
        inner_field = _TYPE_MAP[cls](required=True)

    field_kwargs = {
        "required": True,   # Disallow None as a value, empty dict is fine
        "default": _Default(default, example),
        "metadata": {
            _METADATA_KEY: _OptionMetadata(
                type=cls,
                kind=_OptionKind.STRUCTURE_MAP if is_config(cls) else _OptionKind.SIMPLE_MAP,
                help=help,
            ),
        },
    }
    return types.DictType(inner_field, **field_kwargs)


def make_example(cls: Type[Config]) -> Config:
    """Create an instance of *cls* without supplying data, using "example" or "default" values for each option."""
    with example_mode():
        o = cls()
        o.validate()
        return o


class TomlExampleGenerator:
    _BARE_KEY_REGEX = re.compile(r"^[A-Za-z0-9_-]+$")

    def __init__(self, *, commented=False):
        self._stream = None
        self._commented = commented
        self._encoder = toml.TomlEncoder()
        self._at_start = True

    @contextmanager
    def _use_stream(self, new):
        """Make all :meth:`_write` and :meth:`_writeline` calls go to *new*."""
        old = self._stream
        self._stream = new
        yield
        self._stream = old

    @contextmanager
    def _set_commented(self, new=True):
        """Make sure all non-empty lines start with ``#``."""
        old = self._commented
        self._commented = new
        yield
        self._commented = old

    def _write(self, s, raw=False):
        """Write *s* to the current stream; if *raw* is True, don't apply comment filter."""
        if not raw and self._commented:
            lines = s.split("\n")
            modified = [f"# {l}" if l and not l.startswith("#") else l
                        for l in lines]
            s = "\n".join(modified)
        self._stream.write(s)
        self._at_start = False

    def _writeline(self, s, raw=False):
        """Write *s* to the current stream as a new line; if *raw* is True, don't apply comment filter."""
        if not raw and self._commented and s and not s.startswith("#"):
            s = f"# {s}"
        s = f"{s}\n"
        self._write(s, raw=True)

    def generate(self, obj: Union[Config, Type[Config]], stream: TextIO, prefix: List[str] = None):
        """Generate an example from *obj* and write it to *stream*."""
        if inspect.isclass(obj):
            obj_ = make_example(obj)
        else:
            obj_ = cast(Config, obj)
        assert is_config(obj)
        if prefix is None:
            prefix = []
        with self._use_stream(stream):
            self._generate_structure(obj_, prefix)

    def _generate_option(self,
                         example: Any,
                         field: types.BaseType,
                         absolute_path: List[str],
                         relative_path: List[str]):
        """
        Generate "## <help>" (if present)
        Generate option example:
            _generate_simple
            _generate_simple_list
            _generate_simple_map
            _generate_structure
            _generate_structure_list
            _generate_structure_map
        """
        metadata = self._get_metadata(field)
        if metadata.help:
            self._writeline(f"## {metadata.help}")
        if metadata.kind is _OptionKind.SIMPLE:
            self._generate_simple(example, relative_path)
        elif metadata.kind is _OptionKind.SIMPLE_LIST:
            self._generate_simple_list(example, relative_path)
        elif metadata.kind is _OptionKind.SIMPLE_MAP:
            self._generate_simple_map(example, relative_path)
        elif metadata.kind is _OptionKind.STRUCTURE:
            self._generate_structure(example, absolute_path)
        elif metadata.kind is _OptionKind.STRUCTURE_LIST:
            self._generate_structure_list(example, absolute_path)
        elif metadata.kind is _OptionKind.STRUCTURE_MAP:
            self._generate_structure_map(example, absolute_path)

    def _generate_simple(self, example: Any, relative_path: List[str]):
        """
        Generate <relative_path> = toml(<example>)
        """
        key = self._make_key(relative_path)
        if example is None:
            self._writeline(f"# {key} =")
        else:
            self._writeline(f"{key} = {self._encoder.dump_value(example)}")

    def _generate_simple_list(self, example: List[Any], relative_path: List[str]):
        """
        Generate <relative_path> = toml(<example>)
        """
        return self._generate_simple(example, relative_path)

    def _generate_simple_map(self, example: Dict[str, Any], relative_path: List[str]):
        """
        Generate <relative_path>.<key> = toml(<example[key]>) for each key in <example>
        """
        if len(example) == 0:
            key = self._make_key(relative_path + ["_key_"])
            self._writeline(f"# {key} = _value_")
        else:
            for k, v in example.items():
                self._generate_simple(v, relative_path + [k])

    def _generate_structure(self, example: Config, absolute_path: List[str], is_list_item: bool = False):
        """
        Generate section heading:
            Nothing if top-levell
            [<absolute_path>] if option or map item
            [[<absolute_path>]] if list item
        Generate all "simple" options
        Generate all "structure" options
        """
        if absolute_path:
            key = self._make_key(absolute_path)
            if example is None:
                self._write("# ")
            if is_list_item:
                self._writeline(f"[[{key}]]")
            else:
                self._writeline(f"[{key}]")

        if example is None:
            return

        deferred = []
        for atom in example.atoms():
            metadata = self._get_metadata(atom.field)
            if not metadata.kind.is_simple:
                # Write sections after simple values
                deferred.append(atom)
                continue
            self._generate_option(atom.value,
                                  atom.field,
                                  absolute_path + [atom.name],
                                  [atom.name])

        for atom in deferred:
            self._write("\n")
            self._generate_option(atom.value,
                                  atom.field,
                                  absolute_path + [atom.name],
                                  [atom.name])

    def _generate_structure_list(self, example: List[Any], absolute_path: List[str]):
        """
        For each item in <example>:
            Generate structure with [[<absolute_path>]] heading
        """
        if len(example) == 0:
            key = self._make_key(absolute_path)
            self._writeline(f"# [[{key}]]")
        else:
            for item in example:
                self._generate_structure(item, absolute_path, is_list_item=True)

    def _generate_structure_map(self, example: Dict[str, Any], absolute_path: List[str]):
        """
        For each item in <example>:
            Generate structure from <example[key]> with [<absolute_path>.<key>] heading
        """
        if len(example) == 0:
            key = self._make_key(absolute_path)
            self._writeline(f"# [{key}._key_]")
        else:
            for name, value in example.items():
                self._generate_structure(value, absolute_path + [name])

    @classmethod
    def _get_metadata(cls, field: types.BaseType) -> _OptionMetadata:
        return field.metadata[_METADATA_KEY]

    @classmethod
    def _make_key(cls, path):
        return ".".join([_ if cls._BARE_KEY_REGEX.match(_) else _dump_str(_)
                         for _ in path])


def generate_toml_example(obj: Union[Config, Type[Config]], commented: bool = False) -> str:
    """Generate an example configuration from *obj* as a TOML string."""
    stream = io.StringIO()
    generator = TomlExampleGenerator(commented=commented)
    generator.generate(obj, stream)
    return stream.getvalue()
