"""Export the Ni-RC v2 runs, literature chunks and evidence graph for demo_v2.

The legacy 212-candidate demo is deliberately untouched.  This exporter reads
member A's real JSONL runs, the v2 workbook and the shared PDF library, then
writes a self-contained static page dataset.  Original vector-store rankings
were not delivered, so retrieval shown here is explicitly marked as offline
TF-IDF + BM25 + RRF replay.  Original run citations remain separate.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import load_workbook

from . import literature
from .rag import OfflineHybridRetriever
from .space import ROOT

DATA = ROOT / "Ni_RC_180_candidate_dataset_v2.xlsx"
MEMBER_A = ROOT / "成员A" / "ecat_agent_v1"
RUN_DIR = MEMBER_A / "runs"
OUT_DIR = ROOT / "data" / "v2"
OUT = ROOT / "demo_v2" / "data.js"
FEATURED = "run_20261027_112146"
ELEMENTS = ["Ni", "Al", "Au", "Co", "Cr", "Cu", "Fe", "Ir", "Mg", "Mn", "Mo", "Pd", "Pt", "Rh", "Ru", "W", "Zn"]
META = {"候选ID", "Ni组合方案", "组合元素"}
METRIC_COL = "输出指标改为过电位增量Δη_RC (mV)"

# Member A's constraints pin these IDs to papers; keep them stable.
KNOWN_PAPERS = [
    ("P01", "反向电流机理+保护策略/1-s2.0-S0378775322004633-main.pdf"),
    ("P02", "反向电流机理+保护策略/s12678-017-0423-5.pdf"),
    ("P03", "反向电流机理+保护策略/Small Methods - 2025 - Peng - Strategies and Countermeasures Against Reverse Current for Enhanced Durability in Water.pdf"),
    ("P04", "反向电流机理+保护策略/86_17-00102.pdf"),
    ("P05", "反向电流机理+保护策略/Advanced Energy Materials - 2025 - Wang - Reverse‐Current Induced Cascade Degradation in Ni Ru Electrodes  Tracing the Path.pdf"),
    ("P06", "反向电流机理+保护策略/Adv Funct Materials - 2024 - Jung - Reverse‐Current Tolerance for Hydrogen Evolution Reaction Activity of Lead‐Decorated.pdf"),
    ("P07", "反向电流机理+保护策略/Advanced Energy Materials - 2025 - Wang - Probing Electrode Transformation under Dynamic Operation for Alkaline Water.pdf"),
    ("P08", "反向电流机理+保护策略/cathodic-protection-system-against-a-reverse-current-after-shut-down-in-zero-gap-alkaline-water-electrolysis.pdf"),
]
SHORT_TITLES = {
    "P01": "停机反向电流的起源与工况影响",
    "P02": "碱性电解槽停机后的反向电流",
    "P03": "反向电流防护策略综述",
    "P04": "碱性电解槽反向电流测量",
    "P05": "Ni-Ru 电极反向电流级联退化",
    "P06": "Pb/Ni 的反向电流耐受机制",
    "P07": "动态工况下碱性电解槽电极转变",
    "P08": "零间隙碱性电解槽阴极保护",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_dataset() -> tuple[list[dict], dict, list[dict]]:
    wb = load_workbook(DATA, read_only=True, data_only=True)
    masked = wb["掩盖结果"]
    header = [c.value for c in next(masked.iter_rows(min_row=1, max_row=1))]
    elements = [h for h in header if h and h not in META]
    candidates = []
    for row in masked.iter_rows(min_row=2, values_only=True):
        d = dict(zip(header, row))
        if not d.get("候选ID"):
            continue
        fractions = {e: float(d.get(e) or 0) for e in elements}
        candidates.append({
            "id": d["候选ID"], "composition": d["Ni组合方案"],
            "system": d["组合元素"], "fractions": fractions,
            "elements": [e for e in elements if fractions[e] > 0],
        })

    full = wb["完整数据"]
    fh = [c.value for c in next(full.iter_rows(min_row=1, max_row=1))]
    truth = {}
    for row in full.iter_rows(min_row=2, values_only=True):
        d = dict(zip(fh, row))
        if not d.get("候选ID"):
            continue
        truth[d["候选ID"]] = {
            "value": float(d[METRIC_COL]), "rank": int(d["全局排名"]),
            "top10": d["Top 10%"] == "是", "composition": d["Ni组合方案"],
        }

    conditions = []
    for row in wb["测试条件"].iter_rows(min_row=2, values_only=True):
        if row[0]:
            conditions.append({"name": str(row[0]), "value": str(row[1] or "")})
    wb.close()

    assert len(candidates) == 180, f"expected 180 candidates, got {len(candidates)}"
    assert len({c["id"] for c in candidates}) == 180, "duplicate candidate IDs"
    assert set(truth) == {c["id"] for c in candidates}, "masked/full ID mismatch"
    assert all(c["composition"] == truth[c["id"]]["composition"] for c in candidates)
    sums = [sum(c["fractions"].values()) for c in candidates]
    assert max(abs(v - 1) for v in sums) < 1e-6, "element fractions do not sum to 1"
    return candidates, truth, conditions


def build_literature() -> tuple[list[dict], dict[str, str], list[dict]]:
    """Rebuild all 21 PDFs into a versioned cache without touching legacy data."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    old_cache = literature.CACHE
    literature.CACHE = OUT_DIR / "lit_chunks.json"
    try:
        chunks = literature.build_chunks()
    finally:
        literature.CACHE = old_cache
    files = sorted({c["file"] for c in chunks})
    paper_ids = dict(KNOWN_PAPERS)
    assert all(f in files for _, f in KNOWN_PAPERS), "a pinned paper is missing"
    next_id = 9
    for f in files:
        if f not in paper_ids.values():
            paper_ids[f"P{next_id:02d}"] = f
            next_id += 1
    file_to_pid = {f: p for p, f in paper_ids.items()}
    for c in chunks:
        c["paper_id"] = file_to_pid[c["file"]]
        c["source_file"] = Path(c["file"]).name
    papers = []
    for pid, f in sorted(paper_ids.items()):
        basename = Path(f).stem
        year = re.search(r"(?:19|20)\d{2}", basename)
        papers.append({
            "id": pid, "file": f, "source_file": Path(f).name,
            "title": SHORT_TITLES.get(pid, basename), "topic": Path(f).parent.name,
            "year": int(year.group()) if year else None,
            "chunks": sum(c["file"] == f for c in chunks),
            "is_new": Path(f).parent.name == "new",
        })
    return chunks, paper_ids, papers


