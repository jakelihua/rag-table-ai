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
