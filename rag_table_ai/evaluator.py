"""Safe exact rational arithmetic evaluation without arbitrary code execution.

Features:
- Full-width and Unicode operator normalization: '（' -> '(', '×' -> '*', '÷' -> '/', '−' -> '-'
- Automatic percentage normalization: '80%' -> '(80/100)'
- Context-aware thousands-separator stripping outside function calls: '1,200.50' -> '1200.50'
- Preserves multi-argument function calls such as 'min(1,200,300)' while rejecting leading-zero
  comma splits like 'min(5, 000)' or malformed commas outside function calls
- Exact rational intermediate evaluation (Fraction from source literals, no float rounding and
  no reliance on caller's ambient decimal.getcontext())
"""

from __future__ import annotations

import ast
import re
from fractions import Fraction

MAX_EXPRESSION_LENGTH = 2048
MAX_DEPTH = 32
MAX_NODES = 256
MAX_OPERATIONS = 128
MAX_NUMERIC_LENGTH = 128
MAX_EXPONENT = 100
MAX_INTEGER_BITS = 4096
MAX_FUNC_ARGS = 64
MAX_PLACES_LIMIT = 64

_FULLWIDTH_MAP = {
    "（": "(",
    "）": ")",
    "×": "*",
    "÷": "/",
    "＋": "+",
    "－": "-",
    "−": "-",
    "％": "%",
    "，": ",",
}

_THOUSANDS_RE = re.compile(r"(?<![.,\d])[1-9]\d{0,2}(?:,\d{3})+(?:\.\d+)?(?![.,\d])")
_PERCENT_RE = re.compile(r"((?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*%")
_ALLOWED_CHARS_RE = re.compile(r"[A-Za-z0-9_+\-*/().,\s]+\Z", re.ASCII)
_NUMBER_LITERAL_RE = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


def _strip_thousands(match: re.Match[str]) -> str:
    return match.group(0).replace(",", "")


def _split_function_segments(expr: str) -> list[tuple[bool, str]]:
    """Partition expression into (in_function_call, substring) segments."""
    segments: list[tuple[bool, str]] = []
    paren_stack: list[bool] = []
    seg_start = 0

    for idx, ch in enumerate(expr):
        if ch == "(":
            was_in_func = any(paren_stack)
            prev = idx - 1
            while prev >= 0 and expr[prev].isspace():
                prev -= 1
            ident_end = prev + 1
            while prev >= 0 and (expr[prev].isalnum() or expr[prev] == "_"):
                prev -= 1
            ident = expr[prev + 1 : ident_end]
            is_func = bool(ident) and (ident[0].isalpha() or ident[0] == "_")
            paren_stack.append(is_func)
            now_in_func = any(paren_stack)
            if now_in_func != was_in_func:
                segments.append((was_in_func, expr[seg_start : idx + 1]))
                seg_start = idx + 1
        elif ch == ")" and paren_stack:
            was_in_func = any(paren_stack)
            paren_stack.pop()
            now_in_func = any(paren_stack)
            if now_in_func != was_in_func:
                segments.append((was_in_func, expr[seg_start:idx]))
                seg_start = idx

    segments.append((any(paren_stack), expr[seg_start:]))
    return segments


def normalize_expression(expression: str) -> str:
    """Normalize user or LLM expression string into standard arithmetic format."""
    if expression is None:
        return ""
    if not isinstance(expression, str):
        raise TypeError("Expression must be a string.")

    expr = expression.strip()
    if not expr:
        return ""
    if len(expr) > MAX_EXPRESSION_LENGTH:
        raise ValueError(f"Expression exceeds maximum length of {MAX_EXPRESSION_LENGTH} characters.")

    for fw, hw in _FULLWIDTH_MAP.items():
        expr = expr.replace(fw, hw)

    normalized_parts: list[str] = []
    for in_func_call, segment in _split_function_segments(expr):
        if in_func_call:
            if re.search(r",\s*0\d", segment):
                raise ValueError(
                    "Ambiguous comma detected before leading zeros (e.g. ', 000'). "
                    "Please remove thousand separators before passing to function arguments."
                )
            normalized_parts.append(segment)
        else:
            if re.search(r",\s+0\d", segment):
                raise ValueError(
                    "Ambiguous comma detected before leading zeros (e.g. ', 000'). "
                    "Please remove spaces inside thousand-separated numbers."
                )
            cleaned = _THOUSANDS_RE.sub(_strip_thousands, segment)
            if "," in cleaned:
                raise ValueError(
                    f"Ambiguous or invalid comma outside function arguments in '{expression}'."
                )
            normalized_parts.append(cleaned)

    expr = "".join(normalized_parts)

    # Normalize numeric percentages: e.g. 80% -> (80/100), 12.5% -> (12.5/100)
    expr = _PERCENT_RE.sub(r"(\1/100)", expr)
    if "%" in expr:
        raise ValueError(
            "Unsupported '%' usage; attach '%' directly to a numeric literal (e.g. '80%')."
        )

    return expr


