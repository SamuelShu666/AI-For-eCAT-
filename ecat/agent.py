"""Closed-loop agent as an explicit node graph.

Nodes (same names in the web demo):
  retrieve -> design -> validate -> execute -> diagnose -> memorize -> (next round)

Policies plug into `design`:
  random      : uniform random picks (baseline, no LLM)
  greedy_stat : element-statistics greedy on the memory graph (offline baseline, no LLM)
  lit_only    : LLM sees literature claims only, never sees voltages
  memory      : LLM sees literature + experiment sub-graph + decision trail (full system)

Result isolation: policies only receive masked Candidate objects and the
MemoryGraph; ground truth lives inside HiddenOracle.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

from .claims import load_claims
from .memory import MemoryGraph, traceability
from .oracle import HiddenOracle
from .space import ELEMENTS, ROOT, Candidate, load_candidates

RUNS = ROOT / "data" / "runs"
NODES = ["retrieve", "design", "validate", "execute", "diagnose", "memorize"]

DESIGN_PROMPT = """你是 HER（析氢反应）催化剂研发 Agent，在固定运行条件下寻找槽电压最低的组分（槽电压是 HER 综合性能代理指标，越低越好）。
你只能从下方候选库中挑选，每个候选只能测一次。本轮需要挑选 {n} 个。总预算 {budget} 次，已用 {used} 次，当前第 {rnd} 轮。

## 文献证据（可引用 K 编号）
{claims}

## 科研记忆
{memory}

## 候选库（id 组分；已测过的已移除）
{space}

