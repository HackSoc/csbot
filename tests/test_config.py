import pytest

from . import TempEnvVars
import csbot.plugin
from csbot import config


class MockPlugin(csbot.plugin.Plugin):
    CONFIG_DEFAULTS = {
        'default': 'a default value',
        'env_and_default': 'default, not env',
    }

    CONFIG_ENVVARS = {
        'env_and_default': ['CSBOTTEST_ENV_AND_DEFAULT'],
        'env_only': ['CSBOTTEST_ENV_ONLY'],
        'multiple_env': ['CSBOTTEST_ENV_MULTI_1', 'CSBOTTEST_ENV_MULTI_2'],
    }


class MockBot(csbot.core.Bot):
    available_plugins = csbot.plugin.build_plugin_dict([MockPlugin])


base_config = """
[@mockbot]
plugins = mockplugin
"""

plugin_config = """
[mockplugin]
default = config1
env_and_default = config2
env_only = config3
"""


@pytest.mark.bot(cls=MockBot, config=base_config)
def test_without_plugin_section(bot_helper):
    bot = bot_helper.bot
    # Check the test plugin was loaded
    assert 'mockplugin' in bot.plugins
    plugin = bot.plugins['mockplugin']
    # Check than absent config options are properly absent
    with pytest.raises(KeyError):
        plugin.config_get('absent')
    # Check that default values work
    assert plugin.config_get('default') == 'a default value'
    # Check that environment variables work, if present
    with pytest.raises(KeyError):
        plugin.config_get('env_only')
    with TempEnvVars({'CSBOTTEST_ENV_ONLY': 'env value'}):
        assert plugin.config_get('env_only') == 'env value'
    # Check that environment variables override defaults
    assert plugin.config_get('env_and_default') == 'default, not env'
    with TempEnvVars({'CSBOTTEST_ENV_AND_DEFAULT': 'env, not default'}):
        assert plugin.config_get('env_and_default') == 'env, not default'
    # Check that environment variable order is obeyed
    with pytest.raises(KeyError):
        plugin.config_get('multiple_env')
    with TempEnvVars({'CSBOTTEST_ENV_MULTI_2': 'lowest priority'}):
        assert plugin.config_get('multiple_env') == 'lowest priority'
        with TempEnvVars({'CSBOTTEST_ENV_MULTI_1': 'highest priority'}):
            assert plugin.config_get('multiple_env') == 'highest priority'


@pytest.mark.bot(cls=MockBot, config=base_config + plugin_config)
def test_with_plugin_section(bot_helper):
    bot = bot_helper.bot
    assert 'mockplugin' in bot.plugins
    plugin = bot.plugins['mockplugin']
    # Check that values override defaults
    assert plugin.config_get('default') == 'config1'
    # Check that values override environment variables
    assert plugin.config_get('env_only') == 'config3'
    with TempEnvVars({'CSBOTTEST_ENV_ONLY': 'env value'}):
        assert plugin.config_get('env_only') == 'config3'


def test_config_option_default():
    @config.config
    class Config:
        # Implicit default=None
        a = config.option(int, help="")
        # Default of correct type
        b = config.option(int, default=1, help="")
        # Default is function returning correct type
        c = config.option(int, default=lambda: 2, help="")

    c = config.load({}, Config)
    assert c.a is None
    assert c.b == 1
    assert c.c == 2

    @config.config
    class BadDefault:
        a = config.option(int, default="2", help="")
        b = config.option(int, default=lambda: "3", help="")

    with pytest.raises(TypeError):
        config.load({
            # Set b, so only a's default is tested
            "b": 3,
        }, BadDefault)

    with pytest.raises(TypeError):
        config.load({
            # Set a, so only b's default is tested
            "a": 3,
        }, BadDefault)


def test_config_option_validate():
    @config.config
    class Config:
        # Option with default=None (or omitted) can be None
        a = config.option(int, help="")
        # Option without default=None must not be None
        b = config.option(int, default=1, help="")

    # Both have correctly typed values
    c1 = config.load({
        "a": 3,
        "b": 4,
    }, Config)
    assert c1.a == 3
    assert c1.b == 4

    # None value where default=None is allowed
    c2 = config.load({
        "a": None,
    }, Config)
    assert c2.a is None

    # (But incorrect type is not allowed)
    with pytest.raises(TypeError):
        config.load({
            "a": "3",
        })

    # None value where default!=None is not allowed
    with pytest.raises(TypeError):
        config.load({
            "b": None,
        }, Config)


def test_config_option_env():
    @config.config
    class Config:
        a = config.option(str, env=["A_PRIMARY", "A_FALLBACK"], help="")
        b = config.option(int, env=["B_ENV"], help="")
        c = config.option(bool, env="C_ENV", help="")

    c1 = config.load({}, Config)
    assert c1.a is None
    assert c1.b is None

    # Environment variable precedence
    with TempEnvVars({"A_PRIMARY": "foo", "A_FALLBACK": "bar"}):
        c2 = config.load({}, Config)
        assert c2.a == "foo"
    with TempEnvVars({"A_FALLBACK": "bar"}):
        c3 = config.load({}, Config)
        assert c3.a == "bar"

    # Type conversion: int
    with TempEnvVars({"B_ENV": "2"}):
        c4 = config.load({}, Config)
        assert c4.b == 2

    # Type conversion: bool
    with TempEnvVars({"C_ENV": "yes"}):
        c5 = config.load({}, Config)
        assert c5.c is True
    with TempEnvVars({"C_ENV": "false"}):
        c5 = config.load({}, Config)
        assert c5.c is False

    # Supplied value causes environment variable to be ignored
    with TempEnvVars({"C_ENV": "false"}):
        c5 = config.load({"c": True}, Config)
        assert c5.c is True