def _bounded(value: Fraction) -> Fraction:
    if (
        value.numerator.bit_length() > MAX_INTEGER_BITS
        or value.denominator.bit_length() > MAX_INTEGER_BITS
    ):
        raise ValueError("Numeric value magnitude or precision exceeds safe evaluation bounds.")
    return value


def _parse_literal(text: str) -> Fraction:
    if not text or len(text) > MAX_NUMERIC_LENGTH or not _NUMBER_LITERAL_RE.fullmatch(text):
        raise ValueError(f"Invalid numeric literal: {text!r}")

    mantissa, _, exp_part = text.lower().partition("e")
    int_part = mantissa.partition(".")[0]
    if len(int_part) > 1 and int_part.startswith("0"):
        raise ValueError(f"Leading zeros are not permitted in numeric literal: {text!r}")
    if exp_part and abs(int(exp_part)) > MAX_EXPONENT:
        raise ValueError(f"Numeric exponent exceeds limit ({MAX_EXPONENT}): {text!r}")

    return _bounded(Fraction(text))


def _round_half_up(value: Fraction, ndigits: int) -> Fraction:
    if ndigits >= 0:
        scale = 10**ndigits
        scaled = value * scale
        quotient, remainder = divmod(abs(scaled.numerator), scaled.denominator)
        if 2 * remainder >= scaled.denominator:
            quotient += 1
        signed = -quotient if (value < 0 and quotient > 0) else quotient
        return _bounded(Fraction(signed, scale))

    scale = 10 ** (-ndigits)
    scaled = value / scale
    quotient, remainder = divmod(abs(scaled.numerator), scaled.denominator)
    if 2 * remainder >= scaled.denominator:
        quotient += 1
    signed = -quotient if (value < 0 and quotient > 0) else quotient
    return _bounded(Fraction(signed * scale, 1))


def _format_fraction(value: Fraction, max_places: int) -> str:
    scale = 10**max_places
    scaled = value * scale
    quotient, remainder = divmod(abs(scaled.numerator), scaled.denominator)
    if 2 * remainder >= scaled.denominator:
        quotient += 1
    sign = "-" if (value < 0 and quotient > 0) else ""
    if max_places == 0:
        return f"{sign}{quotient}"

    whole, frac = divmod(quotient, scale)
    decimal_part = f"{frac:0{max_places}d}"
    min_places = min(2, max_places)
    if len(decimal_part) > min_places:
        decimal_part = decimal_part.rstrip("0").ljust(min_places, "0")
    return f"{sign}{whole}.{decimal_part}"


