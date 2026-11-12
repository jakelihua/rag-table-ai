"""Measure one MinerU table under a reproducible text or token budget."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from rag_table_ai import SourceAwareTableChunker, split_mineru_content_list, split_table_row


def coordinates(chunks):
    cells = {}
    counts = Counter()
    for chunk in chunks:
        columns = chunk.metadata.get("column_indices")
        if columns is None:
            raise ValueError("This benchmark requires chunk column metadata.")
        row_count = chunk.end_row - chunk.start_row + 1
        for row, line in enumerate(chunk.markdown_text.splitlines()[-row_count:], chunk.start_row):
            values = split_table_row(line)
            if len(values) != len(columns):
                raise ValueError(f"Chunk {chunk.chunk_index} has an inconsistent row width.")
            for col, value in zip(columns, values):
                key = row, col
                if cells.setdefault(key, value) != value:
                    raise ValueError(f"Inconsistent values for cell {key}.")
                counts[key] += 1
    return cells, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("content_list", type=Path)
    parser.add_argument("--table-block", type=int, required=True, help="Zero-based table block index.")
    parser.add_argument("--header-rows", type=int, required=True)
    parser.add_argument("--budget", type=int, required=True)
    parser.add_argument("--encoding", help="Optional tiktoken encoding; omit to count characters.")
    parser.add_argument("--max-rows", type=int, default=3)
    parser.add_argument("--key-column", type=int, action="append", default=[])
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

    expected, _ = coordinates(split_mineru_content_list(blocks, **options))
    if not expected:
        raise ValueError("Expected a table with at least one data row.")
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
    actual, counts = coordinates(chunks)
    if actual != expected or max(sizes) > args.budget:
        raise ValueError("Chunking changed cell values or exceeded the budget.")
    if any(n > 1 and col not in args.key_column for (_, col), n in counts.items()):
        raise ValueError("Chunking duplicated a non-key cell.")
    cells_json = json.dumps(sorted(actual.items()), ensure_ascii=False).encode()
    print(json.dumps({
        "encoding": args.encoding or "characters",
        "budget": args.budget,
        "data_cells": len(actual),
        "cells_sha256": hashlib.sha256(cells_json).hexdigest(),
        "chunks": len(chunks),
        "total_units": sum(sizes),
        "max_units": max(sizes),
        "repeated_key_cells": sum(counts.values()) - len(counts),
        "counter_calls": counter_calls,
        "median_ms": round(median(times), 3),
    }, indent=2))


if __name__ == "__main__":
    main()
