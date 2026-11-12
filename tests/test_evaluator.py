import pytest
from rag_table_ai.evaluator import calculate_decimal_safe, normalize_expression


def test_normalize_expression():
    # Fullwidth operators
    assert normalize_expression("（100 ＋ 50） × 2") == "(100 + 50) * 2"
    # Percentages
    assert normalize_expression("80%") == "(80/100)"
    assert normalize_expression("(5000 - 100) * 80%") == "(5000 - 100) * (80/100)"
    # Thousands separator stripping
    assert normalize_expression("1,200 * 2") == "1200 * 2"
    assert normalize_expression("1,200,500.50 + 100") == "1200500.50 + 100"


def test_leading_zero_thousands_comma_split_rejected():
    with pytest.raises(ValueError, match="Ambiguous comma detected"):
        normalize_expression("min(5, 000, 8, 000)")


def test_calculate_decimal_safe():
    assert calculate_decimal_safe("(5000 - 100) * 80%") == "3920.00"
    assert calculate_decimal_safe("min(1200, 2000) * 0.5") == "600.00"
    assert calculate_decimal_safe("100 / 3", max_places=4) == "33.3333"
    assert calculate_decimal_safe("1000 + 200 * 2") == "1400.00"
    # Precision test: 0.1 + 0.2 must equal 0.30, not 0.30000000000000004
    assert calculate_decimal_safe("0.1 + 0.2") == "0.30"


def test_calculate_zero_division():
    with pytest.raises(ValueError):
        calculate_decimal_safe("100 / 0")
