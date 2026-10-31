"""Math tools: an engineering calculator and unit conversion.

Design rules (same as time_tools.py):
- The model writes an expression or names units; code does every calculation.
- Expressions are parsed with `ast` and only whitelisted names are allowed.
  `eval()` is never used, so the model cannot run arbitrary Python.
- Docstrings are written for the model. "#" comments are for human readers.
"""

from __future__ import annotations

import ast
import cmath
import difflib
import io
import math
import operator
import re
import statistics
import tokenize

import scipy.constants as sc

from .tools import ToolRegistry

# ---------- calculator ----------

_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
    ast.BitAnd: operator.and_,
    ast.BitOr: operator.or_,
    ast.BitXor: operator.xor,  # only reached for ^ next to hex/binary literals, see _rewrite_caret
}
_UNARY_OPS = {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Invert: operator.invert}

_MAX_EXPONENT = 10_000
_MAX_FACTORIAL = 1_000


def _sqrt(x):
    return cmath.sqrt(x) if isinstance(x, complex) or x < 0 else math.sqrt(x)


def _log(x, base=None):
    return math.log(x) if base is None else math.log(x, base)


def _factorial(n):
    if n != int(n) or n < 0 or n > _MAX_FACTORIAL:
        raise ValueError(f"factorial needs an integer between 0 and {_MAX_FACTORIAL}")
    return math.factorial(int(n))


def _phasor(magnitude, angle_degrees):
    return cmath.rect(magnitude, math.radians(angle_degrees))


def _to_base(n, base):
    n, base = int(n), int(base)
    if base == 2:
        return bin(n)
    if base == 8:
        return oct(n)
    if base == 16:
        return hex(n)
    if not 2 <= base <= 36:
        raise ValueError("base must be between 2 and 36")
    digits, sign, n = "", "-" if n < 0 else "", abs(n)
    while True:
        n, r = divmod(n, base)
        digits = "0123456789abcdefghijklmnopqrstuvwxyz"[r] + digits
        if n == 0:
            return sign + digits


_MAX_SEQUENCE = 100_000
_SEQUENCE_HINT = (
    "For long products or sums write prod(seq(start, end)) or sum(seq(start, end)), "
    "e.g. 1 - prod(seq(343, 365)) / 365**23. perm(n, k) = n*(n-1)*...*(n-k+1)."
)


def _seq(start, end, step=1):
    # Inclusive on both ends, like math notation: seq(343, 365) has 23 numbers.
    if step == 0:
        raise ValueError("step cannot be 0")
    count = math.floor((end - start) / step) + 1
    if count > _MAX_SEQUENCE:
        raise ValueError(f"sequence longer than {_MAX_SEQUENCE} numbers")
    return [start + i * step for i in range(max(count, 0))]


def _many(fn):
    # min(1, 2, 3) and min([1, 2, 3]) should both work.
    return lambda *args: fn(args[0]) if len(args) == 1 and isinstance(args[0], list) else fn(args)


