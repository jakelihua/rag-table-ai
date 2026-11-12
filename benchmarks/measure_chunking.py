"""Measure one MinerU table under a reproducible text or token budget."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from rag_table_ai import SourceAwareTableChunker, is_markdown_separator, split_mineru_content_list, split_table_row
from rag_table_ai.html_tables import _markdown_cell


def coordinates(chunks):
    cells = {}
    counts = Counter()
    labels = {}
    for chunk in chunks:
        columns = chunk.metadata.get("column_indices")
        if not columns or len(set(columns)) != len(columns) or min(columns) < 1:
            raise ValueError("Expected unique, one-based chunk column indices.")
        row_count = chunk.end_row - chunk.start_row + 1
        lines = chunk.markdown_text.splitlines()
        if row_count < 1 or len(lines) < row_count + 2 or not is_markdown_separator(lines[-row_count - 1]):
            raise ValueError(f"Chunk {chunk.chunk_index} lacks a valid header or data rows.")
        paths = chunk.metadata.get("header_paths")
        if paths is None:
            headers = chunk.headers
            rendered = headers
        else:
            headers = [" / ".join(paths[col - 1]) for col in columns]
            rendered = [_markdown_cell(label) for label in headers]
        # Older HTML chunks exposed the rendered labels in .headers.
        if (
            len(headers) != len(columns)
            or chunk.headers not in (headers, rendered)
            or split_table_row(lines[-row_count - 2]) != rendered
            or len(split_table_row(lines[-row_count - 1])) != len(columns)
        ):
            raise ValueError(f"Chunk {chunk.chunk_index} has inconsistent header labels.")
        for col, label in zip(columns, headers):
            if labels.setdefault(col, label) != label:
                raise ValueError(f"Inconsistent labels for column {col}.")
        for row, line in enumerate(lines[-row_count:], chunk.start_row):
            values = split_table_row(line)
            if len(values) != len(columns):
                raise ValueError(f"Chunk {chunk.chunk_index} has an inconsistent row width.")
            for col, value in zip(columns, values):
                key = row, col
                if cells.setdefault(key, value) != value:
                    raise ValueError(f"Inconsistent values for cell {key}.")
                counts[key] += 1
    return cells, counts, labels


def pair_rows(chunks, pair):
    return {
        row for chunk in chunks if set(pair) <= set(chunk.metadata["column_indices"])
        for row in range(chunk.start_row, chunk.end_row + 1)
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("content_list", type=Path)
    parser.add_argument("--table-block", type=int, required=True, help="Zero-based table block index.")
    parser.add_argument("--header-rows", type=int, required=True)
    parser.add_argument("--budget", type=int, required=True)
    parser.add_argument("--encoding", help="Optional tiktoken encoding; omit to count characters.")
    parser.add_argument("--max-rows", type=int, default=3)
    parser.add_argument("--key-column", type=int, action="append", default=[])
    parser.add_argument("--column-pair", type=int, nargs=2, action="append", default=[],
                        help="Report rows whose two original columns share a chunk.")
    parser.add_argument("--repeat", type=int, default=10)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be positive.")
    blocks = json.loads(args.content_list.read_text(encoding="utf-8"))
    index = args.table_block
    if (
        not isinstance(blocks, list)
        or not 0 <= index < len(blocks)
        or not isinstance(blocks[index], dict)
        or blocks[index].get("type") != "table"
    ):
        parser.error("--table-block must identify a table block in a flat Content List V1.")
    blocks = [block if i == index else {"type": "text"} for i, block in enumerate(blocks)]
    options = {"source": args.content_list.stem, "header_rows_by_block": {index: args.header_rows}}

    measure = len
    if args.encoding:
        import tiktoken

        tokenizer = tiktoken.get_encoding(args.encoding)

        def measure(text):
            return len(tokenizer.encode_ordinary(text))

    counter_calls = 0

    def count(text):
        nonlocal counter_calls
        counter_calls += 1
        return measure(text)

    expected, _, expected_labels = coordinates(split_mineru_content_list(blocks, **options))
    if not expected:
        raise ValueError("Expected a table with at least one data row.")
    for pair in args.column_pair:
        if pair[0] == pair[1] or any(col not in expected_labels for col in pair):
            parser.error("--column-pair requires two distinct original column indices.")
    chunker = SourceAwareTableChunker(
        args.max_rows, max_tokens=args.budget, count_tokens=count, repeat_columns=args.key_column,
    )

    def split():
        return split_mineru_content_list(blocks, chunker=chunker, **options)

    split()
    times = []
    for _ in range(args.repeat):
        counter_calls = 0
        start = perf_counter()
        chunks = split()
        times.append((perf_counter() - start) * 1_000)
    sizes = [measure(chunk.markdown_text) for chunk in chunks]
    actual, counts, labels = coordinates(chunks)
    if actual != expected or labels != expected_labels or max(sizes) > args.budget:
        raise ValueError("Chunking changed cell values or exceeded the budget.")
    if any(n > 1 and col not in args.key_column for (_, col), n in counts.items()):
        raise ValueError("Chunking duplicated a non-key cell.")
    cells_json = json.dumps(sorted(actual.items()), ensure_ascii=False).encode()
    headers_json = json.dumps(sorted(labels.items()), ensure_ascii=False).encode()
    row_total = len({row for row, _ in actual})
    print(json.dumps({
        "encoding": args.encoding or "characters",
        "budget": args.budget,
        "data_cells": len(actual),
        "cells_sha256": hashlib.sha256(cells_json).hexdigest(),
        "headers_sha256": hashlib.sha256(headers_json).hexdigest(),
        "chunks": len(chunks),
        "same_chunk_column_pairs": {
            ",".join(map(str, pair)): {"rows_covered": len(pair_rows(chunks, pair)), "rows_total": row_total}
            for pair in args.column_pair
        },
        "total_units": sum(sizes),
        "max_units": max(sizes),
        "repeated_key_cells": sum(counts.values()) - len(counts),
        "counter_calls": counter_calls,
        "median_ms": round(median(times), 3),
    }, indent=2))


if __name__ == "__main__":
    main()
