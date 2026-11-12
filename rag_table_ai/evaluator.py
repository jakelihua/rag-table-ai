"""Safe decimal arithmetic evaluation without arbitrary code execution.

Features:
- Full-width punctuation normalization: '（' -> '(', '）' -> ')', '×' -> '*', '÷' -> '/'
- Automatic percentage normalization: '80%' -> '(80/100)'
- Safe thousands-separator stripping: '1,200.50' -> '1200.50'
- Ambiguity detection: Rejects commas inside min/max that create leading zeros like min(5, 000)
- High-precision Decimal evaluation without calling unsafe python eval()
"""

from __future__ import annotations

import ast
import operator
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_FULLWIDTH_MAP = {
    "（": "(",
    "）": ")",
    "×": "*",
    "÷": "/",
    "＋": "+",
    "－": "-",
    "％": "%",
    "，": ",",
}

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_SAFE_FUNCS = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
}


def normalize_expression(expression: str) -> str:
    """Normalize user or LLM expression string into standard arithmetic format."""
    expr = (expression or "").strip()
    for fw, hw in _FULLWIDTH_MAP.items():
        expr = expr.replace(fw, hw)

    # Normalize percentage: e.g. 80% -> (80/100), 12.5% -> (12.5/100)
    expr = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", expr)

    # Check for ambiguous thousand separator inside functions like min(5, 000, 8, 000)
    # where commas are followed by leading zeros: ', 000'
    if re.search(r",\s*0\d+", expr):
        raise ValueError(
            "Ambiguous comma detected before leading zeros (e.g. ', 000'). "
            "Please remove thousand separators before passing to function arguments."
        )

    # Safely strip valid thousand separators in numbers like 1,200 or 1,200,000.50
    # when not preceded/followed by function argument contexts
    def _strip_thousands(match: re.Match[str]) -> str:
        return match.group(0).replace(",", "")

    # Replace numbers with commas: e.g. 1,000 or 25,400.00
    expr = re.sub(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b", _strip_thousands, expr)

    return expr


def _eval_ast(node: ast.AST) -> Decimal:
    """Recursively evaluate an AST node into Decimal safely."""
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return Decimal(str(node.value))
        raise TypeError(f"Unsupported constant type: {type(node.value)}")

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type in _SAFE_OPS:
            operand = _eval_ast(node.operand)
            return _SAFE_OPS[op_type](operand)
        raise TypeError(f"Unsupported unary operator: {op_type}")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type in _SAFE_OPS:
            left = _eval_ast(node.left)
            right = _eval_ast(node.right)
            if op_type is ast.Div and right == 0:
                raise ZeroDivisionError("Division by zero in arithmetic expression.")
            return _SAFE_OPS[op_type](left, right)
        raise TypeError(f"Unsupported binary operator: {op_type}")

    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _SAFE_FUNCS:
            func = _SAFE_FUNCS[node.func.id]
            args = [_eval_ast(arg) for arg in node.args]
            if not args:
                raise ValueError(f"Function {node.func.id} requires at least one argument.")
            return func(*args)
        raise TypeError(f"Unsupported function call: {getattr(node.func, 'id', str(node.func))}")

    raise TypeError(f"Unsupported AST expression: {type(node)}")


def calculate_decimal_safe(expression: str, max_places: int = 4) -> str:
    """Safely calculate an arithmetic expression string with Decimal precision.

    Returns the formatted string of the decimal result.

    Examples:
        calculate_decimal_safe('(5000 - 100) * 80%') -> '3920.00'
        calculate_decimal_safe('min(1200, 2000) * 0.5') -> '600.00'
    """
    clean_expr = normalize_expression(expression)
    try:
        tree = ast.parse(clean_expr, mode="eval")
        result = _eval_ast(tree)
        # Format output
        rounded = result.quantize(Decimal(10) ** -max_places, rounding=ROUND_HALF_UP)
        # Strip unnecessary trailing zeros after 2 decimal places
        norm_str = f"{rounded:f}"
        if "." in norm_str:
            integer_part, decimal_part = norm_str.split(".")
            # Keep at least 2 decimal places for financial/standard precision
            if len(decimal_part) > 2:
                decimal_part = decimal_part.rstrip("0")
                if len(decimal_part) < 2:
                    decimal_part = decimal_part.ljust(2, "0")
            return f"{integer_part}.{decimal_part}"
        return f"{norm_str}.00"
    except (SyntaxError, InvalidOperation, ValueError, ZeroDivisionError, ArithmeticError) as exc:
        raise ValueError(f"Failed to evaluate arithmetic expression '{expression}': {exc}") from exc
