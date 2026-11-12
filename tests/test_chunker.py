from rag_table_ai.chunker import SourceAwareTableChunker


def test_source_aware_table_chunker():
    chunker = SourceAwareTableChunker(max_rows_per_chunk=5)
    lines = ["| User ID | Score | Tier |", "| --- | --- | --- |"]
    for i in range(1, 13):
        lines.append(f"| user_{i} | {i * 10} | Gold |")
    table_md = "\n".join(lines)

    chunks = chunker.split_table(table_md, caption="Leaderboard")
    assert len(chunks) == 3  # 12 rows / 5 = 3 chunks

    # Every chunk must have headers
    for idx, c in enumerate(chunks, 1):
        assert c.chunk_index == idx
        assert c.total_chunks == 3
        assert "| User ID | Score | Tier |" in c.markdown_text
        assert "| --- | --- | --- |" in c.markdown_text

    # Check boundaries
    assert chunks[0].start_row == 1
    assert chunks[0].end_row == 5
    assert chunks[1].start_row == 6
    assert chunks[1].end_row == 10
    assert chunks[2].start_row == 11
    assert chunks[2].end_row == 12
