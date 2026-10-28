"""Evaluation: reads ground truth (evaluation side only) and scores saved runs.

Metrics
  best_curve        : best-so-far voltage after each experiment
  hit_top10_at      : experiments needed to first hit the top-10% set (None = never)
  top10_found       : how many top-10% candidates were found within budget
  final_rank        : global rank of the best candidate found (1 = global optimum)
  direction_acc     : share of exploit picks better than the median of the space
  traceability      : share of decisions citing literature or prior experiments
"""
from __future__ import annotations

import json
from statistics import mean, median

from .agent import RUNS
from .oracle import Evaluator
from .space import ROOT

SUMMARY = ROOT / "data" / "summary.json"


def score_run(run: dict, ev: Evaluator) -> dict:
    curve, best = [], None
    hit_at = None
    for i, x in enumerate(run["log"], 1):
        v = ev.truth[x["cid"]]
        best = v if best is None else min(best, v)
        curve.append(round(best, 4))
        if hit_at is None and v <= ev.top_threshold:
            hit_at = i
    found = [x["cid"] for x in run["log"] if ev.truth[x["cid"]] <= ev.top_threshold]
    med = median(ev.truth.values())
    exploit = [p["id"] for r in run["trace"] for p in r["picks"] if p.get("role") == "exploit"]
    best_id = min(run["log"], key=lambda x: ev.truth[x["cid"]])["cid"]
    return {"policy": run["policy"], "seed": run["seed"], "curve": curve,
            "hit_top10_at": hit_at, "top10_found": len(found),
            "final_best": curve[-1], "final_rank": ev.rank[best_id],
            "direction_acc": round(mean(ev.truth[c] < med for c in exploit), 3) if exploit else None,
            "traceability": run.get("traceability", 0.0)}


def summarize() -> dict:
    ev = Evaluator()
    by_policy: dict[str, list] = {}
    for f in sorted(RUNS.glob("*.json")):
        run = json.loads(f.read_text(encoding="utf-8"))
        by_policy.setdefault(run["policy"], []).append(score_run(run, ev))
    out = {"space": {"n": len(ev.truth), "top_k": ev.top_k,
                     "top_threshold": round(ev.top_threshold, 4),
                     "global_best": round(ev.global_best, 4)}, "policies": {}}
    for pol, rows in by_policy.items():
        n = len(rows[0]["curve"])
        hits = [r["hit_top10_at"] for r in rows]
        out["policies"][pol] = {
            "runs": len(rows),
            "mean_curve": [round(mean(r["curve"][i] for r in rows), 4) for i in range(n)],
            "hit_rate": round(mean(h is not None for h in hits), 3),
            "mean_hit_at": round(mean(h if h is not None else n + 1 for h in hits), 2),
            "mean_top10_found": round(mean(r["top10_found"] for r in rows), 2),
            "mean_final_best": round(mean(r["final_best"] for r in rows), 4),
            "mean_final_rank": round(mean(r["final_rank"] for r in rows), 2),
            "direction_acc": (round(mean(r["direction_acc"] for r in rows if r["direction_acc"] is not None), 3)
                              if any(r["direction_acc"] is not None for r in rows) else None),
            "traceability": round(mean(r["traceability"] for r in rows), 3),
            "runs_detail": rows,
        }
    SUMMARY.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    s = summarize()
    print(json.dumps(s["space"], ensure_ascii=False))
    for pol, v in s["policies"].items():
        print(f"{pol:12s} runs={v['runs']} hit={v['hit_rate']} hit_at={v['mean_hit_at']} "
              f"top10={v['mean_top10_found']} best={v['mean_final_best']} rank={v['mean_final_rank']} "
              f"dir={v['direction_acc']} trace={v['traceability']}")
