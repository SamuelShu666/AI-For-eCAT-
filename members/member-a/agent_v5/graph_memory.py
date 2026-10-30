# -*- coding: utf-8 -*-
"""Agent 的 Neo4j 记忆接口：按共享元素检索相似实验 + 写回决策与结果"""
import hashlib
import sys
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).resolve()
parents = list(HERE.parents)

# 仓库结构：members/member-a/agent_v5 -> members/member-c
# 本地开发：回退到 D:\AI-For-eCAT\members\member-c
candidates = []
if len(parents) > 2:
    candidates.append(parents[2] / "member-c")
candidates.append(Path(r"D:\AI-For-eCAT\members\member-c"))
GRAPH_DIR = next((p for p in candidates if p.exists()), candidates[-1])
sys.path.insert(0, str(GRAPH_DIR))

# 依次找 .env：当前目录 / 各级父目录
for base in [HERE.parent, *parents]:
    env_file = base / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        break
else:
    load_dotenv()

from build_memory_graph import (  # noqa: E402
    RESULT_COLUMN, get_driver, write_decision, write_experiment_result,
)

NS = "member_a_agent_v5"


class GraphMemory:
    def __init__(self):
        self.driver = get_driver()

    def close(self):
        self.driver.close()

    def available(self):
        try:
            with self.driver.session() as s:
                s.run("RETURN 1").consume()
            return True
        except Exception:
            return False

    def similar_experiments(self, composition, run_id, limit=5):
        query = """
        MATCH (m:Material {composition:$comp})-[:CONTAINS]->(el:Element)
        MATCH (other:Material)-[:CONTAINS]->(el)
        WHERE other <> m
        WITH other, count(DISTINCT el) AS shared
        MATCH (x:Experiment {status:'done', run_id:$run_id})-[:TESTS]->(other)
        MATCH (x)-[:PRODUCES]->(r:Result {metric_name:'delta_eta_rc'})
        RETURN other.candidate_id AS cid, other.composition AS comp,
               shared, r.metric_value AS value
        ORDER BY value ASC, shared DESC
        LIMIT $limit
        """
        with self.driver.session() as s:
            return [dict(r) for r in s.run(query, comp=composition,
                                           run_id=run_id, limit=limit)]

    def memory_text(self, composition, run_id, limit=5):
        rows = self.similar_experiments(composition, run_id, limit)
        if not rows:
            return "（图谱中暂无相似实验）"
        lines = ["图谱记忆：与当前最优组成共享元素的历史实验（越低越好）"]
        for r in rows:
            lines.append(
                f"  {r['cid']} {r['comp']} = {r['value']:.1f} mV"
                f"（共享 {r['shared']} 个元素）"
            )
        return "\n".join(lines)

    def record_round(self, *, run_id, round_num, candidate_id, delta_eta,
                     reason, evidence_ids, confidence=0.6, direction="improve"):
        request_id = f"{run_id}:R{round_num:02d}:{candidate_id}"
        decision_id = write_decision(
            self.driver,
            round_num=round_num,
            candidate_id=candidate_id,
            expected_direction=direction,
            confidence=confidence,
            selection_reason=reason or "无",
            evidence_ids=[{"namespace": NS, "source_id": e} for e in evidence_ids],
            referenced_experiment_ids=[],
            agent_version="agent_v5",
            request_id=request_id,
        )

        suffix = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:10]
        experiment_id = f"EXP_R{round_num:02d}_{candidate_id}_{suffix}"
        result_id = f"RES_R{round_num:02d}_{candidate_id}_{suffix}"

        write_experiment_result(
            self.driver,
            experiment_id=experiment_id,
            result_id=result_id,
            metric_value=float(delta_eta),
            source_row=int(candidate_id[1:]) + 1,
            source_file="Ni_RC_180_candidate_dataset_v2.xlsx",
            source_sheet="完整数据",
            source_column=RESULT_COLUMN,
            unit="mV",
        )

        with self.driver.session() as s:
            s.run("MATCH (d:Decision {decision_id:$d}) SET d.run_id=$r",
                  d=decision_id, r=run_id).consume()
            s.run("MATCH (x:Experiment {experiment_id:$x}) SET x.run_id=$r",
                  x=experiment_id, r=run_id).consume()

        return decision_id, experiment_id