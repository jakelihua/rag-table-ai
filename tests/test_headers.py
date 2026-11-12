from rag_table_ai.headers import is_markdown_separator, resolve_composite_headers, split_table_row


def test_split_table_row():
    row = "| A | B | C |"
    assert split_table_row(row) == ["A", "B", "C"]
    row_no_pipes = "A | B | C"
    assert split_table_row(row_no_pipes) == ["A", "B", "C"]


def test_is_markdown_separator():
    assert is_markdown_separator("| --- | :---: | ---: |")
    assert is_markdown_separator("|---|---|")
    assert not is_markdown_separator("| Header 1 | Header 2 |")
    assert not is_markdown_separator("")


def test_resolve_single_row_headers():
    table = [
        "| Name | Age | Department |",
        "| --- | --- | --- |",
        "| Alice | 30 | Engineering |",
        "| Bob | 25 | Design |",
    ]
    headers, rows = resolve_composite_headers(table)
    assert headers == ["Name", "Age", "Department"]
    assert len(rows) == 2
    assert rows[0] == ["Alice", "30", "Engineering"]
    assert rows[1] == ["Bob", "25", "Design"]


def test_resolve_two_tier_composite_headers():
    table = [
        "| Tier Level | Standard Plan | | Enterprise Plan | |",
        "| | Monthly | Yearly | Monthly | Yearly |",
        "| --- | --- | --- | --- | --- |",
        "| Tier 1 | $10 | $100 | $50 | $500 |",
        "| Tier 2 | $20 | $200 | $100 | $1000 |",
    ]
    headers, rows = resolve_composite_headers(table)
    assert headers == [
        "Tier Level",
        "Standard Plan (Monthly)",
        "Standard Plan (Yearly)",
        "Enterprise Plan (Monthly)",
        "Enterprise Plan (Yearly)",
    ]
    assert len(rows) == 2
    assert rows[0] == ["Tier 1", "$10", "$100", "$50", "$500"]
