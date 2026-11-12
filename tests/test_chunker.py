import pytest

from rag_table_ai import split_table_row
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


def test_chunker_rejects_extra_cells():
    table = "| Item | Cost |\n| --- | --- |\n| A | 1 | unexpected |"
    with pytest.raises(ValueError, match=r"Data row 1 has 3 cells"):
        SourceAwareTableChunker().split_table(table)


def test_chunker_keeps_escaped_pipes_and_dash_values():
    table = "| Item | Cost |\n| --- | --- |\n| A \\| B | 1 |\n| - | - |"
    chunks = SourceAwareTableChunker(max_rows_per_chunk=1).split_table(table)
    assert [chunk.start_row for chunk in chunks] == [1, 2]
    assert chunks[0].markdown_text.endswith("| A \\| B | 1 |")
    assert chunks[1].markdown_text.endswith("| - | - |")


def test_budget_counts_rendered_headers_and_caption():
    table = "| Item | Cost |\n| --- | --- |\n| A | 1 |\n| B | 2 |\n| C | 3 |"
    chunker = SourceAwareTableChunker(max_tokens=49, count_tokens=len)
    chunks = chunker.split_table(table, caption="Rates")
    assert [(c.start_row, c.end_row) for c in chunks] == [(1, 1), (2, 2), (3, 3)]
    assert all(c.markdown_text.startswith("### Rates\n| Item | Cost |") for c in chunks)
    assert all(len(c.markdown_text) <= 49 for c in chunks)


def test_wide_budget_repeats_key_and_preserves_original_columns():
    headers = ["Key", "First", "Second", "Third"]
    rows = [["A", "a" * 16, "b" * 16, "c" * 16], ["B", "d" * 16, "e" * 16, "f" * 16]]
    budget = 70
    chunker = SourceAwareTableChunker(max_tokens=budget, count_tokens=len, repeat_columns=(1,))
    chunks = chunker.split_rows(headers, rows)

    reconstructed = {}
    for chunk in chunks:
        assert len(chunk.markdown_text) <= budget
        assert chunk.metadata["column_indices"][0] == 1
        for row_idx, line in enumerate(chunk.markdown_text.splitlines()[2:], chunk.start_row):
            for col_idx, cell in zip(chunk.metadata["column_indices"], split_table_row(line)):
                reconstructed[row_idx, col_idx] = cell
    assert reconstructed == {
        (row_idx, col_idx): cell
        for row_idx, row in enumerate(rows, 1)
        for col_idx, cell in enumerate(row, 1)
    }


def test_budget_overflow_never_silently_emits_a_partial_row():
    table = "| Key | Detail |\n| --- | --- |\n| A | " + "x" * 80 + " |"
    with pytest.raises(ValueError, match="Data row 1 exceeds"):
        SourceAwareTableChunker(max_tokens=65, count_tokens=len).split_table(table)
    with pytest.raises(ValueError, match="Column 2 with repeated columns exceeds"):
        SourceAwareTableChunker(max_tokens=65, count_tokens=len, repeat_columns=(1,)).split_table(table)


def _assert_budgeted_table(chunks, headers, rows, budget, key_columns=()):
    seen = {}
    for index, chunk in enumerate(chunks, 1):
        assert chunk.chunk_index == index
        assert chunk.total_chunks == len(chunks)
        assert len(chunk.markdown_text) <= budget
        columns = chunk.metadata["column_indices"]
        assert set(key_columns) <= set(columns)
        assert chunk.headers == [headers[col - 1] for col in columns]
        data_lines = chunk.markdown_text.splitlines()[2:]
        assert len(data_lines) == chunk.end_row - chunk.start_row + 1
        for row_no, line in enumerate(data_lines, chunk.start_row):
            cells = split_table_row(line)
            assert len(cells) == len(columns)
            for col, cell in zip(columns, cells):
                coordinate = (row_no, col)
                if coordinate in seen:
                    assert col in key_columns and seen[coordinate] == cell
                seen[coordinate] = cell
    assert seen == {
        (row_no, col): cell
        for row_no, row in enumerate(rows, 1)
        for col, cell in enumerate(row, 1)
    }


def test_balanced_columns_consider_rows_per_chunk():
    headers = ["Site"] + [f"Measure {i}" for i in range(1, 7)]
    rows = [[f"Site {i}"] + [f"{i}.{j:02d}" for j in range(1, 7)] for i in range(1, 7)]
    chunker = SourceAwareTableChunker(3, max_tokens=130, count_tokens=len, repeat_columns=(1,))

    chunks = chunker.split_rows(headers, rows)

    # Wider projections fit a single row but need more chunks overall.
    assert len(chunks) == 6
    assert all(chunk.end_row - chunk.start_row + 1 == 3 for chunk in chunks)
    _assert_budgeted_table(chunks, headers, rows, 130, (1,))
    assert chunks == chunker.split_rows(headers, rows)


@pytest.mark.parametrize("width, keys", [(8, (2, 5)), (40, ()), (40, (2, 5))])
def test_column_strategies_preserve_sparse_and_uneven_values(width, keys):
    headers = [f"H{col}" for col in range(width)]
    rows = [
        ["x" * ((row * 11 + col * 7) % 23) for col in range(width)]
        for row in range(5)
    ]
    budget = 125
    chunks = SourceAwareTableChunker(
        3, max_tokens=budget, count_tokens=len, repeat_columns=keys
    ).split_rows(headers, rows)

    _assert_budgeted_table(chunks, headers, rows, budget, keys)


def test_exact_budget_keeps_full_width_when_the_row_fits():
    headers, rows = ["Key", "Value"], [["A", "123"]]
    budget = len(SourceAwareTableChunker().split_rows(headers, rows)[0].markdown_text)
    chunks = SourceAwareTableChunker(
        max_tokens=budget, count_tokens=len, repeat_columns=(1,)
    ).split_rows(headers, rows)

    assert len(chunks) == 1
    _assert_budgeted_table(chunks, headers, rows, budget, (1,))


def test_search_limit_falls_back_to_greedy_without_losing_cells(monkeypatch):
    monkeypatch.setattr("rag_table_ai.chunker._MAX_BALANCED_COUNTS", 1)
    headers = ["Key", "A", "B", "C"]
    rows = [[f"K{i}", "A" * 13, "B" * 13, "C" * 13] for i in range(5)]
    chunker = SourceAwareTableChunker(3, max_tokens=70, count_tokens=len, repeat_columns=(1,))

    chunks = chunker.split_rows(headers, rows)

    assert len({tuple(chunk.metadata["column_indices"]) for chunk in chunks}) > 1
    _assert_budgeted_table(chunks, headers, rows, 70, (1,))
