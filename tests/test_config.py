import io

import pytest
import toml

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
["@mockbot"]
plugins = ["mockplugin"]
"""

plugin_config = """
[mockplugin]
default = "config1"
env_and_default = "config2"
env_only = "config3"
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
    class Config(config.Config):
        # Implicit default=None
        a = config.option(int, help="")
        # Default of correct type
        b = config.option(int, default=1, help="")
        # Default is function returning correct type
        c = config.option(int, default=lambda: 2, help="")

    c = config.structure({}, Config)
    assert c.a is None
    assert c.b == 1
    assert c.c == 2

    class BadDefault(config.Config):
        a = config.option(int, default="blah", help="")
        b = config.option(int, default=lambda: "blah", help="")

    with pytest.raises(config.ConfigError):
        config.structure({
            # Set b, so only a's default is tested
            "b": 3,
        }, BadDefault)

    with pytest.raises(config.ConfigError):
        config.structure({
            # Set a, so only b's default is tested
            "a": 3,
        }, BadDefault)


def test_config_option_validate():
    class Config(config.Config):
        # Option with default=None (or omitted) can be None
        a = config.option(int, help="")
        # Option without default=None must not be None
        b = config.option(int, default=1, help="")

    # Both have correctly typed values
    c1 = config.structure({
        "a": 3,
        "b": 4,
    }, Config)
    assert c1.a == 3
    assert c1.b == 4

    # None value where default=None is allowed
    c2 = config.structure({
        "a": None,
    }, Config)
    assert c2.a is None

    # (But incorrect type is not allowed)
    with pytest.raises(config.ConfigError):
        config.structure({
            "a": "blah",
        }, Config)

    # None value where default!=None is not allowed
    with pytest.raises(config.ConfigError):
        config.structure({
            "b": None,
        }, Config)


def test_config_option_env():
    class Config(config.Config):
        a = config.option(str, env=["A_PRIMARY", "A_FALLBACK"], help="")
        b = config.option(int, env=["B_ENV"], help="")
        c = config.option(bool, env="C_ENV", help="")

    c1 = config.structure({}, Config)
    assert c1.a is None
    assert c1.b is None

    # Environment variable precedence
    with TempEnvVars({"A_PRIMARY": "foo", "A_FALLBACK": "bar"}):
        c2 = config.structure({}, Config)
        assert c2.a == "foo"
    with TempEnvVars({"A_FALLBACK": "bar"}):
        c3 = config.structure({}, Config)
        assert c3.a == "bar"

    # Type conversion: int
    with TempEnvVars({"B_ENV": "2"}):
        c4 = config.structure({}, Config)
        assert c4.b == 2

    # Type conversion: bool
    with TempEnvVars({"C_ENV": "true"}):
        c5 = config.structure({}, Config)
        assert c5.c is True
    with TempEnvVars({"C_ENV": "false"}):
        c5 = config.structure({}, Config)
        assert c5.c is False

    # Supplied value causes environment variable to be ignored
    with TempEnvVars({"C_ENV": "false"}):
        c5 = config.structure({"c": True}, Config)
        assert c5.c is True


def test_config_option_types():
    """Check that only whitelisted types are allowed for options."""
    class A(config.Config):
        a = config.option(int, default=1, help="")

    class B:
        pass

    # Check that all types that should be valid for options are allowed
    for t in (A, str, int, float, bool):
        config.option(t, help="")
        config.option_list(t, help="")
        config.option_map(t, help="")

    # Check that types that shouldn't be valid for options raise exceptions
    for t in (B, None, object):
        with pytest.raises(TypeError):
            config.option(t, help="")
        with pytest.raises(TypeError):
            config.option_list(t, help="")
        with pytest.raises(TypeError):
            config.option_map(t, help="")


def test_config_option_not_required_no_default():
    """Check that default value of None is the default behaviour."""
    class Config(config.Config):
        a = config.option(int, help="")

    c = config.structure({}, Config)
    assert c.a is None


def test_config_option_required_no_default():
    """Check behaviour of ``required=True`` with no default value."""
    class Config(config.Config):
        a = config.option(int, required=True, help="")

    with pytest.raises(config.ConfigError):
        config.structure({}, Config)

    with pytest.raises(config.ConfigError):
        config.structure({"a": None}, Config)

    c = config.structure({"a": 12}, Config)
    assert c.a == 12


