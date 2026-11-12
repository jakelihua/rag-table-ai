"""Split tables into chunks with column labels and table-relative coordinates."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from rag_table_ai.headers import resolve_composite_headers

# Limit the quadratic search to moderate widths. The greedy fallback still
# enforces the same budget and cell coverage for wider tables.
_MAX_BALANCED_COLUMNS = 32
_MAX_BALANCED_COUNTS = 4_096


@dataclass
class TableChunk:
    chunk_index: int
    total_chunks: int
    start_row: int
    end_row: int
    headers: list[str]
    markdown_text: str
    metadata: dict[str, Any]
    rows: list[list[str]] = field(default_factory=list)


@dataclass(frozen=True)
class _Part:
    start: int
    end: int
    columns: tuple[int, ...]
    text: str
    units: int = 0


class _RowOverflow(ValueError):
    pass


class _PlanningLimit(Exception):
    pass


def _render_row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _render_header(
    headers: Sequence[str],
    columns: Sequence[int],
    caption: str,
) -> str:
    lines = [f"### {caption}"] if caption else []
    lines.append(_render_row([headers[col] for col in columns]))
    lines.append(_render_row(["---"] * len(columns)))
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
        *,
        has_separator: bool | None = None,
    ) -> list[TableChunk]:
        """Split a pipe table into self-contained chunks."""
        headers, rows = resolve_composite_headers(table_markdown.splitlines(), has_separator=has_separator)
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

        caption = " ".join(caption.splitlines()).strip()
        columns = tuple(range(width))
        keys = self._repeated_column_indices(width)
        try:
            parts = self._pack_rows(headers, rows, columns, caption)
        except _RowOverflow:
            if keys is None:
                raise
            values = tuple(col for col in columns if col not in keys)
            if not values:
                raise ValueError("Repeated columns exceed the token budget.") from None
            parts = None
            if len(values) <= _MAX_BALANCED_COLUMNS:
                try:
                    parts = self._balance_columns(headers, rows, caption, keys, values)
                except _PlanningLimit:
                    pass
            if parts is None:
                parts = [
                    part
                    for group in self._greedy_column_groups(headers, rows, caption, keys, values)
                    for part in self._pack_rows(headers, rows, group, caption)
                ]

        chunks = []
        total = len(parts)
        for index, part in enumerate(parts, 1):
            text = part.text
            if caption and self.max_tokens is None:
                text = f"### {caption} (Part {index}/{total})\n{text}"
            chunks.append(TableChunk(
                chunk_index=index,
                total_chunks=total,
                start_row=part.start + 1,
                end_row=part.end,
                headers=[headers[col] for col in part.columns],
                markdown_text=text,
                rows=[[row[col] for col in part.columns] for row in rows[part.start:part.end]],
                metadata={
                    **(source_metadata or {}),
                    "table_id": table_id,
                    "caption": caption,
                    "start_row": part.start + 1,
                    "end_row": part.end,
                    "total_rows": len(rows),
                    "chunk_index": index,
                    "total_chunks": total,
                    "column_indices": [col + 1 for col in part.columns],
                },
            ))
        return chunks

    def _count(self, text: str) -> int:
        assert self.count_tokens is not None
        count = self.count_tokens(text)
        if type(count) is not int or count < 0:
            raise ValueError("count_tokens must return a nonnegative integer.")
        return count

    def _pack_rows(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        columns: tuple[int, ...],
        caption: str,
        *,
        count: Callable[[str], int] | None = None,
    ) -> list[_Part]:
        limit = self.max_tokens
        measure = count or self._count
        prefix = _render_header(headers, columns, caption if limit is not None else "")
        lines = [_render_row([row[col] for col in columns]) for row in rows]
        parts = []
        start = 0
        while start < len(lines):
            end = min(start + self.max_rows_per_chunk, len(lines))
            if limit is None:
                parts.append(_Part(start, end, columns, "\n".join([prefix, *lines[start:end]])))
                start = end
                continue

            text = f"{prefix}\n{lines[start]}"
            units = measure(text)
            if units > limit:
                raise _RowOverflow(f"Data row {start + 1} exceeds the token budget.")
            next_row = start + 1
            while next_row < end:
                candidate = f"{text}\n{lines[next_row]}"
                size = measure(candidate)
                if size > limit:
                    break
                text, units = candidate, size
                next_row += 1
            parts.append(_Part(start, next_row, columns, text, units))
            start = next_row
        return parts

    def _repeated_column_indices(self, width: int) -> set[int] | None:
        if self.repeat_columns is None:
            return None
        if any(type(col) is not int or not 1 <= col <= width for col in self.repeat_columns):
            raise ValueError("repeat_columns must contain 1-based column indices within the table.")
        keys = {col - 1 for col in self.repeat_columns}
        if len(keys) != len(self.repeat_columns):
            raise ValueError("repeat_columns must contain unique column indices.")
        return keys

    def _balance_columns(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        caption: str,
        keys: set[int],
        values: tuple[int, ...],
    ) -> list[_Part]:
        # Work backwards over contiguous value columns. Score each projection
        # after packing its rows, then add the best already solved suffix.
        remaining_counts = _MAX_BALANCED_COUNTS

        def measure(text: str) -> int:
            nonlocal remaining_counts
            if not remaining_counts:
                raise _PlanningLimit
            remaining_counts -= 1
            return self._count(text)

        size = len(values)
        minimum_parts = (len(rows) + self.max_rows_per_chunk - 1) // self.max_rows_per_chunk
        scores = {size: (0, 0)}
        choices: dict[int, tuple[int, list[_Part]]] = {}
        for start in range(size - 1, -1, -1):
            for end in range(size, start, -1):
                if start == 0 and end == size:
                    # This is the full-width projection, which already overflowed.
                    continue
                suffix = scores.get(end)
                if suffix is None:
                    continue
                if start in scores and minimum_parts + suffix[0] > scores[start][0]:
                    continue
                columns = tuple(sorted(keys.union(values[start:end])))
                try:
                    parts = self._pack_rows(headers, rows, columns, caption, count=measure)
                except _RowOverflow:
                    continue
                score = (len(parts) + suffix[0], sum(part.units for part in parts) + suffix[1])
                if start not in scores or score < scores[start]:
                    scores[start] = score
                    choices[start] = (end, parts)

        if 0 not in choices:
            # Without a viable partition, name the individually oversized column.
            for col in values:
                try:
                    self._pack_rows(headers, rows, tuple(sorted(keys | {col})), caption, count=measure)
                except _RowOverflow as exc:
                    raise ValueError(f"Column {col + 1} with repeated columns exceeds the token budget.") from exc
            raise ValueError("No column grouping fits the token budget.")

        result = []
        start = 0
        while start < size:
            start, parts = choices[start]
            result.extend(parts)
        return result

    def _greedy_column_groups(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        caption: str,
        keys: set[int],
        values: tuple[int, ...],
    ) -> list[tuple[int, ...]]:
        assert self.max_tokens is not None
        budget = self.max_tokens

        def fits_all_rows(columns: tuple[int, ...]) -> bool:
            prefix = _render_header(headers, columns, caption)
            return all(
                self._count(f"{prefix}\n{_render_row([row[col] for col in columns])}") <= budget
                for row in reversed(rows)
            )

        groups = []
        current: list[int] = []
        for col in values:
            candidate = tuple(sorted(keys.union(current, (col,))))
            if fits_all_rows(candidate):
                current.append(col)
                continue
            if current:
                groups.append(tuple(sorted(keys.union(current))))
            if not fits_all_rows(tuple(sorted(keys | {col}))):
                raise ValueError(f"Column {col + 1} with repeated columns exceeds the token budget.")
            current = [col]
        groups.append(tuple(sorted(keys.union(current))))
        return groups
