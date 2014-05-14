import ast
import operator as op

from csbot.plugin import Plugin


class Calc(Plugin):
    """
    A plugin that calculates things.
    Heavily based on http://stackoverflow.com/a/9558001/995325
    """

    # Available operators
    operators = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
                 ast.Div: op.truediv, ast.Pow: None, ast.BitXor: op.xor}

    def _power(self, a, b):
        """
        A limited power function to make sure that
        commands do not take too long to process.
        """
        if any(abs(n) > 100 for n in [a, b]):
            raise ValueError((a, b))
        return op.pow(a, b)

    operators[ast.Pow] = _power

    def _eval(self, node):
        """
        Actually do the calculation.
        """
        if isinstance(node, ast.Num):  # <number>
            return node.n
        elif isinstance(node, ast.operator):  # <operator>
            return self.operators[type(node)]
        elif isinstance(node, ast.BinOp):  # <left> <operator> <right>
            return self._eval(node.op)(self._eval(node.left), self._eval(node.right))
        else:
            raise TypeError(node)

    def _calc(self, calc_str):
        """
        Start the calculation.
        """
        return self._eval(ast.parse(calc_str).body[0].value)

    @Plugin.command('calc')
    def do_some_calc(self, e):
        """
        Ask and you shall recieve.
        """
        try:
            answer = self._calc(e["data"])
        except TypeError:
            answer = "Invalid calculation!"
        except ValueError:
            answer = "Too many powers!"
        finally:
            e.protocol.msg(e["reply_to"], str(answer))
