"""Formulas the planner can write, and the code that checks and computes them.

PAT's planner writes code for each step; that is where its breadth comes from.
This app's rule is that a language model never produces a number, so here the
planner writes a *formula* instead — a small expression over named data — and
code checks it before anything runs and computes it afterwards:

    pct(free_cash_flow, net_income)             cash conversion, latest year
    cagr(revenue, 3) - cagr(operating_income, 3) growth gap, in points
    latest(net_debt) / latest(ebitda)            leverage from the statements
    factor_beta_pct * 2                          a computed value, rescaled

Nothing is evaluated by Python's `eval`. The expression is parsed into a syntax
tree and only these node types are allowed: numbers, names, + - * /, unary
minus, and calls to the functions in `FUNCTIONS`. Anything else — attribute
access, subscripts, keywords, comparisons, a name that is not a series or a
value an earlier step computed — is rejected at plan time with a message the
planner's repair can act on. That rejection is the static-analysis pass PAT
runs on its generated code, with a smaller and safer language underneath it.

Two kinds of name, and the difference is checked, not assumed:

  series  an annual statement series (`revenue`, `free_cash_flow`, ...), a
          list of years, newest first. It may only appear as a function's
          first argument, because "revenue" alone has no single value.
  value   a number an earlier step computed (`gross_margin_pct`), or another
          formula's name. It may appear anywhere a number may.

A missing value never becomes zero: a formula that reaches one fails, and the
step reports which input was missing.
"""

from __future__ import annotations

import ast
import difflib
import re
from collections.abc import Callable, Mapping
from typing import Any

from hedge_fund.data.statements import BY_ID as SERIES
from hedge_fund.plan.types import MetricError

#: The longest window a series function may look back, in years. Statements
#: carry four or five years, so more would always fail.
MAX_YEARS = 4

_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _need(v: float | None, what: str) -> float:
    if v is None:
        raise MetricError(f"{what} is missing")
    return v


def _window(s: list[float | None], n: int, what: str) -> list[float]:
    if len(s) <= n:
        raise MetricError(f"{what} has fewer than {n + 1} years")
    vals = s[: n + 1]
    if any(v is None for v in vals):
        raise MetricError(f"{what} has a missing year in the last {n + 1}")
    return [float(v) for v in vals if v is not None]


def _latest(s: list[float | None], name: str) -> float:
    return _need(s[0] if s else None, f"latest {name}")


def _prior(s: list[float | None], name: str, n: int) -> float:
    return _need(s[n] if len(s) > n else None, f"{name} {n} year(s) back")


def _mean(s: list[float | None], name: str, n: int) -> float:
    w = _window(s, n - 1, name)
    return sum(w) / len(w)


def _total(s: list[float | None], name: str, n: int) -> float:
    return sum(_window(s, n - 1, name))


def _not_positive(name: str, w: list[float], what: str) -> MetricError:
    hint = ""
    if all(v < 0 for v in w):
        hint = f"; {name} is reported negative, as an outflow — use -{name}"
    return MetricError(f"{name} is not positive {what}, so it is undefined{hint}")


def _change(s: list[float | None], name: str, n: int) -> float:
    w = _window(s, n, name)
    if w[-1] <= 0:
        raise _not_positive(name, w, f"{n} year(s) back")
    return (w[0] / w[-1] - 1) * 100


def _cagr(s: list[float | None], name: str, n: int) -> float:
    w = _window(s, n, name)
    if w[0] <= 0 or w[-1] <= 0:
        raise _not_positive(name, w, "at both ends")
    growth: float = (w[0] / w[-1]) ** (1 / n)
    return (growth - 1) * 100


def _slope(s: list[float | None], name: str, n: int) -> float:
    """Least-squares change per year, oldest to newest, so rising is positive."""
    w = list(reversed(_window(s, n, name)))
    xs = range(len(w))
    mx, my = sum(xs) / len(w), sum(w) / len(w)
    return sum((x - mx) * (y - my) for x, y in zip(xs, w, strict=True)) / sum(
        (x - mx) ** 2 for x in xs
    )


