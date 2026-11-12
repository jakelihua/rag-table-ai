"""Deterministic semantic table linearization (Chain-of-Table flattening).

Transforms 2D matrix grids into natural, unambiguous key-value tuples.
Eliminates LLM cross-row/cross-column visual misalignment and hallucination
without incurring any extra LLM API call or latency.
"""

from __future__ import annotations

import re
from typing import Any

from rag_table_ai.headers import is_markdown_separator, resolve_composite_headers
from rag_table_ai.intervals import expand_interval_hint


def encode_cell_state(val: str) -> str:
    """Encode special cell tokens into explicit readable semantic markers."""
    clean = val.strip()
    if not clean:
        return "[EMPTY]"
    if clean in ("-", "--", "/", "\\", "—", "不适用", "无", "N/A", "NA"):
        return f"{clean} (Not Applicable)"
    return clean


def flatten_table_chunk(
    text: str,
    source: str = "",
    query_hint: str | None = None,
    max_table_rows: int = 20,
) -> str:
    """Detect Markdown tables in raw text, resolve composite headers,

    and flatten them into structured key-value semantic representations.

    Args:
        text: Raw document chunk or markdown text containing tables.
        source: Optional source document name or section title.
        query_hint: Optional query string to prioritize relevant rows in large tables.
        max_table_rows: Maximum data rows to expand per table before applying sliding-window guard.

    Returns:
        Structured, flattened text optimized for LLM attention and vector retrieval.
    """
    if "|" not in text:
        return text

    lines = text.split("\n")
    output_parts: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        # Check if line is part of a markdown table
        if line.strip().startswith("|") and line.strip().endswith("|"):
            # Gather consecutive table lines
            table_lines: list[str] = []
            start_i = i
            while i < n and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                table_lines.append(lines[i])
                i += 1

            # Verify if table has separator
            has_sep = any(is_markdown_separator(ln) for ln in table_lines)
            if not has_sep or len(table_lines) < 2:
                output_parts.extend(table_lines)
                continue

            # Look back up to 10 lines for title/caption/preceding context
            caption = ""
            for back_offset in range(1, min(10, start_i + 1)):
                prev = lines[start_i - back_offset].strip()
                if prev.startswith("|"):
                    break
                if prev and not prev.startswith("#"):
                    caption = prev
                    break
                if prev.startswith("#"):
                    caption = prev.lstrip("#").strip()
                    break

            headers, data_rows = resolve_composite_headers(table_lines)
            if not headers:
                output_parts.extend(table_lines)
                continue

            # Apply large table guard if row count exceeds max_table_rows
            total_rows = len(data_rows)
            selected_rows = data_rows
            is_truncated = False

            if total_rows > max_table_rows:
                is_truncated = True
                kw = (query_hint or "").strip()
                scored_indices: list[int] = []
                for idx, row in enumerate(data_rows):
                    row_str = " ".join(row)
                    if kw and kw in row_str:
                        scored_indices.append(idx)

                if scored_indices:
                    # Keep matched rows + adjacent neighborhood + first 2 rows
                    keep = set(range(min(2, total_rows)))
                    for idx in scored_indices[:max_table_rows]:
                        for delta in (-1, 0, 1):
                            if 0 <= idx + delta < total_rows:
                                keep.add(idx + delta)
                    selected_indices = sorted(list(keep))[:max_table_rows]
                    selected_rows = [data_rows[idx] for idx in selected_indices]
                else:
                    selected_rows = data_rows[:max_table_rows]

            # Linearize table into key-value pairs
            header_prefix = f"### Structured Table: {caption or source or 'Table'}\n"
            table_kvs: list[str] = [header_prefix]

            for row_idx, row in enumerate(selected_rows, 1):
                kv_pairs: list[str] = []
                for col_idx, h in enumerate(headers):
                    val = row[col_idx] if col_idx < len(row) else ""
                    norm_val = encode_cell_state(val)
                    if col_idx == 0:
                        norm_val = expand_interval_hint(norm_val)
                    kv_pairs.append(f"{h}: {norm_val}")
                table_kvs.append(f"- [Row {row_idx}] " + " | ".join(kv_pairs))

            if is_truncated:
                table_kvs.append(
                    f"\n*(Table truncated: showing {len(selected_rows)} of {total_rows} rows)*"
                )

            output_parts.append("\n".join(table_kvs))
        else:
            output_parts.append(line)
            i += 1

    return "\n".join(output_parts)
