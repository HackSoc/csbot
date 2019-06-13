from typing import Type, List, Dict, Any, Optional, Union, TextIO
import copy
import os
import logging
from contextlib import contextmanager
from enum import Enum
import re
import inspect

import attr
import cattr
import toml
from toml.encoder import _dump_str


LOG = logging.getLogger(__name__)

METADATA_KEY = 'csbot_config'

_BOOL_TRUE = {"true", "yes", "1"}
_BOOL_FALSE = {"false", "no", "0"}


def _read_bool(s: str, _cls: Type) -> bool:
    s_ = s.lower()
    if s_ in _BOOL_TRUE:
        return True
    elif s_ in _BOOL_FALSE:
        return False
    else:
        raise ValueError(f"unrecognised boolean string: {s}")


_env_converter = cattr.Converter()
_env_converter.register_structure_hook(bool, _read_bool)


structure = cattr.structure
unstructure = cattr.unstructure


def loads(s, cls):
    return structure(toml.loads(s), cls)


def dumps(o):
    return toml.dumps(unstructure(o))


def load(f, cls):
    return structure(toml.load(f), cls)


def dump(o, f):
    return toml.dump(unstructure(o), f)


class Factory:
    _example_mode = False

    def __init__(self, cls, *, default: Any = None, example: Any = None, env: List[str] = None):
        self._cls = cls
        if callable(default):
            self._default_callable = default
        else:
            self._default_callable = None
            self._default_value = default
        if callable(example):
            self._example_callable = example
        else:
            self._example_callable = None
            self._example_value = example
        self._env = env or []

    def __call__(self):
        if self._example_mode:
            return self._get_example()
        else:
            return self._get_default()

    def _get_default(self):
        # See if any environment variable is populated
        for var in self._env:
            if var in os.environ:
                return _env_converter.structure(os.environ[var], self._cls)
        # Otherwise use the default
        if self._default_callable:
            return self._default_callable()
        else:
            return copy.copy(self._default_value)

    def _get_example(self):
        if self._example_callable:
            return self._example_callable()
        elif self._example_value is None:
            return self._get_default()
        else:
            return copy.copy(self._example_value)

    @classmethod
    @contextmanager
    def example_mode(cls, enable=True):
        old = cls._example_mode
        cls._example_mode = enable
        yield
        cls._example_mode = old


def make_example(cls):
    with Factory.example_mode():
        return cls()


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
    optional: bool = attr.ib(default=False, validator=attr.validators.instance_of(bool))
    help: str = attr.ib(default="", validator=attr.validators.instance_of(str))


def is_structure(cls):
    return hasattr(cls, '__attrs_attrs__')


def is_allowable_type(cls):
    return is_structure(cls) or cls in (str, bool, int, float)


_ATTRS_KWARGS = {
    "slots": True,
    "kw_only": True,
}


def config(cls):
    return attr.s(**_ATTRS_KWARGS)(cls)


def make_class(name: str, attrs: Union[List[attr.Attribute], Dict[str,attr.Attribute]]):
    return attr.make_class(name, attrs, **_ATTRS_KWARGS)


# TODO: "required" options?
def option(cls: Type, *, default=None, example=None, env: Union[str, List[str]] = None, help: str) -> attr.Attribute:
    assert is_allowable_type(cls)
    type = cls
    validator = attr.validators.instance_of(cls)
    if default is None:
        type = Optional[type]
        validator = attr.validators.optional(validator)
    if isinstance(env, str):
        env = [env]

    attrib_kwargs = {
        "type": type,
        "validator": validator,
        "default": attr.Factory(Factory(cls, default=default, example=example, env=env)),
        "metadata": {
            METADATA_KEY: OptionMetadata(
                type=cls,
                kind=OptionKind.STRUCTURE if is_structure(cls) else OptionKind.SIMPLE,
                optional=default is None,
                help=help,
            ),
        },
    }

    return attr.ib(**attrib_kwargs)


def option_list(cls: Type, *, default=None, example=None, help: str) -> attr.Attribute:
    assert is_allowable_type(cls)
    type = List[cls]
    if default is None:
        default = list
    default = attr.Factory(Factory(type, default=default, example=example))

    attrib_kwargs = {
        "type": type,
        "validator": attr.validators.deep_iterable(
            member_validator=attr.validators.instance_of(cls),
            iterable_validator=attr.validators.instance_of(list),
        ),
        "default": default,
        "metadata": {
            METADATA_KEY: OptionMetadata(
                type=cls,
                kind=OptionKind.STRUCTURE_LIST if is_structure(cls) else OptionKind.SIMPLE_LIST,
                help=help,
            ),
        },
    }
    return attr.ib(**attrib_kwargs)


def option_map(cls: Type, *, default=None, example=None, help: str) -> attr.Attribute:
    assert is_allowable_type(cls)
    type = Dict[str, cls]
    if default is None:
        default = dict
    default = attr.Factory(Factory(type, default=default, example=example))

    attrib_kwargs = {
        "type": type,
        "validator": attr.validators.deep_mapping(
            key_validator=attr.validators.instance_of(str),
            value_validator=attr.validators.instance_of(cls),
            mapping_validator=attr.validators.instance_of(dict),
        ),
        "default": default,
        "metadata": {
            METADATA_KEY: OptionMetadata(
                type=cls,
                kind=OptionKind.STRUCTURE_MAP if is_structure(cls) else OptionKind.SIMPLE_MAP,
                help=help,
            ),
        },
    }
    return attr.ib(**attrib_kwargs)


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

    def generate(self, obj, stream: TextIO, prefix: List[str] = None):
        """Generate an example from *obj* and write it to *stream*."""
        if inspect.isclass(obj):
            obj = make_example(obj)
        assert is_structure(obj)
        if prefix is None:
            prefix = []
        with self._use_stream(stream):
            self._generate_structure(obj, prefix)

    def _generate_option(self,
                         example: Any,
                         attrib: attr.Attribute,
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
        metadata = self._get_metadata(attrib)
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

    def _generate_structure(self, example: Any, absolute_path: List[str], is_list_item: bool = False):
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
        for attrib in self._get_attributes(example):
            metadata = self._get_metadata(attrib)
            if not metadata.kind.is_simple:
                # Write sections after simple values
                deferred.append(attrib)
                continue
            self._generate_option(getattr(example, attrib.name),
                                  attrib,
                                  absolute_path + [attrib.name],
                                  [attrib.name])

        for attrib in deferred:
            self._write("\n")
            self._generate_option(getattr(example, attrib.name),
                                  attrib,
                                  absolute_path + [attrib.name],
                                  [attrib.name])

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
    def _get_metadata(cls, attrib: attr.Attribute) -> OptionMetadata:
        return attrib.metadata[METADATA_KEY]

    @classmethod
    def _make_key(cls, path):
        return ".".join([_ if cls._BARE_KEY_REGEX.match(_) else _dump_str(_)
                         for _ in path])


def generate_toml_example(obj, commented=False):
    from io import StringIO
    stream = StringIO()
    generator = TomlExampleGenerator(commented=commented)
    generator.generate(obj, stream)
    return stream.getvalue()
