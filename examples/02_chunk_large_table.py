#!/usr/bin/env python3
"""02_chunk_large_table.py - Preserving table headers across chunks for RAG."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag_table_ai import SourceAwareTableChunker

chunker = SourceAwareTableChunker(max_rows_per_chunk=5)

# Simulate a 12-row dataset
rows = ["| User Tier | Discount Rate | Free Shipping |", "| :--- | :--- | :--- |"]
for i in range(1, 13):
    rows.append(f"| Level {i} | {i * 2}% | {'Yes' if i > 5 else 'No'} |")
table_markdown = "\n".join(rows)

# Split table into sub-tables
chunks = chunker.split_table(table_markdown, caption="Membership Privileges")

print(f"Total Table Chunks Generated: {len(chunks)}")
for c in chunks:
    print(f"\n--- Chunk {c.chunk_index} of {c.total_chunks} (Rows {c.start_row}-{c.end_row}) ---")
    print(c.markdown_text)
