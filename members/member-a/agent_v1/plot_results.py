# -*- coding: utf-8 -*-
"""Agent vs 随机基线：最佳 Δη 曲线 + Top10 累计发现数"""
import os

os.environ.setdefault("MPLCONFIGDIR", r"D:\her_agent_project\.mplcache")

import json
import random
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import agent_tools as T

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

RUN_DIR = Path(r"D:\her_agent_project\runs")
OUT_DIR = Path(r"D:\her_agent_project\figures")
OUT_DIR.mkdir(exist_ok=True)

DRAWS = 20
SEEDS = 20
TOP10_THRESHOLD = 10.8   # mV


def load_agent_runs():
    runs = []
    for p in sorted(RUN_DIR.glob("run_*.jsonl")):
        rows = [json.loads(line) for line in open(p, encoding="utf-8") if line.strip()]
        if len(rows) != DRAWS:
            continue
        best, cur, top, c = [], 1e9, [], 0
        for r in rows:
            cur = min(cur, r["delta_eta_mv"])
            best.append(cur)
            c += 1 if r.get("top10") else 0
            top.append(c)
        runs.append({
            "file": p.name,
            "best": best,
            "top": top,
            "final_best": best[-1],
            "final_rank": min(x["rank"] for x in rows),
            "n_top10": top[-1],
            "first_hit": next((x["round"] for x in rows if x.get("top10")), None),
        })
    return runs


def random_curves():
    pool = T.load_pool()
    results = T.load_results()
    ids = [p["candidate_id"] for p in pool]

    bests, tops = [], []
    for seed in range(SEEDS):
        rng = random.Random(seed)
        pick = rng.sample(ids, DRAWS)
        cur, best, c, top = 1e9, [], 0, []
        for cid in pick:
            cur = min(cur, results[cid]["delta_eta_mv"])
            best.append(cur)
            c += 1 if results[cid]["top10"] else 0
            top.append(c)
        bests.append(best)
        tops.append(top)
    return bests, tops


def mean_cols(mat):
    return [sum(col) / len(col) for col in zip(*mat)]


def main():
    runs = load_agent_runs()
    if not runs:
        raise SystemExit("runs/ 里没有 20 轮的运行记录")

    rb, rt = random_curves()
    x = list(range(1, DRAWS + 1))

    agent_best = mean_cols([r["best"] for r in runs])
    rand_best = mean_cols(rb)
    agent_top = mean_cols([r["top"] for r in runs])
    rand_top = mean_cols(rt)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))

    ax = axes[0]
    ax.plot(x, agent_best, marker="o", ms=3, lw=2, label=f"eCAT Agent（n={len(runs)}）")
    ax.plot(x, rand_best, marker="s", ms=3, lw=2, ls="--", label=f"随机搜索（n={SEEDS}）")
    ax.axhline(TOP10_THRESHOLD, color="gray", ls=":", lw=1.2, label="Top 10% 门槛")
    ax.set_xlabel("实验次数")
    ax.set_ylabel("历史最佳 Δη_RC（mV，越低越好）")
    ax.set_title("历史最佳性能随实验次数的变化")
    ax.legend(frameon=False)
    ax.grid(alpha=0.25)

    ax = axes[1]
    ax.plot(x, agent_top, marker="o", ms=3, lw=2, label=f"eCAT Agent（n={len(runs)}）")
    ax.plot(x, rand_top, marker="s", ms=3, lw=2, ls="--", label=f"随机搜索（n={SEEDS}）")
    ax.set_xlabel("实验次数")
    ax.set_ylabel("累计发现的 Top10% 候选数")
    ax.set_title("累计发现优质候选的速度")
    ax.legend(frameon=False)
    ax.grid(alpha=0.25)

    fig.tight_layout()
    out = OUT_DIR / "agent_vs_random.png"
    fig.savefig(out, dpi=160)
    print("图已保存:", out)

    print("\n运行汇总：")
    for r in runs:
        print(f"  {r['file']} | 最佳 Δη={r['final_best']:.1f} | rank={r['final_rank']} "
              f"| Top10={r['n_top10']} | 首中={r['first_hit']}")

    print("\nAgent 均值：")
    print("  最佳 Δη:", round(sum(r["final_best"] for r in runs) / len(runs), 2))
    print("  最佳 rank:", round(sum(r["final_rank"] for r in runs) / len(runs), 2))
    print("  Top10 发现数:", round(sum(r["n_top10"] for r in runs) / len(runs), 2))


if __name__ == "__main__":
    main()