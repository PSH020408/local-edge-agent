"""Arithmetic and statement checks for answers about tables and financial statements (Stage 6).

Why (Run 42, the Stage 6 baseline): the answer model did ratios and growth rates in its head and
was off in the last digit twice (19.48% for 19.50%, 28.95% for 28.94%), and every number it computed
was then flagged as "not in the document". Here the arithmetic is done by code:

- `fill_calculations` evaluates the [calc: ...] expressions the answer model is asked to write and
  puts the results in their place;
- `check_arithmetic` recomputes "a / b ≈ c" and "a − b = c" written out in an answer and corrects a
  wrong result;
- `statement_checks` adds up the totals of a statement found in the page text or in a table read
  from a picture (assets = liabilities + equity, gross profit = revenue − cost of sales, operating
  income = gross profit − operating expenses) and reports each check, so a wrong subtotal is found
  by code, not by the model.
"""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}

# A number as printed in statements: 1,234,567 / 12.5 / (4,480,835) / △301,146 / −0.6
_NUM = r"[(△−–-]?\s?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?|[(△−–-]?\s?\d+(?:\.\d+)?\)?"
_NUM_RE = re.compile(rf"(?<![\w.,])(?:{_NUM})(?![\w])")


def parse_number(text: str) -> float | None:
    """'1,234' -> 1234; '(4,480,835)' and '△301,146' -> negative; '~48' -> 48; '-' -> None."""
    t = text.strip().replace("~", "").replace("$", "").replace("%", "").strip()
    negative = t.startswith(("(", "△", "−", "–", "-")) or t.endswith(")")
    t = t.strip("()△−–- ")
    t = t.replace(",", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", t):
        return None
    value = float(t)
    return -value if negative else value


def safe_eval(expression: str) -> float:
    """+ − × ÷ and parentheses over plain numbers; anything else raises ValueError."""
    text = (expression.replace("×", "*").replace("÷", "/").replace("−", "-").replace("–", "-")
            .replace("x", "*").replace("X", "*"))
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)  # thousands separators
    text = text.replace("%", "")
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"not an arithmetic expression: {expression}") from exc

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = walk(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.left), walk(node.right))
        raise ValueError(f"not an arithmetic expression: {expression}")

    return walk(tree)


def format_number(value: float, decimals: int | None = None) -> str:
    """Thousands separators; two decimals unless told otherwise; no trailing zeros for integers."""
    if decimals is None:
        decimals = 0 if abs(value - round(value)) < 1e-9 else 2
    text = f"{value:,.{decimals}f}"
    return text


# --- calculations written by the answer model ---------------------------------------------

_CALC = re.compile(r"\[calc:\s*([^\]]+?)\s*\]", re.IGNORECASE)


def fill_calculations(answer: str) -> tuple[str, list[str]]:
    """Replace each [calc: expression] with 'expression = result'. Returns the answer and the
    results as printed (they count as known numbers for the number check)."""
    results: list[str] = []

    def replace(match: re.Match) -> str:
        expression = match.group(1)
        try:
            value = safe_eval(expression)
        except (ValueError, ZeroDivisionError):
            return f"{expression} (could not be calculated)"
        # Run 43, TB4: 89.3 + 15.4 was printed as 104.70; a sum keeps the operands' decimals.
        decimals = None
        if not re.search(r"[*/×÷]", expression):
            places = [len(n.split(".")[1]) for n in re.findall(r"\d+\.\d+", expression)]
            decimals = max(places) if places else None
        printed = format_number(value, decimals)
        results.append(printed)
        return f"{expression} = {printed}"

    return _CALC.sub(replace, answer), results


# "43,601,051 / 333,605,938 ≈ 0.1307", "85,315,148 - 47,522,179 = 37,792,969", "(112,010 − 93,736) / 93,736 × 100 ≈ 19.48%"
_OPERAND = r"\(?\s*-?\d[\d,]*(?:\.\d+)?\s*\)?"
_ARITH = re.compile(
    rf"(?P<expr>{_OPERAND}(?:\s*[-+−–×*/÷x]\s*{_OPERAND})+)\s*(?P<rel>=|≈)\s*(?P<num>-?\d[\d,]*(?:\.\d+)?)(?P<pct>\s*%)?"
)


