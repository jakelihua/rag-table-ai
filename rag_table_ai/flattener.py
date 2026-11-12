"""Render pipe-table rows as named fields for retrieval and display."""

from __future__ import annotations

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

    limit = max(0, max_table_rows)
    hint = (query_hint or "").strip()
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
            for back_offset in range(1, min(10, start_i) + 1):
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

            total_rows = len(data_rows)
            selected_indices: range | list[int] = range(min(total_rows, limit))
            if total_rows > limit and limit and hint:
                matches = []
                for idx, row in enumerate(data_rows):
                    if hint in " ".join(row):
                        matches.append(idx)
                        if len(matches) == limit:
                            break
                if matches:
                    selected = set(matches)
                    for idx in matches:
                        for neighbor in (idx - 1, idx + 1):
                            if len(selected) < limit and 0 <= neighbor < total_rows:
                                selected.add(neighbor)
                    selected_indices = sorted(selected)

            # Linearize table into key-value pairs
            header_prefix = f"### Structured Table: {caption or source or 'Table'}\n"
            table_kvs: list[str] = [header_prefix]

            for row_idx in selected_indices:
                row = data_rows[row_idx]
                kv_pairs: list[str] = []
                for col_idx, h in enumerate(headers):
                    val = row[col_idx] if col_idx < len(row) else ""
                    norm_val = encode_cell_state(val)
                    if col_idx == 0:
                        norm_val = expand_interval_hint(norm_val)
                    kv_pairs.append(f"{h}: {norm_val}")
                table_kvs.append(f"- [Row {row_idx + 1}] " + " | ".join(kv_pairs))

            if total_rows > limit:
                table_kvs.append(
                    f"\n*(Table truncated: showing {len(selected_indices)} of {total_rows} rows)*"
                )

            output_parts.append("\n".join(table_kvs))
        else:
            output_parts.append(line)
            i += 1

    return "\n".join(output_parts)
