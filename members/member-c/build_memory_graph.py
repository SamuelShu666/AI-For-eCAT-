# -*- coding: utf-8 -*-
"""
build_memory_graph.py
=====================
Neo4j 科研记忆图谱写入模块（对应比赛报告第四章）。

功能：
  1. seed_candidate_pool()  : 从 212 条 xlsx 候选池一次性 MERGE Element / Material / CONTAINS 关系
  2. write_fixed_condition() : 写入本次比赛固定测试条件节点
  3. write_decision()        : 写回一轮决策（Decision + 关系）
  4. write_experiment_result(): 结果接口返回后写回 Experiment/Result/Diagnosis/Suggestion

使用：
  pip install neo4j pandas openpyxl
  export NEO4J_URI=bolt://localhost:7687
  export NEO4J_USER=neo4j
  export NEO4J_PASSWORD=your_password

  python build_memory_graph.py --seed
"""
from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

import pandas as pd
from neo4j import GraphDatabase, Driver


# ---------------------------------------------------------------------------
# 1. 连接
# ---------------------------------------------------------------------------
def get_driver() -> Driver:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pwd = os.environ.get("NEO4J_PASSWORD", "neo4j")
    return GraphDatabase.driver(uri, auth=(user, pwd))


# ---------------------------------------------------------------------------
# 2. 解析 composition 字符串
#    "Ag-0.4-Pd-0.6" -> [("Ag", 0.4), ("Pd", 0.6)]
#    "Rh-1.0"        -> [("Rh", 1.0)]
# ---------------------------------------------------------------------------
COMP_RE = re.compile(r"([A-Z][a-z]?)-(\d+\.\d+)")

def parse_composition(comp: str) -> list[tuple[str, float]]:
    parts = comp.split("-")
    out = []
    for i in range(0, len(parts), 2):
        out.append((parts[i], float(parts[i + 1])))
    return out


# ---------------------------------------------------------------------------
# 3. 初始化：候选池 212 条 -> Element + Material + CONTAINS
# ---------------------------------------------------------------------------
def seed_candidate_pool(driver: Driver, xlsx_path: str = "attachments/HER实验数据-212条.xlsx") -> None:
    df = pd.read_excel(xlsx_path)
    assert list(df.columns)[:2] == ["composition", "voltage"], f"列名不符: {df.columns}"

    with driver.session() as s:
        # 3.1 固定条件节点
        s.run(
            """
            MERGE (c:Condition {cond_key:'fixed_running_standard'})
              SET c.condition_type='test_mode',
                  c.name='anti-reverse-current HER fixed running test',
                  c.note='所有 212 条候选均在此固定条件下测试，cell_voltage_V 为唯一代理指标，越低越好'
            """
        )

        # 3.2 批量 MERGE Material + Element + CONTAINS
        for _, row in df.iterrows():
            comp = row["composition"]
            elems = parse_composition(comp)
            mat_type = "pure" if len(elems) == 1 else ("binary" if len(elems) == 2 else "ternary")
            # material_id 直接用 composition 转义，避免依赖 APOC
            mat_id = "MAT_" + comp.replace("-", "_").replace(".", "_")
            s.run(
                """
                MERGE (m:Material {composition:$comp})
                  SET m.material_id   = $mat_id,
                      m.n_elements   = $n,
                      m.element_list = [x IN $elems | x[0]],
                      m.material_type= $mat_type,
                      m.in_candidate_pool = true
                WITH m
                UNWIND $elems AS pair
                  MERGE (el:Element {symbol: pair[0]})
                  MERGE (m)-[r:CONTAINS]->(el)
                    SET r.ratio = pair[1]
                """,
                comp=comp, mat_id=mat_id, n=len(elems),
                elems=[list(p) for p in elems], mat_type=mat_type,
            )
        print(f"[seed] 已 MERGE {len(df)} 条候选 Material 节点")


# ---------------------------------------------------------------------------
# 4. Agent 一轮决策写回
# ---------------------------------------------------------------------------
@dataclass
class AgentDecision:
    round_num: int
    selected_composition: str
    expected_direction: Literal["lower_voltage", "stability_check", "explore_unknown"]
    confidence: float
    selection_reason: str
    evidence_ids: list[str] = field(default_factory=list)
    referenced_experiment_ids: list[str] = field(default_factory=list)
    agent_version: str = "agent-v0.1"