FUNCTIONS = {
    # basic
    "abs": abs, "round": round, "floor": math.floor, "ceil": math.ceil,
    "min": _many(min), "max": _many(max), "sum": _many(sum), "prod": _many(math.prod),
    "seq": _seq, "len": len, "mean": _many(statistics.fmean), "pow": math.pow,
    # powers, roots, logarithms
    "sqrt": _sqrt, "cbrt": math.cbrt, "exp": math.exp,
    "ln": math.log, "log": _log, "log10": math.log10, "log2": math.log2,
    # trigonometry in radians
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan, "atan2": math.atan2,
    "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
    "asinh": math.asinh, "acosh": math.acosh, "atanh": math.atanh,
    # trigonometry in degrees (models often confuse degrees and radians)
    "sind": lambda x: math.sin(math.radians(x)),
    "cosd": lambda x: math.cos(math.radians(x)),
    "tand": lambda x: math.tan(math.radians(x)),
    "asind": lambda x: math.degrees(math.asin(x)),
    "acosd": lambda x: math.degrees(math.acos(x)),
    "atand": lambda x: math.degrees(math.atan(x)),
    "radians": math.radians, "degrees": math.degrees, "hypot": math.hypot,
    # combinatorics and integers
    "factorial": _factorial, "comb": math.comb, "perm": math.perm, "gcd": math.gcd, "lcm": math.lcm,
    # decibels (electronics, telecom)
    "db": lambda power_ratio: 10 * math.log10(power_ratio),
    "db20": lambda amplitude_ratio: 20 * math.log10(amplitude_ratio),
    "from_db": lambda db: 10 ** (db / 10),
    "from_db20": lambda db: 10 ** (db / 20),
    "dbm_to_watts": lambda dbm: 10 ** ((dbm - 30) / 10),
    "watts_to_dbm": lambda watts: 10 * math.log10(watts) + 30,
    "dbw_to_watts": lambda dbw: 10 ** (dbw / 10),
    "watts_to_dbw": lambda watts: 10 * math.log10(watts),
    # complex numbers (AC circuits)
    "real": lambda z: complex(z).real, "imag": lambda z: complex(z).imag,
    "conj": lambda z: complex(z).conjugate(),
    "phase": lambda z: cmath.phase(z), "phased": lambda z: math.degrees(cmath.phase(z)),
    "phasor": _phasor,
    # number bases and bits (computer engineering)
    "to_base": _to_base, "from_base": lambda text, base: int(str(text), int(base)),
    "xor": lambda a, b: int(a) ^ int(b),
}

# Names models use for functions that exist under another name.
# Run 8: the model wrote product(...) instead of prod(...).
FUNCTION_ALIASES = {
    "product": "prod", "average": "mean", "avg": "mean", "power": "pow",
    "arcsin": "asin", "arccos": "acos", "arctan": "atan", "arctan2": "atan2",
    "square_root": "sqrt", "choose": "comb", "ncr": "comb", "npr": "perm", "fact": "factorial",
    "log_e": "ln", "absolute": "abs",
}

# Functions whose result is an angle in radians.
_RADIAN_RESULTS = {"asin", "acos", "atan", "atan2", "phase"}

CONSTANTS = {
    "pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf, "j": 1j,
    "speed_of_light": sc.c,
    "standard_gravity": sc.g,
    "gravitational_constant": sc.G,
    "planck": sc.h,
    "boltzmann": sc.k,
    "avogadro": sc.N_A,
    "gas_constant": sc.R,
    "elementary_charge": sc.e,
    "electron_mass": sc.m_e,
    "vacuum_permittivity": sc.epsilon_0,
    "vacuum_permeability": sc.mu_0,
    "stefan_boltzmann": sc.sigma,
}


# Functions that take a whole list (aggregate). Every other function is applied
# element by element when given a list, like numpy: exp([1, 2]) = [e, e**2].
_LIST_FUNCTIONS = {"min", "max", "sum", "prod", "len", "mean", "seq"}
_LOOP_NAMES = {"i", "k", "n", "x", "t", "m"}


def _broadcast(fn, *args):
    # Run 9: the model wrote exp([2.0, 1.0, 0.1]) / sum(exp([2.0, 1.0, 0.1])) for softmax.
    lists = [a for a in args if isinstance(a, list)]
    if not lists:
        return fn(*args)
    length = len(lists[0])
    if any(len(a) != length for a in lists):
        raise ValueError("lists in one operation must have the same length")
    return [_broadcast(fn, *[a[i] if isinstance(a, list) else a for a in args]) for i in range(length)]


