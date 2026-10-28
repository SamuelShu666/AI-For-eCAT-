"""Literature cold start: retrieve relevant chunks, let an LLM extract grounded claims.

Each claim must quote a chunk id that exists; ungrounded claims are dropped.
Output: data/claims.json
"""
from __future__ import annotations

import json

from .literature import ELEMENT_ALIASES, LiteratureIndex
from .llm import LLM
from .space import ELEMENTS, ROOT

CLAIMS = ROOT / "data" / "claims.json"

TOPIC_QUERIES = [
    "reverse current oxidation cathode degradation hydrogen evolution",
    "reverse current tolerance HER catalyst redox potential protection",
    "alloy hydrogen adsorption free energy volcano HER activity",
    "dissolution noble metal stability shutdown alkaline electrolysis",
    "active learning closed loop autonomous experiment optimization agent",
]

PROMPT = """你是电催化文献分析员。下面是若干文献片段，每段有 chunk_id。
任务：抽取对"HER 催化剂元素/合金选择"有用的事实陈述（活性、稳定性、抗反向电流、溶解、氢吸附、协同效应、AI 闭环方法等）。
规则：
- 只依据片段原文，不得编造；每条必须给出来源 chunk_id。
- elements 只能取自 {elements}，没有涉及具体元素就留空数组。
- effect 取值：promote_activity / hurt_activity / promote_stability / hurt_stability / method / other
- text 用中文一句话概括（≤60字）。
- 至多 {k} 条，宁缺毋滥。
只输出 JSON：{{"claims":[{{"text":"...","elements":["Pd"],"effect":"promote_activity","chunk":"L0001"}}]}}

片段：
{chunks}
"""


def select_chunks(index: LiteratureIndex, per_query: int = 3) -> list[dict]:
    picked: dict[str, dict] = {}
    queries = list(TOPIC_QUERIES)
    for el in ELEMENTS:
        name = ELEMENT_ALIASES[el][0]
        queries.append(f"{name} hydrogen evolution catalyst")
        queries.append(f"{name} oxidation dissolution reverse current")
    for q in queries:
        for c in index.search(q, k=per_query):
            picked.setdefault(c["id"], c)
    return list(picked.values())


def extract(model: str = "claude-sonnet-5-5", batch: int = 8) -> list[dict]:
    index = LiteratureIndex()
    chunks = select_chunks(index)
    llm = LLM(model, tag="claims")
    claims: list[dict] = []
    for i in range(0, len(chunks), batch):
        part = chunks[i:i + batch]
        body = "\n\n".join(f"[{c['id']}] ({c['file']} p.{c['page']})\n{c['text']}" for c in part)
        data = llm.json(PROMPT.format(elements=ELEMENTS, k=6, chunks=body), max_tokens=2500)
        valid_ids = {c["id"] for c in part}
        for cl in data.get("claims", []):
            cid = cl.get("chunk")
            if cid not in valid_ids:
                continue  # ungrounded -> drop
            src = index.get(cid)
            claims.append({
                "id": f"K{len(claims):03d}",
                "text": str(cl.get("text", ""))[:120],
                "elements": [e for e in cl.get("elements", []) if e in ELEMENTS],
                "effect": cl.get("effect", "other"),
                "source": {"chunk": cid, "file": src["file"], "page": src["page"],
                           "quote": src["text"][:280]},
            })
        print(f"claims: batch {i // batch + 1}/{(len(chunks) + batch - 1) // batch} -> {len(claims)}")
    CLAIMS.parent.mkdir(exist_ok=True)
    CLAIMS.write_text(json.dumps(claims, ensure_ascii=False, indent=1), encoding="utf-8")
    return claims


def load_claims() -> list[dict]:
    return json.loads(CLAIMS.read_text(encoding="utf-8")) if CLAIMS.exists() else []


if __name__ == "__main__":
    extract()
