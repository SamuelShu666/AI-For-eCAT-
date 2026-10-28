# 成员 C · Neo4j 科研记忆图谱

本目录保存科研记忆图谱的 schema、Cypher 脚本、示意图片与构建脚本。

## 目录

```text
member-c/
├── neo4j_memory_schema.md
├── build_memory_graph.py
├── cypher/
│   ├── 00_constraints.cypher
│   └── 02_seed_candidates.cypher
└── diagrams/
    ├── 01_literature_subgraph.png
    ├── 02_experiment_subgraph.png
    ├── 03_decision_subgraph.png
    └── 04_overview.png
```

## 图谱语义

- 文献子图：`Paper`、`Evidence`，通过 `CONTAINS` / `MENTIONS` 关联。
- 实验子图：`Material`、`Experiment`、`Result`、`Condition`。
- 决策子图：`Round`、`Decision`、`Diagnosis`、`Suggestion`。
- 共享实体：`Element`，连接文献提及和材料组成。

完整字段、边类型与写回规则见 `neo4j_memory_schema.md`。

## 与当前展示版的关系

`demo_v2` 的四子图视图参考本目录的 schema，并使用 180 条 Ni-RC v2 运行记录重建展示数据。

需要注意：本目录的 Cypher 和示意图含有早期 212 条槽电压体系的历史字段，尚未全部替换为 v2 的 Δη_RC。它们用于表达图谱结构，不应把图中旧数值当作当前 v2 结果。

## 后续整理建议

1. 在 `00_constraints.cypher` 中把旧的槽电压字段统一迁移到 `delta_eta_rc_mV`。
2. 补充 `01_seed_literature.cypher`，写入 `Paper` / `Evidence` 种子。
3. 将 `02_seed_candidates.cypher` 切换到 180 条候选及真实排名字段。
4. 为每条关系增加 `source_run_id`、`evidence_id` 和写入时间，保证可追溯。
