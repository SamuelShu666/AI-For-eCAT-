# 成员 C · Neo4j 科研记忆图谱

本目录给出面向抗反向电流 HER 催化剂研发的三子图设计和可执行导入骨架：文献知识、实验事实、决策轨迹。自动化实验平台执行结构化任务；Neo4j 保存可追溯的证据、实验回传和 Agent 决策，不把模型推断写成实验事实。

## 文件导航

- `neo4j_memory_schema.md`：目标边界、180 条候选数据字典、节点/关系字段、分层权限、事务写回规则和查询例子。
- `build_memory_graph.py`：候选池、文献块及带来源别名的导入；含决策和可信实验结果写回接口。
- `cypher/00_constraints.cypher`：唯一约束、索引和全文检索索引。
- `cypher/01_literature_evidence.cypher`：文献、原文片段、别名、待核 Claim 的幂等导入模板。
- `cypher/02_seed_candidates.cypher`：180 条候选池导入说明。
- `diagrams/01_*.svg` 至 `04_*.svg`：中文矢量子图图示；同名 `.jpg` 用于快速预览。

## 数据口径

候选身份和组成来自 `data/raw/Ni_RC_180_candidate_dataset_v2.xlsx` 的 `掩盖结果` 表；测试条件来自项目 v2 manifest。候选种子阶段不会读 `完整数据` 中的 Δη_RC、排名或 Top 10% 标签。实验返回后，可信回调以指标、单位、定义、源文件和行号写入 `Result`。

`Δη_RC` 的属性名为 `delta_eta_rc`，单位为 mV；旧数据中的 `cell_voltage_V` 是整电池端电压，是独立指标，不能改名或换算后写入 Δη_RC。

## 推荐导入顺序

在项目根目录配置 Neo4j 环境变量后依次执行：

```powershell
cypher-shell -f members/member-c/cypher/00_constraints.cypher
python members/member-c/build_memory_graph.py --seed-candidates
python members/member-c/build_memory_graph.py --import-literature
python members/member-c/build_memory_graph.py --import-agent-v5-aliases
```

`--import-agent-v5-aliases` 需读取 `members/member-a/agent_v5/paper_registry.csv` 与 `her_chunks_v5.csv`。导入时以该 registry 文件名和来源文献为准，`P03` 这种短编号只有在对应命名空间内才有意义；不可用 demo 导出里的旧固定映射解析 Agent 引用。

先在 Neo4j 测试库完成 schema 和数据检查，再连接 Agent 或自动化实验平台。脚本不会自动提交真实实验任务；`write_decision` 只在被上层服务调用时建立待执行任务，任务派发及鉴权由 Orchestrator 负责。

## 证据编号规则

图谱内部 `paper_id` 和 `evidence_id` 按来源路径、页码及原文内容生成稳定键。外部编号以 `EvidenceAlias(namespace, source_id)` 保存并解析到原文片段。当前确认的成员 A v5 映射包括：`P01`→停机反向电流 JPS 论文，`P03`→Pb/Ni AFM 论文，`P06`→零间隙电解槽阴极保护论文。`ecat/export_demo_v2.py` 及现有 `demo_v2/data.js` 的固定映射把 P03/P06 指向了其他论文；不要从该演示映射回写证据身份。

`data/claims.json` 中的摘录被导为 `Claim(review_status='pending_human_review')`，必须人工核验后才能作为结构化知识被 Agent 使用。证据片段保留原文及页码；Claim 的总结不替代 Evidence。