def _ratio(a: float, b: float) -> float:
    if b == 0:
        raise MetricError("division by zero")
    return a / b


#: name -> (takes a series first?, number of extra integer args, implementation)
FUNCTIONS: dict[str, tuple[bool, int, Callable[..., float]]] = {
    "latest": (True, 0, _latest),
    "prior": (True, 1, _prior),
    "mean": (True, 1, _mean),
    "total": (True, 1, _total),
    "change": (True, 1, _change),
    "cagr": (True, 1, _cagr),
    "slope": (True, 1, _slope),
    "ratio": (False, 0, _ratio),
    "pct": (False, 0, lambda a, b: _ratio(a, b) * 100),
    "abs": (False, 0, abs),
}

DESCRIPTIONS = {
    "latest": "latest(series): the latest year",
    "prior": "prior(series, n): the value n years back",
    "mean": "mean(series, n): average of the latest n years",
    "total": "total(series, n): sum of the latest n years",
    "change": "change(series, n): percent change over n years",
    "cagr": "cagr(series, n): compound annual growth over n years, percent",
    "slope": "slope(series, n): average change per year over n years, rising is positive",
    "ratio": "ratio(a, b): a divided by b",
    "pct": "pct(a, b): a as a percentage of b",
    "abs": "abs(x): absolute value",
}


_FIELD = re.compile(r"^[a-z][a-z0-9_]*$")


class _Normalise(ast.NodeTransformer):
    """Rewrite what a model writes naturally into the strict form.

    Observed on the eval, all on the first real run:
      `revenue_growth.revenue_growth_latest_pct`  step.field  ->  the field
      `latest(net_debt)` where net_debt is a value         ->  net_debt
    Only these two. Anything else is left for `check` to accept or refuse, so
    the gate is still one function.
    """

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        if isinstance(node.value, ast.Name) and _FIELD.match(node.attr):
            return ast.copy_location(ast.Name(id=node.attr, ctx=ast.Load()), node)
        return self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "latest"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id not in SERIES
        ):
            return node.args[0]
        return node


def _parse(expression: str) -> ast.Expression:
    tree = ast.parse(expression, mode="eval")
    out = ast.fix_missing_locations(_Normalise().visit(tree))
    assert isinstance(out, ast.Expression)
    return out


def candidates(name: str, known: set[str]) -> list[str]:
    """Names the writer probably meant, best first."""
    # The unit suffix left off: "revenue_cagr" is revenue_cagr_pct.
    suffixed = [k for k in (f"{name}_pct", f"{name}_pp") if k in known]
    if len(suffixed) == 1:
        return suffixed
    close = difflib.get_close_matches(name, sorted(known), n=2, cutoff=0.5)
    # Abbreviations a ratio cannot see: "fcf" is free_cash_flow.
    initials = [k for k in sorted(known) if "".join(w[0] for w in k.split("_")) == name]
    return list(dict.fromkeys(initials + close))


def _suggest(name: str, known: set[str]) -> str:
    """'; did you mean free_cash_flow?' — the repair is told what to write."""
    hits = candidates(name, known)
    return f"; did you mean {' or '.join(hits)}?" if hits else ""


def rename(expression: str, old: str, new: str) -> str:
    """The expression with one name replaced, as the harness's correction."""

    class _R(ast.NodeTransformer):
        def visit_Name(self, node: ast.Name) -> ast.AST:
            return ast.Name(id=new, ctx=node.ctx) if node.id == old else node

    return ast.unparse(_R().visit(ast.parse(expression, mode="eval")))


#: Units the check reasons about. "" is a plain number (a ratio, a score), and
#: "?" is not known — never refused, because an unknown is not a wrong.
_AMOUNT = {"currency", "shares", "currency per share"}


