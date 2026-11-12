"""Look up an express shipping rate from self-contained table chunks."""

from rag_table_ai import RagTableAI, split_table_row

RATES = """\
| Weight (whole kg) | Standard (USD) | Express (USD) |
| ----------------- | -------------- | ------------- |
| 0–10 kg           | 6.00           | 9.00          |
| 11–20 kg          | 12.00          | 18.00         |
"""


def main() -> None:
    engine = RagTableAI(max_rows_per_chunk=1)
    query = "15 kg"
    chunks = engine.split_table(RATES, table_id="shipping-rates")

    # The demo uses one data row per chunk and omits the optional caption.
    matches = []
    for chunk in chunks:
        row = split_table_row(chunk.markdown_text.splitlines()[-1])
        if engine.match(row[chunk.headers.index("Weight (whole kg)")], query):
            matches.append((chunk, row))
    if len(matches) != 1:
        raise ValueError(f"Expected one shipping tier for {query}, found {len(matches)}.")

    chunk, row = matches[0]
    express = row[chunk.headers.index("Express (USD)")]
    discounted = engine.calculate(f"{express} × 80%")

    print("Row without headers:")
    print(chunk.markdown_text.splitlines()[-1])
    print("\nRetrieved chunk with headers:")
    print(chunk.markdown_text)
    print(f"Source: {chunk.metadata['table_id']}, data row {chunk.start_row}")
    print(f"Express for {query}, with 20% off: USD {discounted}")


if __name__ == "__main__":
    main()
