"""Bundle evaluation summary + featured run trajectories into demo/data.js.

The demo is a static page (double-click to open). Ground-truth voltages appear
only for candidates the agent actually tested, mirroring what a lab would know.
"""
from __future__ import annotations

import json

from .agent import NODES, RUNS
from .evaluate import summarize
from .oracle import Evaluator
from .space import ROOT, load_candidates

OUT = ROOT / "demo" / "data.js"
POLICY_META = {
    "random": {"name": "随机筛选", "desc": "无先验基线，等概率抽样"},
    "greedy_stat": {"name": "统计贪心", "desc": "按已测元素均值贪心，离线不用 LLM"},
    "lit_only": {"name": "仅文献 LLM", "desc": "LLM 只读文献，不看实验反馈"},
    "memory": {"name": "eCAT 记忆闭环", "desc": "文献 + 实验 + 决策三图谱记忆闭环"},
}


def _slim_run(run: dict) -> dict:
    return {k: run[k] for k in ("policy", "seed", "model", "rounds", "per_round",
                                "trace", "log", "traceability", "graph") if k in run}


def build() -> dict:
    summ = summarize()
    ev = Evaluator()
    cands = load_candidates()
    systems: dict[str, int] = {}
    for c in cands:
        systems[c.system] = systems.get(c.system, 0) + 1

    featured = {}
    for pol in ("memory", "lit_only", "greedy_stat", "random"):
        files = sorted(RUNS.glob(f"{pol}_s*.json"))
        if not files:
            continue
        # featured run = the one reaching the best rank earliest
        def key(f):
            r = json.loads(f.read_text(encoding="utf-8"))
            best = min(r["log"], key=lambda x: ev.truth[x["cid"]])
            idx = next(i for i, x in enumerate(r["log"]) if x["cid"] == best["cid"])
            return (ev.rank[best["cid"]], idx)
        f = min(files, key=key)
        featured[pol] = _slim_run(json.loads(f.read_text(encoding="utf-8")))

    for pol, v in summ["policies"].items():
        v.update(POLICY_META.get(pol, {"name": pol, "desc": ""}))
        for r in v["runs_detail"]:
            r.pop("policy", None)

    data = {
        "space": {**summ["space"], "systems": len(systems),
                  "elements": sorted({e for c in cands for e in c.elements})},
        "nodes": NODES,
        "policies": summ["policies"],
        "featured": featured,
        "candidates": [{"id": c.cid, "composition": c.composition, "system": c.system} for c in cands],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("window.ECAT = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
    return data


if __name__ == "__main__":
    d = build()
    print(OUT, round(OUT.stat().st_size / 1024, 1), "KB", list(d["featured"]))
