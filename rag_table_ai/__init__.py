"""Header-preserving table chunking and numeric lookup helpers for RAG."""

from __future__ import annotations

from rag_table_ai.chunker import SourceAwareTableChunker, TableChunk
from rag_table_ai.evaluator import calculate_decimal_safe, normalize_expression
from rag_table_ai.flattener import encode_cell_state, flatten_table_chunk
from rag_table_ai.headers import is_markdown_separator, resolve_composite_headers, split_table_row
from rag_table_ai.intervals import expand_interval_hint, extract_range, match_interval

__version__ = "0.1.0"
__all__ = [
    "RagTableAI",
    "SourceAwareTableChunker",
    "TableChunk",
    "flatten_table_chunk",
    "resolve_composite_headers",
    "split_table_row",
    "is_markdown_separator",
    "match_interval",
    "extract_range",
    "expand_interval_hint",
    "encode_cell_state",
    "normalize_expression",
    "calculate_decimal_safe",
]


class RagTableAI:
    """Unified facade for rag-table-ai table processing and evaluation."""

    def __init__(self, max_table_rows: int = 20, max_rows_per_chunk: int = 15):
        self.max_table_rows = max_table_rows
        self.chunker = SourceAwareTableChunker(max_rows_per_chunk=max_rows_per_chunk)

    def flatten(
        self,
        markdown_text: str,
        source: str = "",
        query_hint: str | None = None,
    ) -> str:
        """Render Markdown table rows as named fields."""
        return flatten_table_chunk(
            text=markdown_text,
            source=source,
            query_hint=query_hint,
            max_table_rows=self.max_table_rows,
        )

    def split_table(
        self,
        table_markdown: str,
        table_id: str = "table_1",
        caption: str = "",
    ) -> list[TableChunk]:
        """Split large table into header-preserving sub-tables for RAG chunking."""
        return self.chunker.split_table(
            table_markdown=table_markdown,
            table_id=table_id,
            caption=caption,
        )

    def match(self, cell_text: str, query_text: str) -> bool:
        """Match a quantity against a closed interval or match a text label."""
        return match_interval(cell_text, query_text)

    def calculate(self, expression: str, max_places: int = 4) -> str:
        """Safely calculate arithmetic expression string with Decimal precision."""
        return calculate_decimal_safe(expression, max_places=max_places)
