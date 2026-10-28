# -*- coding: utf-8 -*-
"""三组对比：随机 / 仅文献 / 文献+记忆"""
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
TOP10_THRESHOLD = 10.8


def load_runs():
    out = {"memory": [], "lit_only": []}
    for p in sorted(RUN_DIR.glob("run_*.jsonl")):
        rows = [json.loads(line) for line in open(p, encoding="utf-8") if line.strip()]
        if len(rows) != DRAWS:
            continue
        mode = rows[0].get("mode", "memory")
        if mode not in out:
            continue

        best, cur, top, c = [], 1e9, [], 0
        for r in rows:
            cur = min(cur, r["delta_eta_mv"])
            best.append(cur)
            c += 1 if r.get("top10") else 0
            top.append(c)

        out[mode].append({
            "file": p.name,
            "best": best,
            "top": top,
        })
    return out


def random_curves():
    pool = T.load_pool()
    res = T.load_results()
    ids = [p["candidate_id"] for p in pool]
    bests, tops = [], []

    for seed in range(SEEDS):
        pick = random.Random(seed).sample(ids, DRAWS)
        cur, best, c, top = 1e9, [], 0, []
        for cid in pick:
            cur = min(cur, res[cid]["delta_eta_mv"])
            best.append(cur)
            c += 1 if res[cid]["top10"] else 0
            top.append(c)
        bests.append(best)
        tops.append(top)

    return bests, tops


def mean_cols(mat):
    return [sum(col) / len(col) for col in zip(*mat)]


def main():
    runs = load_runs()
    if not runs["memory"] and not runs["lit_only"]:
        raise SystemExit("没有可用的 20 轮运行记录")

    rb, rt = random_curves()
    x = list(range(1, DRAWS + 1))

    series = {
        "文献+记忆": (mean_cols([r["best"] for r in runs["memory"]]),
                    mean_cols([r["top"] for r in runs["memory"]]),
                    f"eCAT 记忆闭环（n={len(runs['memory'])}）"),
        "仅文献": (mean_cols([r["best"] for r in runs["lit_only"]]),
                 mean_cols([r["top"] for r in runs["lit_only"]]),
                 f"仅文献 Agent（n={len(runs['lit_only'])}）"),
        "随机": (mean_cols(rb), mean_cols(rt), f"随机搜索（n={SEEDS}）"),
    }

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))

    ax = axes[0]
    for name, (best, _, label) in series.items():
        style = "--" if name == "随机" else "-"
        ax.plot(x, best, style, marker="o", ms=3, lw=2, label=label)
    ax.axhline(TOP10_THRESHOLD, color="gray", ls=":", lw=1.2, label="Top 10% 门槛")
    ax.set_xlabel("实验次数")
    ax.set_ylabel("历史最佳 Δη_RC（mV，越低越好）")
    ax.set_title("历史最佳性能随实验次数的变化")
    ax.legend(frameon=False)
    ax.grid(alpha=0.25)

    ax = axes[1]
    for name, (_, top, label) in series.items():
        style = "--" if name == "随机" else "-"
        ax.plot(x, top, style, marker="o", ms=3, lw=2, label=label)
    ax.set_xlabel("实验次数")
    ax.set_ylabel("累计发现的 Top10% 候选数")
    ax.set_title("累计发现优质候选的速度")
    ax.legend(frameon=False)
    ax.grid(alpha=0.25)

    fig.tight_layout()
    out = OUT_DIR / "agent_vs_random_v5.png"
    fig.savefig(out, dpi=160)
    print("图已保存:", out)

    for name in ["文献+记忆", "仅文献"]:
        rows = runs["memory"] if name == "文献+记忆" else runs["lit_only"]
        if rows:
            print(f"{name}: n={len(rows)}")


if __name__ == "__main__":
    main()