def check_arithmetic(answer: str) -> tuple[str, list[tuple[str, str, str]], list[str]]:
    """Recompute arithmetic written out in the answer. A result that is wrong at the precision it is
    shown with is replaced. Returns the answer, the corrections (expression, written, correct) and
    every result checked (as printed), which count as known numbers."""
    fixes: list[tuple[str, str, str]] = []
    checked: list[str] = []

    def replace(match: re.Match) -> str:
        expression, written = match.group("expr"), match.group("num")
        if not re.search(r"\d\s*[-+−–×*/÷x]\s*\(?\s*\d", expression):
            return match.group(0)
        if re.fullmatch(r"\s*\d{4}\s*[-–]\s*\d{4}\s*", expression):  # a range of years, not a subtraction
            return match.group(0)
        try:
            value = safe_eval(expression)
        except (ValueError, ZeroDivisionError):
            return match.group(0)
        shown = parse_number(written)
        if shown is None:
            return match.group(0)
        decimals = len(written.split(".")[1]) if "." in written else 0
        candidates = [value]
        if match.group("pct"):
            candidates.append(value * 100)  # "a / b ≈ 28.95%": the ratio written as a percentage
        if any(abs(round(c, decimals) - shown) < 10 ** -decimals / 2 + 1e-9 for c in candidates):
            checked.append(written)
            return match.group(0)
        best = min(candidates, key=lambda c: abs(c - shown))
        correct = format_number(best, decimals)
        if "," not in written:
            correct = correct.replace(",", "")
        fixes.append((expression.strip(), written, correct))
        checked.append(correct)
        return match.group(0).replace(written, correct, 1)

    return _ARITH.sub(replace, answer), fixes, checked


# --- statement checks ----------------------------------------------------------------------

@dataclass
class Row:
    label: str
    values: list[float]