## 要求
1. 若存在上一轮假设，先给出判定 previous_verdict: supported / refuted / inconclusive，并用一句话说明依据。
2. 提出本轮一个可被实验检验的假设 hypothesis（≤50字）。
3. 选出 {n} 个候选，兼顾“利用”（靠近当前最优）与“探索”（验证假设或填补空白）。每个给出 reason（≤40字）、evidence（引用 K 编号或已测候选 id，至少 1 个）、predicted（预测电压，V）、role（exploit / explore）。
只输出 JSON：
{{"previous_verdict":"supported","verdict_note":"...","hypothesis":"...","picks":[{{"id":"C017","reason":"...","evidence":["K003","C120"],"predicted":2.45,"role":"exploit"}}]}}
"""


def claims_text(claims: list[dict], limit: int = 40) -> str:
    if not claims:
        return "（暂无文献证据）"
    return "\n".join(f"{c['id']} [{','.join(c['elements']) or '-'}|{c['effect']}] {c['text']}"
                     for c in claims[:limit])


# ---------------------------------------------------------------- policies
class RandomPolicy:
    name = "random"

    def __init__(self, seed: int):
        self.rng = random.Random(seed)

    def design(self, ctx) -> dict:
        picks = self.rng.sample(ctx["available"], min(ctx["n"], len(ctx["available"])))
        return {"hypothesis": "随机采样", "picks": [
            {"id": c.cid, "reason": "随机", "evidence": [], "role": "explore"} for c in picks]}


class GreedyStatPolicy:
    """Offline memory baseline: score = fraction-weighted mean voltage of known elements."""
    name = "greedy_stat"

    def __init__(self, seed: int):
        self.rng = random.Random(seed)

    def design(self, ctx) -> dict:
        stats, avail, n = ctx["memory"].element_stats(), ctx["available"], ctx["n"]
        if not stats:
            picks = self.rng.sample(avail, n)
            return {"hypothesis": "冷启动：随机覆盖", "picks": [
                {"id": c.cid, "reason": "冷启动覆盖", "evidence": [], "role": "explore"} for c in picks]}
        prior = max(s["weighted_mean"] for s in stats.values())

        def score(c: Candidate):
            return sum(f * stats.get(e, {"weighted_mean": prior})["weighted_mean"] for e, f in c.fractions)

        ranked = sorted(avail, key=score)
        n_explore = max(1, n // 5)
        exploit = ranked[:n - n_explore]
        unseen = [c for c in avail if any(e not in stats for e in c.elements) and c not in exploit]
        explore = self.rng.sample(unseen or ranked[n:], min(n_explore, len(unseen or ranked[n:])))
        best = ctx["memory"].experiments()[0]["id"]
        return {"hypothesis": "低电压元素的组合更优", "picks":
                [{"id": c.cid, "reason": "元素统计得分低", "evidence": [best], "role": "exploit",
                  "predicted": round(score(c), 3)} for c in exploit] +
                [{"id": c.cid, "reason": "含未测元素", "evidence": [], "role": "explore"} for c in explore]}


class LLMPolicy:
    def __init__(self, seed: int, model: str, use_memory: bool):
        from .llm import LLM
        self.name = "memory" if use_memory else "lit_only"
        self.use_memory = use_memory
        self.seed = seed
        self.llm = LLM(model, tag=f"{self.name}-s{seed}")

    def design(self, ctx) -> dict:
        rng = random.Random(self.seed * 1000 + ctx["round"])
        avail = list(ctx["available"])
        rng.shuffle(avail)  # seed changes ordering -> independent replicates
        if self.use_memory:
            memory = ctx["memory"].summary_text()
        else:
            memory = f"（本对照组不提供实验结果）已测 {ctx['used']} 个，id: " + \
                     ", ".join(x["id"] for x in ctx["memory"].experiments())
        prompt = DESIGN_PROMPT.format(
            n=ctx["n"], budget=ctx["budget"], used=ctx["used"], rnd=ctx["round"],
            claims=claims_text(ctx["claims"]), memory=memory,
            space="\n".join(f"{c.cid} {c.composition}" for c in avail))
        return self.llm.json(prompt, max_tokens=2500)


def make_policy(name: str, seed: int, model: str = "claude-sonnet-5-5"):
    if name == "random":
        return RandomPolicy(seed)
    if name == "greedy_stat":
        return GreedyStatPolicy(seed)
    if name in ("memory", "lit_only"):
        return LLMPolicy(seed, model, use_memory=(name == "memory"))
    raise ValueError(name)


# ---------------------------------------------------------------- loop
def validate(proposal: dict, available: list[Candidate], n: int, rng: random.Random) -> list[dict]:
    """Rule check: id must exist, be untested, no duplicates. Shortfall is filled and flagged."""
    by_id = {c.cid: c for c in available}
    picks, seen = [], set()
    for p in proposal.get("picks", []):
        cid = str(p.get("id", "")).strip()
        if cid in by_id and cid not in seen:
            seen.add(cid)
            picks.append({**p, "id": cid, "composition": by_id[cid].composition, "rule": "ok"})
        else:
            picks.append({"id": cid, "rule": "rejected"})
    ok = [p for p in picks if p["rule"] == "ok"][:n]
    rejected = [p for p in picks if p["rule"] == "rejected"]
    for c in rng.sample([c for c in available if c.cid not in seen], max(0, n - len(ok))):
        ok.append({"id": c.cid, "composition": c.composition, "reason": "规则补位",
                   "evidence": [], "role": "explore", "rule": "filled"})
    return ok, rejected


def run(policy_name: str, seed: int, *, rounds: int = 8, per_round: int = 5,
        model: str = "claude-sonnet-5-5", save: bool = True, verbose: bool = True) -> dict:
    candidates = load_candidates()
    claims = load_claims() if policy_name in ("memory", "lit_only") else []
    oracle = HiddenOracle(budget=rounds * per_round)
    memory = MemoryGraph()
    for c in claims:
        memory.add_claim(c)
    policy = make_policy(policy_name, seed, model)
    rng = random.Random(seed)
    trace = []
    best = None
    for rnd in range(1, rounds + 1):
        t0 = time.time()
        tested = {x["cid"] for x in oracle.log}
        available = [c for c in candidates if c.cid not in tested]
        ctx = {"round": rnd, "n": per_round, "budget": oracle.budget, "used": oracle.used,
               "available": available, "memory": memory, "claims": claims}
        # retrieve + design
        proposal = policy.design(ctx)
        # diagnose previous hypothesis (LLM policies return a verdict for round-1)
        if rnd > 1 and proposal.get("previous_verdict"):
            memory.close_hypothesis(rnd - 1, proposal["previous_verdict"], proposal.get("verdict_note", ""))
            trace[-1]["verdict"] = proposal["previous_verdict"]
            trace[-1]["verdict_note"] = proposal.get("verdict_note", "")
        # validate
        picks, rejected = validate(proposal, available, per_round, rng)
        # memorize decisions, then execute through the black box
        # keep only evidence that really exists: claim K-ids or already-tested experiments
        for p in picks:
            refs = []
            for e in p.get("evidence", []) or []:
                e = str(e).strip().removeprefix("X:")
                if e.startswith("K") and e in memory.nodes:
                    refs.append(e)
                elif "X:" + e in memory.nodes:
                    refs.append("X:" + e)
            p["evidence"] = refs
        memory.add_round(rnd, proposal.get("hypothesis", ""), picks)
        by_id = {c.cid: c for c in candidates}
        for p in picks:
            p["voltage"] = oracle.run(p["id"])
            memory.add_experiment(rnd, by_id[p["id"]].to_public(), p["voltage"])
        round_best = min(picks, key=lambda p: p["voltage"])
        if best is None or round_best["voltage"] < best["voltage"]:
            best = {"id": round_best["id"], "composition": round_best["composition"],
                    "voltage": round_best["voltage"], "round": rnd}
        trace.append({"round": rnd, "hypothesis": proposal.get("hypothesis", ""),
                      "picks": picks, "rejected": rejected, "best_so_far": dict(best),
                      "seconds": round(time.time() - t0, 1)})
        if verbose:
            print(f"[{policy_name} s{seed}] R{rnd} best={best['voltage']:.3f} "
                  f"({best['composition']}) picks={[p['id'] for p in picks]}")
    result = {"policy": policy_name, "seed": seed, "model": model if claims else None,
              "rounds": rounds, "per_round": per_round, "trace": trace,
              "log": [{"cid": x["cid"], "voltage": x["voltage"]} for x in oracle.log],
              "traceability": traceability(memory), "graph": memory.to_json()}
    if save:
        RUNS.mkdir(parents=True, exist_ok=True)
        (RUNS / f"{policy_name}_s{seed}.json").write_text(
            json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result
