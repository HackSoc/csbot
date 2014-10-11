import ast
import operator as op
import math

from csbot.plugin import Plugin
from csbot.util import pairwise

# Available operators
operators = {
    # boolop
    ast.And: op.and_,
    ast.Or: op.or_,
    # operator
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Mod: op.mod,
    ast.BitOr: op.or_,
    ast.BitXor: op.xor,
    ast.BitAnd: op.and_,
    ast.FloorDiv: op.floordiv,
    # unaryop
    ast.Invert: op.inv,
    ast.Not: op.not_,
    ast.UAdd: op.pos,
    ast.USub: op.neg,
    # cmpop
    ast.Eq: op.eq,
    ast.NotEq: op.ne,
    ast.Lt: op.lt,
    ast.LtE: op.le,
    ast.Gt: op.gt,
    ast.GtE: op.ge,
    ast.Is: op.is_,
    ast.IsNot: op.is_not,
}

def limited_power(a, b):
    """A limited power function to make sure that
    commands do not take too long to process.
    """
    if any(abs(n) > 1000 for n in [a, b]):
        raise OverflowError("{}**{} is too big".format(a, b))
    return op.pow(a, b)

operators[ast.Pow] = limited_power

constants = {
    "e": math.e,
    "pi": math.pi,
    "π": math.pi,
    "F": 1.2096,            # Barrucadu's Constant (microfortnights in a second)
    "c": 299792458,         # m s-1
    "G": 6.6738480e-11,     # m3 kg-1 s-2
    "h": 6.6260695729e-34,  # J s
    "N": 6.0221412927e23,   # mol-1
}

def calc_eval(node):
    """Actually do the calculation.
    """
    # ast.Load is always preceded by something else
    assert not isinstance(node, ast.Load)

    if isinstance(node, ast.Expr):  # Top level expression
        return calc_eval(node.value)
    elif isinstance(node, ast.Name):  # <constant>
        if node.id in constants:
            return constants[node.id]
        else:
            raise NotImplementedError(node.id)
    elif isinstance(node, ast.NameConstant):
        return node.value
    elif isinstance(node, ast.Num):  # <number>
        return node.n
    elif (isinstance(node, ast.operator) or
          isinstance(node, ast.unaryop) or
          isinstance(node, ast.cmpop)):  # <operator>
        if type(node) in operators:
            return operators[type(node)]
        elif isinstance(node, ast.LShift) or isinstance(node, ast.RShift):
            raise ValueError("cannot use bitshifting")
        else:
            raise KeyError(type(node).__name__.lower())
    elif isinstance(node, ast.UnaryOp):  # <operator> <operand>
        return calc_eval(node.op)(calc_eval(node.operand))
    elif isinstance(node, ast.BinOp):  # <left> <operator> <right>
        return calc_eval(node.op)(calc_eval(node.left), calc_eval(node.right))
    elif isinstance(node, ast.Compare):  # boolean comparisons are more tricky
        comparisons = zip(node.ops, pairwise([node.left] + node.comparators))
        return all(calc_eval(op)(calc_eval(left), calc_eval(right)) for op, (left, right) in comparisons)
    else:
        raise TypeError(node)


class Calc(Plugin):
    """A plugin that calculates things.
    Heavily based on http://stackoverflow.com/a/9558001/995325
    """

    def _calc(self, calc_str):
        """Start the calculation, and handle any exceptions.
        Returns a string of the answer.
        """

        if not calc_str:
            return "You want to calculate something? Type in an expression then!"
        try:
            res = calc_eval(ast.parse(calc_str).body[0])
            res = str(res)
            if len(res) > 300:
                raise OverflowError("result is too long")
            return res
        except KeyError as ex:
            return "Error, invalid operator {}".format(str(ex))
        except (OverflowError, ValueError, ZeroDivisionError) as ex:
            # 1 ** 100000, 1 << -1, 1 / 0
            return "Error, {}".format(str(ex))
        except NotImplementedError as ex:  # "sgdsdg + 3"
            return "Error, unknown or invalid constant '{}'".format(str(ex))
        except (TypeError, SyntaxError):  # "1 +"
            return "Error, '{}' is not a valid calculation".format(calc_str)


    @Plugin.command('calc')
    def do_some_calc(self, e):
        """
        What? You don't have a calculator handy?
        """
        e.protocol.msg(e["reply_to"], self._calc(e["data"]))
