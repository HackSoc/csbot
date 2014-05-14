import ast
import operator as op

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

def calc_eval(node):
    """
    Actually do the calculation.
    """
    if isinstance(node, ast.Num):  # <number>
        return node.n
    elif isinstance(node, ast.operator):  # <operator>
        return operators[type(node)]
    elif isinstance(node, ast.BinOp):  # <left> <operator> <right>
        return calc_eval(node.op)(calc_eval(node.left), calc_eval(node.right))
    elif isinstance(node, ast.Name):
        raise NotImplementedError
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
        try:
            return str(calc_eval(ast.parse(calc_str).body[0].value))
        except ValueError as ex:
            x, y = ex.args
            return "Error, {}**{} is too big".format(x, y)
        except ZeroDivisionError:  # "1 / 0"
            return "Silly, you cannot divide by 0"
        except NotImplementedError:  # "pi + 3"
            return "You cannot yet use mathematical constants"
        except (TypeError, SyntaxError):  # "1 +"
            return "Error, \"{}\" is not a valid calculation".format(calc_str)


    @Plugin.command('calc')
    def do_some_calc(self, e):
        """
        What? You don't have a calculator handy?
        """
        e.protocol.msg(e["reply_to"], self._calc(e["data"]))