def test_config_option_required_default():
    """Check behaviour of ``required=True`` with a default value."""
    class Config(config.Config):
        a = config.option(int, required=True, default=12, help="")

    c = config.structure({}, Config)
    assert c.a == 12

    c = config.structure({"a": 23}, Config)
    assert c.a == 23

    with pytest.raises(config.ConfigError):
        config.structure({"a": None}, Config)


def test_config_option_required_example():
    """Check behaviour of ``required=True`` with an example value (but no default)."""
    class Config(config.Config):
        a = config.option(int, required=True, example=12, help="")

    with pytest.raises(config.ConfigError):
        config.structure({}, Config)

    c = config.make_example(Config)
    assert c.a == 12


def test_config_option_implicitly_required():
    """Check that a non-None default value forces the field to be required."""
    class Config(config.Config):
        a = config.option(int, default=12, help="")

    c = config.structure({}, Config)
    assert c.a == 12

    with pytest.raises(config.ConfigError):
        config.structure({"a": None}, Config)


def test_config_option_not_required_default():
    """Check that ``required=False`` overrides the "implicitly required" behaviour of having a default."""
    class Config(config.Config):
        a = config.option(int, default=12, required=False, help="")

    c = config.structure({"a": None}, Config)
    assert c.a is None


def test_config_option_list():
    default_list = [1, 2, 3]

    class Config(config.Config):
        a = config.option_list(int, help="")
        b = config.option_list(int, default=default_list, help="")
        c = config.option_list(int, default=lambda: [4, 5, 6], help="")

    # Check all default values
    c1 = config.structure({}, Config)
    assert c1.a == []
    assert c1.b == [1, 2, 3]
    assert c1.c == [4, 5, 6]

    # Avoid pitfall of mutable default values
    default_list[1] = 20
    assert c1.b == [1, 2, 3]

    # Check supplied values
    c2 = config.structure({
        "a": [9, 8],
        "b": [],
        "c": [7, 6, 5],
    }, Config)
    assert c2.a == [9, 8]
    assert c2.b == []
    assert c2.c == [7, 6, 5]

    # Check other sequences are read as lists
    c3 = config.structure({
        "a": (10, 11),
    }, Config)
    assert c3.a == [10, 11]

    # Check the type of sequence values
    with pytest.raises(config.ConfigError):
        config.structure({
            "a": [1, None],
        }, Config)


def test_config_option_map():
    default_map = {
        "x": 1,
        "y": 2,
    }

    class Config(config.Config):
        a = config.option_map(int, help="")
        b = config.option_map(int, default=default_map, help="")
        c = config.option_map(int, default=lambda: {"y": 3, "z": 4}, help="")

    # Check all default values
    c1 = config.structure({}, Config)
    assert c1.a == {}
    assert c1.b == {"x": 1, "y": 2}
    assert c1.c == {"y": 3, "z": 4}

    # Avoid pitfall of mutable default values
    default_map["x"] = 20
    assert c1.b == {"x": 1, "y": 2}

    # Check supplied values
    c2 = config.structure({
        "a": {"n": -1, "m": -2},
        "b": {},
        "c": {"i": 0, "j": -1},
    }, Config)
    assert c2.a == {"n": -1, "m": -2}
    assert c2.b == {}
    assert c2.c == {"i": 0, "j": -1}

    # Check the type of keys is enforced
    c3 = config.structure({
        "a": {(1, 2): 2},
    }, Config)
    assert c3.a == {"(1, 2)": 2}

    # Check the type of values
    with pytest.raises(config.ConfigError):
        config.structure({
            "a": {"x": None},
        }, Config)


def test_config_nested():
    class Inner(config.Config):
        x = config.option(int, default=1, help="")
        y = config.option(int, default=2, help="")

    class Config(config.Config):
        a = config.option(Inner, help="")
        b = config.option(Inner, default=Inner, help="")
        c = config.option(Inner, default=lambda: Inner(dict(x=3, y=4)), help="")

    # Check all default values
    c1 = config.structure({}, Config)
    assert c1.a is None
    assert c1.b.x == 1
    assert c1.b.y == 2
    assert c1.c.x == 3
    assert c1.c.y == 4

    # Check structuring from unstructured data
    c2 = config.structure({
        "a": {"x": 10},
    }, Config)
    assert isinstance(c2.a, Inner)
    assert c2.a.x == 10
    assert c2.a.y == 2


