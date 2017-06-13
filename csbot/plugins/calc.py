import ast
import operator as op
import math

from csbot.plugin import Plugin
from csbot.util import pairwise


def is_too_long(n):
    # Don't care about floats
    return isinstance(n, int) and n != 0 and math.log10(abs(n)) > 127


def guarded_power(a, b):
    """A limited power function to make sure that
    commands do not take too long to process.
    """
    if any(abs(n) > 1000 for n in [a, b]):
        raise CalcError("would take too long to calculate")
    try:
        return op.pow(a, b)
    except OverflowError:
        raise CalcError("too large to represent as float")


def guarded_lshift(a, b):
    if not (isinstance(a, int) and isinstance(b, int)):
        raise CalcError("non-integer shift values")
    elif b.bit_length() > 64:
        # Only need to check how much the number is being shifted by
        raise CalcError("would take too long to calculate")
    return op.lshift(a, b)

def guarded_rshift(a, b):
    if not (isinstance(a, int) and isinstance(b, int)):
        raise CalcError("non-integer shift values")
    return op.rshift(a, b)

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
    ast.Pow: guarded_power,
    ast.LShift: guarded_lshift,
    ast.RShift: guarded_rshift,
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


def guarded_factorial(a):
    # Any larger than this would be too long to output regardless
    if a > 100:
        raise CalcError("would take too long to calculate")
    return math.factorial(a)


identifiers = {
    # Available constants
    "e": math.e,
    "pi": math.pi,
    "π": math.pi,
    "F": 1.2096,            # Barrucadu's Constant (seconds in a microfortnight)
    "c": 299792458,         # m s-1
    "G": 6.6738480e-11,     # m3 kg-1 s-2
    "h": 6.6260695729e-34,  # J s
    "N": 6.0221412927e23,   # mol-1

    # Available functions
    "ceil": math.ceil,
    "factorial": guarded_factorial,
    "floor": math.floor,
    "isfinite": math.isfinite,
    "isinf": math.isinf,
    "isnan": math.isnan,
    "exp": math.exp,
    "log": math.log,
    "sqrt": math.sqrt,
    # Trig
    "acos": math.acos,
    "asin": math.asin,
    "atan": math.atan,
    "cos": math.cos,
    "sin": math.sin,
    "tan": math.tan,
    "degrees": math.degrees,
    "deg": math.degrees,
    "radians": math.radians,
    "rad": math.radians,
}

class CalcEval(ast.NodeVisitor):
    def visit_Module(self, node):
        return self.visit(node.body[0]) # Special case, since we're only dealing with one-liners

    def visit_Expr(self, node):
        return self.visit(node.value) # Reimplementation needed or it goes via generic_visit

    def visit_BinOp(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)
        if node.op.__class__ in (ast.Mod, ast.Div, ast.FloorDiv) and right == 0:
            raise CalcError("division by zero")
        operator = operators[node.op.__class__]
        try:
            return operator(left, right)
        except TypeError:
            raise CalcError("invalid arguments")

    def visit_UnaryOp(self, node):
        operator = operators[node.op.__class__]
        operand = self.visit(node.operand)
        return operator(operand)

    def visit_Compare(self, node):
        comparisons = zip(node.ops, pairwise([node.left] + node.comparators))
        try:
            return all(operators[op.__class__](self.visit(left), self.visit(right)) for op, (left, right) in comparisons)
        except KeyError:
            raise CalcError("invalid operator")

    def visit_Call(self, node):
        args = [self.visit(arg) for arg in node.args]
        func = self.visit(node.func)
        try:
            return func(*args)
        except TypeError:
            raise CalcError("invalid arguments")
        except ValueError as e:
            raise CalcError(e)

    def visit_Name(self, node):
        try:
            return identifiers[node.id]
        except KeyError:
            raise CalcError("unknown constant or function")

    def visit_Num(self, node):
        return node.n

    def visit_NameConstant(self, node):
        return node.value

    def visit_Str(self, node):
        raise CalcError("invalid argument")

class CalcError(Exception):
    pass

class Calc(Plugin):
    """A plugin that calculates things.
    """

    def _calc(self, calc_str):
        """Start the calculation, and handle any exceptions.
        Returns a string of the answer.
        """

        if not calc_str:
            return "You want to calculate something? Type in an expression then!"

        try:
            res = CalcEval().visit(ast.parse(calc_str))
            if res is None:
                raise CalcError("invalid calculation")
            if is_too_long(res):
                raise CalcError("result too long to be printed")
            return str(res)
        except (CalcError, SyntaxError) as ex:
            return "Error, {}".format(str(ex))


    @Plugin.command('calc', help='For calculating, not interpreting')
    def do_some_calc(self, e):
        """What? You don't have a calculator handy?
        """
        e.reply(self._calc(e["data"]))