def _units(tree: ast.Expression, units: Mapping[str, str]) -> list[str]:
    """Dimensional analysis: the second half of PAT's static pass, on units.

    Seen on the eval, both with valid syntax and both reaching the analysis as
    findings: pct(latest(buybacks), latest(total_return_pct)) — dollars over a
    percentage, -114,984,155,152% — and a percent change divided by dollars
    per share, 8,051%. Every series and every computed field declares a unit,
    so a formula's arithmetic can be checked for meaning before it runs.
    Refused: adding or subtracting unlike units, dividing an amount by a
    percentage or a percentage by an amount, and pct() of unlike things.
    Everything else — currency / shares, a P/E over a growth rate — passes.
    """
    problems: list[str] = []
    series_unit = {k: s.unit for k, s in SERIES.items()}

    def name_unit(n: str) -> str:
        if n in series_unit:
            return series_unit[n]
        u = units.get(n, "?") if units else "?"
        return u if u else ""

    def div(a: str, b: str, where: str) -> str:
        if "?" in (a, b) or b == "#":
            return a if b in ("", "#") else "?"
        if a == "#":
            return "?"
        if b == "":
            return a
        if a == b:
            return ""
        if a == "currency" and b == "shares":
            return "currency per share"
        if (a in _AMOUNT and b == "%") or (a == "%" and b in _AMOUNT):
            problems.append(
                f"'{where}' divides {'an amount' if a in _AMOUNT else 'a percentage'} by "
                f"{'a percentage' if b == '%' else 'an amount'}, which has no meaning"
            )
        return "?"

    def same(a: str, b: str, where: str, what: str) -> str:
        if a in ("#", "?"):
            return b
        if b in ("#", "?"):
            return a
        if a != b:
            problems.append(f"'{where}' {what} {a or 'a plain number'} and {b or 'a plain number'}")
            return "?"
        return a

    def u(node: ast.AST) -> str:
        if isinstance(node, ast.Expression):
            return u(node.body)
        if isinstance(node, ast.Constant):
            return "#"  # a bare number takes the unit of what it meets
        if isinstance(node, ast.Name):
            return name_unit(node.id)
        if isinstance(node, ast.UnaryOp):
            return u(node.operand)
        if isinstance(node, ast.BinOp):
            a, b = u(node.left), u(node.right)
            where = ast.unparse(node)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                return same(a, b, where, "adds or subtracts")
            if isinstance(node.op, ast.Div):
                return div(a, b, where)
            if a in ("", "#"):
                return b
            return a if b in ("", "#") else "?"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            f, args = node.func.id, node.args
            if f in ("change", "cagr"):
                u(args[0])
                return "%"
            if f in ("latest", "prior", "mean", "total", "slope"):
                return u(args[0])
            if f == "abs":
                return u(args[0])
            a, b = u(args[0]), u(args[1])
            if f == "pct":
                same(a, b, ast.unparse(node), "takes a percentage of")
                return "%"
            return div(a, b, ast.unparse(node))
        return "?"

    u(tree)
    return problems