def evidence_library(chunks: list[dict], paper_ids: dict[str, str], ids: set[str]) -> dict:
    by_file_page: dict[tuple[str, int], list[dict]] = {}
    for c in chunks:
        by_file_page.setdefault((c["file"], c["page"]), []).append(c)
    out = {}
    for eid in sorted(ids):
        m = re.fullmatch(r"(P\d{2})_p(\d+)_(\d+)", eid)
        if not m or m.group(1) not in paper_ids:
            out[eid] = {"id": eid, "resolved": False, "note": "未找到论文映射"}
            continue
        pid, page = m.group(1), int(m.group(2))
        file = paper_ids[pid]
        page_chunks = by_file_page.get((file, page), [])
        out[eid] = {
            "id": eid, "resolved": bool(page_chunks), "paper_id": pid,
            "file": file, "source_file": Path(file).name, "page": page,
            "title": SHORT_TITLES.get(pid, Path(file).stem),
            "chunk_ids": [c["id"] for c in page_chunks],
            "note": "原始 Chroma chunk 未随交付；此处保留原编号，并提供同 PDF 同页的新解析 chunk。",
        }
    return out


def query_for_round(entries: list[dict], index: int) -> str:
    if index == 0:
        return "Ni-based alloy catalyst hydrogen evolution reaction in alkaline electrolyte"
    best = min(entries[:index], key=lambda x: x["delta_eta_mv"])
    elems = re.findall(r"[A-Z][a-z]?", best["composition"])
    elems = [e for e in dict.fromkeys(elems) if e != "Ni"]
    return f"Ni {' '.join(elems[:3])} alloy hydrogen evolution alkaline"


