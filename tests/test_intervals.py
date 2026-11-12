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
