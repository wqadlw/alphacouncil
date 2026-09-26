"""S-03 — no prediction or prescription field.

**Defect guarded:** product red lines 1 and 2. This product optimises the
*process* of deciding; it does not predict prices and it does not tell anyone
what to buy. A field named ``target_price`` is not a neutral convenience — it is
the feature that turns a decision journal into a stock-tipping app, and it will
be filled in by whoever adds the next screen because the column already exists.

Anti-pattern (forbidden)::

    class ResearchReport(BaseModel):
        target_price: float           # 目标价
        rating: Literal["buy", "hold", "sell"]   # 买卖建议
        expected_return: float

    @app.get("/api/v1/recommendations/{code}")
    def recommend(code: str) -> ...: ...

Correct form::

    class ResearchReport(BaseModel):
        facts: list[Fact]             # each with source_url + captured_at
        open_questions: list[str]
        kill_criteria: list[Predicate]  # {metric, operator, threshold, as_of}

Why a test cannot catch this: the field works. A test asserting that
``target_price`` round-trips through the API passes, and would keep passing
right up to the point where the product has become the thing it was built to
replace. The defect is the *existence* of the field, not its behaviour.

Scope: field names, function names, route paths, and string literals. String
literals are included for the Chinese UI vocabulary only (``目标价``,
``买卖建议`` …), because those reach a user directly and no identifier rule would
see them.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from checks.framework import (
    CheckMeta,
    CheckResult,
    ScanContext,
    contains_token,
    declared_fields,
    format_target,
)

CODE = "CHECK_PREDICTION_FIELD"

META = CheckMeta(
    check_id="S-03",
    slug="no-prediction-field",
    title="no prediction or prescription field",
    priority="P0",
    code=CODE,
)


#: Whole-word tokens, matched against snake_case identifiers. Deliberately a
#: curated list rather than a prefix hunt: `expected_return` is a prediction,
#: `expected_publish_date` is a fact, and only the list can tell them apart.
PREDICTION_TOKENS = (
    "target_price",
    "price_target",
    "target_return",
    "expected_return",
    "upside_target",
    "fair_value_target",
    "predicted",
    "prediction",
    "predict",
    "forecast",
    "buy_signal",
    "sell_signal",
    "trade_signal",
    "trading_signal",
    "recommendation",
    "recommend",
    "bullish",
    "bearish",
    "conviction_score",
    "win_probability",
)

#: Tokens that reach a user as prose. Matched against string literals too.
PREDICTION_PHRASES = (
    "目标价",
    "涨跌预测",
    "买卖建议",
    "荐股",
    "看好",
    "看空",
    "买入评级",
    "跑赢大盘",
)

_ROUTE_DECORATORS = re.compile(r"^(app|router)\.(get|post|put|patch|delete)$")


def run(ctx: ScanContext) -> CheckResult:
    """Scan the product for prediction-shaped names and phrases."""
    result = CheckResult()
    for path in ctx.python_files(ctx.product):
        tree = ctx.tree(path)
        if tree is None:
            continue
        result.files.append(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                _check_class(ctx, result, path, node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _check_function(ctx, result, path, node)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                _check_phrase(ctx, result, path, node)
    return result


def _report(ctx: ScanContext, result: CheckResult, path: Path, lineno: int, what: str) -> None:
    result.error(
        CODE,
        f"{what} is prediction/prescription-shaped",
        target=format_target(ctx, path, lineno),
        fix="Remove it. Record what you know (facts with sources), what would "
        "prove you wrong (`kill_criteria`), and what you decided — not what you "
        "expect to happen.",
    )


def _check_class(ctx: ScanContext, result: CheckResult, path: Path, node: ast.ClassDef) -> None:
    for name, lineno, _annotation in declared_fields(node):
        token = contains_token(name, PREDICTION_TOKENS)
        if token:
            _report(ctx, result, path, lineno, f"field `{node.name}.{name}` (matched `{token}`)")


def _check_function(
    ctx: ScanContext, result: CheckResult, path: Path, node: ast.FunctionDef | ast.AsyncFunctionDef
) -> None:
    token = contains_token(node.name, PREDICTION_TOKENS)
    if token:
        _report(ctx, result, path, node.lineno, f"function `{node.name}` (matched `{token}`)")
    for decorator in node.decorator_list:
        route = _route_path(decorator)
        if route is None:
            continue
        token = _route_token(route)
        if token:
            lineno = getattr(decorator, "lineno", node.lineno)
            _report(ctx, result, path, lineno, f"route `{route}`")


def _route_token(route: str) -> str | None:
    """Substring match against a URL path, where plurals and dashes are normal.

    A route is not an identifier: ``/api/v1/recommendations`` and
    ``/target-price`` have to be caught, and word-run matching on an identifier
    would miss both. Stripping separators makes one comparison cover
    ``target_price``, ``target-price`` and ``targetPrice``.
    """
    squashed = route.lower().replace("_", "").replace("-", "").replace("/", "")
    for token in PREDICTION_TOKENS:
        if token.replace("_", "") in squashed:
            return token
    return None


def _route_path(decorator: ast.expr) -> str | None:
    """The literal path of an ``@app.get("/...")`` decorator, if that is what it is."""
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    if not isinstance(func, ast.Attribute) or not _ROUTE_DECORATORS.match(
        f"{getattr(func.value, 'id', '')}.{func.attr}"
    ):
        return None
    for arg in decorator.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    return None


def _check_phrase(ctx: ScanContext, result: CheckResult, path: Path, node: ast.Constant) -> None:
    text = node.value
    if not isinstance(text, str):
        return
    for phrase in PREDICTION_PHRASES:
        if phrase in text:
            _report(ctx, result, path, node.lineno, f"string literal containing `{phrase}`")
            return


__all__ = ["META", "run"]
