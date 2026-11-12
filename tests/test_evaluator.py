import decimal

import pytest

from rag_table_ai.evaluator import calculate_decimal_safe, normalize_expression


def test_normalize_expression():
    # Fullwidth and Unicode operators
    assert normalize_expression("（100 ＋ 50） × 2") == "(100 + 50) * 2"
    assert normalize_expression("100 − 25.5 ÷ 5") == "100 - 25.5 / 5"
    # Percentages
    assert normalize_expression("80%") == "(80/100)"
    assert normalize_expression("(5000 - 100) * 80%") == "(5000 - 100) * (80/100)"
    assert normalize_expression("1,200%") == "(1200/100)"
    # Thousands separator stripping outside function calls (including ,000)
    assert normalize_expression("1,000 * 2") == "1000 * 2"
    assert normalize_expression("1,200 * 2") == "1200 * 2"
    assert normalize_expression("1,200,500.50 + 100") == "1200500.50 + 100"
    # Function argument commas must never be stripped into a single number
    assert normalize_expression("min(1,200,300)") == "min(1,200,300)"
    assert normalize_expression("1,000 + min(1,200,300)") == "1000 + min(1,200,300)"


def test_leading_zero_and_malformed_commas_rejected():
    with pytest.raises(ValueError, match="Ambiguous comma detected"):
        normalize_expression("min(5, 000, 8, 000)")
    with pytest.raises(ValueError, match="Ambiguous comma detected"):
        normalize_expression("min(5,000, 8,000)")
    with pytest.raises(ValueError, match="Ambiguous comma detected"):
        normalize_expression("5, 000 * 2")
    with pytest.raises(ValueError):
        normalize_expression("0,500 + 1")
    with pytest.raises(ValueError):
        normalize_expression("(100, 200)")


def test_calculate_decimal_safe():
    assert calculate_decimal_safe("(5000 - 100) * 80%") == "3920.00"
    assert calculate_decimal_safe("min(1200, 2000) * 0.5") == "600.00"
    assert calculate_decimal_safe("min(1,200,300)") == "1.00"
    assert calculate_decimal_safe("max(1,200,300)") == "300.00"
    assert calculate_decimal_safe("1,000 + min(1,200,300)") == "1001.00"
    assert calculate_decimal_safe("100 / 3", max_places=4) == "33.3333"
    assert calculate_decimal_safe("1000 + 200 * 2") == "1400.00"
    assert calculate_decimal_safe("0.1 + 0.2") == "0.30"
    assert calculate_decimal_safe("abs(-12.345)", max_places=4) == "12.345"
    assert calculate_decimal_safe("round(2.345, 2)") == "2.35"
    assert calculate_decimal_safe("round((1 / 3) * 3 - 0.5)") == "1.00"
    assert calculate_decimal_safe("round((1234 + abs(-1)) / 10, 2)") == "123.50"


def test_high_precision_literals_bypass_float_truncation():
    # IEEE-754 float loses 0.01 when added to 1e16
    assert calculate_decimal_safe("10000000000000000.01 - 10000000000000000.0") == "0.01"
    # 30 decimal places exceed both IEEE-754 float (~15-17 digits) and default Decimal prec=28
    expr = "0.123456789012345678901234567890 + 0.000000000000000000000000000001"
    assert (
        calculate_decimal_safe(expr, max_places=30)
        == "0.123456789012345678901234567891"
    )


def test_isolated_from_caller_decimal_context():
    with decimal.localcontext() as ctx:
        ctx.prec = 1
        ctx.rounding = decimal.ROUND_FLOOR
        ctx.traps[decimal.Inexact] = True
        ctx.traps[decimal.Rounded] = True

        assert calculate_decimal_safe("100 / 3", max_places=4) == "33.3333"
        assert calculate_decimal_safe("(5000 - 100) * 80%") == "3920.00"
        assert calculate_decimal_safe("2.675", max_places=2) == "2.68"


def test_invalid_expressions_and_zero_division_raise_value_error():
    for bad_expr in [
        "",
        "100 / 0",
        "min(100)",
        "max(100)",
        "abs(1, 2)",
        "round(1.23, 0.5)",
        "1 ** 2",
        "True + 1",
        "(20 + 30)%",
        "__import__('os')",
    ]:
        with pytest.raises(ValueError):
            calculate_decimal_safe(bad_expr)


@pytest.mark.parametrize("expression", [
    "(abs)(1,234)",
    "((round)) (1,234)",
    "max(2, （abs）（1，234）)",
])
def test_parenthesized_call_targets_are_rejected_before_comma_normalization(expression):
    with pytest.raises(ValueError, match="bare function name"):
        normalize_expression(expression)
    with pytest.raises(ValueError, match="bare function name"):
        calculate_decimal_safe(expression)


@pytest.mark.parametrize(("expression", "limit"), [
    (" " * 100_000 + "1", 2048),
    ("9" * 100_000, 2048),
    ("9" * 129, 128),
])
def test_input_limits_are_enforced_without_echoing_overlong_values(expression, limit):
    with pytest.raises(ValueError, match=f"maximum length of {limit}") as error:
        calculate_decimal_safe(expression)
    assert len(str(error.value)) < 200


def test_expression_at_exact_raw_length_limit_is_accepted():
    assert calculate_decimal_safe(" " * 2047 + "1") == "1.00"
