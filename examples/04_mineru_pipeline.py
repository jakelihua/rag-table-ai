"""Run the MinerU-to-RAG pipeline using a synthetic MinerU Content List V1."""

from collections import Counter
import json
from pathlib import Path
import re

from rag_table_ai import RagTableAI, SourceAwareTableChunker, split_mineru_content_list

FIXTURE = Path(__file__).with_name("fixtures") / "shipping_content_list.json"
BUDGET = 45


def demo_count(text: str) -> int:
    """Use reproducible regex counts for the demo, independent of a model."""
    return len(re.findall(r"\w+|[^\w\s]", text))


def main() -> None:
    content = json.loads(FIXTURE.read_text(encoding="utf-8"))
    chunker = SourceAwareTableChunker(max_tokens=BUDGET, count_tokens=demo_count, repeat_columns=(1,))
    chunks = split_mineru_content_list(
        content, source="shipping.pdf", chunker=chunker, header_rows_by_block={1: 2}
    )

    # Verify coverage using original logical coordinates, including across column groups.
    coordinates: Counter[tuple[int, int]] = Counter()
    for chunk in chunks:
        if demo_count(chunk.markdown_text) > BUDGET:
            raise AssertionError(f"Chunk {chunk.chunk_index} exceeded the demo budget.")
        for row in range(chunk.start_row, chunk.end_row + 1):
            coordinates.update((row, col) for col in chunk.metadata["column_indices"])
    expected = {(row, col) for row in (1, 2) for col in range(1, 6)}
    if set(coordinates) != expected or any(
        count != 1 for (_, col), count in coordinates.items() if col != 1
    ):
        raise AssertionError("Chunk coordinates do not cover the fixture.")
    print(f"Coverage: {len(coordinates)}/{len(expected)} logical cells across {len(chunks)} chunks")
    print(f"Largest chunk: {max(demo_count(c.markdown_text) for c in chunks)}/{BUDGET} demo count units")

    engine = RagTableAI()
    matches = []
    for chunk in chunks:
        if "Rate (USD) / Express" not in chunk.headers:
            continue
        weight_index = chunk.headers.index("Weight")
        price_index = chunk.headers.index("Rate (USD) / Express")
        for row_number, row in enumerate(chunk.rows, chunk.start_row):
            if engine.match(row[weight_index], "15 kg"):
                matches.append((chunk, row_number, row[price_index]))
    if len(matches) != 1:
        raise ValueError(f"Expected one express rate, found {len(matches)}.")

    chunk, row, price = matches[0]
    print(chunk.markdown_text)
    print(f"Express for 15 kg, with 20% off: USD {engine.calculate(f'{price} × 80%')}")
    print(f"Source: {chunk.metadata['source']}, page {chunk.metadata['page_number']}, data row {row}")


if __name__ == "__main__":
    main()
