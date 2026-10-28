# 成员 A · 文献 RAG 与 Agent 闭环

本目录保留成员 A 的两次交付快照和真实运行记录。

## 目录

```text
member-a/
├── agent_v1/             # 早期 LangGraph 闭环与 3 次 2026-10-27 运行
├── agent_v5/             # 上传至 GitHub main 的 v5 快照与 10 次 2026-10-28 运行
├── legacy_retriever/     # 早期混合检索工具单文件版本
├── data/                 # 旧版 HER 清洗数据
└── assets/               # 架构草图与任务说明截图
```

## 入口

- v5 主流程：`agent_v5/agent_graph.py`
- v5 文献工具：`agent_v5/tool_literature.py`
- v5 混合检索：`agent_v5/hybrid_retriever_safe.py`
- v1 主流程：`agent_v1/agent_graph.py`
- v1 运行记录：`agent_v1/runs/*.jsonl`，共 3 次，均为 20 轮。
- v5 运行记录：`agent_v5/runs/*.jsonl`，共 10 次，日期为 2026-10-28。

在 `agent_v5/` 内运行：

```bash
python agent_graph.py --mode memory --rounds 20
```

依赖与环境变量说明以根目录 `requirements.txt` 和 `.env.example` 为准。

## 展示层如何复用

`demo_v2` 使用 `agent_v1/runs/` 中 3 次真实运行做逐轮回放，并保留原始 `evidence_id`、候选选择与结果。由于原始 Chroma 数据库和 MiniLM 缓存未交付：

- 页面保留原始运行引用，不重写其 chunk 编号；
- 另用 TF-IDF + BM25 + RRF 做可复现的离线重放；
- 同 PDF、同页的新解析 chunk 单独展示，不冒充原始向量文本。

## 归档说明

- `agent_v5/README_original.md` 是成员 A 上传时的原始 README，保留其历史口径。
- v5 的历史语料规模与 `demo_v2` 当前 21 篇 / 1490 chunk 展示库不同，两者数字不直接混算。
- 未上传内部聊天记录、压缩包和重复素材。