def next_change(entries: list[dict], i: int, by_id: dict[str, dict]) -> dict:
    if i + 1 >= len(entries):
        return {"type": "stop", "text": "预算已用完：保留最佳记录，停止新增实验", "added": [], "removed": [], "shared": []}
    cur = set(by_id[entries[i]["candidate_id"]]["elements"])
    nxt = set(by_id[entries[i + 1]["candidate_id"]]["elements"])
    added, removed, shared = sorted(nxt - cur), sorted(cur - nxt), sorted(cur & nxt)
    if cur == nxt:
        kind, text = "refine", "同体系调整元素比例"
    elif shared:
        kind, text = "partial", f"保留 {'/'.join(shared)}，调整伴生元素"
    else:
        kind, text = "switch", "切换至新的元素体系"
    return {"type": kind, "text": text, "added": added, "removed": removed, "shared": shared}


def diagnosis(entries: list[dict], i: int) -> tuple[str, str, float | None]:
    cur = entries[i]["delta_eta_mv"]
    if i == 0:
        return "baseline", f"首轮基准：Δη={cur:.1f} mV。下一轮在该体系内细化比例。", None
    prev_best = min(x["delta_eta_mv"] for x in entries[:i])
    delta = prev_best - cur
    if cur < prev_best:
        return "new_best", f"改善：Δη 从 {prev_best:.1f} 降到 {cur:.1f} mV。继续在该体系内细化。", delta
    return "no_improve", f"未改善：Δη={cur:.1f} mV，差于最佳 {prev_best:.1f} mV。下一轮换元素体系，不在同一组元素上微调。", delta


def build_graph(entries: list[dict], by_id: dict[str, dict], evidence: dict) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    edge_keys = set()

    def add(nid: str, label: str, subgraph: str, round_no: int, **props):
        if nid not in nodes:
            nodes[nid] = {"id": nid, "label": label, "subgraph": subgraph, "round": round_no, **props}
        return nodes[nid]

    def link(src: str, dst: str, rel: str, round_no: int, derived: bool = False):
        key = (src, dst, rel)
        if key not in edge_keys:
            edge_keys.add(key)
            edges.append({"src": src, "dst": dst, "rel": rel, "round": round_no, "derived": derived})

    first_citation: dict[str, int] = {}
    for e in entries:
        for eid in e["evidence_chunk_ids"]:
            first_citation.setdefault(eid, e["round"])

    for eid, r in first_citation.items():
        ev = evidence[eid]
        if not ev.get("resolved"):
            continue
        pid = ev["paper_id"]
        add(f"Paper:{pid}", "Paper", "literature", r, title=ev["title"], file=ev["file"], paper_id=pid)
        add(f"Evidence:{eid}", "Evidence", "literature", r, evidence_id=eid,
            title=ev["title"], file=ev["file"], page=ev["page"])
        link(f"Paper:{pid}", f"Evidence:{eid}", "CONTAINS", r)

    best_round = None
    for i, e in enumerate(entries):
        r = e["round"]
        cand = by_id[e["candidate_id"]]
        round_id, dec_id = f"Round:{r}", f"Decision:{r}"
        mat_id, exp_id = f"Material:{e['candidate_id']}", f"Experiment:{r}"
        res_id, dia_id, sug_id = f"Result:{r}", f"Diagnosis:{r}", f"Suggestion:{r}"
        add(round_id, "Round", "decision", r, round=r)
        add(dec_id, "Decision", "decision", r, candidate_id=e["candidate_id"], reason=e["reason"], round=r)
        add(mat_id, "Material", "experiment", r, candidate_id=e["candidate_id"],
            composition=e["composition"], fractions=cand["fractions"])
        add(exp_id, "Experiment", "experiment", r, candidate_id=e["candidate_id"],
            composition=e["composition"], value=e["delta_eta_mv"], round=r)
        add(res_id, "Result", "experiment", r, value=e["delta_eta_mv"], rank=e["rank"], top10=e["top10"], round=r)
        feedback, diag, delta = diagnosis(entries, i)
        add(dia_id, "Diagnosis", "decision", r, text=diag, feedback=feedback, delta=delta, round=r)
        change = next_change(entries, i, by_id)
        add(sug_id, "Suggestion", "decision", r, text=change["text"], change=change, round=r)
        if r == 1:
            add("Condition:NiRC", "Condition", "experiment", 1,
                text="1 M KOH · 10 mA cm⁻² · 反向电流 +0.1 mA cm⁻² 30 min")
        link(round_id, dec_id, "HAS_DECISION", r)
        link(dec_id, mat_id, "SELECTS", r)
        link(dec_id, exp_id, "EXECUTED_AS", r)
        link(exp_id, mat_id, "TESTS", r)
        link(exp_id, "Condition:NiRC", "UNDER", r)
        link(exp_id, res_id, "PRODUCES", r)
        link(res_id, dia_id, "DIAGNOSED_BY", r)
        link(dia_id, sug_id, "GENERATES", r)
        if r > 1:
            link(f"Round:{r-1}", round_id, "FOLLOWS", r)
            link(sug_id, f"Decision:{r+1}", "GUIDES", r + 1) if i + 1 < len(entries) else None
        if best_round is not None:
            link(dec_id, f"Experiment:{best_round}", "REFERENCES_EXPERIMENT", r, derived=True)
            link(dia_id, f"Result:{best_round}", "COMPARED_TO", r, derived=True)
        for eid in e["evidence_chunk_ids"]:
            if evidence[eid].get("resolved"):
                link(dec_id, f"Evidence:{eid}", "REFERENCES_EVIDENCE", r)
        for symbol, ratio in cand["fractions"].items():
            if ratio <= 0:
                continue
            el_id = f"Element:{symbol}"
            add(el_id, "Element", "shared", r, symbol=symbol)
            link(mat_id, el_id, "CONTAINS", r)
            nodes[el_id]["round"] = min(nodes[el_id]["round"], r)
        if best_round is None or e["delta_eta_mv"] < entries[best_round - 1]["delta_eta_mv"]:
            best_round = r

    # Evidence-to-element links use only symbols explicitly present on the page.
    element_pattern = re.compile(r"\b(" + "|".join(ELEMENTS) + r")\b")
    for eid, r in first_citation.items():
        ev = evidence[eid]
        if not ev.get("resolved"):
            continue
        page_text = " ".join(c["text"] for c in chunks_global if c["id"] in ev["chunk_ids"])
        for symbol in sorted(set(element_pattern.findall(page_text))):
            add(f"Element:{symbol}", "Element", "shared", r, symbol=symbol)
            nodes[f"Element:{symbol}"]["round"] = min(nodes[f"Element:{symbol}"]["round"], r)
            link(f"Evidence:{eid}", f"Element:{symbol}", "MENTIONS", r)

    counts = dict(Counter(n["label"] for n in nodes.values()))
    return {"nodes": list(nodes.values()), "edges": edges, "counts": counts}


