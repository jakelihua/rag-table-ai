"""Universal numeric and discrete range matching.

Enables LLMs and retrievers to match discrete user query numbers
(e.g., '78 years old', '78岁', '15kg', '$350', '3 years') against tabular range cells
(e.g., '76周岁-80周岁', '10kg - 20kg', '$100 - $500', '1~3 years').
"""

from __future__ import annotations

import re

_RANGE_PATTERN = re.compile(
    r"(?:[A-Za-z\u4e00-\u9fa5$¥€%]+\s*)?(\d{1,10})\s*(?:[A-Za-z\u4e00-\u9fa5$¥€%]+)?(?:\([^)]*\))?\s*[-—~至到–]\s*(?:[A-Za-z\u4e00-\u9fa5$¥€%]+\s*)?(\d{1,10})\s*(?:[A-Za-z\u4e00-\u9fa5$¥€%]+)?"
)
_DIGITS_PATTERN = re.compile(r"\d+")


def extract_range(text: str) -> tuple[int, int] | None:
    """Extract numeric lower and upper bounds from a range string.

    Examples:
        '76周岁-80周岁' -> (76, 80)
        '10kg~20kg' -> (10, 20)
        '100-500' -> (100, 500)
    """
    m = _RANGE_PATTERN.search(text)
    if not m:
        return None
    try:
        low, high = int(m.group(1)), int(m.group(2))
        return (min(low, high), max(low, high))
    except (ValueError, TypeError):
        return None


def match_interval(cell_text: str, query_text: str) -> bool:
    """Check if query_text matches cell_text either literally or numerically.

    Returns True if:
      1. query_text is a substring of cell_text (or vice-versa),
      2. or query_text contains a single integer that falls within the numeric range of cell_text.
    """
    norm_cell = re.sub(r"[\s_]", "", cell_text)
    norm_query = re.sub(r"[\s_]", "", query_text)

    if not norm_cell or not norm_query:
        return False

    if norm_query in norm_cell or norm_cell in norm_query:
        return True

    # Numeric interval check
    cell_range = extract_range(norm_cell)
    if not cell_range:
        return False

    query_digits = _DIGITS_PATTERN.findall(norm_query)
    if len(query_digits) == 1:
        try:
            val = int(query_digits[0])
            low, high = cell_range
            return low <= val <= high
        except ValueError:
            return False

    return False


def expand_interval_hint(cell_text: str, max_expanded: int = 12) -> str:
    """If cell_text is a compact range with <= max_expanded discrete steps,

    expand it into an explicit semantic hint for zero-shot LLM comprehension.

    Example:
        '76-80岁' -> '76-80岁 [covers: 76, 77, 78, 79, 80]'
    """
    rng = extract_range(cell_text)
    if not rng:
        return cell_text

    low, high = rng
    span = high - low + 1
    if 1 < span <= max_expanded:
        items = [str(x) for x in range(low, high + 1)]
        return f"{cell_text} [covers: {', '.join(items)}]"

    return cell_text