def _evaluate(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and node.value is Ellipsis:
        # Run 7-8: the model wrote "(365/365) * (364/365) * ... * (343/365)".
        raise ValueError(f"'...' cannot be used. {_SEQUENCE_HINT}")
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, complex, str)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in CONSTANTS:
            return CONSTANTS[node.id]
        # Run 7: the model wrote "-R * C * ln(1 - 0.9)" with symbols instead of numbers.
        # Run 9: it wrote seq(365 - i, i, 0, 22) with a loop variable.
        loop_hint = f" {_SEQUENCE_HINT}" if node.id in _LOOP_NAMES else ""
        raise ValueError(
            f"unknown name '{node.id}'. Variables are not supported: put the numbers in "
            f"(e.g. R = 10 kOhm -> 10000).{loop_hint} Known constants: {', '.join(CONSTANTS)}"
        )
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_evaluate(item) for item in node.elts]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _broadcast(_UNARY_OPS[type(node.op)], _evaluate(node.operand))
    if isinstance(node, ast.BinOp):
        op = node.op
        if type(op) not in _BINARY_OPS:
            raise ValueError(f"operator {type(op).__name__} is not allowed")
        left, right = _evaluate(node.left), _evaluate(node.right)
        exponents = right if isinstance(right, list) else [right]
        if isinstance(op, (ast.Pow, ast.LShift)) and any(
            isinstance(r, (int, float)) and abs(r) > _MAX_EXPONENT for r in exponents
        ):
            raise ValueError(f"exponent larger than {_MAX_EXPONENT} is not allowed")
        return _broadcast(_BINARY_OPS[type(op)], left, right)
    if isinstance(node, ast.Call):
        name = getattr(node.func, "id", None)
        name = FUNCTION_ALIASES.get((name or "").lower(), name)
        if not isinstance(node.func, ast.Name) or name not in FUNCTIONS:
            raise ValueError(f"function '{name or 'this call'}' is not available. Available: {', '.join(FUNCTIONS)}")
        if node.keywords:
            raise ValueError("keyword arguments are not supported; pass values in order")
        args = [_evaluate(arg) for arg in node.args]
        if name in _LIST_FUNCTIONS:
            return FUNCTIONS[name](*args)
        return _broadcast(FUNCTIONS[name], *args)
    raise ValueError(f"'{ast.unparse(node)}' is not allowed in an expression")


def _format_number(value) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return f"{value:.12g}"
    if isinstance(value, complex):
        if abs(value.imag) < 1e-15:
            return _format_number(value.real)
        sign = "+" if value.imag >= 0 else "-"
        rect = f"{_format_number(value.real)} {sign} {_format_number(abs(value.imag))}j"
        return f"{rect} (magnitude {_format_number(abs(value))}, angle {_format_number(math.degrees(cmath.phase(value)))} degrees)"
    if isinstance(value, list):
        return "[" + ", ".join(_format_number(v) for v in value) + "]"
    return str(value)


_BIT_LITERAL = re.compile(r"0[xXbBoO]")


