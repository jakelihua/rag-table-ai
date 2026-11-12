import json
from pathlib import Path

import pytest

from rag_table_ai import SourceAwareTableChunker, split_html_table, split_mineru_content_list, split_table_row


def test_mineru_merged_headers_and_source_metadata():
    fixture = Path(__file__).resolve().parents[1] / "examples/fixtures/shipping_content_list.json"
    content = json.loads(fixture.read_text(encoding="utf-8"))
    chunks = split_mineru_content_list(
        content,
        source="shipping.pdf",
        chunker=SourceAwareTableChunker(max_rows_per_chunk=1),
        header_rows_by_block={1: 2},
    )

    first, second = chunks
    assert first.headers == [
        "Weight", "Rate (USD) / Standard", "Rate (USD) / Express",
        "Transit (days) / Standard", "Transit (days) / Express",
    ]
    assert second.metadata["header_paths"][2] == ["Rate (USD)", "Express"]
    assert second.metadata["source"] == "shipping.pdf"
    assert second.metadata["page_idx"] == 2
    assert second.metadata["page_number"] == 3
    assert second.metadata["bbox"] == [120, 200, 880, 540]
    assert second.metadata["table_footnotes"] == ["Weight bands use whole kilograms."]
    assert second.metadata["table_id"] == "shipping.pdf#table-2"
    assert (second.start_row, second.end_row) == (2, 2)
    assert split_table_row(second.markdown_text.splitlines()[-1])[2] == "18.00"


def test_html_preserves_body_spans_and_escapes_literal_cell_delimiters():
    html = """<table><caption>Limits</caption>
    <thead><tr><th>Tier</th><th>Name</th><th>Value</th></tr></thead>
    <tbody><tr><th rowspan="2">A</th><td>Name &amp; type | ID</td><td>1</td></tr>
    <tr><td colspan="2">No<br>data</td></tr></tbody></table>"""
    first, second = split_html_table(html, chunker=SourceAwareTableChunker(max_rows_per_chunk=1))
    assert first.metadata["caption"] == "Limits"
    assert split_table_row(first.markdown_text.splitlines()[-1]) == ["A", "Name &amp; type \\| ID", "1"]
    assert split_table_row(second.markdown_text.splitlines()[-1]) == ["A", "No data", "No data"]


@pytest.mark.parametrize("html, error", [
    ("<table><tr><th rowspan='3'>A</th></tr><tr><td>1</td></tr></table>", "rowspan crosses"),
    (
        "<table><tr><th>A</th><th>B</th><th>C</th></tr>"
        "<tr><td>1</td><td rowspan='2'>2</td><td>3</td></tr>"
        "<tr><td colspan='2'>4</td></tr></table>",
        "Overlapping",
    ),
    (
        "<table><thead><tr><th>A</th></tr></thead>"
        "<tbody><tr><td rowspan='2'>1</td></tr></tbody>"
        "<tbody><tr><td>2</td></tr></tbody></table>",
        "row group",
    ),
    ("<table><tr><th>A</th><th>B</th></tr><tr><td>1</td></tr></table>", "rectangular"),
    ("<table><tr><td><table></table></td></tr></table>", "nested"),
    ("<table><tr><th>A</th></tr><tr><td>1</td></tr>", "complete"),
    ("<table><tr><th colspan='250001'>A</th></tr></table>", "grid limit"),
])
def test_unsupported_html_is_reported_with_context(html, error):
    with pytest.raises(ValueError, match=f"MinerU table block 0 in input.pdf: .*{error}"):
        split_mineru_content_list([{"type": "table", "html": html}], source="input.pdf")


def test_flat_content_list_requires_known_payload_shape():
    with pytest.raises(ValueError, match="Content List V1"):
        split_mineru_content_list([[{"type": "table"}]], source="input.pdf")
    with pytest.raises(ValueError, match="Expected an HTML table"):
        split_mineru_content_list([{"type": "table"}], source="input.pdf")


def test_html_blank_corner_is_part_of_multirow_header():
    html = (
        "<table><tr><td rowspan='2'></td><th colspan='2'>Rate</th></tr>"
        "<tr><th>Std</th><th>Exp</th></tr>"
        "<tr><td>A</td><td>6</td><td>9</td></tr></table>"
    )
    chunk = split_html_table(html)[0]
    assert chunk.headers == ["Column_1", "Rate / Std", "Rate / Exp"]
    assert chunk.rows == [["A", "6", "9"]]
    assert (chunk.start_row, chunk.end_row) == (1, 1)


def test_ambiguous_mixed_header_requires_an_explicit_override():
    html = (
        "<table><tr><td></td><th colspan='2'>Rate</th></tr>"
        "<tr><td>Weight</td><th>Std</th><th>Exp</th></tr>"
        "<tr><td>0–10 kg</td><td>6</td><td>9</td></tr></table>"
    )
    with pytest.raises(ValueError, match="specify header_rows"):
        split_html_table(html)
    assert split_html_table(html, header_rows=2)[0].rows == [["0–10 kg", "6", "9"]]


def test_header_only_html_is_rejected_instead_of_silently_dropped():
    with pytest.raises(ValueError, match="data row"):
        split_html_table("<table><tr><td>Total</td><td>50</td></tr></table>")
    with pytest.raises(ValueError, match="data row"):
        split_html_table("<table><tr><td>A</td></tr><tr><td>1</td></tr></table>", header_rows=2)


def test_html_keeps_decoded_values_separate_from_markdown_and_uses_caption_fallback():
    from rag_table_ai import match_interval

    chunks = split_mineru_content_list([{
        "type": "table",
        "html": (
            "<table><caption>Real</caption><tr><th>Dept &amp; Group</th></tr>"
            "<tr><td>R&amp;D</td></tr></table>"
        ),
        "table_caption": ["", " "],
    }], source="test.pdf")
    chunk = chunks[0]
    assert chunk.headers == ["Dept & Group"]
    assert chunk.metadata["header_paths"] == [["Dept & Group"]]
    assert chunk.rows == [["R&D"]]
    assert match_interval(chunk.rows[0][0], "R&D")
    assert chunk.markdown_text.splitlines()[1] == "| Dept &amp; Group |"
    assert chunk.metadata["caption"] == "Real"
