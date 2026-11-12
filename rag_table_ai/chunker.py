"""Source-Aware Table Chunking for RAG pipelines.

Solves the classic RAG table truncation disaster:
When a 100-row table is split into multiple chunks, subsequent chunks lose their headers,
leaving LLMs completely blind to column meanings.

SourceAwareTableChunker guarantees:
1. Every chunk inherits the verified full headers (repeated headers).
2. Physical row tracking: start_row and end_row metadata are preserved.
3. Zero silent row dropping: 100% data conservation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rag_table_ai.headers import is_markdown_separator, resolve_composite_headers


@dataclass
class TableChunk:
    chunk_index: int
    total_chunks: int
    start_row: int
    end_row: int
    headers: list[str]
    markdown_text: str
    metadata: dict[str, Any]


class SourceAwareTableChunker:
    """Chunk large Markdown tables into self-contained, header-preserving sub-tables."""

    def __init__(self, max_rows_per_chunk: int = 15):
        self.max_rows_per_chunk = max(1, max_rows_per_chunk)

    def split_table(
        self,
        table_markdown: str,
        table_id: str = "table_1",
        caption: str = "",
    ) -> list[TableChunk]:
        """Split a Markdown table into self-contained TableChunk instances.

        Each chunk carries the complete header row and markdown table formatting.
        """
        lines = [ln.strip() for ln in table_markdown.strip().split("\n") if ln.strip()]
        if not lines:
            return []

        headers, data_rows = resolve_composite_headers(lines)
        if not headers or not data_rows:
            return []

        total_rows = len(data_rows)
        step = self.max_rows_per_chunk
        total_chunks = (total_rows + step - 1) // step
        chunks: list[TableChunk] = []

        header_line = "| " + " | ".join(headers) + " |"
        separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"

        for idx in range(total_chunks):
            start = idx * step
            end = min(start + step, total_rows)
            slice_rows = data_rows[start:end]

            chunk_lines = []
            if caption:
                chunk_lines.append(f"### {caption} (Part {idx + 1}/{total_chunks})")
            chunk_lines.append(header_line)
            chunk_lines.append(separator_line)

            for row in slice_rows:
                padded = row + [""] * (len(headers) - len(row))
                chunk_lines.append("| " + " | ".join(padded[: len(headers)]) + " |")

            chunk_md = "\n".join(chunk_lines)
            chunks.append(
                TableChunk(
                    chunk_index=idx + 1,
                    total_chunks=total_chunks,
                    start_row=start + 1,
                    end_row=end,
                    headers=headers,
                    markdown_text=chunk_md,
                    metadata={
                        "table_id": table_id,
                        "caption": caption,
                        "start_row": start + 1,
                        "end_row": end,
                        "total_rows": total_rows,
                        "chunk_index": idx + 1,
                        "total_chunks": total_chunks,
                    },
                )
            )

        return chunks