def normalize_run(path: Path, by_id: dict[str, dict], retriever: OfflineHybridRetriever, evidence: dict) -> dict:
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(entries) == 20, f"{path.name}: expected 20 rounds"
    assert len({e["candidate_id"] for e in entries}) == 20, f"{path.name}: duplicate experiments"
    normalized = []
    for i, e in enumerate(entries):
        cand = by_id[e["candidate_id"]]
        assert cand["composition"] == e["composition"], f"composition mismatch in {path.name} R{i+1}"
        feedback, diag, delta = diagnosis(entries, i)
        query = query_for_round(entries, i)
        retrieved = retriever.search(query, k=4)
        prev_best = min((x["delta_eta_mv"] for x in entries[:i]), default=None)
        normalized.append({
            "round": e["round"], "candidate_id": e["candidate_id"],
            "composition": e["composition"], "fractions": cand["fractions"],
            "elements": cand["elements"], "value": e["delta_eta_mv"],
            "best_so_far": e["best_so_far"], "previous_best": prev_best,
            "rank": e["rank"], "top10": e["top10"], "reason": e["reason"],
            "evidence_ids": e["evidence_chunk_ids"],
            "retrieval_ids": [c["id"] for c in retrieved], "query": query,
            "feedback": feedback, "diagnosis": diag, "delta_vs_best": delta,
            "next_change": next_change(entries, i, by_id),
            "validation": {
                "candidate_in_pool": True, "not_repeated": True,
                "has_evidence": bool(e["evidence_chunk_ids"]),
                "resolved_evidence": sum(bool(evidence[x].get("resolved")) for x in e["evidence_chunk_ids"]),
                "original_retry_log": False,
            },
        })
    graph = build_graph(entries, by_id, evidence)
    for e in normalized:
        r = e["round"]
        e["memory"] = {
            "nodes": sum(n["round"] == r for n in graph["nodes"]),
            "edges": sum(x["round"] == r for x in graph["edges"]),
            "citations": len(e["evidence_ids"]),
        }
    hit = next((e["round"] for e in entries if e["top10"]), 21)
    metrics = {
        "first_hit": hit, "top10_found": sum(bool(e["top10"]) for e in entries),
        "final_best": min(e["delta_eta_mv"] for e in entries),
        "final_rank": min(e["rank"] for e in entries),
        "traceability": sum(bool(e["evidence_chunk_ids"]) for e in entries) / len(entries),
        "curve": [e["best_so_far"] for e in entries],
        "top_curve": list(__import__("itertools").accumulate([1 if e["top10"] else 0 for e in entries])),
    }
    return {
        "id": path.stem, "file": path.name, "model": "deepseek-chat",
        "rounds": 20, "per_round": 1, "entries": normalized,
        "metrics": metrics, "graph": graph,
    }


