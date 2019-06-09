from typing import Type, List, Dict, Any, Optional, Union
import copy
import os

import attr
import cattr
import toml


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


load = cattr.structure
dump = cattr.unstructure


class Factory:
    def __init__(self, cls, *, default: Any = None, env: List[str] = None):
        self._cls = cls
        if callable(default):
            self._default_callable = default
        else:
            self._default_callable = None
            self._default_value = default
        self._env = env or []

    def __call__(self):
        # See if any environment variable is populated
        for var in self._env:
            if var in os.environ:
                return _env_converter.structure(os.environ[var], self._cls)
        # Otherwise use the default
        if self._default_callable:
            return self._default_callable()
        else:
            return copy.copy(self._default_value)


def config(cls: Type):
    attrs_kwargs = {
        "slots": True,
        "kw_only": True,
    }
    return attr.s(**attrs_kwargs)(cls)


def option(cls: Type, *, default=None, env: Union[str, List[str]] = None, help: str) -> attr.Attribute:
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
        "default": attr.Factory(Factory(cls, default=default, env=env)),
        "metadata": {
            METADATA_KEY: {
                "help": help,
            },
        },
    }

    return attr.ib(**attrib_kwargs)


def option_list(cls: Type, *, default=None, help: str) -> attr.Attribute:
    if default is None:
        default = attr.Factory(list)
    elif callable(default):
        default = attr.Factory(default)
    else:
        default = copy.copy(default)

    attrib_kwargs = {
        "type": List[cls],
        "validator": attr.validators.deep_iterable(
            member_validator=attr.validators.instance_of(cls),
            iterable_validator=attr.validators.instance_of(list),
        ),
        "default": default,
        "metadata": {
            METADATA_KEY: {
                "help": help,
            },
        },
    }
    return attr.ib(**attrib_kwargs)


def option_map(cls: Type, *, default=None, help: str) -> attr.Attribute:
    if default is None:
        default = attr.Factory(dict)
    elif callable(default):
        default = attr.Factory(default)
    else:
        default = copy.copy(default)

    attrib_kwargs = {
        "type": Dict[str, cls],
        "validator": attr.validators.deep_mapping(
            key_validator=attr.validators.instance_of(str),
            value_validator=attr.validators.instance_of(cls),
            mapping_validator=attr.validators.instance_of(dict),
        ),
        "default": default,
        "metadata": {
            METADATA_KEY: {
                "help": help,
            },
        },
    }
    return attr.ib(**attrib_kwargs)
