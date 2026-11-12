from rag_table_ai.flattener import encode_cell_state, flatten_table_chunk


def test_encode_cell_state():
    assert encode_cell_state("") == "[EMPTY]"
    assert encode_cell_state("-") == "- (Not Applicable)"
    assert encode_cell_state("N/A") == "N/A (Not Applicable)"
    assert encode_cell_state("1200") == "1200"


def test_flatten_standard_table():
    md = """
### Pricing Sheet
| Plan | Price | Bandwidth |
| --- | --- | --- |
| Basic | $10 | 100GB |
| Pro | $30 | 1TB |
"""
    flattened = flatten_table_chunk(md, source="Pricing Sheet")
    assert "Structured Table: Pricing Sheet" in flattened
    assert "- [Row 1] Plan: Basic | Price: $10 | Bandwidth: 100GB" in flattened
    assert "- [Row 2] Plan: Pro | Price: $30 | Bandwidth: 1TB" in flattened


def test_flatten_two_tier_table_with_intervals():
    md = """
| Weight Range | Express Delivery | | Standard Freight | |
| | First 1kg | Extra 1kg | First 1kg | Extra 1kg |
| --- | --- | --- | --- | --- |
| 1-3kg | $15 | $5 | $8 | $2 |
| 4-10kg | $25 | $4 | $12 | $1.5 |
"""
    flattened = flatten_table_chunk(md, source="Shipping Rates")
    assert "Express Delivery (First 1kg)" in flattened
    assert "Express Delivery (Extra 1kg)" in flattened
    assert "covers: 1, 2, 3" in flattened


def test_large_table_truncation_guard():
    rows = ["| ID | Value | Status |", "| --- | --- | --- |"]
    for i in range(1, 31):
        rows.append(f"| Item_{i} | {i * 10} | Active |")
    md = "\n".join(rows)

    flattened = flatten_table_chunk(md, max_table_rows=10, query_hint="Item_25")
    assert "Table truncated: showing" in flattened
    assert "Item_25" in flattened