def mean_cols(matrix: list[list[float]]) -> list[float]:
    return [sum(col) / len(col) for col in zip(*matrix)]


def build_benchmark(candidates: list[dict], truth: dict, runs: dict) -> dict:
    ids = [c["id"] for c in candidates]
    random_runs = []
    for seed in range(20):
        picks = random.Random(seed).sample(ids, 20)
        best, curve, top_curve, count = float("inf"), [], [], 0
        for cid in picks:
            best = min(best, truth[cid]["value"])
            curve.append(best)
            count += int(truth[cid]["top10"])
            top_curve.append(count)
        hit = next((i + 1 for i, cid in enumerate(picks) if truth[cid]["top10"]), 21)
        random_runs.append({
            "seed": seed, "curve": curve, "top_curve": top_curve, "first_hit": hit,
            "final_best": curve[-1], "final_rank": min(truth[c]["rank"] for c in picks),
            "top10_found": count,
        })
    agent = list(runs.values())
    agent_curves = [r["metrics"]["curve"] for r in agent]
    rand_curves = [r["curve"] for r in random_runs]
    def avg(values):
        return sum(values) / len(values)
    return {
        "agent_mean_curve": mean_cols(agent_curves),
        "random_mean_curve": mean_cols(rand_curves),
        "agent_top_curve": mean_cols([r["metrics"]["top_curve"] for r in agent]),
        "random_top_curve": mean_cols([r["top_curve"] for r in random_runs]),
        "random_p10": [sorted(col)[2] for col in zip(*rand_curves)],
        "random_p90": [sorted(col)[17] for col in zip(*rand_curves)],
        "random_runs": random_runs,
        "agent_metrics": {
            "runs": len(agent), "mean_hit_at": avg([r["metrics"]["first_hit"] for r in agent]),
            "mean_top10_found": avg([r["metrics"]["top10_found"] for r in agent]),
            "mean_final_best": avg([r["metrics"]["final_best"] for r in agent]),
            "mean_final_rank": avg([r["metrics"]["final_rank"] for r in agent]),
            "traceability": avg([r["metrics"]["traceability"] for r in agent]),
        },
        "random_metrics": {
            "runs": len(random_runs), "mean_hit_at": avg([r["first_hit"] for r in random_runs]),
            "mean_top10_found": avg([r["top10_found"] for r in random_runs]),
            "mean_final_best": avg([r["final_best"] for r in random_runs]),
            "mean_final_rank": avg([r["final_rank"] for r in random_runs]),
            "hit_rate": sum(r["first_hit"] <= 20 for r in random_runs) / len(random_runs),
        },
    }


chunks_global: list[dict] = []


