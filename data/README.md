# 数据说明

## 当前 v2

| 文件 | 内容 |
|---|---|
| `raw/Ni_RC_180_candidate_dataset_v2.xlsx` | 180 条 Ni 基候选，含完整结果、掩盖结果和测试条件三个工作表 |
| `v2/manifest.json` | 数据指纹、指标口径、校验状态与展示入口 |
| `v2/lit_chunks.json` | 21 篇文献、1490 个真实解析 chunk，保留页码和 paper_id |

- 指标：Δη_RC（mV，越低越好）。
- Top10%：18 条，阈值 10.8 mV。
- 全局最优：`C024`，5.8 mV。
- 当前 Agent 最佳：`C054`，5.9 mV，全局第 2。

## 历史 212 条

| 文件 | 内容 |
|---|---|
| `raw/HER实验数据-212条.xlsx` | 212 条候选与槽电压结果 |
| `raw/HER实验数据-212条 - 结果已掩盖.xlsx` | 对应的决策阶段掩盖版 |
| `claims.json` | 旧版文献主张 |
| `lit_chunks.json` | 旧版文献缓存 |
| `runs/` | 旧版随机、仅文献、记忆与贪心基线 |

旧版指标为槽电压 V，v2 为 Δη_RC mV。两套数据的候选 ID、数值和排名不可混用。

## 运行记录

`runs/` 保存 `ecat` 对照实验的结构化结果，用于重新汇总和绘图。成员 A 的 JSONL 运行记录单独存放在 `members/member-a/agent_v1/runs/` 与 `agent_v5/runs/`。

`llm_ledger.jsonl` 为模型调用台账，不含 API Key。
