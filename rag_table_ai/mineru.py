"""Adapt MinerU Content List V1 tables to RAG chunks without importing MinerU."""

from __future__ import annotations

from math import isfinite

from rag_table_ai.chunker import SourceAwareTableChunker, TableChunk
from rag_table_ai.html_tables import split_html_table


def _text_parts(value: object, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(part, str) for part in value):
        return value.copy()
    raise ValueError(f"{field} must be a string or a list of strings.")


def split_mineru_content_list(
    content: list[dict],
    *,
    source: str,
    chunker: SourceAwareTableChunker | None = None,
    header_rows_by_block: dict[int, int] | None = None,
) -> list[TableChunk]:
    """Chunk HTML table blocks from a flat MinerU Content List V1.

    The optional header overrides use zero-based indices in the input list.
    Page indices and bounding boxes are copied when present. Page numbers are
    derived from those indices for human-readable citations.
    """
    if not isinstance(content, list) or any(not isinstance(block, dict) for block in content):
        raise ValueError("Expected a flat MinerU Content List V1 (a list of block objects).")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source must identify the original document.")
    header_overrides = header_rows_by_block or {}
    if any(
        type(index) is not int or not 0 <= index < len(content) or content[index].get("type") != "table"
        for index in header_overrides
    ):
        raise ValueError("Header overrides must refer to table block indices in the input list.")
    chunker = chunker or SourceAwareTableChunker()
    chunks = []
    for index, block in enumerate(content):
        if block.get("type") != "table":
            continue
        try:
            body = block.get("table_body") or block.get("html")
            if not isinstance(body, str):
                raise ValueError("Expected an HTML table in table_body or html.")
            caption = " ".join(_text_parts(block.get("table_caption"), "table_caption"))
            footnotes = _text_parts(block.get("table_footnote"), "table_footnote")
            metadata = {"source": source, "mineru_block_index": index, "table_footnotes": footnotes}
            page_idx = block.get("page_idx")
            if page_idx is not None:
                if type(page_idx) is not int or page_idx < 0:
                    raise ValueError("page_idx must be a nonnegative integer.")
                metadata.update(page_idx=page_idx, page_number=page_idx + 1)
            bbox = block.get("bbox")
            if bbox is not None:
                if not isinstance(bbox, list) or len(bbox) != 4 or any(
                    type(coord) not in (int, float) or (type(coord) is float and not isfinite(coord))
                    for coord in bbox
                ):
                    raise ValueError("bbox must contain four finite numeric coordinates.")
                metadata["bbox"] = bbox.copy()

            chunks.extend(split_html_table(
                body,
                chunker=chunker,
                table_id=f"{source}#table-{index + 1}",
                caption=caption,
                header_rows=header_overrides.get(index),
                source_metadata=metadata,
            ))
        except ValueError as exc:
            raise ValueError(f"MinerU table block {index} in {source}: {exc}") from exc
    return chunks