def _parse_expression_ast(clean_expr: str) -> ast.expr:
    if not clean_expr:
        raise ValueError("Expression cannot be empty.")
    if not _ALLOWED_CHARS_RE.fullmatch(clean_expr):
        raise ValueError("Expression contains unsupported characters.")

    depth = 0
    for ch in clean_expr:
        if ch == "(":
            depth += 1
            if depth > MAX_DEPTH:
                raise ValueError(f"Expression nesting exceeds maximum depth of {MAX_DEPTH}.")
        elif ch == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("Unbalanced closing parenthesis in expression.")
    if depth != 0:
        raise ValueError("Unbalanced opening parenthesis in expression.")

    try:
        tree = ast.parse(clean_expr, mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise ValueError("Invalid arithmetic syntax.") from exc

    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise ValueError(f"Expression exceeds maximum AST node count of {MAX_NODES}.")

    return tree.body


class _RationalEvaluator:
    """AST evaluator backed by exact Fraction arithmetic from source segments."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.operations = 0

    def _tick(self) -> None:
        self.operations += 1
        if self.operations > MAX_OPERATIONS:
            raise ValueError(f"Expression exceeds maximum operation count of {MAX_OPERATIONS}.")

    def evaluate(self, node: ast.expr, depth: int = 1) -> Fraction:
        if depth > MAX_DEPTH:
            raise ValueError(f"Expression nesting exceeds maximum depth of {MAX_DEPTH}.")

        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            segment = ast.get_source_segment(self.source, node)
            return _parse_literal(segment or "")

        if isinstance(node, ast.UnaryOp):
            self._tick()
            if isinstance(node.op, ast.UAdd):
                return self.evaluate(node.operand, depth + 1)
            if isinstance(node.op, ast.USub):
                return -self.evaluate(node.operand, depth + 1)
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")

        if isinstance(node, ast.BinOp):
            self._tick()
            left = self.evaluate(node.left, depth + 1)
            right = self.evaluate(node.right, depth + 1)
            if isinstance(node.op, ast.Add):
                return _bounded(left + right)
            if isinstance(node.op, ast.Sub):
                return _bounded(left - right)
            if isinstance(node.op, ast.Mult):
                return _bounded(left * right)
            if isinstance(node.op, ast.Div):
                if right == 0:
                    raise ZeroDivisionError("Division by zero in arithmetic expression.")
                return _bounded(left / right)
            raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")

        if isinstance(node, ast.Call):
            if node.keywords or not isinstance(node.func, ast.Name):
                raise ValueError("Unsupported function call syntax.")
            func_name = node.func.id
            if func_name not in {"min", "max", "abs", "round"}:
                raise ValueError(f"Unsupported function call: {func_name}")
            if len(node.args) > MAX_FUNC_ARGS:
                raise ValueError(f"Function {func_name} exceeds maximum argument count.")

            self._tick()
            args = [self.evaluate(arg, depth + 1) for arg in node.args]

            if func_name in {"min", "max"}:
                if len(args) < 2:
                    raise ValueError(f"Function {func_name} requires at least two arguments.")
                return min(args) if func_name == "min" else max(args)

            if func_name == "abs":
                if len(args) != 1:
                    raise ValueError("Function abs requires exactly one argument.")
                return abs(args[0])

            if len(args) not in (1, 2):
                raise ValueError("Function round requires one or two arguments.")
            ndigits = 0
            if len(args) == 2:
                if args[1].denominator != 1:
                    raise ValueError("Function round precision must be an integer.")
                ndigits = int(args[1].numerator)
                if not -12 <= ndigits <= 12:
                    raise ValueError("Function round precision must be between -12 and 12.")
            return _round_half_up(args[0], ndigits)

        raise ValueError(f"Unsupported AST expression: {type(node).__name__}")


def calculate_decimal_safe(expression: str, max_places: int = 4) -> str:
    """Safely calculate an arithmetic expression string with exact rational precision.

    Intermediate operations use exact Fraction values parsed directly from source
    substrings (never float literals or caller's ambient Decimal context), then round
    half-up to ``max_places`` decimal places.

    Examples:
        calculate_decimal_safe('(5000 - 100) * 80%') -> '3920.00'
        calculate_decimal_safe('min(1,200,300)') -> '1.00'
    """
    if isinstance(max_places, bool) or not isinstance(max_places, int) or not 0 <= max_places <= MAX_PLACES_LIMIT:
        raise ValueError(f"max_places must be an integer between 0 and {MAX_PLACES_LIMIT}.")

    try:
        clean_expr = normalize_expression(expression)
        body = _parse_expression_ast(clean_expr)
        result = _RationalEvaluator(clean_expr).evaluate(body)
        return _format_fraction(result, max_places=max_places)
    except (TypeError, ValueError, ZeroDivisionError, ArithmeticError) as exc:
        raise ValueError(f"Failed to evaluate arithmetic expression '{expression}': {exc}") from exc