def check(expression: str, values: Mapping[str, str] | set[str]) -> list[str]:
    """Problems with a formula, empty when it is valid. No data is touched.

    `values` are the names earlier steps will compute, with their units when
    known; anything else that is not a series is unknown.
    """
    try:
        tree = _parse(expression)
    except SyntaxError as e:
        return [f"formula does not parse: {e.msg}"]
    problems: list[str] = []

    def visit(node: ast.AST, as_series: bool = False) -> None:
        if isinstance(node, ast.Expression):
            visit(node.body)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        ):
            pass  # a number is fine anywhere, including scaling a series
        elif isinstance(node, ast.Name):
            if as_series:
                if node.id in values:
                    problems.append(
                        f"'{node.id}' is a single value, not a series; a series function needs "
                        f"statement series such as free_cash_flow / shares"
                    )
                elif node.id not in SERIES:
                    problems.append(f"'{node.id}' is not a series{_suggest(node.id, set(SERIES))}")
            # A bare series in arithmetic means its latest year.
            elif node.id not in SERIES and node.id not in values:
                problems.append(
                    f"'{node.id}' is not computed by any earlier step"
                    f"{_suggest(node.id, set(SERIES) | set(values))}"
                )
        elif isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)
        ):
            # Inside a series function this is year-by-year arithmetic on
            # series — equity / shares is book value per share each year.
            visit(node.left, as_series)
            visit(node.right, as_series)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            visit(node.operand)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if name not in FUNCTIONS:
                problems.append(f"unknown function '{name}'; allowed: {', '.join(FUNCTIONS)}")
                return
            if node.keywords:
                problems.append(f"{name}() takes no keyword arguments")
            takes_series, n_int, _fn = FUNCTIONS[name]
            want = (1 if takes_series else 2 if name != "abs" else 1) + n_int
            if len(node.args) != want:
                problems.append(f"{name}() takes {want} argument(s), got {len(node.args)}")
                return
            if takes_series:
                visit(node.args[0], as_series=True)
                for a in node.args[1:]:
                    if not (
                        isinstance(a, ast.Constant)
                        and isinstance(a.value, int)
                        and 1 <= a.value <= MAX_YEARS
                    ):
                        problems.append(
                            f"{name}() needs a whole number of years from 1 to {MAX_YEARS}"
                        )
            else:
                for a in node.args:
                    visit(a)
        elif isinstance(node, ast.Compare):
            problems.append(
                f"'{ast.unparse(node)}' compares; formulas return numbers, so subtract instead "
                "(a - b is positive when a is larger)"
            )
        else:
            problems.append(f"'{ast.unparse(node)}' is not allowed in a formula")

    visit(tree)
    if problems:
        return problems
    return _units(tree, values if isinstance(values, Mapping) else {})


def evaluate(
    expression: str, series: dict[str, list[float | None]], values: dict[str, Any]
) -> float:
    """Compute a formula that `check` passed. Raises MetricError on missing data."""
    tree = _parse(expression)

    def sv(node: ast.AST) -> list[float | None]:
        """A series expression, year by year. A missing or undefined year stays None."""
        if isinstance(node, ast.Name):
            return list(series.get(node.id) or [])
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return [float(node.value)] * 8
        if isinstance(node, ast.UnaryOp):
            return [None if v is None else -v for v in sv(node.operand)]
        if isinstance(node, ast.BinOp):
            a, b = sv(node.left), sv(node.right)
            out: list[float | None] = []
            for x, y in zip(a, b, strict=False):
                if x is None or y is None:
                    out.append(None)
                elif isinstance(node.op, ast.Add):
                    out.append(x + y)
                elif isinstance(node.op, ast.Sub):
                    out.append(x - y)
                elif isinstance(node.op, ast.Mult):
                    out.append(x * y)
                else:
                    out.append(x / y if y else None)
            return out
        raise MetricError(f"cannot evaluate '{ast.unparse(node)}' as a series")

    def label(node: ast.AST) -> str:
        return node.id if isinstance(node, ast.Name) else ast.unparse(node)

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in SERIES:
            return _latest(series.get(node.id) or [], node.id)
        if isinstance(node, ast.Name):
            v = values.get(node.id)
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise MetricError(f"'{node.id}' has no numeric value")
            return float(v)
        if isinstance(node, ast.UnaryOp):
            return -ev(node.operand) if isinstance(node.op, ast.USub) else ev(node.operand)
        if isinstance(node, ast.BinOp):
            a, b = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Add):
                return a + b
            if isinstance(node.op, ast.Sub):
                return a - b
            if isinstance(node.op, ast.Mult):
                return a * b
            return _ratio(a, b)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            takes_series, _n, fn = FUNCTIONS[node.func.id]
            if takes_series:
                ints = [int(a.value) for a in node.args[1:]]  # type: ignore[attr-defined]
                return float(fn(sv(node.args[0]), label(node.args[0]), *ints))
            return float(fn(*[ev(a) for a in node.args]))
        raise MetricError(f"cannot evaluate '{ast.unparse(node)}'")  # check() rejects these

    out = ev(tree)
    if out != out or abs(out) == float("inf"):
        raise MetricError("the formula did not produce a finite number")
    return out


def valid_name(name: str) -> bool:
    return bool(_NAME.match(name))