def write_decision(driver: Driver, d: AgentDecision) -> str:
    decision_id = f"DEC_R{d.round_num:02d}_001"
    exp_id      = f"EXP_R{d.round_num:02d}_001"

    with driver.session() as s:
        # 4.1 校验候选池
        row = s.run(
            "MATCH (m:Material {composition:$c}) RETURN m.composition AS c",
            c=d.selected_composition,
        ).single()
        if row is None:
            raise ValueError(f"候选 {d.selected_composition} 不在 212 条候选池中，拒绝写入")

        # 4.2 决策必须有依据
        if not d.evidence_ids and not d.referenced_experiment_ids:
            raise ValueError("Decision 必须至少引用 1 条 Evidence 或历史 Experiment")
        if d.round_num == 1 and d.referenced_experiment_ids:
            raise ValueError("Round 1 为文献冷启动，不允许引用历史实验")

        # 4.3 写 Round / Decision / Experiment(submitted)
        s.run(
            """
            MERGE (rd:Round {round_num:$round})
              SET rd.started_at = datetime(),
                  rd.agent_version = $ver,
                  rd.method_tag = CASE WHEN $round=1 THEN 'full_memory' ELSE 'full_memory' END
            WITH rd
            MERGE (d:Decision {decision_id:$did})
              SET d.round_num=$round,
                  d.selected_composition=$comp,
                  d.expected_direction=$dir,
                  d.confidence=$conf,
                  d.selection_reason=$reason,
                  d.agent_version=$ver,
                  d.output_schema_version='v1',
                  d.created_at=datetime()
            MERGE (rd)-[:HAS_DECISION]->(d)
            WITH d
            MERGE (exp:Experiment {experiment_id:$eid})
              SET exp.round_num=$round,
                  exp.status='submitted',
                  exp.timestamp=datetime(),
                  exp.submitted_by=$ver
            MERGE (d)-[:EXECUTED_AS]->(exp)
            MERGE (d)-[:SELECTS]->(:Material {composition:$comp})
            MERGE (exp)-[:TESTS]->(:Material {composition:$comp})
            MERGE (exp)-[:UNDER]->(:Condition {cond_key:'fixed_running_standard'})
            """,
            round=d.round_num, did=decision_id, eid=exp_id,
            comp=d.selected_composition, dir=d.expected_direction,
            conf=d.confidence, reason=d.selection_reason, ver=d.agent_version,
        )

        # 4.4 挂引用证据
        for eid in d.evidence_ids:
            s.run(
                """
                MATCH (d:Decision {decision_id:$did})
                MATCH (e:Evidence {evidence_id:$eid})
                MERGE (d)-[:REFERENCES_EVIDENCE {ref_weight:1.0}]->(e)
                """,
                did=decision_id, eid=eid,
            )

        # 4.5 挂引用历史实验
        for old_exp_id in d.referenced_experiment_ids:
            s.run(
                """
                MATCH (d:Decision {decision_id:$did})
                MATCH (old:Experiment {experiment_id:$oid})
                MERGE (d)-[:REFERENCES_EXPERIMENT {similarity_score:0.0}]->(old)
                """,
                did=decision_id, oid=old_exp_id,
            )

    print(f"[decision] {decision_id} 已写回 -> {d.selected_composition}")
    return decision_id


# ---------------------------------------------------------------------------
# 5. 结果接口返回后写回（由确定性程序调用，Agent 不可改数值）
# ---------------------------------------------------------------------------
def write_experiment_result(
    driver: Driver,
    round_num: int,
    cell_voltage_V: float,
    result_label: Literal["best_new", "improved", "flat", "degraded", "abnormal"] = "flat",
    diagnosis_text: str = "",
    suggestion_text: str = "",
    adjustment_type: str = "",
) -> None:
    exp_id  = f"EXP_R{round_num:02d}_001"
    res_id  = f"RES_R{round_num:02d}_001"
    dia_id  = f"DIA_R{round_num:02d}_001"
    sug_id  = f"SUG_R{round_num:02d}_001"

    with driver.session() as s:
        s.run(
            """
            MATCH (exp:Experiment {experiment_id:$eid})
            SET exp.status='done', exp.timestamp=datetime()
            MERGE (r:Result {result_id:$rid})
              SET r.cell_voltage_V=$v,
                  r.test_status='ok',
                  r.created_at=datetime()
            MERGE (exp)-[:PRODUCES]->(r)
            WITH r
            MATCH (exp)-[:PRODUCES]->(r)
            OPTIONAL MATCH (best:Result)
            WHERE best.is_best_so_far = true AND best.result_id <> r.result_id
            WITH r, best
            ORDER BY best.cell_voltage_V DESC NULLS LAST
            LIMIT 1
            SET r.is_best_so_far = (best IS NULL OR r.cell_voltage_V < best.cell_voltage_V)
            WITH r
            MERGE (d:Diagnosis {diagnosis_id:$did})
              SET d.result_label=$label,
                  d.objective_conclusion=$diag,
                  d.human_reviewed=false,
                  d.created_at=datetime()
            MERGE (r)<-[:DIAGNOSED_BY]-(d)
            WITH d
            MERGE (s:Suggestion {suggestion_id:$sid})
              SET s.adjustment_type=$adj,
                  s.specific_strategy=$sug,
                  s.based_on_diagnosis_id=$did
            MERGE (d)-[:GENERATES]->(s)
            """,
            eid=exp_id, rid=res_id, did=dia_id, sid=sug_id,
            v=cell_voltage_V, label=result_label,
            diag=diagnosis_text, sug=suggestion_text, adj=adjustment_type,
        )
    print(f"[result] {exp_id} -> {cell_voltage_V} V, label={result_label}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true", help="从 xlsx 初始化 212 条候选池")
    ap.add_argument("--xlsx", default="attachments/HER实验数据-212条.xlsx")
    args = ap.parse_args()

    drv = get_driver()
    try:
        if args.seed:
            seed_candidate_pool(drv, args.xlsx)
        else:
            print("请加 --seed 初始化候选池；单轮写回请 import 后调用 write_decision / write_experiment_result")
    finally:
        drv.close()
