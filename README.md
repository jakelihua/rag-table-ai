# rag-table-ai 📊⚡

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-17%20passed-brightgreen.svg)]()
[![Deterministic](https://img.shields.io/badge/execution-100%25%20deterministic-success.svg)]()
[![Zero LLM Cost](https://img.shields.io/badge/LLM%20Token%20Cost-0-orange.svg)]()

> 🇨🇳 **专为解决大模型与 RAG 中超复杂表格解析难题而生**（彻底解决多层复合表头、连续区间匹配、切片丢表头及心算幻觉，100% 确定性、零额外 Token 成本）。  
> 🌐 **Deterministic, zero-LLM engine built to solve ultra-complex table parsing, chunking & semantic linearization challenges in RAG & AI Agents.**  
> *Solves hierarchical headers, interval alignment, cross-chunk table fragmentation, and arithmetic errors without extra latency or tokens.*

---

[English](#english) | [中文说明](#中文说明)

---

<a name="english"></a>
## 💡 Why rag-table-ai?

Most RAG pipelines perform horribly when dealing with dense, complex tables (financial statements, shipping rate cards, technical spec sheets, pricing matrices):

1. **Table Fragmentation Disaster**: Traditional chunkers split by character count (e.g., 512 tokens). When a 50-row table is sliced into 3 chunks, Chunks 2 & 3 lose their headers completely. Retrieved chunks become useless to LLMs.
2. **2D Matrix Misalignment**: LLMs operate on 1D token sequences. When reading dense 2D Markdown tables, they frequently read across lines or mix up adjacent columns.
3. **Continuous/Discrete Interval Blindness**: When a table row specifies `10kg-20kg` or `76-80 years old`, user queries like `15kg` or `78` fail to match due to naive literal equality checks.
4. **Arithmetic Failure**: LLMs make hallucinations when computing percentages (`(5000 - 100) * 80%`) or fail when numbers contain thousand separators (`1,200`).

`rag-table-ai` provides a **100% deterministic, zero-token, microsecond-speed preprocessor and evaluator** to solve all four problems.

---

## 🚀 Key Features

* **🧩 Hierarchical Header Path Resolution**: Automatically collapses two-tier or multi-tier nested headers (e.g. `Standard Plan -> Monthly`) into unambiguous flat paths.
* **📈 Chain-of-Table Semantic Linearization**: Flattens dense 2D matrices into clear, row-by-row key-value representations, eliminating visual cross-line hallucination.
* **🎯 Universal Interval & Range Matching**: Automatically aligns queries (`15kg`, `350`, `78`) with range cells (`10-20kg`, `$100-$500`, `76-80周岁`) and generates explicit semantic expansion hints.
* **✂️ Source-Aware Table Chunking**: Chunks huge tables while guaranteeing that **every single sub-table inherits the verified header row (`repeated_header`)** with full physical row coordinate tracking.
* **🧮 Safe Decimal Arithmetic Evaluator**: High-precision arithmetic evaluator without unsafe Python `eval()`. Supports full-width punctuation, percentages (`80%`), and safely strips thousand separators.

---

## 📦 Installation

```bash
pip install rag-table-ai
```
*(Or install locally from source)*
```bash
git clone https://github.com/jakelihua/rag-table-ai.git
cd rag-table-ai
pip install -e .
```

---

## ⚡ 30-Second Quickstart

```python
from rag_table_ai import RagTableAI

engine = RagTableAI()

markdown_table = """
### Cloud Instance Pricing
| Instance Class | On-Demand (Hourly) | | 1-Year Reserved (Monthly) | |
| | US-East | AP-East | US-East | AP-East |
| --- | --- | --- | --- | --- |
| General (2-4 vCPU) | $0.096 | $0.124 | $48.00 | $62.00 |
| Compute (8-16 vCPU) | $0.384 | $0.496 | $192.00 | $248.00 |
"""

# 1. Linearize into LLM-friendly Key-Value format (Chain-of-Table)
flattened = engine.flatten(markdown_table)
print(flattened)
# Output:
# - [Row 1] Instance Class: General (2-4 vCPU) [covers: 2, 3, 4] | On-Demand (Hourly) (US-East): $0.096 | ...

# 2. Universal Numeric Interval Matching
print(engine.match("2-4 vCPU", "4 vCPU"))  # True
print(engine.match("8-16 vCPU", "12 vCPU")) # True

# 3. Safe Decimal Arithmetic (Supports %, full-width chars, thousand commas)
result = engine.calculate("(248.00 - 192.00) * 80%")
print(result) # "44.80"
```

### ✂️ Chunking Large Tables with Header Preservation

```python
from rag_table_ai import SourceAwareTableChunker

chunker = SourceAwareTableChunker(max_rows_per_chunk=10)
# Splits 100-row table into 10 sub-tables; each chunk retains complete headers
chunks = chunker.split_table(huge_markdown_table, caption="Annual Report")

for chunk in chunks:
    print(f"Chunk {chunk.chunk_index}/{chunk.total_chunks} (Rows {chunk.start_row}-{chunk.end_row})")
    print(chunk.markdown_text) # Contains Markdown headers + separators!
```

---

<a name="中文说明"></a>
## 🇨🇳 中文说明

在严肃的企业级 RAG 与大模型应用中，表格往往是导致模型“睁眼说瞎话”和算错数据的重灾区：

1. **切片把表格拦腰截断**：常规按字符或固定 Token 切块，一张长表格被切成多段后，第 2、3 段完全没有表头，检索出来模型根本不知道列代表什么含义。
2. **二维视线对齐困难**：大模型本质是一维自回归生成，面对密集的 Markdown 管道表极易“看串行、对错列”。
3. **连续区间无法检索**：表格行写着 `10kg-20kg` 或 `76周岁-80周岁`，用户口语化提问 `15kg` 或 `78岁` 时，传统语义检索与字面全等比对完全无法命中。
4. **百分号与算术幻觉**：大模型心算费率或总价时，经常被百分号（`80%`）、千分位逗号（`1,200`）或全角符号搞崩溃。

`rag-table-ai` 是一个**纯确定性、零 LLM 开销、微秒级响应**的通用表格处理与保真切分工具包：

* **多层复合表头递归融合**：自动将 `父分类 | 首次投保 / 重新投保` 等复杂双层表头折叠为单一清晰语义路径；
* **语义键值展平（Chain-of-Table）**：将二维表格自动转为行级语义键值对，彻底杜绝模型跨行串视线；
* **数值与离散区间通用映射**：任意单位与范围自动识别并展开覆盖明细（如 `[含76/77/78/79/80岁]`）；
* **源感知切片与表头继承**：保证切开后的每一片子表格都**无损携带完整父表头**，且不丢行、不错位；
* **十进制安全符号计算器**：完全阻断代码注入，支持全角、百分号与千分位清洗，保证算术准确率 100%。

---

## 🧪 Testing

Run the full deterministic unit test suite:

```bash
pytest tests/ -v
```

```
tests/test_chunker.py::test_source_aware_table_chunker PASSED
tests/test_evaluator.py::test_normalize_expression PASSED
tests/test_evaluator.py::test_leading_zero_thousands_comma_split_rejected PASSED
tests/test_evaluator.py::test_calculate_decimal_safe PASSED
tests/test_evaluator.py::test_calculate_zero_division PASSED
tests/test_facade.py::test_rag_table_ai_facade PASSED
tests/test_flattener.py::test_encode_cell_state PASSED
tests/test_flattener.py::test_flatten_standard_table PASSED
tests/test_flattener.py::test_flatten_two_tier_table_with_intervals PASSED
tests/test_flattener.py::test_large_table_truncation_guard PASSED
tests/test_headers.py::test_split_table_row PASSED
tests/test_headers.py::test_is_markdown_separator PASSED
tests/test_headers.py::test_resolve_single_row_headers PASSED
tests/test_headers.py::test_resolve_two_tier_composite_headers PASSED
tests/test_intervals.py::test_extract_range PASSED
tests/test_intervals.py::test_match_interval PASSED
tests/test_intervals.py::test_expand_interval_hint PASSED

============================== 17 passed in 0.02s ==============================
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
