#!/usr/bin/env python3
"""01_quickstart.py - 30-second Quickstart for rag-table-ai."""

import sys
from pathlib import Path

# Add project root to sys.path for direct execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag_table_ai import RagTableAI

# 1. Initialize the engine
rag_table = RagTableAI()

# 2. Markdown table with multi-tier composite headers & intervals
sample_markdown = """
### Global Cloud Instance Pricing
| Instance Class | On-Demand (Hourly) | | 1-Year Reserved (Monthly) | |
| | US-East | AP-East | US-East | AP-East |
| --- | --- | --- | --- | --- |
| General (2-4 vCPU) | $0.096 | $0.124 | $48.00 | $62.00 |
| Compute (8-16 vCPU) | $0.384 | $0.496 | $192.00 | $248.00 |
| Memory (32-64 vCPU) | $0.768 | $0.992 | $384.00 | $496.00 |
"""

# 3. Linearize 2D matrix into semantic key-value tuples (Chain-of-Table format)
flattened = rag_table.flatten(sample_markdown)
print("=== Linearized Table Output ===")
print(flattened)

# 4. Range interval query matching
print("\n=== Range Matching Test ===")
print("Query: 4 vCPU matches General class?", rag_table.match("2-4 vCPU", "4 vCPU"))
print("Query: 12 vCPU matches Compute class?", rag_table.match("8-16 vCPU", "12 vCPU"))

# 5. Deterministic Safe Decimal Calculation
print("\n=== Safe Decimal Calculation ===")
calc_res = rag_table.calculate("(248.00 - 192.00) * 80%")
print("Formula: (248.00 - 192.00) * 80% =", calc_res)
