import pytest

from benchmarks.measure_chunking import coordinates, pair_rows
from rag_table_ai import TableChunk


def test_reconstruction_detects_rendered_header_drift():
    chunk = TableChunk(
        1, 1, 1, 1, ["A", "B"], "| A | WRONG |\n| --- | --- |\n| 1 | 2 |",
        {"column_indices": [1, 2]},
    )
    with pytest.raises(ValueError, match="inconsistent header"):
        coordinates([chunk])


def test_same_chunk_measure_counts_joint_evidence_by_row():
    chunks = [
        TableChunk(1, 3, 1, 2, [], "", {"column_indices": [1, 2]}),
        TableChunk(2, 3, 1, 1, [], "", {"column_indices": [1, 3]}),
        TableChunk(3, 3, 2, 2, [], "", {"column_indices": [1, 2, 3]}),
    ]
    assert pair_rows(chunks, (2, 3)) == {2}
    assert pair_rows(chunks, (1, 3)) == {1, 2}
