from contextlib import contextmanager
from enum import Enum
from functools import partial
import inspect
import io
import logging
import os
import re
from typing import Type, TypeVar, List, Dict, Any, Union, Callable, TextIO

import attr
from schematics import Model, types
import schematics.exceptions
import toml
from toml.encoder import _dump_str

# TODO: add test that checks that the example configuration can be generated and loaded (therefore that no plugins have
#       required options without an example value)
# TODO: warn about mutable default/example values
# TODO: required=True for option_list and option_map?
# TODO: choices?
# TODO; custom errors instead of leaking Schematics exceptions?

LOG = logging.getLogger(__name__)

METADATA_KEY = 'csbot_config'

_TYPE_MAP = {
    str: types.StringType,
    int: types.IntType,
    float: types.FloatType,
    bool: types.BooleanType,
}

_T = TypeVar("_T")

_DefaultValue = Union[type(None), _T, Callable[[], _T]]

_example_mode = False


class OptionKind(Enum):
    SIMPLE = "simple"
    STRUCTURE = "structure"
    SIMPLE_LIST = "simple_list"
    SIMPLE_MAP = "simple_map"
    STRUCTURE_LIST = "structure_list"
    STRUCTURE_MAP = "structure_map"

    @property
    def is_simple(self):
        return self in {self.SIMPLE, self.SIMPLE_LIST, self.SIMPLE_MAP}


@attr.s(slots=True, frozen=True)
class OptionMetadata:
    type = attr.ib()
    kind: OptionKind = attr.ib(validator=attr.validators.in_(OptionKind))
    help: str = attr.ib(default="", validator=attr.validators.instance_of(str))


@contextmanager
def example_mode():
    global _example_mode
    old = _example_mode
    _example_mode = True
    yield
    _example_mode = old


class Config(Model):
    def __repr__(self):
        return f"{self.__class__.__name__}({', '.join(f'{a.name}={repr(a.value)}' for a in self.atoms())})"


ConfigError = schematics.exceptions.DataError


_SimpleOptionType = Union[Type[str], Type[int], Type[float], Type[bool]]
_OptionType = Union[Type[Config], _SimpleOptionType]


def is_config(obj):
    if inspect.isclass(obj):
        return issubclass(obj, Config)
    else:
        return isinstance(obj, Config)


def is_allowable_type(cls):
    return cls in _TYPE_MAP or is_config(cls)


def structure(data: Dict[str, Any], cls: Type[Config]) -> Config:
    o = cls(data)
    o.validate()
    return o


def unstructure(obj: Config) -> Dict[str, Any]:
    return obj.to_native()


def loads(s: str, cls: Type[Config]) -> Config:
    return structure(toml.loads(s), cls)


def dumps(obj: Config) -> str:
    return toml.dumps(unstructure(obj))


def load(f, cls: Type[Config]) -> Config:
    return structure(toml.load(f), cls)


def dump(obj: Config, f):
    return toml.dump(unstructure(obj), f)


class Default:
    """A callable to get a default or example value.

    Returns *default* (or the result of calling it, if callable) when called.

    If inside a ``with example_mode()``, first tries to return *example* (or the result of calling it, if callable),
    and falls back to *default* if *example* was None.

    This allows plugin configuration to define required fields that can still generate a useful example without any
    data being supplied.

    TODO: document *env*
    """
    def __init__(self, default: _DefaultValue = None, example: _DefaultValue = None, env: List[str] = None):
        self._default = default if callable(default) else lambda: default
        self._example = example if callable(example) else lambda: example
        self._env = env or []

    def __call__(self):
        global _example_mode
        if _example_mode:
            return self._get_example()
        else:
            return self._get_default()

    def _get_default(self, use_env: bool = True):
        if use_env:
            for var in self._env:
                if var in os.environ:
                    print(f"found {var} in os.environ")
                    return os.environ[var]
        return self._default()

    def _get_example(self):
        example = self._example()
        if example is None:
            example = self._get_default(use_env=False)
        return example


