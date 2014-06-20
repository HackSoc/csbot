# -*- coding: utf-8 -*-
import ast
import operator as op
import math

from csbot.plugin import Plugin

# Available operators
operators = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
             ast.Div: op.truediv, ast.Pow: None, ast.BitXor: op.xor}

def limited_power(a, b):
    """
    A limited power function to make sure that
    commands do not take too long to process.
    """
    if any(abs(n) > 100 for n in [a, b]):
        raise ValueError(a, b)
    return op.pow(a, b)

operators[ast.Pow] = limited_power

constants = {
    "e": math.e,
    "pi": math.pi,
    u"π": math.pi,
    "F": 1.2096,  # Barrucadu's Constant (microfortnights in a second)
    "c": 299792458,  # m*(s**-1)
    "G": 6.6738480*10**-11,  # (m**3)*(kg**-1)*(s**-2)
    "h": 6.6260695729*10**-34,  # J*s
    "N": 6.0221412927*10**23  # mol**-1
}

def calc_eval(node):
    """
    Actually do the calculation.
    """
    if isinstance(node, ast.Expr):  # Top level expression
        return calc_eval(node.value)
    elif isinstance(node, ast.Load):  # <constant>
        return
    elif isinstance(node, ast.Name):  # (actual) <constant>
        if str(node.id) in constants:
            return constants[str(node.id)]
        else:
            raise NotImplementedError(node.id)
    elif isinstance(node, ast.Num):  # <number>
        return node.n
    elif isinstance(node, ast.operator):  # <operator>
        return operators[type(node)]
    elif isinstance(node, ast.BinOp):  # <left> <operator> <right>
        return calc_eval(node.op)(calc_eval(node.left), calc_eval(node.right))
    else:
        raise TypeError(node)


class Calc(Plugin):
    """
    A plugin that calculates things.
    Heavily based on http://stackoverflow.com/a/9558001/995325
    """

    def _calc(self, calc_str):
        """
        Start the calculation, and handle any exceptions.
        Returns a string of the answer.
        """

        if not calc_str:
            return "You want to calculate something? Type in an expression then, silly!"
        try:
            return str(calc_eval(ast.parse(calc_str).body[0]))
        except ValueError as ex:
            x, y = ex.args
            return "Error, {}**{} is too big".format(x, y)
        except ZeroDivisionError:  # "1 / 0"
            return "Silly, you cannot divide by 0"
        except NotImplementedError as ex:  # "sgdsdg + 3"
            return "Unknown or invalid constant \"{}\"".format(ex.args)
        except (TypeError, SyntaxError):  # "1 +"
            return "Error, \"{}\" is not a valid calculation".format(calc_str)


    @Plugin.command('calc')
    def do_some_calc(self, e):
        """
        What? You don't have a calculator handy?
        """
        e.protocol.msg(e["reply_to"], self._calc(e["data"]))
