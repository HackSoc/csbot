from contextlib import contextmanager
from functools import partial
import logging
import os
from typing import Type, TypeVar, List, Dict, Any, Optional, Union, Callable, TextIO

from schematics import Model, types
import schematics.exceptions

# TODO: add test that checks that the example configuration can be generated and loaded (therefore that no plugins have
#       required options without an example value)
# TODO: warn about mutable default/example values
# TODO: required=True for option_list and option_map?
# TODO: choices?
# TODO; custom errors?

LOG = logging.getLogger(__name__)

_TYPE_MAP = {
    str: types.StringType,
    int: types.IntType,
    float: types.FloatType,
    bool: types.BooleanType,
}

_T = TypeVar("_T")

_DefaultValue = Union[type(None), _T, Callable[[], _T]]

_example_mode = False


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


_OptionType = Union[Type[Config], Type[str], Type[int], Type[float], Type[bool]]


def is_config(cls):
    return issubclass(cls, Config)


def is_allowable_type(cls):
    return cls in _TYPE_MAP or is_config(cls)


def structure(data: Dict[str, Any], cls: Type[Config]) -> Config:
    o = cls(data)
    o.validate()
    return o


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
    }
    return types.DictType(inner_field, **field_kwargs)


def make_example(cls: Type[Config]) -> Config:
    with example_mode():
        o = cls()
        o.validate()
        return o