def option(cls: _OptionType, *,
           required: bool = False,
           default: _DefaultValue = None,
           example: _DefaultValue = None,
           env: Union[str, List[str]] = None,
           help: str) -> types.BaseType:
    if not is_allowable_type(cls):
        raise TypeError(f"cls must be subclass of Config or one of {_TYPE_MAP.keys()}")

    if isinstance(env, str):
        env = [env]

    if is_config(cls):
        field = partial(types.ModelType, cls)
    else:
        field = _TYPE_MAP[cls]

    field_kwargs = {
        "required": required or default is not None,
        "default": Default(default, example, env),
        "metadata": {
            METADATA_KEY: OptionMetadata(
                type=cls,
                kind=OptionKind.STRUCTURE if is_config(cls) else OptionKind.SIMPLE,
                help=help,
            ),
        },
    }
    return field(**field_kwargs)


def option_list(cls: _OptionType, *,
                default: _DefaultValue = None,
                example: _DefaultValue = None,
                help: str):
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
        "default": Default(default, example),
        "metadata": {
            METADATA_KEY: OptionMetadata(
                type=cls,
                kind=OptionKind.STRUCTURE_LIST if is_config(cls) else OptionKind.SIMPLE_LIST,
                help=help,
            ),
        },
    }
    return types.ListType(inner_field, **field_kwargs)


def option_map(cls: _OptionType, *,
               default: _DefaultValue = None,
               example: _DefaultValue = None,
               help: str):
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
        "default": Default(default, example),
        "metadata": {
            METADATA_KEY: OptionMetadata(
                type=cls,
                kind=OptionKind.STRUCTURE_MAP if is_config(cls) else OptionKind.SIMPLE_MAP,
                help=help,
            ),
        },
    }
    return types.DictType(inner_field, **field_kwargs)


def make_example(cls: Type[Config]) -> Config:
    with example_mode():
        o = cls()
        o.validate()
        return o


# TODO: commented output
# TODO: distinguish between "example" and "default" values?
class TomlExampleGenerator:
    _BARE_KEY_REGEX = re.compile(r"^[A-Za-z0-9_-]+$")

    def __init__(self, *, commented=False):
        self._stream = None
        self._commented = False
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
            obj = make_example(obj)
        assert is_config(obj)
        if prefix is None:
            prefix = []
        with self._use_stream(stream):
            self._generate_structure(obj, prefix)

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
        if metadata.kind is OptionKind.SIMPLE:
            self._generate_simple(example, relative_path)
        elif metadata.kind is OptionKind.SIMPLE_LIST:
            self._generate_simple_list(example, relative_path)
        elif metadata.kind is OptionKind.SIMPLE_MAP:
            self._generate_simple_map(example, relative_path)
        elif metadata.kind is OptionKind.STRUCTURE:
            self._generate_structure(example, absolute_path)
        elif metadata.kind is OptionKind.STRUCTURE_LIST:
            self._generate_structure_list(example, absolute_path)
        elif metadata.kind is OptionKind.STRUCTURE_MAP:
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
            # TODO: generate skeleton/outline of structure class?
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
            # TODO: generate skeleton/outline of structure class?
        else:
            for name, value in example.items():
                self._generate_structure(value, absolute_path + [name])

    @classmethod
    def _get_attributes(cls, obj):
        return getattr(obj, "__attrs_attrs__")

    @classmethod
    def _get_metadata(cls, field: types.BaseType) -> OptionMetadata:
        return field.metadata[METADATA_KEY]

    @classmethod
    def _make_key(cls, path):
        return ".".join([_ if cls._BARE_KEY_REGEX.match(_) else _dump_str(_)
                         for _ in path])


def generate_toml_example(obj, commented=False):
    stream = io.StringIO()
    generator = TomlExampleGenerator(commented=commented)
    generator.generate(obj, stream)
    return stream.getvalue()
