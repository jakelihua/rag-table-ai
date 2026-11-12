# GitHub 发布与推广方案

## 仓库首页

把 [英文 README](../README.md) 和 [中文 README](../README.zh-CN.md) 放到默认分支后，再把流量集中到仓库首页。首屏的用例保持为运费表，访客可以看到列名如何随切片保留，然后直接运行 [MinerU 示例](../examples/04_mineru_pipeline.py)。

- **About** — `专治 RAG 复杂表格“切碎丢表头”难题（支持合并表头展开、MinerU HTML 与预算切片） | Header-preserving table chunking & evidence lookup for RAG`
- **Topics** — `rag`, `table-chunking`, `mineru`, `html-tables`, `markdown-tables`, `chunking`, `document-processing`, `llm`, `python`。它们对应用户会搜索的上下游工具、输入格式与核心任务。[GitHub Topics](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics)
- **社交预览** — 左边展示 `11–20 kg | 12.00 | 18.00`，右边保留 `Weight | Standard | Express`，底部放 `USD 14.40 · PDF p.3 · row 2`。预览图、README 和文章共用同一案例。[GitHub 仓库自定义](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository)

## 首次发布

合并后准备一个 GitHub Release。发布说明列出 MinerU Content List V1 的输入契约、跨列合并表头、预算切片及页码引用。附上测试过的 wheel、示例入口和支持边界。版本号建议使用 `v0.2.0`，发布时与包元数据同步。[GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)

### Release 标题

`Header-preserving RAG chunks from MinerU tables`

### 中文发布文案

RAG 找到了正确的一行，却分不出哪一个数字是加急价。这个例子把 MinerU 的表格 HTML 切成带表头和原文页码的分片，再用 15 kg 匹配运费档位。示例可在本地运行，输出 USD 14.40，来源是 PDF 第 3 页、表内第 2 条数据行。

### English release copy

Your retriever found the right shipping row. Can it tell which number is the express rate? The demo turns MinerU table HTML into chunks that keep their headers and page references. Run it locally to look up 15 kg, apply a 20% discount, and cite the source page.

## 发布后一周

1. 先发一次能从 GitHub 复现的技术文章。标题可用《RAG 找对了行，为什么还会报错价？从 MinerU 表格到可引用分片》。文章附输入、输出、命令，以及一例预算不足时的报错。
2. 用[表格复现模板](../.github/ISSUE_TEMPLATE/table-case.md)邀请用户分享脱敏后的最小案例。优先转成测试的是合并表头错位、PDF 引用偏移和宽表分组问题。
3. 跟踪带复现的 issue 数、真实项目接入反馈、修复后进入测试集的样例数。推广时可引用合成运费示例的 **10/10 逻辑单元格覆盖**，注明样本规模。正式检索准确率等到同预算对照实验完成后再公布。
