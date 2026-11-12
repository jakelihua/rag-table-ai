"""Convert an HTML table to a rectangular grid with hierarchical headers."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from html import escape
from html.parser import HTMLParser

from rag_table_ai.chunker import SourceAwareTableChunker, TableChunk

_MAX_GRID_CELLS = 250_000
_SECTIONS = {"thead", "tbody", "tfoot"}


@dataclass
class _Cell:
    is_header: bool
    rowspan: int
    colspan: int
    parts: list[str] = field(default_factory=list)

    @cached_property
    def text(self) -> str:
        return " ".join("".join(self.parts).split())


@dataclass
class _Row:
    in_thead: bool
    group: int
    cells: list[_Cell] = field(default_factory=list)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.seen = False
        self.closed = False
        self.section = ""
        self.group = 0
        self.rows: list[_Row] = []
        self.row: _Row | None = None
        self.cell: _Cell | None = None
        self.caption: list[str] = []
        self.in_caption = False
        self.ignored_tag = ""

    def handle_starttag(self, tag, attrs):
        if self.ignored_tag:
            return
        if tag in {"script", "style"}:
            self.ignored_tag = tag
            return
        if tag == "table":
            if self.seen:
                raise ValueError("Expected exactly one HTML table without nested tables.")
            self.seen = True
        elif not self.seen or self.closed:
            return
        elif tag in _SECTIONS:
            self.row = self.cell = None
            self.section = tag
            self.group += 1
        elif tag == "caption":
            self.in_caption = True
        elif tag == "tr":
            self.in_caption = False
            self.cell = None
            self.row = _Row(in_thead=self.section == "thead", group=self.group)
            self.rows.append(self.row)
        elif tag in {"td", "th"}:
            if self.row is None:
                raise ValueError("HTML table cell outside a row.")
            values = dict(attrs)
            self.cell = _Cell(tag == "th", _span(values, "rowspan"), _span(values, "colspan"))
            self.row.cells.append(self.cell)
        elif tag in {"br", "p", "div"}:
            self.handle_data(" ")

    def handle_endtag(self, tag):
        if self.ignored_tag:
            if tag == self.ignored_tag:
                self.ignored_tag = ""
            return
        if not self.seen or self.closed:
            return
        if tag == "table":
            self.closed = True
        elif tag in {"td", "th"}:
            self.cell = None
        elif tag == "tr" or tag in _SECTIONS:
            self.row = self.cell = None
            if tag in _SECTIONS:
                self.section = ""
                self.group += 1
        elif tag == "caption":
            self.in_caption = False
        elif tag in {"p", "div"}:
            self.handle_data(" ")

    def handle_data(self, data):
        if self.ignored_tag or self.closed:
            return
        if self.cell is not None:
            self.cell.parts.append(data)
        elif self.in_caption:
            self.caption.append(data)


def _span(attrs: dict, name: str) -> int:
    value = attrs.get(name, "1")
    try:
        span = int(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid {name} in HTML table.") from exc
    if not 1 <= span <= _MAX_GRID_CELLS:
        raise ValueError(f"{name} must be positive and within the HTML grid limit.")
    return span


def _header_count(rows: list[_Row], header_rows: int | None) -> int:
    if header_rows is not None:
        if type(header_rows) is not int or not 1 <= header_rows < len(rows):
            raise ValueError("header_rows must leave at least one HTML data row.")
        return header_rows

    thead = [idx for idx, row in enumerate(rows) if row.in_thead]
    if thead:
        if thead != list(range(len(thead))):
            raise ValueError("Expected the HTML table header section before the data.")
        count = len(thead)
    else:
        count = 0
        for row in rows:
            header_cells = sum(cell.is_header for cell in row.cells)
            if header_cells and all(cell.is_header or not cell.text for cell in row.cells):
                count += 1
                continue
            if count and header_cells >= 2 and any(
                cell.colspan > 1 for previous in rows[:count] for cell in previous.cells
            ):
                raise ValueError("Ambiguous mixed HTML header rows; specify header_rows.")
            break
        count = count or 1
    if count >= len(rows):
        raise ValueError("HTML table requires at least one data row after the header.")
    return count


def _expand_grid(rows: list[_Row], header_count: int) -> list[list[_Cell]]:
    grid: list[dict[int, _Cell]] = [{} for _ in rows]
    positions = 0
    for row_idx, row in enumerate(rows):
        col = 0
        for cell in row.cells:
            while col in grid[row_idx]:
                col += 1
            end = row_idx + cell.rowspan
            if end > len(rows) or row_idx < header_count < end:
                raise ValueError(f"rowspan crosses the table or header boundary at HTML row {row_idx + 1}.")
            if rows[end - 1].group != row.group:
                raise ValueError(f"rowspan crosses an HTML row group at HTML row {row_idx + 1}.")
            positions += cell.rowspan * cell.colspan
            if positions > _MAX_GRID_CELLS:
                raise ValueError("Expanded HTML table exceeds the grid cell limit.")
            for target in grid[row_idx:end]:
                for column in range(col, col + cell.colspan):
                    if column in target:
                        raise ValueError(f"Overlapping HTML table spans at HTML row {row_idx + 1}.")
                    target[column] = cell
            col += cell.colspan

    width = max((max(row, default=-1) + 1 for row in grid), default=0)
    if not width or any(len(row) != width for row in grid):
        raise ValueError("HTML table spans must resolve to a rectangular grid.")
    return [[row[col] for col in range(width)] for row in grid]


def _markdown_cell(text: str) -> str:
    return escape(text, quote=False).replace("\\", "\\\\").replace("|", "\\|")


def split_html_table(
    table_html: str,
    *,
    chunker: SourceAwareTableChunker | None = None,
    table_id: str = "table_1",
    caption: str = "",
    header_rows: int | None = None,
    source_metadata: dict | None = None,
) -> list[TableChunk]:
    """Expand spans, resolve header paths, and chunk a single HTML table.

    Header rows come from thead or leading th rows with optional blank td cells.
    Specify header_rows for ambiguous mixed rows or multiple all-td header rows.
    """
    parser = _TableParser()
    parser.feed(table_html)
    parser.close()
    if not parser.closed or not parser.rows:
        raise ValueError("Expected a complete, nonempty HTML table.")
    header_count = _header_count(parser.rows, header_rows)
    grid = _expand_grid(parser.rows, header_count)

    paths = []
    for col in range(len(grid[0])):
        path = []
        previous = None
        for row in grid[:header_count]:
            cell = row[col]
            if cell is not previous and cell.text:
                path.append(cell.text)
            previous = cell
        paths.append(path or [f"Column_{col + 1}"])

    headers = [" / ".join(path) for path in paths]
    # Spans share a _Cell instance. Normalize its text once for the whole grid.
    rendered_cells = {}
    rows = []
    for row in grid[header_count:]:
        rendered_row = []
        for cell in row:
            key = id(cell)
            if key not in rendered_cells:
                rendered_cells[key] = _markdown_cell(cell.text)
            rendered_row.append(rendered_cells[key])
        rows.append(rendered_row)

    chunks = (chunker or SourceAwareTableChunker()).split_rows(
        [_markdown_cell(header) for header in headers],
        rows,
        table_id=table_id,
        caption=caption.strip() or " ".join("".join(parser.caption).split()),
        source_metadata={**(source_metadata or {}), "header_paths": paths},
    )
    for chunk in chunks:
        columns = [column - 1 for column in chunk.metadata["column_indices"]]
        chunk.headers = [headers[col] for col in columns]
        data = grid[header_count + chunk.start_row - 1:header_count + chunk.end_row]
        chunk.rows = [[row[col].text for col in columns] for row in data]
    return chunks
