# -*- coding: utf-8 -*-
"""随机基线：20 次实验 × 20 个种子，含 Top10% 找到数"""
import random
import statistics

import agent_tools as T

pool = T.load_pool()
results = T.load_results()
ids = [p["candidate_id"] for p in pool]


def one_run(seed, draws=20):
    rng = random.Random(seed)
    pick = rng.sample(ids, draws)
    etas = [results[i]["delta_eta_mv"] for i in pick]
    ranks = [results[i]["rank"] for i in pick]
    top10 = sum(1 for cid in pick if results[cid]["top10"])
    hit = next((k + 1 for k, cid in enumerate(pick) if results[cid]["top10"]), None)
    return hit, min(etas), min(ranks), top10


def main():
    hits, best_etas, best_ranks, top10_counts = [], [], [], []
    for seed in range(20):
        hit, eta, rank, n10 = one_run(seed, draws=20)
        hits.append(hit)
        best_etas.append(eta)
        best_ranks.append(rank)
        top10_counts.append(n10)

    got = [h for h in hits if h]
    print("随机基线（20 次实验 × 20 个种子）")
    print("  命中 Top10% 的种子比例:", f"{len(got)}/20")
    if got:
        print("  首次命中平均轮次:", round(statistics.mean(got), 1))
    print("  最佳 Δη 均值:", round(statistics.mean(best_etas), 1), "mV")
    print("  最佳排名均值:", round(statistics.mean(best_ranks), 1))
    print("  最佳排名中位数:", statistics.median(best_ranks))
    print("  找到 Top10% 数量均值:", round(statistics.mean(top10_counts), 2))
    print("  找到 Top10% 数量最大:", max(top10_counts))


if __name__ == "__main__":
    main()