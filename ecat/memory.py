"""Research memory: one property graph with three sub-graphs.

  literature  : Paper, Claim, Element          (what papers say)
  experiment  : Candidate, Experiment, Element (what the black box returned)
  decision    : Round, Hypothesis, Decision    (why the agent chose what it chose)

Cross-subgraph edges make every decision traceable:
  Decision -CITES-> Claim -FROM-> Paper
  Decision -SELECTS-> Candidate <-TESTS- Experiment
  Experiment -SUPPORTS/REFUTES-> Hypothesis

The graph is kept in-process (no server needed) and can be exported to
Neo4j Cypher with `to_cypher()`, or to JSON for the web demo.
"""
from __future__ import annotations

import json
from collections import defaultdict
from statistics import mean

SUBGRAPH = {
    "Paper": "literature", "Claim": "literature",
    "Candidate": "experiment", "Experiment": "experiment",
    "Round": "decision", "Hypothesis": "decision", "Decision": "decision",
    "Element": "shared",
}


class MemoryGraph:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []

    # ---------- primitives ----------
    def add_node(self, nid: str, label: str, **props) -> str:
        node = self.nodes.setdefault(nid, {"id": nid, "label": label,
                                           "subgraph": SUBGRAPH[label]})
        node.update(props)
        return nid

    def add_edge(self, src: str, rel: str, dst: str, **props) -> None:
        if src in self.nodes and dst in self.nodes:
            self.edges.append({"src": src, "rel": rel, "dst": dst, **props})

    # ---------- domain writers ----------
    def add_claim(self, claim: dict) -> None:
        """claim = {id, text, elements:[..], effect, source:{chunk, file, page} | None}"""
        src = claim.get("source")
        if src:
            pid = "P:" + src["file"]
            self.add_node(pid, "Paper", file=src["file"])
        self.add_node(claim["id"], "Claim", text=claim["text"], effect=claim.get("effect", ""),
                      grounded=bool(src), page=(src or {}).get("page"))
        if src:
            self.add_edge(claim["id"], "FROM", pid, page=src["page"], chunk=src["chunk"])
        for el in claim.get("elements", []):
            self.add_node("E:" + el, "Element", symbol=el)
            self.add_edge(claim["id"], "ABOUT", "E:" + el)

    def add_experiment(self, rnd: int, cand: dict, voltage: float) -> None:
        cid = cand["id"]
        self.add_node(cid, "Candidate", composition=cand["composition"], system=cand["system"])
        for el, frac in cand["fractions"].items():
            self.add_node("E:" + el, "Element", symbol=el)
            self.add_edge(cid, "CONTAINS", "E:" + el, fraction=frac)
        xid = f"X:{cid}"
        self.add_node(xid, "Experiment", round=rnd, voltage=voltage)
        self.add_edge(xid, "TESTS", cid)

    def add_round(self, rnd: int, hypothesis: str, decisions: list[dict]) -> None:
        r, h = f"R:{rnd}", f"H:{rnd}"
        self.add_node(r, "Round", round=rnd)
        self.add_node(h, "Hypothesis", round=rnd, text=hypothesis, status="open")
        self.add_edge(r, "PROPOSES", h)
        if rnd > 1:
            self.add_edge(f"R:{rnd - 1}", "NEXT", r)
        for d in decisions:
            did = f"D:{rnd}:{d['id']}"
            self.add_node(did, "Decision", round=rnd, reason=d.get("reason", ""),
                          predicted=d.get("predicted"))
            self.add_edge(r, "MAKES", did)
            self.add_edge(did, "TESTS_HYPOTHESIS", h)
            self.add_node(d["id"], "Candidate", composition=d.get("composition", ""))
            self.add_edge(did, "SELECTS", d["id"])
            for ev in d.get("evidence", []):
                if ev in self.nodes:
                    self.add_edge(did, "CITES", ev)

    def close_hypothesis(self, rnd: int, verdict: str, note: str) -> None:
        h = f"H:{rnd}"
        if h in self.nodes:
            self.nodes[h].update(status=verdict, note=note)
            rel = {"supported": "SUPPORTS", "refuted": "REFUTES"}.get(verdict, "INCONCLUSIVE")
            for e in self.edges:
                if e["rel"] == "MAKES" and e["src"] == f"R:{rnd}":
                    cid = next((x["dst"] for x in self.edges
                                if x["src"] == e["dst"] and x["rel"] == "SELECTS"), None)
                    if cid and f"X:{cid}" in self.nodes:
                        self.add_edge(f"X:{cid}", rel, h)

    # ---------- readers used by the agent ----------
    def experiments(self) -> list[dict]:
        out = []
        for n in self.nodes.values():
            if n["label"] == "Experiment":
                cid = n["id"][2:]
                out.append({"id": cid, "round": n["round"], "voltage": n["voltage"],
                            "composition": self.nodes[cid]["composition"]})
        return sorted(out, key=lambda x: x["voltage"])

    def element_stats(self) -> dict[str, dict]:
        """Fraction-weighted observed voltage per element (experiment sub-graph only)."""
        acc = defaultdict(list)
        volt = {n["id"][2:]: n["voltage"] for n in self.nodes.values() if n["label"] == "Experiment"}
        for e in self.edges:
            if e["rel"] == "CONTAINS" and e["src"] in volt:
                acc[e["dst"][2:]].append((volt[e["src"]], e["fraction"]))
        stats = {}
        for el, rows in acc.items():
            w = sum(f for _, f in rows)
            stats[el] = {"n": len(rows), "weighted_mean": round(sum(v * f for v, f in rows) / w, 4),
                         "best": round(min(v for v, _ in rows), 4)}
        return stats

    def hypotheses(self) -> list[dict]:
        return [n for n in self.nodes.values() if n["label"] == "Hypothesis"]

    def summary_text(self, max_rows: int = 30) -> str:
        exps = self.experiments()
        if not exps:
            return "尚无实验结果。"
        lines = [f"已测 {len(exps)} 个。按槽电压从低到高（越低越好）："]
        lines += [f"  {x['id']} {x['composition']} = {x['voltage']:.3f} V (第{x['round']}轮)"
                  for x in exps[:max_rows]]
        if len(exps) > max_rows:
            lines.append(f"  ……另有 {len(exps) - max_rows} 个更差的结果，最差 {exps[-1]['voltage']:.3f} V")
        lines.append("元素统计（含该元素候选的组分加权平均电压 / 最佳）：")
        for el, s in sorted(self.element_stats().items(), key=lambda kv: kv[1]["weighted_mean"]):
            lines.append(f"  {el}: n={s['n']} 均值={s['weighted_mean']:.3f} 最佳={s['best']:.3f}")
        for h in self.hypotheses():
            lines.append(f"假设 第{h['round']}轮 [{h['status']}]: {h['text']}"
                         + (f" -> {h.get('note', '')}" if h.get("note") else ""))
        return "\n".join(lines)

    # ---------- export ----------
    def to_json(self) -> dict:
        counts = defaultdict(int)
        for n in self.nodes.values():
            counts[n["subgraph"]] += 1
        return {"nodes": list(self.nodes.values()), "edges": self.edges, "counts": dict(counts)}

    def to_cypher(self) -> str:
        out = []
        for n in self.nodes.values():
            props = {k: v for k, v in n.items() if k != "label" and v is not None}
            out.append(f"MERGE (n:{n['label']} {{id:{json.dumps(n['id'])}}}) SET n += "
                       + json.dumps(props, ensure_ascii=False).replace('"', "'"))
        for e in self.edges:
            props = {k: v for k, v in e.items() if k not in ("src", "dst", "rel")}
            out.append(f"MATCH (a {{id:{json.dumps(e['src'])}}}),(b {{id:{json.dumps(e['dst'])}}}) "
                       f"MERGE (a)-[:{e['rel']} {json.dumps(props).replace(chr(34), '')}]->(b)")
        return ";\n".join(out) + ";\n"


def traceability(graph: MemoryGraph) -> float:
    """Share of decisions that cite at least one literature-grounded claim or prior experiment."""
    decisions = [n["id"] for n in graph.nodes.values() if n["label"] == "Decision"]
    if not decisions:
        return 0.0
    cited = {e["src"] for e in graph.edges if e["rel"] == "CITES"}
    return round(sum(d in cited for d in decisions) / len(decisions), 3)


def mean_or(xs, default=None):
    return mean(xs) if xs else default