def test_config_nested_list():
    class Inner(config.Config):
        x = config.option(int, default=1, help="")
        y = config.option(int, default=2, help="")

    class Config(config.Config):
        a = config.option_list(Inner, help="")

    # Check default value
    c1 = config.structure({}, Config)
    assert c1.a == []

    # Check structuring from unstructured data
    c2 = config.structure({
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
    with pytest.raises(config.ConfigError):
        config.structure({
            "a": [
                {"x": None},
            ],
        }, Config)


def test_config_nested_map():
    class Inner(config.Config):
        x = config.option(int, default=1, help="")
        y = config.option(int, default=2, help="")

    class Config(config.Config):
        a = config.option_map(Inner, help="")

    # Check default value
    c1 = config.structure({}, Config)
    assert c1.a == {}

    # Check structuring from unstructured data
    c2 = config.structure({
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
    with pytest.raises(config.ConfigError):
        config.structure({
            "a": {
                "b": {"x": None},
            },
        }, Config)


def test_config_option_example():
    class Config(config.Config):
        a = config.option(int, default=1, example=2, help="default and example values")
        b = config.option(int, default=lambda: 3, example=lambda: 4, help="default and example callables")
        c = config.option(int, default=5, help="only default")
        d = config.option(int, example=lambda: 6, help="only example")
        e = config.option_list(int, default=[1, 2, 3], example=[4, 5, 6], help="list: default and example values")
        f = config.option_list(int, default=[1, 2, 3], help="list: only default")
        g = config.option_list(int, example=[4, 5, 6], help="list: only example")
        h = config.option_map(int, default={"x": 1}, example={"x": 2}, help="map: default and example values")
        i = config.option_map(int, default={"x": 1}, help="map: only default")
        j = config.option_map(int, example={"x": 2}, help="map: only example")

    c1 = Config()
    assert c1.a == 1
    assert c1.b == 3
    assert c1.c == 5
    assert c1.d is None
    assert c1.e == [1, 2, 3]
    assert c1.f == [1, 2, 3]
    assert c1.g == []
    assert c1.h == {"x": 1}
    assert c1.i == {"x": 1}
    assert c1.j == {}

    c2 = config.make_example(Config)
    assert c2.a == 2
    assert c2.b == 4
    assert c2.c == 5
    assert c2.d == 6
    assert c2.e == [4, 5, 6]
    assert c2.f == [1, 2, 3]
    assert c2.g == [4, 5, 6]
    assert c2.h == {"x": 2}
    assert c2.i == {"x": 1}
    assert c2.j == {"x": 2}


def test_config_option_wordlist():
    class Config(config.Config):
        a = config.option(config.WordList, help="")
        b = config.option(config.WordList, help="")
        c = config.option(config.WordList, default="foo bar baz", help="")
        d = config.option(config.WordList, default=["ab", "cd", "ef"], help="")
        e = config.option_list(config.WordList, help="")
        f = config.option_map(config.WordList, help="")

    c = config.structure({
        "a": "foo bar baz",
        "b": ["ab", "cd", "ef"],
        "e": ["foo bar baz", ["ab", "cd", "ef"]],
        "f": {"x": "foo bar baz", "y": ["ab", "cd", "ef"]},
    }, Config)
    assert c.a == ["foo", "bar", "baz"]
    assert c.b == ["ab", "cd", "ef"]
    assert c.c == ["foo", "bar", "baz"]
    assert c.d == ["ab", "cd", "ef"]
    assert c.e == [["foo", "bar", "baz"], ["ab", "cd", "ef"]]
    assert c.f == {"x": ["foo", "bar", "baz"], "y": ["ab", "cd", "ef"]}


def assert_valid_toml(s):
    try:
        toml.loads(s)
    except Exception as e:
        pytest.fail("error loading TOML: %s" % (e,))


def assert_toml_equal(a, b):
    if isinstance(a, str):
        a = [_.rstrip() for _ in a.split("\n") if _]
    if isinstance(b, str):
        b = [_.rstrip() for _ in b.split("\n") if _]
    assert a == b


CONFIG_GENERATOR_TESTS = []


@CONFIG_GENERATOR_TESTS.append
def _test_config_generator_simple():
    class Config(config.Config):
        a = config.option(int, default=12, help="int with default value")
        b = config.option(int, example=22, help="int with example value")
        c = config.option(int, help="int with no default value")
        d = config.option(int, help="")  # No help text

    return Config, [
        "## int with default value",
        "a = 12",
        "## int with example value",
        "b = 22",
        "## int with no default value",
        "# c =",
        # int with no help text
        "# d =",
    ]


@CONFIG_GENERATOR_TESTS.append
def _test_config_generator_simple_list():
    class Config(config.Config):
        a = config.option_list(int, default=[1, 2, 3], help="list of ints with default value")
        b = config.option_list(int, help="list of ints with no default value")

    return Config, [
        "## list of ints with default value",
        "a = [ 1, 2, 3,]",
        "## list of ints with no default value",
        "b = []",
    ]


@CONFIG_GENERATOR_TESTS.append
def _test_config_generator_simple_map():
    class Config(config.Config):
        a = config.option_map(int, default={"x": 1, "y": 2}, help="map of ints with default value")
        b = config.option_map(int, help="map of ints with no default value")

    return Config, [
        "## map of ints with default value",
        "a.x = 1",
        "a.y = 2",
        "## map of ints with no default value",
        "# b._key_ = _value_",
    ]


@CONFIG_GENERATOR_TESTS.append
def _test_config_generator_structure():
    class Inner(config.Config):
        x = config.option(int, default=1, help="")

    class Config(config.Config):
        a = config.option(Inner, help="no default")
        b = config.option(Inner, default=Inner(dict(x=100)), help="default value")
        c = config.option(Inner, default=lambda: Inner(dict(x=200)), help="default callable")

    return Config, [
        "## no default",
        "# [a]",
        "## default value",
        "[b]",
        "x = 100",
        "## default callable",
        "[c]",
        "x = 200",
    ]


@CONFIG_GENERATOR_TESTS.append
def _test_config_generator_structure_list():
    class Inner(config.Config):
        x = config.option(int, help="")

    class Config(config.Config):
        a = config.option_list(Inner, help="no default")
        b = config.option_list(Inner, default=[Inner(dict(x=10)), Inner(dict(x=20))], help="default value")

    return Config, [
        "## no default",
        "# [[a]]",
        "## default value",
        "[[b]]",
        "x = 10",
        "[[b]]",
        "x = 20",
    ]


@CONFIG_GENERATOR_TESTS.append
def _test_config_generator_structure_map():
    class Inner(config.Config):
        x = config.option(int, help="")

    class Config(config.Config):
        a = config.option_map(Inner, help="no default")
        b = config.option_map(Inner, default={"i": Inner(dict(x=10)), "j": Inner(dict(x=20))}, help="default value")

    return Config, [
        "## no default",
        "# [a._key_]",
        "## default value",
        "[b.i]",
        "x = 10",
        "[b.j]",
        "x = 20",
    ]


@CONFIG_GENERATOR_TESTS.append
def _test_config_generator_complex_nesting():
    class InnerB(config.Config):
        a = config.option(int, default=1, help="")

    class InnerA(config.Config):
        a = config.option_list(InnerB, default=[InnerB(), InnerB()], help="")
        b = config.option_map(InnerB, default={"x": InnerB(), "y": InnerB()}, help="")

    class Config(config.Config):
        a = config.option_list(InnerA, default=[InnerA(), InnerA()], help="")
        b = config.option_map(InnerA, default={"x": InnerA(), "y": InnerA()}, help="")

    return Config, [
        # Start first in list of InnerA instances
        "[[a]]",
        # First in list of InnerB instances
        "[[a.a]]",
        "a = 1",
        # Second in list of InnerB instances
        "[[a.a]]",
        "a = 1",
        # Map of InnerB instances
        "[a.b.x]",
        "a = 1",
        "[a.b.y]",
        "a = 1",
        # Start second in list of InnerA instances
        "[[a]]",
        "[[a.a]]",
        "a = 1",
        "[[a.a]]",
        "a = 1",
        "[a.b.x]",
        "a = 1",
        "[a.b.y]",
        "a = 1",
        # First item in map of InnerA instances
        "[b.x]",
        "[[b.x.a]]",
        "a = 1",
        "[[b.x.a]]",
        "a = 1",
        "[b.x.b.x]",
        "a = 1",
        "[b.x.b.y]",
        "a = 1",
        "[b.y]",
        "[[b.y.a]]",
        "a = 1",
        "[[b.y.a]]",
        "a = 1",
        "[b.y.b.x]",
        "a = 1",
        "[b.y.b.y]",
        "a = 1",
    ]


@CONFIG_GENERATOR_TESTS.append
def _test_config_generator_quoted_key():
    """Check keys that need to be quoted to be valid TOML."""
    class Inner(config.Config):
        a = config.option(int, default=1, help="")
        b = config.option_map(int, default={"?": 1, "#": 2, "[": 3}, help="")

    class Config(config.Config):
        a = config.option_map(Inner, default={"?": Inner(), "#": Inner(), "[": Inner()}, help="")
        b = config.option_map(int, default={"?": 1, "#": 2, "[": 3}, help="")

    return Config, [
        # Simple map of Config.b first
        'b."?" = 1',
        'b."#" = 2',
        'b."[" = 3',
        # Structure map of Config.a starts
        '[a."?"]',
        'a = 1',
        'b."?" = 1',
        'b."#" = 2',
        'b."[" = 3',
        '[a."#"]',
        'a = 1',
        'b."?" = 1',
        'b."#" = 2',
        'b."[" = 3',
        '[a."["]',
        'a = 1',
        'b."?" = 1',
        'b."#" = 2',
        'b."[" = 3',
    ]


@pytest.mark.parametrize("test_factory", CONFIG_GENERATOR_TESTS)
def test_config_generator(test_factory):
    cls, expected = test_factory()

    # From class: check it's valid TOML and matches the expected
    output_cls = config.generate_toml_example(cls)
    assert_valid_toml(output_cls)
    assert_toml_equal(output_cls, expected)

    # From instance: check it's valid TOML, matches the expected, and is unchanged by
    # the round trip from object to TOML to object
    obj = config.make_example(cls)
    output_obj = config.generate_toml_example(obj)
    assert_valid_toml(output_obj)
    assert_toml_equal(output_obj, expected)
    assert config.loads(output_obj, cls) == obj


def test_config_generator_commented():
    class Inner(config.Config):
        x = config.option(int, help="")

    class Config(config.Config):
        a = config.option_map(Inner, help="no default")
        b = config.option_map(Inner, default={"i": Inner(dict(x=10)), "j": Inner(dict(x=20))}, help="default value")

    expected = [
        "## no default",
        "# [a._key_]",
        "## default value",
        "# [b.i]",
        "# x = 10",
        "# [b.j]",
        "# x = 20",
    ]

    obj = config.make_example(Config)
    output = config.generate_toml_example(obj, commented=True)
    assert_valid_toml(output)
    assert_toml_equal(output, expected)


class TestExampleConfig:
    @pytest.fixture(params=csbot.plugin.find_plugins())
    def plugin_cls(self, request):
        """Generates a test for each available plugin."""
        if not config.is_config(getattr(request.param, "Config", None)):
            pytest.skip("plugin does not have Config class")
        return request.param

    @pytest.fixture
    def irc_client_class(self, plugin_cls):
        """Generate a bot class that contains only the plugin under test."""
        class Bot(csbot.core.Bot):
            available_plugins = csbot.plugin.build_plugin_dict([plugin_cls])
        return Bot

    @pytest.fixture
    def config_file(self, irc_client_class):
        """Generate an example config for the bot class which contains only the plugin under test."""
        cfg = io.StringIO()
        irc_client_class.write_example_config(cfg)
        cfg.seek(0)
        return cfg

    def test_example_config_is_valid(self, event_loop, irc_client_class, config_file, plugin_cls):
        """Test that the generated config can be loaded by the plugin under test."""
        bot = irc_client_class(config=toml.load(config_file), loop=event_loop)
        plugin_cls(bot)
