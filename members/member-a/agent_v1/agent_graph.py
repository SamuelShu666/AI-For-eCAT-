# -*- coding: utf-8 -*-
"""Ni 基 HER 催化剂筛选 · LangGraph 单 Agent 闭环 v3"""
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

import agent_tools as T
from tool_literature import literature_retrieve

load_dotenv()

RUN_DIR = Path(r"D:\her_agent_project\runs")
RUN_DIR.mkdir(exist_ok=True)

POOL = T.load_pool()
RESULTS = T.load_results()
POOL_BY_ID = {p["candidate_id"]: p for p in POOL}
CONSTRAINTS = T.constraints_text()
PRIORS = T.priors_text()

llm = ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    temperature=float(os.getenv("AGENT_TEMP", "0.2")),
)


class State(TypedDict, total=False):
    round: int
    max_rounds: int
    history: list
    best: dict | None
    literature: str
    available_evidence: list
    candidate: dict | None
    validation_error: str
    retry: int
    log_path: str
    last_diagnosis: str


def retrieve_node(state):
    r = state.get("round", 1)
    if r == 1:
        query = "Ni-based alloy catalyst hydrogen evolution reaction in alkaline electrolyte"
    else:
        best = state.get("best") or {}
        comp = best.get("composition", "")
        elems = re.findall(r"[A-Z][a-z]?", comp)
        elems = [e for e in dict.fromkeys(elems) if e not in ("Ni",)]
        query = f"Ni {' '.join(elems[:3])} alloy hydrogen evolution alkaline"

    text = literature_retrieve.invoke({"query": query})
    ids = re.findall(r"P\d{2}_p\d+_\d+", text)
    print(f"  [retrieve] {query} | 证据 {len(set(ids))} 条")
    return {"literature": text, "available_evidence": sorted(set(ids))}


def design_node(state):
    tried = {h["candidate_id"] for h in state.get("history", [])}
    untried = [p for p in POOL if p["candidate_id"] not in tried]
    pool_lines = "\n".join(f'{p["candidate_id"]} | {p["composition"]}' for p in untried)

    hist = state.get("history", [])
    if hist:
        hist_lines = "\n".join(
            f'第{h["round"]}轮 {h["candidate_id"]} {h["composition"]} '
            f'-> Δη={h["delta_eta_mv"]:.1f} mV (rank {h["rank"]})'
            for h in hist
        )
    else:
        hist_lines = "无（这是第 1 轮）"

    tested_block = ""
    if tried:
        tested_block = f"【禁止再选，这些已经测过】{', '.join(sorted(tried))}\n"

    diag = state.get("last_diagnosis", "")
    diag_block = f"\n【上一轮诊断，必须参考】{diag}\n" if diag else ""

    err = state.get("validation_error", "")
    err_block = f"\n【上次输出无效，请修正】{err}\n" if err else ""

    allowed = ", ".join(state.get("available_evidence", []))

    prompt = f"""你是碱性电解水 HER 催化剂筛选专家。
目标：在 Ni 基候选组成中，用尽量少的实验找到 Δη_RC 最低的配方。
规则：
1. 只能从"未测试候选"里选一个，输出 candidate_id
2. Δη_RC 越小越好
3. evidence_chunk_ids 只能从本轮给出的文献 chunk_id 里选：{allowed}
4. 参考元素先验：活性高、碱稳定性好的元素优先，但也要保留探索
5. 绝对不要选"禁止再选"里的 ID

【文献证据】
{state.get("literature", "")[:3000]}

【元素先验】
{PRIORS}

【硬约束】
{CONSTRAINTS}

【已测试历史】
{hist_lines}

{tested_block}{diag_block}{err_block}
【未测试候选】（候选ID | 组成）
{pool_lines}

只输出 JSON，不要任何解释，不要用 ``` 包裹：
{{"candidate_id":"Cxxx","reason":"一句话说明为什么选它","evidence_chunk_ids":["P07_p1_001"],"expected_direction":"lower_delta_eta"}}"""

    msg = llm.invoke(prompt)
    text = (msg.content or "").strip()
    text = text.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        data = json.loads(m.group(0)) if m else {}

    return {
        "candidate": {
            "candidate_id": str(data.get("candidate_id", "")).strip(),
            "reason": data.get("reason", ""),
            "evidence_chunk_ids": data.get("evidence_chunk_ids", []),
            "expected_direction": data.get("expected_direction", ""),
        }
    }


