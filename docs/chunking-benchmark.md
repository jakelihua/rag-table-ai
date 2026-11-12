# Wide table chunking benchmark

[中文说明](#中文说明)

This measures table structure and index size. It uses table 3 on PDF page 6 of [MinerU's public demo1.pdf](https://github.com/opendatalab/MinerU/blob/master/demo/pdfs/demo1.pdf), exported locally with MinerU 3.4.5 in pipeline mode. Each run uses the same exported table, two header rows, column 1 as the repeated row key, and at most three data rows per chunk.

| Budget | Chunks, greedy → balanced | Total indexed characters or tokens | Largest balanced chunk |
| --- | ---: | ---: | ---: |
| 185 characters | 33 → 25 | 5,173 → 3,968 | 180 characters |
| 64 tokens, `cl100k_base` | 34 → 25 | 1,970 → 1,557 | 64 tokens |
| 128 tokens, `cl100k_base` | 14 → 10 | 1,512 → 1,152 | 118 tokens |
| 256 tokens, `cl100k_base` | 4 → 4 | 923 → 923 | 255 tokens |

All eight runs reconstruct the same 110 logical data cells, with the same coordinate/value and header hashes. With tiktoken 0.13.0 on the test machine, the median time over 30 runs went from 3.3 to 7.1 ms at 64 tokens and from 3.6 to 13.6 ms at 128 tokens. At 256 tokens the full table width fit, so the planner did not search column groupings. For the pair `Percentile / 20` and `Percentile / 30` (original columns 3 and 4), same-chunk coverage went from 10/10 rows to 0/10 at 64 tokens and stayed at 10/10 at 128 tokens. Chunk counts, index sizes, and same-chunk coverage are structural measurements. Measure retrieval recall separately for single-cell and cross-column questions.

In the reviewer's 33-column, 100-row case at 220 tokens and 50 rows per chunk, the bounded planner reduced tokenizer calls from 63,029 to 7,696 and local elapsed time from 3.12 s to 0.27 s compared with `2214296`. The fallback produced 200 chunks instead of 107 in that case.

## Reproduce

Export the first six pages of the demo PDF with MinerU 3.4.5.

```bash
mineru -p demo1.pdf -o mineru-output -b pipeline -m txt -f false -t true -s 0 -e 5
```

From the repository root, install the package, then run the same measurement with both versions. The demo export used table block index 79. Use the index of the block with caption `Coefficient of efficiency, E` if your export orders the blocks differently.

```bash
python -m pip install .
python -m pip install tiktoken==0.13.0  # Optional for token budgets.
git worktree add --detach ../rag-table-ai-baseline 7c2f5b9

export_file=mineru-output/demo1/txt/demo1_content_list.json
PYTHONPATH=../rag-table-ai-baseline python benchmarks/measure_chunking.py "$export_file" \
  --table-block 79 --header-rows 2 --key-column 1 --budget 64 --encoding cl100k_base --repeat 30 --column-pair 3 4
python benchmarks/measure_chunking.py "$export_file" \
  --table-block 79 --header-rows 2 --key-column 1 --budget 64 --encoding cl100k_base --repeat 30 --column-pair 3 4
```

Omit `--encoding` for character counts. The script checks rendered headers, coverage, and duplicate values by logical coordinates, enforces the budget on each complete chunk, and reports the maximum size, total size, tokenizer calls, and median planning time. Compare `cells_sha256` and `headers_sha256` across versions to verify values and column labels. The reported time includes the adapter and chunk planner, with the PDF extraction and tokenizer loading outside the timed region.

## 中文说明

对同一份 MinerU 3.4.5 导出，固定表头行数、行标识列和每片最多三行，只改变分列策略。旧策略先尽量多塞列。新策略先计算每种候选列组能放几行，再以总分片数优先、总计数次之选择组合。整表宽度能放下时，仍保留整列按行切分。为限制规划开销，超过 32 个非标识列或用完 4,096 次候选计数时回退到贪心分组。

在公开样例中，64 token 预算下分片从 **34 降到 25**，索引文本从 **1,970 降到 1,557 token**。两版都能逐格还原 110 个数据单元格，表头哈希一致。同一行的第 3、4 列同时出现在一个分片里的覆盖率，在 64 token 下从 10/10 行降到 0/10 行，在 128 token 下两版均为 10/10 行。新增规划会多调用 tokenizer，这组数据衡量的是保真与索引体积。评估召回时应另外固定检索预算，并分别标注单值查找和需要两列同时出现的查询。
