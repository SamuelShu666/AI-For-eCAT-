# -*- coding: utf-8 -*-
"""汇总三组消融：随机 / 仅文献 / 文献+记忆"""
import json
import random
import statistics
from pathlib import Path

import agent_tools as T

RUN_DIR = Path(r"D:\her_agent_project\runs")
DRAWS = 20
SEEDS = 20


def load_agent_runs():
    out = {"memory": [], "lit_only": []}
    for p in sorted(RUN_DIR.glob("run_*.jsonl")):
        rows = [json.loads(line) for line in open(p, encoding="utf-8") if line.strip()]
        if len(rows) != DRAWS:
            continue
        mode = rows[0].get("mode", "memory")
        if mode not in out:
            continue
        out[mode].append({
            "file": p.name,
            "best": min(r["delta_eta_mv"] for r in rows),
            "rank": min(r["rank"] for r in rows),
            "top10": sum(1 for r in rows if r.get("top10")),
            "hit": next((r["round"] for r in rows if r.get("top10")), None),
        })
    return out


def random_baseline():
    pool = T.load_pool()
    res = T.load_results()
    ids = [p["candidate_id"] for p in pool]
    rows = []
    for seed in range(SEEDS):
        pick = random.Random(seed).sample(ids, DRAWS)
        rows.append({
            "best": min(res[c]["delta_eta_mv"] for c in pick),
            "rank": min(res[c]["rank"] for c in pick),
            "top10": sum(1 for c in pick if res[c]["top10"]),
            "hit": next((k + 1 for k, c in enumerate(pick) if res[c]["top10"]), None),
        })
    return rows


def summarize(name, rows):
    if not rows:
        return f"{name:<10} 无数据"
    hits = [r["hit"] for r in rows if r["hit"]]
    return (f"{name:<10} n={len(rows)}  "
            f"最佳Δη={statistics.mean(r['best'] for r in rows):5.1f}  "
            f"rank={statistics.mean(r['rank'] for r in rows):4.1f}  "
            f"Top10={statistics.mean(r['top10'] for r in rows):4.1f}  "
            f"首中={statistics.mean(hits) if hits else float('nan'):4.1f}")


def main():
    agent = load_agent_runs()
    print("组别        运行数  最佳Δη(mV)  最佳rank  Top10数  首次命中")
    print(summarize("随机", random_baseline()))
    print(summarize("仅文献", agent["lit_only"]))
    print(summarize("文献+记忆", agent["memory"]))

    print("\n明细：")
    for mode, rows in agent.items():
        for r in rows:
            print(f"  [{mode}] {r['file']}  Δη={r['best']:.1f} rank={r['rank']} "
                  f"Top10={r['top10']} 首中={r['hit']}")


if __name__ == "__main__":
    main()