def table_rows(text: str) -> list[Row]:
    """Rows of a statement: a label followed by numbers, from plain text lines or Markdown tables."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not cells or set("".join(cells)) <= set("-: "):
                continue
            label, values = cells[0], [parse_number(c) for c in cells[1:]]
        else:
            numbers = list(_NUM_RE.finditer(line))
            if not numbers:
                continue
            label = line[: numbers[0].start()]
            values = [parse_number(m.group(0)) for m in numbers]
        label = re.sub(r"\(주[\d,\s]*\)|\(Note[^)]*\)|\$", "", label).strip(" ㆍ·:　\t")
        values = [v for v in values if v is not None]
        if label and values and re.search(r"[A-Za-z가-힣]", label):
            rows.append(Row(label, values))
    return rows


# Each check: a result row and the rows it is made of, with signs. Labels are matched as whole
# labels (case-insensitive, spaces ignored), first match wins.
_CHECKS = [
    ("total assets = total liabilities + total equity",
     [r"자산총계|자산\s*계|totalassets"], [(1, r"부채총계|부채\s*계|totalliabilities"),
                                           (1, r"자본총계|자본\s*계|totalshareholders['’]?equity|totalequity")]),
    ("total liabilities and equity = total assets",
     [r"부채와자본총계|부채와자본계|totalliabilitiesandshareholders['’]?equity|totalliabilitiesandequity"],
     [(1, r"자산총계|자산\s*계|totalassets")]),
    ("gross profit = revenue − cost of sales",
     [r"매출총이익|grossprofit|grossmargin"], [(1, r"매출액|수익\(매출액\)|totalnetsales|revenue|netsales|totalrevenue"),
                                              (-1, r"매출원가|totalcostofsales|costofrevenue|costofsales")]),
    ("operating income = gross profit − operating expenses",
     [r"영업이익|operatingincome"], [(1, r"매출총이익|grossprofit|grossmargin"),
                                     (-1, r"판매비와관리비|판관비|totaloperatingexpenses|operatingexpenses")]),
]


def _find(rows: list[Row], pattern: str) -> Row | None:
    for row in rows:
        key = re.sub(r"\s+", "", row.label.lower())
        key = re.sub(r"\(.*?\)$", "", key)
        if re.fullmatch(pattern, key):
            return row
    return None


@dataclass
class Check:
    name: str
    column: int
    expected: float
    printed: float
    note: str = ""  # a part that was itself wrong and was used with its recomputed value

    @property
    def ok(self) -> bool:
        return abs(self.expected - self.printed) <= max(1.0, abs(self.printed) * 1e-9)


def statement_checks(text: str) -> list[Check]:
    """Recompute the main totals of a statement for every period column found.

    Checks run in order, and a subtotal that failed its own check is used with its recomputed value
    in the next one. Run 42, SC6: with gross profit printed 100 too high, operating income was
    called wrong as well, although it is right for the correct gross profit."""
    rows = table_rows(text)
    corrected: dict[tuple[int, int], float] = {}
    found = []
    for name, (result_pattern,), parts in _CHECKS:
        result = _find(rows, result_pattern)
        components = [(sign, _find(rows, pattern)) for sign, pattern in parts]
        if result is None or any(row is None for _, row in components):
            continue
        columns = min([len(result.values)] + [len(row.values) for _, row in components])
        for col in range(columns):
            expected, notes = 0.0, []
            for sign, row in components:
                value = corrected.get((id(row), col), row.values[col])
                if (id(row), col) in corrected:
                    notes.append(f"{row.label} taken as {format_number(value)}")
                # A cost printed in parentheses is already negative: subtract its size, not its sign.
                expected += -abs(value) if sign < 0 else value
            check = Check(name, col, expected, result.values[col], "; ".join(notes))
            if not check.ok:
                corrected[(id(result), col)] = expected
            found.append(check)
    return found


def describe_checks(checks: list[Check], page: int | None = None) -> str:
    """Lines for the context: each check with its numbers, marked as done by code."""
    where = f"p.{page}, " if page else ""
    lines = []
    for check in checks:
        mark = "matches" if check.ok else f"DOES NOT MATCH: the parts give {format_number(check.expected)}"
        if check.note:
            mark += f" (with {check.note})"
        lines.append(f"[{where}checked by code] {check.name}, column {check.column + 1}: printed "
                     f"{format_number(check.printed)}; {mark}")
    return "\n".join(lines)


# --- numbers the answer computed itself ------------------------------------------------------

_ANSWER_NUMBER = re.compile(r"(?<![\w.])-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.,])-?\d+(?:\.\d+)?(?![\d])")


def _combinations(a: float, b: float) -> list[tuple[str, float]]:
    out = [("{a} + {b}", a + b), ("{a} - {b}", a - b), ("{a} × {b}", a * b), ("{a} × {b} / 100", a * b / 100)]
    if b:
        out += [("{a} / {b}", a / b), ("{a} / {b} × 100", a / b * 100), ("({a} - {b}) / {b} × 100", (a - b) / b * 100)]
    return out


def explain_numbers(answer: str, unknown: list[str], known: set[str]) -> tuple[str, list[tuple[str, str, str]], list[str]]:
    """Numbers in the answer that are not in the document, explained as one step of arithmetic on
    two numbers from the same paragraph that are in the document (a + b, a − b, a × b, a / b,
    a / b × 100, (a − b) / b × 100, a × b / 100).

    Run 43: the prompt asks for [calc: ...], but answers written with LaTeX did the arithmetic in
    their own words: TB1 wrote 19.49% for (112,010 − 93,736) / 93,736 × 100 = 19.495, and the
    computed values were flagged as invented. A result that matches at the precision shown is a
    computed value; one that is off only in its last digit is corrected. Returns the answer, the
    corrections (expression, written, correct) and the numbers explained."""
    fixes: list[tuple[str, str, str]] = []
    explained: list[str] = []
    paragraphs = re.split(r"\n\s*\n", answer)
    for number in unknown:
        written = number
        shown = parse_number(written)
        if shown is None:
            continue
        decimals = len(written.split(".")[1]) if "." in written else 0
        unit = 10 ** -decimals
        for paragraph in paragraphs:
            if number not in paragraph.replace(",", ""):
                continue
            operands = []
            for m in _ANSWER_NUMBER.finditer(paragraph):
                clean = m.group(0).replace(",", "")
                if clean in known and clean != number:
                    value = parse_number(clean)
                    if value is not None and value not in operands:
                        operands.append(value)
            match = None
            for a in operands[:12]:
                for b in operands[:12]:
                    if a == b:
                        continue
                    for form, value in _combinations(a, b):
                        if abs(round(value, decimals) - shown) < unit / 2 + 1e-9:
                            match = ("exact", form.format(a=format_number(a), b=format_number(b)), value)
                            break
                        if match is None and abs(value - shown) <= unit * 1.01 and abs(value) >= 1:
                            match = ("near", form.format(a=format_number(a), b=format_number(b)), value)
                    if match and match[0] == "exact":
                        break
                if match and match[0] == "exact":
                    break
            if match:
                kind, expression, value = match
                if kind == "near":
                    correct = format_number(value, decimals).replace(",", "") if "," not in written else format_number(value, decimals)
                    fixes.append((expression, written, correct))
                    answer = re.sub(rf"(?<![\d.]){re.escape(written)}(?![\d])", correct, answer)
                    explained.append(correct.replace(",", ""))
                explained.append(number)
                break
    return answer, fixes, explained