def _rewrite_caret(expression: str) -> tuple[str, str]:
    """Decide what each ^ means. Returns (rewritten expression, note for the model).

    Run 6 showed both uses: "10^(30/10)" meant a power, "0xFF ^ 0b1010" meant XOR.
    Rule: ^ next to a hex/binary/octal literal is XOR; otherwise it is a power.
    This runs on tokens, not on the syntax tree, because in Python ^ binds more
    loosely than +, so "3^2 + 4^2" would otherwise be parsed as 3 ^ (2 + 4) ^ 2.
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(expression).readline))
    except (tokenize.TokenError, SyntaxError):
        return expression, ""
    rebuilt, meanings = [], set()
    for i, tok in enumerate(tokens):
        if tok.type == tokenize.OP and tok.string == "^":
            neighbors = [tokens[i - 1].string if i > 0 else "", tokens[i + 1].string if i + 1 < len(tokens) else ""]
            if any(_BIT_LITERAL.match(n) for n in neighbors):
                meanings.add("bitwise XOR")
                rebuilt.append((tok.type, "^"))
            else:
                meanings.add("power")
                rebuilt.append((tok.type, "**"))
        else:
            rebuilt.append((tok.type, tok.string))
    if not meanings:
        return expression, ""
    note = f" (note: ^ was read as {' and '.join(sorted(meanings))}; use ** for power or xor(a, b) for XOR to be explicit)"
    return tokenize.untokenize(rebuilt).strip(), note


def evaluate_expression(expression: str) -> str:
    rewritten, note = _rewrite_caret(expression.strip())
    try:
        tree = ast.parse(rewritten, mode="eval")
    except SyntaxError:
        # Run 6: the model sent "(100 km/h - 0) / 8 s" to the plain calculator six times.
        raise ValueError(
            f"cannot parse '{expression}'. Use numbers, operators and functions only; loops are not supported. "
            f"{_SEQUENCE_HINT} If the expression has units (km/h, s, N, V...), use calculate_with_units instead."
        ) from None
    value = _evaluate(tree)
    body = tree.body
    if (
        isinstance(body, ast.Call)
        and isinstance(body.func, ast.Name)
        and body.func.id in _RADIAN_RESULTS
        and isinstance(value, (int, float))
    ):
        # Run 6: the model got 0.1863 rad from atan() and converted it to degrees
        # in its head (10.68 instead of 10.67). Give both units so it never has to.
        note = f" radians = {_format_number(math.degrees(value))} degrees" + note
    return _format_number(value) + note


# ---------- units ----------

_UNIT_REGISTRY = None

# Symbols and Korean units that pint does not read directly.
_UNIT_ALIASES = {
    "℃": "degC", "°c": "degC", "°C": "degC", "celsius": "degC",
    "℉": "degF", "°f": "degF", "°F": "degF", "fahrenheit": "degF",
    "평": "pyeong", "근": "geun", "돈": "don", "kph": "km/h",
    "²": "**2", "³": "**3", "·": "*", "×": "*", "µ": "u", "μ": "u",
}


def _ureg():
    # Loading pint takes a moment, so it is created once, on first use.
    global _UNIT_REGISTRY
    if _UNIT_REGISTRY is None:
        import pint

        ureg = pint.UnitRegistry(autoconvert_offset_to_baseunit=True)
        ureg.define("pyeong = 400 / 121 * meter ** 2")  # Korean floor area unit
        ureg.define("geun = 600 * gram")  # Korean weight unit for meat
        ureg.define("don = 3.75 * gram")  # Korean weight unit for gold
        _UNIT_REGISTRY = ureg
    return _UNIT_REGISTRY


def _normalize_unit(text: str) -> str:
    text = text.strip()
    if text in _UNIT_ALIASES:
        return _UNIT_ALIASES[text]
    for symbol, replacement in _UNIT_ALIASES.items():
        if len(symbol) == 1 and not symbol.isalpha():
            text = text.replace(symbol, replacement)
    return _UNIT_ALIASES.get(text.lower(), text)


def convert(value: float, from_unit: str, to_unit: str) -> str:
    import pint

    ureg = _ureg()
    src, dst = _normalize_unit(from_unit), _normalize_unit(to_unit)
    try:
        result = ureg.Quantity(value, src).to(dst)
    except pint.errors.UndefinedUnitError as exc:
        bad = str(exc).split("'")[1] if "'" in str(exc) else str(exc)
        matches = difflib.get_close_matches(bad, [u for u in dir(ureg) if not u.startswith("_")], n=3)
        hint = f" Did you mean: {', '.join(matches)}?" if matches else ""
        raise ValueError(f"unknown unit '{bad}'.{hint}") from None
    except pint.errors.DimensionalityError as exc:
        raise ValueError(
            f"cannot convert {from_unit} ({exc.dim1}) to {to_unit} ({exc.dim2}); they measure different things"
        ) from None
    return f"{_format_number(float(value))} {from_unit} = {_format_number(float(result.magnitude))} {to_unit}"


# A number followed by a unit, e.g. "8 s", "4 ohm", "10 m^2", "1.5e-3 kg".
_QUANTITY = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*([A-Za-z_°µΩ][A-Za-z_°µΩ0-9]*(?:\s*(?:\*\*|\^)\s*-?\d+)?)"
)


def _group_quantities(expression: str) -> str:
    # pint reads "12 V / 4 ohm" as (12 V / 4) * ohm. Wrapping each number+unit
    # pair in parentheses gives the meaning people expect: (12 V) / (4 ohm).
    return _QUANTITY.sub(lambda m: f"({m.group(1)} {m.group(2)})", expression)


_FUNCTION_CALL = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def _closing_paren(text: str, open_index: int) -> int:
    depth = 0
    for i in range(open_index, len(text)):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0:
            return i
    raise ValueError("unbalanced parentheses")


def _split_arguments(text: str) -> list[str]:
    parts, depth, current = [], 0, ""
    for ch in text:
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    return parts + [current]


def _quantity_text(quantity) -> str:
    magnitude = repr(float(quantity.magnitude))
    return f"({magnitude})" if quantity.dimensionless else f"({magnitude} * {quantity.units})"


def _evaluate_quantity(text: str):
    """Evaluate a unit formula with pint, handling calculator functions first.

    pint has no functions. Run 6 used sqrt(...) and Run 7 used ln(...) inside unit
    formulas, so each call is evaluated innermost-first and replaced by its value:
    sqrt keeps units (sqrt(4 m**2) = 2 m); every other function needs a number
    without units, e.g. ln(10) or exp(-(1 s) / ((10 kohm) * (47 uF))).
    """
    ureg = _ureg()
    while True:
        match = next(
            (m for m in _FUNCTION_CALL.finditer(text) if m.group(1) in FUNCTIONS or m.group(1).lower() in FUNCTION_ALIASES),
            None,
        )
        if match is None:
            break
        name = FUNCTION_ALIASES.get(match.group(1).lower(), match.group(1))
        open_index = match.end() - 1
        close_index = _closing_paren(text, open_index)
        args = [_evaluate_quantity(a) for a in _split_arguments(text[open_index + 1 : close_index])]
        if name == "sqrt":
            value = args[0] ** 0.5
        else:
            plain = []
            for arg in args:
                if not arg.dimensionless:
                    raise ValueError(f"{name}() needs a value without units, but got {arg.units}")
                plain.append(float(arg.to("dimensionless").magnitude))
            number = FUNCTIONS[name](*plain)
            if not isinstance(number, (int, float)):
                raise ValueError(f"{name}() did not return a real number")
            value = ureg.Quantity(float(number))
        text = text[: match.start()] + _quantity_text(value) + text[close_index + 1 :]
    quantity = ureg.parse_expression(_group_quantities(text))
    return quantity if isinstance(quantity, ureg.Quantity) else ureg.Quantity(quantity)


# A lone letter used as a variable: after an operator/bracket/start, not after a number or "/".
# Run 9: "ln(10) * R * C" was read as gas constant * coulomb.
_BARE_SYMBOL = re.compile(r"(?:^|[*+\-(,])\s*([A-Za-z])(?![A-Za-z0-9_(])")
_SYMBOL_MEANINGS = {"R": "the gas constant", "C": "coulomb", "c": "the speed of light", "L": "liter",
                    "V": "volt", "I": "an unknown name", "h": "hour", "t": "metric ton", "k": "the Boltzmann constant",
                    "F": "farad", "m": "meter", "s": "second", "g": "gram", "A": "ampere"}


def _variable_hint(expression: str) -> str:
    symbols = sorted({m.group(1) for m in _BARE_SYMBOL.finditer(expression)})
    if not symbols:
        return ""
    readings = ", ".join(f"{s} = {_SYMBOL_MEANINGS.get(s, 'a unit or constant')}" for s in symbols)
    return (
        f" Lone letters are read as units or constants here ({readings}), not as variables. "
        "Write each value as a number with its unit, e.g. (10 kΩ) * (47 µF) * ln(10)."
    )


# Plain names for common dimensions. Run 10: qwen3:8b saw "[length] / [time] ** 2"
# in an error, did not recognize it as an acceleration, and repeated the call.
_NAMED_DIMENSIONS = [
    ("an acceleration", "m/s**2"), ("a speed", "m/s"), ("a force", "N"), ("an energy or torque", "J"),
    ("a power", "W"), ("a pressure or stress", "Pa"), ("a length", "m"), ("a time", "s"), ("a mass", "kg"),
    ("an electric current", "A"), ("a voltage", "V"), ("a resistance", "ohm"), ("a capacitance", "F"),
    ("an inductance", "H"), ("a frequency", "Hz"), ("an electric charge", "C"), ("a temperature", "K"),
    ("an area", "m**2"), ("a volume", "m**3"), ("a density", "kg/m**3"), ("an energy per mass (J/kg = m²/s²)", "J/kg"),
    ("a momentum", "kg*m/s"), ("a plain number without units", "dimensionless"),
]


def _describe_dimension(dimensionality) -> str:
    ureg = _ureg()
    for name, unit in _NAMED_DIMENSIONS:
        if ureg.parse_units(unit).dimensionality == dimensionality:
            pretty = f"{ureg.parse_units(unit):~P}" or "no unit"
            return name if "(" in name else f"{name} ({pretty})"
    return f"a quantity with dimensions {dimensionality}"


# Run 10: both models got the link budget wrong (2 W treated as 2 dBm, or 10*log10(2) used as dBm).
_DECIBEL_HINT = (
    " Decibel values are added, not multiplied: received dBm = watts_to_dbm(transmit watts) + gains in dB - losses in dB. "
    "Use calculator, e.g. watts_to_dbm(2) + 10 + 3 - 100. Note 10*log10(watts) is dBW; dBm = dBW + 30."
)


def calculate_quantities(expression: str, to_unit: str = "") -> str:
    import pint

    ureg = _ureg()
    if re.search(r"(?<![A-Za-z_])\d*j\b", expression):
        # Run 6: the model put a complex j into a unit formula three times.
        raise ValueError(
            "complex numbers are not supported with units. Convert values to SI numbers "
            "(e.g. 50 mH -> 0.05) and use calculator, which supports 3+4j."
        )
    # Run 7 bug: replacing "Ω" with " ohm " turned "kΩ" into "k ohm", and pint reads
    # "k" as the Boltzmann constant. Replace without spaces so "kΩ" becomes "kohm".
    text = expression.replace("Ω", "ohm")
    for symbol, replacement in _UNIT_ALIASES.items():
        if len(symbol) == 1 and not symbol.isalpha():
            text = text.replace(symbol, replacement)
    decibel_hint = _DECIBEL_HINT if re.search(r"dB", expression + to_unit) else ""
    try:
        quantity = _evaluate_quantity(text)
        if to_unit.strip():
            target = ureg.parse_units(_normalize_unit(to_unit))
            if not decibel_hint and quantity.dimensionality != target.dimensionality:
                raise ValueError(
                    f"the formula gives {_describe_dimension(quantity.dimensionality)}, but '{to_unit}' is "
                    f"{_describe_dimension(target.dimensionality)}. Either change to_unit to a unit of "
                    f"{_describe_dimension(quantity.dimensionality)} or fix the formula.{_variable_hint(text)}"
                )
            result = quantity.to(target)
        else:
            result = quantity.to_base_units()
    except pint.errors.UndefinedUnitError as exc:
        name = str(exc).split("'")[1] if "'" in str(exc) else str(exc)
        matches = difflib.get_close_matches(name, [u for u in dir(ureg) if not u.startswith("_")], n=3)
        hint = f"unknown unit '{name}'." + (f" Did you mean: {', '.join(matches)}?" if matches else "")
        raise ValueError(hint + _variable_hint(text) + decibel_hint) from None
    except pint.errors.DimensionalityError as exc:
        raise ValueError(
            f"the result cannot be converted to {to_unit}. Check the formula.{_variable_hint(text)}{decibel_hint}"
        ) from None
    except ValueError as exc:
        if str(exc).startswith("the formula gives"):
            raise
        raise ValueError(f"cannot read '{expression}': {exc}{decibel_hint}") from None
    except (SyntaxError, TypeError, AttributeError, ZeroDivisionError) as exc:
        raise ValueError(f"cannot read '{expression}': {exc}{decibel_hint}") from None
    return f"{expression} = {_format_number(float(result.magnitude))} {result.units:~P}"


# ---------- tools ----------

def register_math_tools(registry: ToolRegistry) -> None:
    @registry.register
    def calculator(expression: str) -> str:
        """Engineering calculator for plain numbers. Always use it instead of doing math yourself. Not for dates or times. For values with units use calculate_with_units.
        Operators: + - * / // % ** (power), << >> & |, xor(a, b) for bitwise XOR. Complex numbers: 3+4j.
        Use numbers only, no variables. Hex/binary literals work as written: 0xFF, 0b1010.
        Lists work element by element: exp([2, 1, 0.1]) / sum(exp([2, 1, 0.1])) is softmax; round([0.6591, 0.2424], 2).
        Functions: sqrt cbrt exp ln log(x) log(x,base) log10 log2 pow abs round floor ceil min max sum prod mean len;
        seq(start, end, step) lists numbers from start to end inclusive, e.g. prod(seq(343, 365)), sum(seq(1, 100));
        sin cos tan asin acos atan atan2 sinh cosh tanh (radians) and sind cosd tand asind acosd atand (degrees; use these when the answer should be in degrees), radians degrees hypot;
        factorial comb(n, k) perm(n, k) (= n*(n-1)*...*(n-k+1)) gcd lcm;
        decibels: db db20 from_db from_db20 watts_to_dbm dbm_to_watts watts_to_dbw dbw_to_watts. Link budgets add dB values:
        received dBm = watts_to_dbm(transmit watts) + antenna gains (dB) - losses (dB), e.g. watts_to_dbm(2) + 10 + 3 - 100;
        real imag conj phase phased phasor(magnitude, angle_degrees); to_base(n, base) from_base('ff', 16) xor.
        Constants: pi e tau j speed_of_light standard_gravity gravitational_constant planck boltzmann avogadro gas_constant elementary_charge electron_mass vacuum_permittivity vacuum_permeability stefan_boltzmann.

        Args:
            expression: One expression, e.g. "sqrt(3**2 + 4**2)", "sind(30) * 10", "db(2)", "comb(45, 6)".
        """
        return evaluate_expression(expression)

    @registry.register
    def convert_units(value: float, from_unit: str, to_unit: str) -> str:
        # Run 7: the model passed a formula as the value: "50e3 / (pi * 0.01**2)".
        # Evaluate it with the calculator instead of failing.
        if isinstance(value, str):
            value = _evaluate(ast.parse(_rewrite_caret(value)[0], mode="eval"))
            if not isinstance(value, (int, float)):
                raise ValueError("value must be a real number")
        """Convert a value between units: length, mass, time, temperature, area, volume, speed, force, pressure, energy, power, torque, data size, and compound units like km/h or N*m. Korean units pyeong, geun, don are supported.

        Args:
            value: The number to convert. A plain arithmetic formula such as 50e3 / (pi * 0.01**2) also works.
            from_unit: Unit of the value, e.g. 'km/h', 'degC', 'psi', 'N*m', 'GB', 'pyeong', 'mile'.
            to_unit: Target unit, e.g. 'm/s', 'degF', 'bar', 'kgf*cm', 'MB', 'm**2', 'km'.
        """
        return convert(value, from_unit, to_unit)

    @registry.register
    def calculate_with_units(expression: str, to_unit: str = "") -> str:
        """Calculate a formula whose values have units, and get the answer in the unit you want. Use for physics and engineering formulas, e.g. acceleration, force, energy, power, current.

        Args:
            expression: Formula with a unit after each number, e.g. "(100 km/h) / (8 s)", "2 kg * 9.80665 m/s^2", "12 V / 4 ohm", "sqrt(2 * 9.80665 m/s**2 * 10 m)", "10 kΩ * 47 µF * ln(10)". Functions such as ln, exp, sind need values without units inside. Never use letters as variables (R, C); write numbers with units. No complex numbers here; use calculator for those.
            to_unit: Unit for the answer, e.g. 'm/s**2', 'N', 'A', 'kJ'. Empty gives SI base units.
        """
        return calculate_quantities(expression, to_unit)
