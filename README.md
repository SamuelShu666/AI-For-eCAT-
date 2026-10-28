# eCAT · 基于 AI Agent 的催化材料智能优化系统

面向碱性电解水制氢抗反向电流 HER 催化剂的智能筛选系统。项目把文献证据、规则校验、LangGraph 决策闭环、实验反馈和科研记忆图谱连接成一条可追溯的发现过程。

> 参赛：浙江大学“启真问创·重器领航”智能过程装备创新创业大赛 · 题目二十一

## 核心结果

当前展示版使用 **180 条 Ni 基合金候选**，指标为反向电流应力前后 HER 过电位增量 **Δη_RC（mV，越低越好）**。在 20 次实验预算下：

| 指标 | 文献 + 实验反馈 Agent | 随机搜索 |
|---|---:|---:|
| 平均首次命中 Top10% | **4.0 轮** | 7.95 轮 |
| 平均发现 Top10% 候选 | **7.0 / 18** | 2.3 / 18 |
| 平均最终最佳 Δη_RC | **5.9 mV** | 7.725 mV |
| 平均最终全局排名 | **#2 / 180** | #8.15 |

- 全局最优为 `C024`（`Co31Cr15Fe13Mo32Ni9`，5.8 mV），当前三次运行未发现该候选，因此本文和页面只表述为“找到全局第 2”，不写成“找到全局最优”。
- Agent 对照为 `n=3`，且前两次运行有 17/20 个同位置候选相同。结果用于机制展示，不作为强统计显著性证据。

## 仓库结构

```text
.
├── ecat/                 # 主流程：数据、检索、Agent、评估与展示数据导出
├── backend/              # 模型网关适配
├── scripts/              # 模型接入与探测脚本
├── data/
│   ├── raw/              # 180 条 v2 与历史 212 条工作簿
│   ├── runs/             # 消融实验与随机基线记录
│   ├── v2/               # v2 文献 chunk 缓存与校验清单
│   └── *.json            # 旧版缓存与汇总
├── demo/                 # 旧版 212 条槽电压展示
├── demo_v2/              # 当前 Ni-RC v2 展示，双击即可运行
├── docs/                 # 比赛文档、实施路线、评审意见
├── members/
│   ├── member-a/         # 文献 RAG、v1/v5 Agent、真实运行记录
│   ├── member-b/         # 展示层与数据整合说明
│   └── member-c/         # Neo4j 图谱 schema、Cypher 与示意图
├── references/           # 文献索引与团队总结，不包含版权 PDF
├── .env.example
└── requirements.txt
```

## 快速开始

### 直接查看展示

双击 `demo_v2/index.html`。页面为零外部依赖的静态 HTML/CSS/JavaScript，`data.js` 需与它位于同一目录。

旧版 212 条展示仍保留在 `demo/index.html`，两版数据口径不混用。

### 重新生成展示数据

```bash
pip install -r requirements.txt
python -m ecat.export_demo_v2
```

### 运行成员 A 的 Agent 快照

```bash
cd members/member-a/agent_v5
python agent_graph.py --mode memory --rounds 20
```

该快照保留成员 A 上传时的原始说明与运行记录。它包含比当前展示版更大的历史文献语料，数字不直接与 `demo_v2` 的 `n=3` 对照混算。

## 数据与指标

- 候选池：`data/raw/Ni_RC_180_candidate_dataset_v2.xlsx`，180 条，17 种元素，49 个体系。
- 指标：Δη_RC，反向电流应力前后 HER 过电位增量，单位 mV，越低越好。
- Top10%：18 条，阈值 10.8 mV。
- 条件：1 M KOH、10 mA cm⁻²、三电极、Hg/HgO 校准至 RHE、石墨对电极；+0.1 mA cm⁻² 恒电流反向应力 30 min。
- 数据指纹记录在 `data/v2/manifest.json`。

## 可追溯证据

每次决策关联原始运行引用的 `evidence_id`、PDF 编号和页码。当前仓库存放的是派生 chunk 与页级定位信息，不包含原始 PDF。

成员 A 原始向量库（Chroma + MiniLM）未随交付提供，因此页面把“原始运行引用”与“TF-IDF + BM25 + RRF 离线重放”分开展示，不把重放排名冒充原始向量检索结果。

## 分支约定

- `main`：整合版，保留完整项目结构与最新展示。
- `member-a`：成员 A 的 Agent / RAG 开发线，主要修改 `members/member-a/`。
- `member-b`：成员 B 的展示与数据整合线，主要修改 `ecat/`、`demo_v2/`、`data/v2/`。
- `member-c`：成员 C 的图谱开发线，主要修改 `members/member-c/`。

成员分支均从整合版创建。合并前先同步 `main`，避免用个人分支覆盖其他人的目录。

## 数据与版权说明

- 仓库不包含原始论文 PDF，仅保留文献索引、页码与派生 chunk。论文版权归原作者及出版方所有。
- 不提交 `.env`、API Key、模型缓存、向量数据库、内部聊天记录或临时备份。
- 真实实验数据用于本项目复现与评审展示；如需公开复用，请先征得数据负责人同意。
