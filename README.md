# rag-table-ai

**Keep the headers with the rows your RAG pipeline retrieves.**

[简体中文](README.zh-CN.md) · [Quickstart](#quickstart) · [Shipping demo](examples/03_shipping_rates.py)

`rag-table-ai` is a lightweight Python library for splitting pipe tables into chunks that carry their column labels. It can also render rows as named fields, check numeric ranges, and evaluate supported arithmetic expressions. The core has no runtime dependencies and makes no LLM calls.

**Example query:** What does express shipping cost for 15 kg with a 20% discount?

```text
Plain row fragment
  | 11–20 kg | 12.00 | 18.00 |
  Which price is Express?

Chunk with column labels
  | Weight (whole kg) | Standard (USD) | Express (USD) |
  | 11–20 kg          | 12.00          | 18.00         |
  Express: USD 18.00 × 80% = USD 14.40
  Evidence: shipping-rates, data row 2
```

## Quickstart

Requires Python 3.9 or newer. Run these commands from the root of your checkout.

```bash
python -m pip install .
python examples/03_shipping_rates.py
```

```python
from rag_table_ai import RagTableAI

table = """\
| Weight   | Standard (USD) | Express (USD) |
| -------- | -------------- | ------------- |
| 0–10 kg  | 6.00           | 9.00          |
| 11–20 kg | 12.00          | 18.00         |
"""

engine = RagTableAI(max_rows_per_chunk=1)
_, chunk = engine.split_table(table, table_id="shipping-rates")

print(chunk.markdown_text)  # Row 2 carries Weight, Standard, and Express.
assert (chunk.start_row, chunk.end_row) == (2, 2)
assert engine.match("11–20 kg", "15 kg")
assert not engine.match("11–20 kg", "15 lb")
assert engine.calculate("18.00 × 80%") == "14.40"
```

The [shipping demo](examples/03_shipping_rates.py) selects the matching tier and price column from the chunks. The caller supplies the quantity, column name, and discount.

## Pipeline integration

1. Pass an extracted pipe table to `split_table()`. Index each chunk's `markdown_text` so the search text includes column labels. Store `metadata` alongside it for table and row references.
2. Use `flatten()` for a named-field view when it suits the consumer. Its row cap can omit rows, so use the chunks for full-table coverage. When a literal query hint matches, matched rows take priority within the cap.
3. Pass a quantity to `match()` and use `calculate()` for a supported arithmetic expression. If more than one interval matches, the caller can report ambiguity or apply its own rule.

| Capability | Current contract |
| --- | --- |
| Table input | Pipe tables with one header row or the [two-row convention](examples/01_quickstart.py) where blank parent cells extend the previous label. Extract PDFs, images, and HTML upstream. |
| Chunking | Splits by row count. Chunks repeat resolved column labels and expose inclusive, 1-based data row numbers within the table. Over-wide data rows raise `ValueError`; short rows are padded on the right. |
| Range matching | Closed ranges of signed integers or decimals. Explicit units must agree; there is no unit conversion. A bare number inherits the range's unit. Pass a quantity such as `15 kg` or a text label. |
| Arithmetic | Restricted arithmetic with Decimal evaluation, percentages, and common full-width operators. The caller provides the expression. Check rounding and input conventions for your use case. |

## Evaluation

The shipping example demonstrates the behavior on a small fixture. For a retrieval benchmark, measure whether the top results include the correct cell **and its column label**. Compare plain text splitting and a baseline that already repeats table headers under the same retrieval and context budget. Report core processing time, indexed text size, and downstream context tokens separately.

## Development

```bash
python -m pip install '.[dev]'
python -m pytest -q
```

Found a table that loses context or matches the wrong tier? Open an issue with a small, sanitized table, the query, and the expected row and column.

[MIT License](LICENSE)
