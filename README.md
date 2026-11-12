# rag-table-ai

**Keep the headers with the rows your RAG pipeline retrieves.**

[简体中文](README.zh-CN.md) · [Quickstart](#quickstart) · [MinerU](#mineru-and-html-tables) · [Shipping demo](examples/03_shipping_rates.py)

`rag-table-ai` is a lightweight Python library for splitting pipe tables into chunks that carry their column labels. It also supports HTML tables from MinerU, budgeted row and column splitting, numeric ranges, and restricted arithmetic. The core has no runtime dependencies and makes no LLM calls.

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
| Table input | Pipe tables with one header row or the [two-row convention](examples/01_quickstart.py), and individual HTML tables with merged cells. Extract PDFs and images upstream. For delimiterless pipe tables with dash-only rows, pass `has_separator=False`. |
| Chunking | Splits by row count and an optional token budget. Chunks repeat resolved column labels and expose inclusive, 1-based table row and column coordinates. Over-wide data rows raise `ValueError`; short rows are padded on the right. |
| Range matching | Closed ranges of signed integers or decimals, with standard comma grouping and common units and currency codes. Explicit units must agree; there is no unit conversion. A bare number inherits the range's unit. Pass a quantity such as `15 kg` or a text label. Unparsed numeric text is compared only as an exact label. |
| Arithmetic | Restricted exact rational arithmetic (`+`, `-`, `*`, `/`, `min`, `max`, `abs`, `round`), percentages, and common full-width operators. Outside function calls, standard thousands separators are stripped. Inside a call, commas separate arguments. Use bare function names, such as `min(1, 2)`. The raw input is limited to 2,048 characters. Rounded half-up on output without relying on global `Decimal` context. |

## MinerU and HTML tables

```bash
python examples/04_mineru_pipeline.py
```

The [MinerU demo](examples/04_mineru_pipeline.py) uses a [synthetic MinerU Content List V1 fixture](examples/fixtures/shipping_content_list.json) with two header rows and merged cells. It preserves all 10 logical data cells across four chunks, selects the express rate for 15 kg, and returns **USD 14.40** with the citation **shipping.pdf, page 3, data row 2**. The demo uses a regex count for reproducibility.

```python
import json
from pathlib import Path

from rag_table_ai import SourceAwareTableChunker, split_mineru_content_list

path = Path("examples/fixtures/shipping_content_list.json")
blocks = json.loads(path.read_text(encoding="utf-8"))
chunker = SourceAwareTableChunker(
    max_rows_per_chunk=10,
    max_tokens=185,
    count_tokens=len,  # Character budget for this example. Use your tokenizer for a token budget.
    repeat_columns=(1,),
)
chunks = split_mineru_content_list(
    blocks,
    source="shipping.pdf",
    chunker=chunker,
    header_rows_by_block={1: 2},
)
assert chunks
assert all(len(chunk.markdown_text) <= 185 for chunk in chunks)
assert all(chunk.metadata["page_number"] == 3 for chunk in chunks)
```

- **Input.** Pass a flat MinerU Content List V1. The adapter reads HTML from `table_body` or `html`, skips non-table blocks, and attaches the original document identifier, caption, footnotes, and page or bounding box data when present. Use `split_html_table()` for a standalone HTML table. See the [MinerU output documentation](https://opendatalab.github.io/MinerU/reference/output_files/) for export options.
- **Header detection.** HTML spans are expanded before chunking. The parser uses `thead`, leading all-`th` rows, or the first row. Blank `td` cells can accompany `th` cells. For ambiguous mixed headers or multiple header rows written with `td`, set `header_rows_by_block` with **zero-based input block indices**, or pass `header_rows` to `split_html_table()`. Nested tables, nonrectangular grids, and invalid spans raise `ValueError`. Positive `rowspan` and `colspan` are supported. At least one data row is required.
- **Budget.** Supply `max_tokens` with a deterministic `count_tokens(text)`, such as `lambda text: len(tokenizer.encode(text))`. It counts the full `markdown_text`, including the caption and headers. If a row is too wide, `repeat_columns=(1,)` permits column groups and repeats column 1 as the row key. Use `()` for groups without repeated keys, or `None` to report an overflow. An indivisible row or column group raises `ValueError`. When projecting up to 32 non-key columns, the planner scores adjacent column groups by the resulting chunk count, then total measured size. The planner falls back to greedy grouping beyond 32 non-key columns or 4,096 candidate token counts.
- **Coordinates.** `start_row`, `end_row`, and `column_indices` refer to the logical table, starting at 1. `header_paths` is an immutable tuple of tuples for the whole table. `column_indices` maps chunk columns to those paths. `page_idx` is zero-based, and `page_number` is the one-based page for citations. For HTML input, use `chunk.rows` and `chunk.headers` for decoded values. Use `markdown_text` for indexing. The adapter carries the supplied **table-level** bounding box and treats each emitted table block independently.

## Evaluation

The [wide table benchmark](docs/chunking-benchmark.md) compares both planners on a real MinerU export. At a 64-token budget, it produced 25 chunks instead of 34 while preserving all 110 logical cells. One measured column pair lost same-chunk coverage at that budget. The shipping example demonstrates the behavior on a small fixture. For a retrieval benchmark, measure whether the top results include the correct cell **and its column label**. Compare plain text splitting and a baseline that already repeats table headers under the same retrieval and context budget. Report core processing time, indexed text size, and downstream context tokens separately.

## Development

```bash
python -m pip install '.[dev]'
python -m pytest -q
```

Found a table that loses context or matches the wrong tier? [Report a small, sanitized example](https://github.com/jakelihua/rag-table-ai/issues/new?template=table-case.md).

[MIT License](LICENSE)