def validate_node(state):
    cand = state.get("candidate") or {}
    cid = cand.get("candidate_id", "")
    tried = {h["candidate_id"] for h in state.get("history", [])}
    allowed = set(state.get("available_evidence", []))
    ev = cand.get("evidence_chunk_ids") or []

    err = ""
    if cid not in POOL_BY_ID:
        err = f"候选 {cid!r} 不在候选池中"
    elif cid in tried:
        err = f"候选 {cid} 已经测过"
    elif not ev:
        err = "没有引用任何文献证据 chunk_id"
    else:
        bad = [e for e in ev if e not in allowed]
        if bad:
            err = f"引用了本轮未检索到的证据 {bad}"

    if err:
        retry = state.get("retry", 0) + 1
        print(f"  [validate] 不合格（第 {retry} 次）：{err}")
        if retry >= 3:
            fallback = next(p for p in POOL if p["candidate_id"] not in tried)
            print(f"  [validate] 连续失败，改用兜底候选 {fallback['candidate_id']}")
            return {
                "candidate": {**cand, "candidate_id": fallback["candidate_id"],
                              "reason": "fallback：连续校验失败"},
                "validation_error": "",
                "retry": retry,
            }
        return {"validation_error": err, "retry": retry}

    return {"validation_error": "", "retry": 0}


def route_after_validate(state):
    return "retry" if state.get("validation_error") else "ok"


def execute_node(state):
    cand = state["candidate"]
    cid = cand["candidate_id"]
    res = RESULTS[cid]
    r = state.get("round", 1)

    entry = {
        "round": r,
        "candidate_id": cid,
        "composition": POOL_BY_ID[cid]["composition"],
        "delta_eta_mv": res["delta_eta_mv"],
        "rank": res["rank"],
        "top10": res["top10"],
        "reason": cand.get("reason", ""),
        "evidence_chunk_ids": cand.get("evidence_chunk_ids", []),
    }

    history = list(state.get("history", [])) + [entry]
    best = state.get("best")
    if best is None or res["delta_eta_mv"] < best["delta_eta_mv"]:
        best = dict(entry)

    print(f"  [execute] 第{r}轮 {cid} {entry['composition'][:30]} "
          f"-> Δη={res['delta_eta_mv']:.1f} mV | rank {res['rank']}")

    with open(state["log_path"], "a", encoding="utf-8") as f:
        f.write(json.dumps({**entry, "best_so_far": best["delta_eta_mv"]},
                           ensure_ascii=False) + "\n")

    return {"round": r + 1, "history": history, "best": best}


def diagnose_node(state):
    hist = state["history"]
    cur = hist[-1]
    prev = [h["delta_eta_mv"] for h in hist[:-1]]

    if not prev:
        text = f"首轮基准：Δη={cur['delta_eta_mv']:.1f} mV。下一轮在该体系内细化比例。"
    elif cur["delta_eta_mv"] < min(prev):
        text = f"改善：Δη 从 {min(prev):.1f} 降到 {cur['delta_eta_mv']:.1f} mV。继续在该体系内细化。"
    else:
        text = (f"未改善：Δη={cur['delta_eta_mv']:.1f} mV，差于最佳 {min(prev):.1f} mV。"
                f"下一轮换元素体系，不要在同一组元素上微调。")

    print(f"  [diagnose] {text}")
    return {"last_diagnosis": text}


def route_after_diagnose(state):
    return "end" if state.get("round", 1) > state.get("max_rounds", 20) else "continue"


g = StateGraph(State)
g.add_node("retrieve", retrieve_node)
g.add_node("design", design_node)
g.add_node("validate", validate_node)
g.add_node("execute", execute_node)
g.add_node("diagnose", diagnose_node)

g.add_edge(START, "retrieve")
g.add_edge("retrieve", "design")
g.add_edge("design", "validate")
g.add_conditional_edges("validate", route_after_validate,
                        {"retry": "design", "ok": "execute"})
g.add_edge("execute", "diagnose")
g.add_conditional_edges("diagnose", route_after_diagnose,
                        {"continue": "retrieve", "end": END})

app = g.compile()


def run(max_rounds=20):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = RUN_DIR / f"run_{stamp}.jsonl"

    init = {
        "round": 1, "max_rounds": max_rounds, "history": [], "best": None,
        "literature": "", "available_evidence": [], "candidate": None,
        "validation_error": "", "retry": 0, "log_path": str(log_path),
        "last_diagnosis": "",
    }

    print(f"开始运行：{max_rounds} 轮 | 日志 {log_path}")
    out = app.invoke(init, config={"recursion_limit": 300})

    best = out.get("best") or {}
    print("\n==== 运行结束 ====")
    print("最佳候选:", best.get("candidate_id"), best.get("composition"))
    print("最佳 Δη:", best.get("delta_eta_mv"), "mV | rank", best.get("rank"))
    print("日志:", log_path)


if __name__ == "__main__":
    run(max_rounds=20)