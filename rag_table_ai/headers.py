"""Composite and hierarchical table header resolution.

Solves the common LLM failure where two-tier table headers (common in financial reports,
rate cards, pricing sheets, and technical specifications) get dropped or corrupted.
"""

from __future__ import annotations

import re

_MD_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")


def is_markdown_separator(line: str) -> bool:
    """Return True if line is a Markdown table separator like | --- | :---: |."""
    stripped = line.strip()
    return bool(stripped and _MD_SEPARATOR_RE.match(stripped))


def split_table_row(line: str) -> list[str]:
    """Split a markdown pipe table row into stripped cell values."""
    raw = line.strip()
    if raw.startswith("|"):
        raw = raw[1:]
    if raw.endswith("|"):
        raw = raw[:-1]
    return [c.strip() for c in raw.split("|")]


def resolve_composite_headers(
    lines: list[str],
) -> tuple[list[str], list[list[str]]]:
    """Parse a block of Markdown table lines and resolve single or multi-row headers.

    Returns:
        tuple of (headers, data_rows)
        where headers is a list of resolved column names,
        and data_rows is a list of rows with corresponding cell values.
    """
    clean_lines = [ln.strip() for ln in lines if ln.strip()]
    if not clean_lines:
        return [], []

    first_row = split_table_row(clean_lines[0])
    if len(clean_lines) == 1:
        return first_row, []

    # Detect separator position
    sep_idx = -1
    for idx, ln in enumerate(clean_lines[:4]):
        if is_markdown_separator(ln):
            sep_idx = idx
            break

    if sep_idx == 1:
        # Standard single-row header:
        # Line 0: Header
        # Line 1: Separator
        # Line 2+: Data
        headers = first_row
        data_rows = [
            split_table_row(ln)
            for ln in clean_lines[2:]
            if not is_markdown_separator(ln)
        ]
        return headers, data_rows

    if sep_idx == 2:
        # Two-tier composite header:
        # Line 0: Parent Category (often with empty/spanning cells)
        # Line 1: Child Subcategories
        # Line 2: Separator
        # Line 3+: Data
        parent_row = first_row
        child_row = split_table_row(clean_lines[1])
        max_cols = max(len(parent_row), len(child_row))
        p_padded = parent_row + [""] * (max_cols - len(parent_row))
        c_padded = child_row + [""] * (max_cols - len(child_row))

        headers: list[str] = []
        last_parent = ""
        for p, c in zip(p_padded, c_padded):
            if p:
                last_parent = p
            effective_p = p or last_parent
            if effective_p and c and effective_p != c:
                headers.append(f"{effective_p} ({c})")
            elif c:
                headers.append(c)
            elif effective_p:
                headers.append(effective_p)
            else:
                headers.append(f"Column_{len(headers) + 1}")

        data_rows = [
            split_table_row(ln)
            for ln in clean_lines[3:]
            if not is_markdown_separator(ln)
        ]
        return headers, data_rows

    # Fallback when no standard separator line is present
    headers = first_row
    data_rows = [
        split_table_row(ln)
        for ln in clean_lines[1:]
        if not is_markdown_separator(ln)
    ]
    return headers, data_rows
