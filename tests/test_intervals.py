from decimal import Decimal

from rag_table_ai.intervals import expand_interval_hint, extract_range, match_interval


def test_extract_range():
    assert extract_range("10-20kg") == (10, 20)
    assert extract_range("76周岁-80周岁") == (76, 80)
    assert extract_range("100~500") == (100, 500)
    assert extract_range("50以上至100") == (50, 100)
    assert extract_range("No range here") is None


def test_match_interval():
    # Numeric containment
    assert match_interval("76周岁-80周岁", "78岁")
    assert match_interval("76周岁-80周岁", "76")
    assert match_interval("76周岁-80周岁", "80")
    assert not match_interval("76周岁-80周岁", "81")
    assert not match_interval("76周岁-80周岁", "75")

    # Weights / pricing
    assert match_interval("10kg-20kg", "15kg")
    assert match_interval("$100-$500", "350")
    assert not match_interval("$100-$500", "600")

    # Literal substring
    assert match_interval("VIP Member", "VIP")
    assert match_interval("Enterprise", "Enterprise")


def test_expand_interval_hint():
    expanded = expand_interval_hint("76-80岁", max_expanded=10)
    assert "covers: 76, 77, 78, 79, 80" in expanded

    # Not expanded if span is too wide
    not_expanded = expand_interval_hint("1-1000岁", max_expanded=10)
    assert "covers" not in not_expanded


def test_numeric_matching_checks_units_signs_and_bounds():
    assert match_interval("10–20 kg", "15 kg")
    assert not match_interval("10–20 kg", "15 lb")
    assert not match_interval("10–20 kg", "-15 kg")
    assert not match_interval("10–20 kg", "0")
    assert not match_interval("10–20 kg", "1 5")
    assert not match_interval("10 kg–20 lb", "15 kg")
    assert not match_interval("10–20 mW", "15 MW")
    assert not match_interval("$100–$500", "€350")
    assert match_interval("−10–−5 kg", "-7 kg")


def test_decimal_range_uses_whole_bounds():
    assert extract_range("1.5–2.5 kg") == (Decimal("1.5"), Decimal("2.5"))
    assert match_interval("1.5–2.5 kg", "2.5 kg")
    assert not match_interval("1.5–2.5 kg", "2.5001 kg")
    assert extract_range("2.5–1.5 kg") is None
    assert expand_interval_hint("1.5–2.5 kg") == "1.5–2.5 kg"
