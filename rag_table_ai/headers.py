"""Resolve single-row and two-row headers in pipe tables."""

from __future__ import annotations

import re

_MD_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
# A pipe is a separator when the preceding run of backslashes has even length.
_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)(?:\\\\)*(\|)")


def is_markdown_separator(line: str) -> bool:
    """Return True if line is a Markdown table separator like | --- | :---: |."""
    return _MD_SEPARATOR_RE.fullmatch(line.strip()) is not None


def split_table_row(line: str) -> list[str]:
    """Split a pipe row, keeping escaped pipes in the original cell text."""
    raw = line.strip()
    cells: list[str] = []
    start = 0
    for match in _UNESCAPED_PIPE_RE.finditer(raw):
        pipe = match.start(1)
        if pipe != 0:
            cells.append(raw[start:pipe].strip())
        start = pipe + 1
    if start < len(raw) or not cells:
        cells.append(raw[start:].strip())
    return cells


def resolve_composite_headers(
    lines: list[str],
) -> tuple[list[str], list[list[str]]]:
    """Resolve column labels and return the parsed data rows.

    A delimiter can follow one header row or a two-row header whose blank
    parent cells continue the previous label. Without a delimiter, the first
    row is the header. Rows wider than the resolved header raise ValueError.
    """
    clean_lines = [line.strip() for line in lines if line.strip()]
    if not clean_lines:
        return [], []

    separator = next(
        (i for i, line in enumerate(clean_lines) if is_markdown_separator(line)),
        None,
    )
    if separator is not None and separator not in (1, 2):
        raise ValueError("Expected a Markdown delimiter after one or two header rows.")

    headers = split_table_row(clean_lines[0])
    if separator == 2:
        children = split_table_row(clean_lines[1])
        width = max(len(headers), len(children))
        parents = headers + [""] * (width - len(headers))
        children += [""] * (width - len(children))
        headers = []
        parent = ""
        for label, child in zip(parents, children):
            parent = label or parent
            if parent and child and parent != child:
                headers.append(f"{parent} ({child})")
            else:
                headers.append(child or parent or f"Column_{len(headers) + 1}")

    if separator is not None and len(split_table_row(clean_lines[separator])) != len(headers):
        raise ValueError("Markdown delimiter width does not match the resolved header width.")

    data_start = 1 if separator is None else separator + 1
    rows = []
    for row_number, line in enumerate(clean_lines[data_start:], 1):
        row = split_table_row(line)
        if len(row) > len(headers):
            raise ValueError(
                f"Data row {row_number} has {len(row)} cells; "
                f"the header defines {len(headers)} columns."
            )
        rows.append(row)
    return headers, rows