def build() -> dict:
    global chunks_global
    candidates, truth, conditions = load_dataset()
    chunks, paper_ids, papers = build_literature()
    chunks_global = chunks
    by_id = {c["id"]: c for c in candidates}
    run_files = sorted(RUN_DIR.glob("run_*.jsonl"))
    raw_entries = [[json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()] for p in run_files]
    evidence_ids = {eid for entries in raw_entries for e in entries for eid in e["evidence_chunk_ids"]}
    with (MEMBER_A / "constraints.csv").open(encoding="utf-8-sig") as f:
        constraints = list(csv.DictReader(f))
    evidence_ids.update(r["evidence_chunk"] for r in constraints if r["evidence_chunk"])
    evidence = evidence_library(chunks, paper_ids, evidence_ids)
    retriever = OfflineHybridRetriever(chunks)
    runs = {p.stem: normalize_run(p, by_id, retriever, evidence) for p in run_files}
    with (MEMBER_A / "element_priors.csv").open(encoding="utf-8-sig") as f:
        priors = list(csv.DictReader(f))

    top = [t for t in truth.values() if t["top10"]]
    global_best = min(truth.values(), key=lambda t: t["value"])
    best_cid = next(cid for cid, t in truth.items() if t is global_best)
    benchmark = build_benchmark(candidates, truth, runs)
    first_two = raw_entries[:2]
    overlap = sum(a["candidate_id"] == b["candidate_id"] for a, b in zip(*first_two)) if len(first_two) >= 2 else 0
    chunk_by_id = {c["id"]: c for c in chunks}

    data = {
        "meta": {
            "title": "eCAT · Ni-RC v2", "dataset_id": "ni_rc_v2_180",
            "source_file": DATA.name, "sha256": sha256(DATA),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "legacy_note": "旧版 212 条槽电压 Demo 保留在 demo/；本页仅使用 180 条 Ni-RC v2，不与旧指标混算。",
            "evidence_note": "运行引用来自成员 A 原始 JSONL；检索结果为本页离线重放，原始 Chroma/MiniLM 向量库未随交付。",
            "rank_note": "rank/top10 在本页仅作评测展示；本适配层不把排名写入新的决策查询。",
        },
        "space": {
            "n": len(candidates), "metric": "Δη_RC", "unit": "mV", "direction": "lower",
            "top_k": len(top), "top_threshold": max(t["value"] for t in top),
            "global_best": global_best["value"],
            "global_best_candidate": {"id": best_cid, "composition": global_best["composition"]},
            "elements": ELEMENTS, "systems": len({c["system"] for c in candidates}),
            "conditions": conditions,
        },
        "candidates": candidates,
        "literature": {
            "papers": papers, "chunks": chunks, "chunk_count": len(chunks),
            "paper_count": len(papers), "new_paper_count": sum(p["is_new"] for p in papers),
            "chunk_chars": 900, "retrieval_method": retriever.method,
            "replay_note": "文献页与 chunk 为当前 PDF 的真实解析结果；每轮 top4 为离线检索重放，不等同于原始向量库排名。",
        },
        "evidence": evidence,
        "runs": runs, "featured": FEATURED if FEATURED in runs else next(iter(runs)),
        "benchmark": benchmark,
        "constraints": constraints, "priors": priors,
        "validation": {
            "candidate_count": len(candidates), "unique_ids": True,
            "fraction_sums": True, "composition_match": True,
            "run_count": len(runs), "all_runs_20_unique": True,
            "unique_citations": len(evidence_ids),
            "resolved_citations": sum(bool(e.get("resolved")) for e in evidence.values()),
            "first_two_same_position": overlap,
            "chunk_lookup_count": len(chunk_by_id),
        },
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("window.ECAT_V2 = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    (OUT_DIR / "manifest.json").write_text(json.dumps({
        "dataset": data["meta"], "space": data["space"], "validation": data["validation"],
        "featured": data["featured"], "output": str(OUT.relative_to(ROOT)),
        "restore": "旧版入口为 demo/index.html；备份位于 backups/20261027_memberB/。",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


if __name__ == "__main__":
    d = build()
    print(OUT, round(OUT.stat().st_size / 1024, 1), "KB")
    print(json.dumps({"papers": d["literature"]["paper_count"], "chunks": d["literature"]["chunk_count"],
                      "runs": len(d["runs"]), "validation": d["validation"],
                      "agent": d["benchmark"]["agent_metrics"], "random": d["benchmark"]["random_metrics"]}, ensure_ascii=False, indent=2))
