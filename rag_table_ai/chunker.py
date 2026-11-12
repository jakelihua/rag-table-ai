"""Split tables into chunks with column labels and table-relative coordinates."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from rag_table_ai.headers import resolve_composite_headers


@dataclass
class TableChunk:
    chunk_index: int
    total_chunks: int
    start_row: int
    end_row: int
    headers: list[str]
    markdown_text: str
    metadata: dict[str, Any]


def _render_row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _render_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    columns: Sequence[int],
    caption: str,
) -> str:
    lines = [f"### {caption}"] if caption else []
    lines.append(_render_row([headers[col] for col in columns]))
    lines.append(_render_row(["---"] * len(columns)))
    lines.extend(_render_row([row[col] for col in columns]) for row in rows)
    return "\n".join(lines)


class SourceAwareTableChunker:
    """Split tables by row count and, optionally, a caller-defined token budget."""

    def __init__(
        self,
        max_rows_per_chunk: int = 15,
        *,
        max_tokens: int | None = None,
        count_tokens: Callable[[str], int] | None = None,
        repeat_columns: Sequence[int] | None = None,
    ):
        if (max_tokens is None) != (count_tokens is None):
            raise ValueError("Supply max_tokens and count_tokens together.")
        if max_tokens is not None and (type(max_tokens) is not int or max_tokens < 1):
            raise ValueError("max_tokens must be a positive integer.")
        if repeat_columns is not None and max_tokens is None:
            raise ValueError("Column splitting requires a token budget.")
        self.max_rows_per_chunk = max(1, max_rows_per_chunk)
        self.max_tokens = max_tokens
        self.count_tokens = count_tokens
        # None disables column splitting. An empty sequence enables it without keys.
        self.repeat_columns = tuple(repeat_columns) if repeat_columns is not None else None

    def split_table(
        self,
        table_markdown: str,
        table_id: str = "table_1",
        caption: str = "",
    ) -> list[TableChunk]:
        """Split a pipe table into self-contained chunks."""
        headers, rows = resolve_composite_headers(table_markdown.splitlines())
        return self.split_rows(headers, rows, table_id=table_id, caption=caption)

    def split_rows(
        self,
        headers: Sequence[str],
        data_rows: Sequence[Sequence[str]],
        *,
        table_id: str = "table_1",
        caption: str = "",
        source_metadata: Mapping[str, Any] | None = None,
    ) -> list[TableChunk]:
        """Split resolved rows whose cells are already escaped for pipe Markdown."""
        width = len(headers)
        if not data_rows:
            return []
        if not width:
            raise ValueError("Data rows require at least one column.")
        rows = []
        for number, row in enumerate(data_rows, 1):
            if len(row) > width:
                raise ValueError(f"Data row {number} has {len(row)} cells; expected at most {width}.")
            rows.append(list(row) + [""] * (width - len(row)))

        caption = " ".join(caption.splitlines())
        groups = self._column_groups(headers, rows, caption)
        parts = []
        for columns in groups:
            start = 0
            while start < len(rows):
                limit = min(start + self.max_rows_per_chunk, len(rows))
                end = limit
                if self.max_tokens is not None:
                    end = start + 1
                    text = _render_table(headers, rows[start:end], columns, caption)
                    if not self._fits(text):
                        raise ValueError(f"Data row {end} exceeds the token budget.")
                    while end < limit:
                        candidate = _render_table(headers, rows[start:end + 1], columns, caption)
                        if not self._fits(candidate):
                            break
                        end += 1
                        text = candidate
                else:
                    text = _render_table(headers, rows[start:end], columns, "")
                parts.append((start, end, columns, text))
                start = end

        chunks = []
        total = len(parts)
        for index, (start, end, columns, text) in enumerate(parts, 1):
            if caption and self.max_tokens is None:
                text = f"### {caption} (Part {index}/{total})\n{text}"
            chunks.append(TableChunk(
                chunk_index=index,
                total_chunks=total,
                start_row=start + 1,
                end_row=end,
                headers=[headers[col] for col in columns],
                markdown_text=text,
                metadata={
                    **(source_metadata or {}),
                    "table_id": table_id,
                    "caption": caption,
                    "start_row": start + 1,
                    "end_row": end,
                    "total_rows": len(rows),
                    "chunk_index": index,
                    "total_chunks": total,
                    "column_indices": [col + 1 for col in columns],
                },
            ))
        return chunks

    def _fits(self, text: str) -> bool:
        assert self.count_tokens is not None and self.max_tokens is not None
        count = self.count_tokens(text)
        if type(count) is not int or count < 0:
            raise ValueError("count_tokens must return a nonnegative integer.")
        return count <= self.max_tokens

    def _column_groups(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        caption: str,
    ) -> list[tuple[int, ...]]:
        all_columns = tuple(range(len(headers)))
        if self.repeat_columns is None:
            return [all_columns]
        if any(type(col) is not int or not 1 <= col <= len(headers) for col in self.repeat_columns):
            raise ValueError("repeat_columns must contain 1-based column indices within the table.")
        keys = {col - 1 for col in self.repeat_columns}
        if len(keys) != len(self.repeat_columns):
            raise ValueError("repeat_columns must contain unique column indices.")

        def fits_all_rows(columns: tuple[int, ...]) -> bool:
            return all(self._fits(_render_table(headers, [row], columns, caption)) for row in rows)

        if fits_all_rows(all_columns):
            return [all_columns]

        groups = []
        current: list[int] = []
        for column in all_columns:
            if column in keys:
                continue
            candidate = tuple(sorted(keys.union(current, (column,))))
            if fits_all_rows(candidate):
                current.append(column)
                continue
            if current:
                groups.append(tuple(sorted(keys.union(current))))
            if not fits_all_rows(tuple(sorted(keys | {column}))):
                raise ValueError(f"Column {column + 1} with repeated columns exceeds the token budget.")
            current = [column]
        if not current:
            raise ValueError("Repeated columns exceed the token budget.")
        groups.append(tuple(sorted(keys.union(current))))
        return groups