def test_config_option_list():
    default_list = [1, 2, 3]

    @config.config
    class Config:
        a = config.option_list(int, help="")
        b = config.option_list(int, default=default_list, help="")
        c = config.option_list(int, default=lambda: [4, 5, 6], help="")

    # Check all default values
    c1 = config.load({}, Config)
    assert c1.a == []
    assert c1.b == [1, 2, 3]
    assert c1.c == [4, 5, 6]

    # Avoid pitfall of mutable default values
    default_list[1] = 20
    assert c1.b == [1, 2, 3]

    # Check supplied values
    c2 = config.load({
        "a": [9, 8],
        "b": [],
        "c": [7, 6, 5],
    }, Config)
    assert c2.a == [9, 8]
    assert c2.b == []
    assert c2.c == [7, 6, 5]

    # Check other sequences are read as lists
    c3 = config.load({
        "a": (10, 11),
    }, Config)
    assert c3.a == [10, 11]

    # Check the type of sequence values
    with pytest.raises(TypeError):
        config.load({
            "a": [1, None],
        })


def test_config_option_map():
    default_map = {
        "x": 1,
        "y": 2,
    }

    @config.config
    class Config:
        a = config.option_map(int, help="")
        b = config.option_map(int, default=default_map, help="")
        c = config.option_map(int, default=lambda: {"y": 3, "z": 4}, help="")

    # Check all default values
    c1 = config.load({}, Config)
    assert c1.a == {}
    assert c1.b == {"x": 1, "y": 2}
    assert c1.c == {"y": 3, "z": 4}

    # Avoid pitfall of mutable default values
    default_map["x"] = 20
    assert c1.b == {"x": 1, "y": 2}

    # Check supplied values
    c2 = config.load({
        "a": {"n": -1, "m": -2},
        "b": {},
        "c": {"i": 0, "j": -1},
    }, Config)
    assert c2.a == {"n": -1, "m": -2}
    assert c2.b == {}
    assert c2.c == {"i": 0, "j": -1}

    # Check the type of keys is enforced
    c3 = config.load({
        "a": {(1, 2): 2},
    }, Config)
    assert c3.a == {"(1, 2)": 2}

    # Check the type of values
    with pytest.raises(TypeError):
        config.load({
            "a": {"x": None},
        }, Config)


def test_config_nested():
    @config.config
    class Inner:
        x = config.option(int, default=1, help="")
        y = config.option(int, default=2, help="")

    @config.config
    class Config:
        a = config.option(Inner, help="")
        b = config.option(Inner, default=Inner, help="")
        c = config.option(Inner, default=lambda: Inner(x=3, y=4), help="")

    # Check all default values
    c1 = config.load({}, Config)
    assert c1.a is None
    assert c1.b.x == 1
    assert c1.b.y == 2
    assert c1.c.x == 3
    assert c1.c.y == 4

    # Check structuring from unstructured data
    c2 = config.load({
        "a": {"x": 10},
    }, Config)
    assert isinstance(c2.a, Inner)
    assert c2.a.x == 10
    assert c2.a.y == 2


def test_config_nested_list():
    @config.config
    class Inner:
        x = config.option(int, default=1, help="")
        y = config.option(int, default=2, help="")

    @config.config
    class Config:
        a = config.option_list(Inner, help="")

    # Check default value
    c1 = config.load({}, Config)
    assert c1.a == []

    # Check structuring from unstructured data
    c2 = config.load({
        "a": [
            {"x": 10, "y": 20},
            {"x": 11, "y": 21},
            {"x": 12, "y": 22},
        ],
    }, Config)
    assert all(isinstance(o, Inner) for o in c2.a)
    assert c2.a[0].x == 10
    assert c2.a[0].y == 20
    assert c2.a[1].x == 11
    assert c2.a[1].y == 21
    assert c2.a[2].x == 12
    assert c2.a[2].y == 22

    # Check type enforcement
    with pytest.raises(TypeError):
        config.load({
            "a": [
                {"x": None},
            ],
        }, Config)


def test_config_nested_map():
    @config.config
    class Inner:
        x = config.option(int, default=1, help="")
        y = config.option(int, default=2, help="")

    @config.config
    class Config:
        a = config.option_map(Inner, help="")

    # Check default value
    c1 = config.load({}, Config)
    assert c1.a == {}

    # Check structuring from unstructured data
    c2 = config.load({
        "a": {
            "b": {"x": 10, "y": 20},
            "c": {"x": 11, "y": 21},
        },
    }, Config)
    assert all(isinstance(v, Inner) for v in c2.a.values())
    assert c2.a["b"].x == 10
    assert c2.a["b"].y == 20
    assert c2.a["c"].x == 11
    assert c2.a["c"].y == 21

    # Check type enforcement
    with pytest.raises(TypeError):
        config.load({
            "a": {
                "b": {"x": None},
            },
        }, Config)
