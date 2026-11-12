# rag-table-ai

**让 RAG 召回一行数据时，也能召回解释它的表头。**

[English](README.md) · [快速开始](#快速开始) · [MinerU](#接入-mineru-和-html-表格) · [运费示例](examples/03_shipping_rates.py)

`rag-table-ai` 是一个轻量 Python 库。它把表格切成自带列名的分片，支持 MinerU 输出的 HTML 表格、按预算拆行和分列、区间匹配及受限算式求值。核心无运行时依赖，无需调用大模型。

**示例问题：**15 kg 的货物走加急，打八折后多少钱？

```text
普通切片
  | 11–20 kg | 12.00 | 18.00 |
  哪个数字是加急价？

带表头的切片
  | 重量（整 kg） | 普通（USD） | 加急（USD） |
  | 11–20 kg     | 12.00      | 18.00      |
  加急：18.00 × 80% = 14.40 USD
  来源：shipping-rates，表内第 2 条数据行
```

## 快速开始

需要 Python 3.9 或更高版本。请在本地仓库根目录运行以下命令。示例会匹配运费档位、读取加急价并计算折后价。

```bash
python -m pip install .
python examples/03_shipping_rates.py
```

```python
from rag_table_ai import RagTableAI

table = """\
| Weight   | Standard (USD) | Express (USD) |
| -------- | -------------- | ------------- |
| 0–10 kg  | 6.00           | 9.00          |
| 11–20 kg | 12.00          | 18.00         |
"""

engine = RagTableAI(max_rows_per_chunk=1)
_, chunk = engine.split_table(table, table_id="shipping-rates")

print(chunk.markdown_text)  # 第二条数据行仍带有重量、普通和加急三列的列名。
assert (chunk.start_row, chunk.end_row) == (2, 2)
assert engine.match("11–20 kg", "15 kg")
assert not engine.match("11–20 kg", "15 lb")
assert engine.calculate("18.00 × 80%") == "14.40"
```

[完整运费示例](examples/03_shipping_rates.py)会从分片中选出匹配的档位和价格列。调用方提供待匹配的重量、目标列和折扣。

## 如何接入 RAG

1. 将抽取好的管道表格交给 `split_table()`。用分片的 `markdown_text` 建索引，让检索文本带有列名。另存 `metadata`，用于引用表格与表内行号。
2. 用 `flatten()` 生成带字段名的阅读视图。它有行数上限，完整入库请使用切片。有关键词命中时，优先保留命中行，再补相邻行。
3. 用 `match()` 判断给定数值是否落在某个区间，用 `calculate()` 计算受支持的算式。命中多个区间时，由调用方报告歧义或按业务规则选择。

| 能力 | 当前支持范围 |
| --- | --- |
| 表格输入 | 单层表头，或按[示例约定](examples/01_quickstart.py)填写的双层表头。父级的空白单元格沿用左侧父级名称。也支持含合并单元格的 HTML 表格。PDF 和图片交给上游抽取。 |
| 切片 | 按数据行数和可选 token 预算切分，每片重复列名，并记录从 1 开始的表内行范围和列号。超宽数据行抛出 `ValueError`，短行在右侧补空。 |
| 区间匹配 | 支持带正负号的整数和小数闭区间。显式单位须一致，裸数字沿用区间单位。输入为 `15 kg` 这样的数值或文本标签。 |
| 算式求值 | 支持受限的 Decimal 算式、百分号和常见全角运算符。调用方提供表达式，并按自己的业务规则校验输入格式和舍入行为。 |

## 接入 MinerU 和 HTML 表格

```bash
python examples/04_mineru_pipeline.py
```

[MinerU 示例](examples/04_mineru_pipeline.py)读取[合成的 MinerU Content List V1](examples/fixtures/shipping_content_list.json)，其中有两层表头和合并单元格。切成 4 个分片后仍覆盖全部 10 个逻辑数据单元格。查询 15 kg 加急运费，八折后得到 **USD 14.40**，可引用 **shipping.pdf 第 3 页、表内第 2 条数据行**。示例使用固定的正则计数规则，方便复现。

```python
import json
from pathlib import Path

from rag_table_ai import SourceAwareTableChunker, split_mineru_content_list

path = Path("examples/fixtures/shipping_content_list.json")
blocks = json.loads(path.read_text(encoding="utf-8"))
chunker = SourceAwareTableChunker(
    max_rows_per_chunk=10,
    max_tokens=185,
    count_tokens=len,  # 示例按字符计数。实际 token 预算请传入所用模型的 tokenizer。
    repeat_columns=(1,),
)
chunks = split_mineru_content_list(
    blocks,
    source="shipping.pdf",
    chunker=chunker,
    header_rows_by_block={1: 2},
)
assert chunks
assert all(len(chunk.markdown_text) <= 185 for chunk in chunks)
assert all(chunk.metadata["page_number"] == 3 for chunk in chunks)
```

- **输入格式。**传入扁平的 MinerU Content List V1。适配器从 `table_body` 或 `html` 读取表格，跳过其他块，并保留原文档标识、表题、脚注，以及可用的页码和边界框。单独的 HTML 表格可用 `split_html_table()`。[MinerU 输出文档](https://opendatalab.github.io/MinerU/reference/output_files/)
- **表头识别。**先展开正整数的 `rowspan` 和 `colspan`，再按 `thead`、开头连续的全 `th` 行或首行识别表头。如果多层表头全部用 `td`，通过 `header_rows_by_block` 指定，键是输入列表中从 0 开始的块索引。直接处理 HTML 时传 `header_rows`。嵌套表格、非矩形网格和非法跨度会报错。
- **切片预算。**同时传入 `max_tokens` 和确定性的 `count_tokens(text)`，例如 `lambda text: len(tokenizer.encode(text))`。计数覆盖完整的 `markdown_text`，包括表题和表头。单行过宽时，`repeat_columns=(1,)` 允许分列并重复第 1 列作为行标识。传 `()` 可分列但不重复列，传 `None` 则明确报超限。最小分组仍放不下时抛出 `ValueError`。分列时，最多 32 个非标识列会按切完后的分片数和文本总量选择列组。更宽的表采用贪心分组。
- **来源与坐标。**`start_row`、`end_row`、`column_indices` 都是从 1 开始的表内逻辑坐标。完整表头路径存于 `header_paths`，分片列通过 `column_indices` 对应到原表。`page_idx` 从 0 开始，引用用从 1 开始的 `page_number`。适配器保留 MinerU 给出的**表级**边界框，各表格块独立处理。

## 如何评估

[宽表评测](docs/chunking-benchmark.md#中文说明)用真实 MinerU 导出比较两种策略。在 64 token 预算下，分片从 34 降到 25，110 个逻辑数据单元格全部保留。运费示例用于复现一次表头保留和查价。做检索评测时，先看前几个结果能否给出**正确单元格及对应列名**。用相同的召回与上下文预算比较普通文本切片和已有的重复表头方案。核心处理耗时、索引文本体积及下游上下文 token 分别报告。

## 开发与测试

```bash
python -m pip install '.[dev]'
python -m pytest -q
```

遇到丢表头或匹配错档位的案例，欢迎[提交脱敏后的最小复现](https://github.com/jakelihua/rag-table-ai/issues/new?template=table-case.md)。

[MIT 许可证](LICENSE)
