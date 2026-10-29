# -*- coding: utf-8 -*-
"""Import Ni-RC v2 candidates and versioned literature evidence into Neo4j.

The script intentionally separates three trust levels:
1) candidate-pool metadata (read from the result-masked sheet),
2) source literature chunks and unreviewed extracted claims, and
3) trusted experiment/decision callbacks invoked by the orchestration service.

Run from the repository root, or pass explicit paths. No result column is read
by --seed-candidates. Legacy citation IDs are namespaced aliases and are only
resolved against the matching registry; P03 alone is never a paper identity.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from neo4j import Driver, GraphDatabase

ROOT = Path(__file__).resolve().parents[2]
DATASET_VERSION = "Ni_RC_180_candidate_dataset_v2"
RESULT_COLUMN = "输出指标改为过电位增量Δη_RC (mV)"
ELEMENTS = ["Ni", "Al", "Au", "Co", "Cr", "Cu", "Fe", "Ir", "Mg", "Mn", "Mo", "Pd", "Pt", "Rh", "Ru", "W", "Zn"]
DEFAULT_XLSX = ROOT / "data" / "raw" / "Ni_RC_180_candidate_dataset_v2.xlsx"
DEFAULT_CHUNKS = ROOT / "data" / "v2" / "lit_chunks.json"
DEFAULT_CLAIMS = ROOT / "data" / "claims.json"
DEFAULT_MANIFEST = ROOT / "data" / "v2" / "manifest.json"
DEFAULT_AGENT_V5 = ROOT / "members" / "member-a" / "agent_v5"


def get_driver() -> Driver:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        raise RuntimeError("请设置 NEO4J_PASSWORD；不要使用脚本内置默认密码")
    return GraphDatabase.driver(uri, auth=(user, password))


def _number(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", " ".join(text.split()))


def _stable_key(*parts: str, prefix: str) -> str:
    payload = "\0".join(_normalized(str(part)) for part in parts)
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _paper_key(source_file: str) -> str:
    # Keep directory components: identical basenames in different folders are
    # different source documents. Normalize separators and Unicode only.
    path = unicodedata.normalize("NFC", source_file.replace("\\", "/")).strip("/")
    return _stable_key(path, prefix="PAPER_")


def seed_candidate_pool(driver: Driver, xlsx_path: Path = DEFAULT_XLSX) -> int:
    """Import only candidate identities/compositions from the masked sheet."""
    df = pd.read_excel(xlsx_path, sheet_name="掩盖结果")
    required = {"候选ID", "Ni组合方案", "组合元素", *ELEMENTS}
    missing = required - set(map(str, df.columns))
    if missing:
        raise ValueError(f"掩盖结果表缺少字段: {sorted(missing)}")
    if len(df) != 180:
        raise ValueError(f"Ni-RC v2 应有 180 条候选，实际 {len(df)}")
    ids = df["候选ID"].astype(str)
    if df["候选ID"].isna().any() or ids.duplicated().any():
        raise ValueError("候选ID 为空或重复")

    digest = hashlib.sha256(xlsx_path.read_bytes()).hexdigest()
    manifest_path = DEFAULT_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    condition_rows = manifest.get("space", {}).get("conditions", [])
    records: list[dict[str, Any]] = []
    for row_index, row in df.iterrows():
        cid = str(row["候选ID"]).strip()
        raw = str(row["Ni组合方案"]).strip()
        names = [part.strip() for part in str(row["组合元素"]).split(",") if part.strip()]
        fractions = {symbol: _number(row[symbol]) for symbol in ELEMENTS}
        fractions = {symbol: value for symbol, value in fractions.items() if value is not None and value != 0}
        if not names:
            names = list(fractions)
        if set(names) != set(fractions):
            raise ValueError(f"{cid}: 组合元素与元素分数非零列不一致")
        if len(names) != len(set(names)):
            raise ValueError(f"{cid}: 组合元素重复")
        records.append({
            "candidate_id": cid,
            "composition_raw": raw,
            "element_list": names,
            "fractions": fractions,
            "element_count": len(names),
            "material_class": "pure" if len(names) == 1 else "binary" if len(names) == 2 else "multi",
            "source_file": xlsx_path.name,
            "source_sheet": "掩盖结果",
            "source_row": int(row_index) + 2,
            "source_sha256": digest,
        })

    with driver.session() as session:
        def write(tx):
            tx.run(
                """MERGE (ds:DatasetVersion {version:$version})
                   SET ds.source_file=$file, ds.source_sha256=$sha,
                       ds.candidate_count=$count, ds.registered_at=coalesce(ds.registered_at, datetime()),
                       ds.result_visibility='masked_from_agent'""",
                version=DATASET_VERSION, file=xlsx_path.name, sha=digest, count=len(records),
            ).consume()
            for item in condition_rows:
                name, value = str(item.get("name", "")).strip(), str(item.get("value", "")).strip()
                if not name or not value:
                    continue
                condition_key = _stable_key(DATASET_VERSION, name, value, prefix="COND_")
                tx.run(
                    """MERGE (c:Condition {condition_key:$condition_key})
                       SET c.name=$name, c.value=$value, c.unit=$unit,
                           c.source_file=$source_file, c.source_field='data/v2/manifest.json:space.conditions',
                           c.dataset_version=$version, c.parse_status='copied_from_project_manifest'
                       WITH c
                       MATCH (ds:DatasetVersion {version:$version})
                       MERGE (ds)-[:USES_CONDITION]->(c)""",
                    condition_key=condition_key, name=name, value=value, unit="",
                    source_file=manifest_path.name, version=DATASET_VERSION,
                ).consume()
            for rec in records:
                tx.run(
                    """MERGE (m:Material {candidate_id:$candidate_id})
                       SET m.composition_raw=$composition_raw, m.element_list=$element_list,
                           m.element_count=$element_count, m.material_class=$material_class,
                           m.in_candidate_pool=true, m.dataset_version=$dataset_version,
                           m.source_file=$source_file, m.source_sheet=$source_sheet,
                           m.source_row=$source_row, m.source_sha256=$source_sha256
                       WITH m
                       UNWIND keys($fractions) AS symbol
                       WITH m, symbol, $fractions[symbol] AS fraction
                       MERGE (el:Element {symbol:symbol})
                       MERGE (m)-[rel:CONTAINS]->(el)
                       SET rel.fraction=fraction, rel.fraction_basis='source workbook; basis requires metadata confirmation',
                           rel.source_file=$source_file, rel.source_row=$source_row""",
                    dataset_version=DATASET_VERSION, **rec,
                ).consume()
                tx.run(
                    """MATCH (m:Material {candidate_id:$cid})
                       MATCH (ds:DatasetVersion {version:$version})
                       MERGE (ds)-[:CONTAINS_CANDIDATE]->(m)""",
                    cid=rec["candidate_id"], version=DATASET_VERSION,
                ).consume()
        session.execute_write(write)
    return len(records)


def load_literature(chunks_path: Path, claims_path: Path | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    """Read v2 parsed chunks; preserve source path/page and create stable keys."""
    raw_chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    if not isinstance(raw_chunks, list):
        raise ValueError("lit_chunks.json 必须是 JSON 数组")
    chunks: list[dict[str, Any]] = []
    papers: dict[str, dict[str, Any]] = {}
    source_ids: set[tuple[str, str]] = set()
    for item in raw_chunks:
        source_file = str(item.get("file", "")).strip()
        text = str(item.get("text", "")).strip()
        if not source_file or not text:
            continue
        paper_id = _paper_key(source_file)
        source_id = str(item.get("id", "")).strip()
        if source_id and ("demo_v2_lit_chunks", source_id) in source_ids:
            raise ValueError(f"重复的来源 chunk ID: {source_id}")
        if source_id:
            source_ids.add(("demo_v2_lit_chunks", source_id))
        page = item.get("page")
        page_num = int(page) if page is not None else None
        evidence_id = _stable_key(paper_id, str(page_num), _normalized(text), prefix="EV_")
        papers[paper_id] = {
            "paper_id": paper_id,
            "source_file": source_file,
            "title": Path(source_file).stem,
            "topic": str(item.get("topic", "")),
            "identity_scheme": "normalized_source_path_v1",
            "parse_status": "parsed_chunk_source",
        }
        chunks.append({
            "evidence_id": evidence_id,
            "paper_id": paper_id,
            "page_start": page_num,
            "page_end": page_num,
            "content": text,
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "source_chunk_id": source_id or None,
            "source_namespace": "demo_v2_lit_chunks",
            "source_file": source_file,
            "chunk_version": "data_v2_lit_chunks",
        })

    claims: list[dict[str, Any]] = []
    if claims_path and claims_path.exists():
        raw_claims = json.loads(claims_path.read_text(encoding="utf-8"))
        for item in raw_claims:
            source = item.get("source") or {}
            source_chunk = str(source.get("chunk", "")).strip()
            source_file = str(source.get("file", "")).strip()
            source_evidence = next((
                c["evidence_id"] for c in chunks
                if c["source_chunk_id"] == source_chunk and c["source_file"] == source_file
            ), None)
            if not source_evidence:
                raise ValueError(f"Claim {item.get('id')} 引用的来源块未找到: {source_chunk} / {source_file}")
            claims.append({
                "claim_id": str(item["id"]),
                "claim_text": str(item.get("text", "")),
                "effect": str(item.get("effect", "")),
                "elements": [str(x) for x in item.get("elements", [])],
                "review_status": "pending_human_review",
                "source_evidence_id": source_evidence,
                "source_quote": str(source.get("quote", "")),
            })
    return list(papers.values()), chunks, claims


def import_literature(driver: Driver, chunks_path: Path = DEFAULT_CHUNKS, claims_path: Path | None = DEFAULT_CLAIMS) -> tuple[int, int]:
    papers, chunks, claims = load_literature(chunks_path, claims_path)
    with driver.session() as session:
        def write(tx):
            for paper in papers:
                tx.run(
                    """MERGE (p:Paper {paper_id:$paper_id})
                       SET p.source_file=$source_file, p.title=coalesce(p.title,$title),
                           p.topic=$topic, p.identity_scheme=$identity_scheme,
                           p.parse_status=$parse_status, p.updated_at=datetime()""",
                    **paper,
                ).consume()
            for chunk in chunks:
                tx.run(
                    """MATCH (p:Paper {paper_id:$paper_id})
                       MERGE (e:Evidence {evidence_id:$evidence_id})
                       SET e.page_start=$page_start, e.page_end=$page_end, e.content=$content,
                           e.content_sha256=$content_sha256, e.source_file=$source_file,
                           e.chunk_version=$chunk_version, e.evidence_kind='verbatim_source_chunk',
                           e.updated_at=datetime()
                       MERGE (p)-[:CONTAINS]->(e)
                       WITH e
                       MERGE (a:EvidenceAlias {alias_key:$alias_key})
                       SET a.namespace=$source_namespace, a.source_id=$source_chunk_id,
                           a.source_file=$source_file, a.page_num=$page_start,
                           a.mapping_status='exact_source_chunk'
                       MERGE (a)-[:RESOLVES_TO]->(e)""",
                    alias_key=_stable_key("demo_v2_lit_chunks", chunk["source_chunk_id"] or chunk["evidence_id"], prefix="ALIAS_"),
                    **chunk,
                ).consume()
            for claim in claims:
                tx.run(
                    """MATCH (e:Evidence {evidence_id:$source_evidence_id})
                       MERGE (c:Claim {claim_id:$claim_id})
                       SET c.text=$claim_text, c.effect=$effect, c.elements=$elements,
                           c.review_status=$review_status, c.source_quote=$source_quote,
                           c.updated_at=datetime()
                       MERGE (c)-[:GROUNDED_IN]->(e)""",
                    **claim,
                ).consume()
        session.execute_write(write)
    return len(papers), len(chunks)


def import_agent_v5_aliases(
    driver: Driver, agent_dir: Path = DEFAULT_AGENT_V5,
    chunks_source_path: Path = DEFAULT_CHUNKS,
) -> int:
    """Import source chunks and Pxx_pN_nnn aliases from the exact v5 registry."""
    registry_path = agent_dir / "paper_registry.csv"
    chunks_path = agent_dir / "her_chunks_v5.csv"
    if not registry_path.exists() or not chunks_path.exists():
        raise FileNotFoundError(f"需要同时提供 {registry_path.name} 和 {chunks_path.name}")
    with registry_path.open(encoding="utf-8-sig", newline="") as f:
        registry = {row["paper_id"]: row["source_file"] for row in csv.DictReader(f)}
    known_sources: dict[str, list[str]] = {}
    if chunks_source_path.exists():
        for item in json.loads(chunks_source_path.read_text(encoding="utf-8")):
            source = str(item.get("file", ""))
            if source:
                known_sources.setdefault(Path(source).name, []).append(source)
    aliases: list[dict[str, Any]] = []
    with chunks_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            pid = row["paper_id"]
            source_file = row["source_file"]
            if registry.get(pid) != source_file:
                raise ValueError(f"registry 与 chunk 文件冲突: {pid} -> {source_file}")
            matches = known_sources.get(source_file, [])
            if len(matches) > 1:
                raise ValueError(f"PDF basename 在 v2 文献中不唯一，拒绝猜测: {source_file}")
            canonical_source = matches[0] if matches else f"member_a_agent_v5/{source_file}"
            paper_id = _paper_key(canonical_source)
            text = row["original_chunk_text"].strip()
            page = int(row["page_start"]) if row.get("page_start", "").isdigit() else None
            evidence_id = _stable_key(paper_id, str(page), _normalized(text), prefix="EV_")
            if not text:
                continue
            aliases.append({
                "paper_id": paper_id,
                "paper_source": canonical_source,
                "paper_title": Path(source_file).stem,
                "evidence_id": evidence_id,
                "source_id": row["chunk_id"],
                "source_file": source_file,
                "page_num": page,
                "content": text,
                "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            })
    with driver.session() as session:
        def write(tx):
            for alias in aliases:
                tx.run(
                    """MERGE (p:Paper {paper_id:$paper_id})
                       ON CREATE SET p.source_file=$paper_source, p.title=$paper_title,
                           p.identity_scheme='normalized_source_path_v1', p.parse_status='v5_chunk_source'
                       MERGE (e:Evidence {evidence_id:$evidence_id})
                       SET e.page_start=$page_num, e.page_end=$page_num, e.content=$content,
                           e.content_sha256=$content_sha256, e.source_file=$source_file,
                           e.chunk_version='member_a_agent_v5', e.evidence_kind='verbatim_source_chunk',
                           e.updated_at=datetime()
                       MERGE (p)-[:CONTAINS]->(e)
                       WITH e
                       MERGE (a:EvidenceAlias {alias_key:$alias_key})
                       SET a.namespace='member_a_agent_v5', a.source_id=$source_id,
                           a.source_file=$source_file, a.page_num=$page_num,
                           a.content_sha256=$content_sha256,
                           a.mapping_status='exact_source_chunk'
                       MERGE (a)-[:RESOLVES_TO]->(e)""",
                    alias_key=_stable_key("member_a_agent_v5", alias["source_id"], prefix="ALIAS_"),
                    **alias,
                ).consume()
        session.execute_write(write)
    return len(aliases)


def _resolve_reference(tx, reference: str | dict[str, str]) -> str:
    if isinstance(reference, dict):
        namespace, source_id = reference.get("namespace"), reference.get("source_id")
    else:
        namespace, source_id = "member_a_agent_v5", reference
    if not namespace or not source_id:
        raise ValueError("证据引用必须带 namespace 和 source_id")
    row = tx.run(
        """MATCH (a:EvidenceAlias {alias_key:$key})-[:RESOLVES_TO]->(e:Evidence)
           WHERE a.namespace=$namespace AND a.source_id=$source_id
             AND a.mapping_status IN ['exact_source_chunk','exact_content_match']
           RETURN e.evidence_id AS id""",
        key=_stable_key(namespace, source_id, prefix="ALIAS_"), namespace=namespace, source_id=source_id,
    ).single()
    if not row:
        raise ValueError(f"证据别名不存在、未精确解析或有歧义: {namespace}:{source_id}")
    return row["id"]


def write_decision(
    driver: Driver, *, round_num: int, candidate_id: str,
    expected_direction: Literal["improve", "not_improve", "uncertain"], confidence: float,
    selection_reason: str, evidence_ids: list[str | dict[str, str]],
    referenced_experiment_ids: list[str], suggestion_ids: list[str] | None = None,
    agent_version: str = "agent-v1",
    request_id: str | None = None,
) -> str:
    """Persist an accepted decision and its structured experiment task atomically."""
    if round_num < 1:
        raise ValueError("round_num 必须从 1 开始")
    if expected_direction not in {"improve", "not_improve", "uncertain"}:
        raise ValueError("expected_direction 必须是 improve|not_improve|uncertain")
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("confidence 必须是 [0,1] 内的有限数")
    if not selection_reason.strip():
        raise ValueError("selection_reason 不能为空")
    if not evidence_ids and not referenced_experiment_ids:
        raise ValueError("决策至少需要一条文献证据或已完成历史实验")
    if round_num == 1 and referenced_experiment_ids:
        raise ValueError("第一轮是文献冷启动，不可引用历史实验")
    round_id = f"R{round_num:02d}"
    suggestion_ids = suggestion_ids or []
    request_id = request_id or f"{round_id}:{candidate_id}"
    request_suffix = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:10]
    decision_id = f"DEC_R{round_num:02d}_{candidate_id}_{request_suffix}"
    experiment_id = f"EXP_R{round_num:02d}_{candidate_id}_{request_suffix}"
    with driver.session() as session:
        def write(tx):
            if not tx.run(
                "MATCH (m:Material {candidate_id:$id, in_candidate_pool:true, dataset_version:$version}) RETURN m",
                id=candidate_id, version=DATASET_VERSION,
            ).single():
                raise ValueError(f"候选不在 {DATASET_VERSION} 候选池: {candidate_id}")
            resolved = [_resolve_reference(tx, ref) for ref in evidence_ids]
            for experiment_ref in referenced_experiment_ids:
                if not tx.run(
                    """MATCH (x:Experiment {experiment_id:$id, status:'done'})-[:PRODUCES]->(:Result)
                       RETURN x""", id=experiment_ref,
                ).single():
                    raise ValueError(f"历史实验未完成或无结果: {experiment_ref}")
            for suggestion_id in suggestion_ids:
                if not tx.run(
                    "MATCH (:Suggestion {suggestion_id:$id, status:'proposed'}) RETURN 1",
                    id=suggestion_id,
                ).single():
                    raise ValueError(f"建议不存在或尚未处于可采纳状态: {suggestion_id}")
            payload_hash = hashlib.sha256(json.dumps({
                "candidate_id": candidate_id, "direction": expected_direction,
                "confidence": confidence, "reason": selection_reason,
                "evidence": sorted(resolved), "experiments": sorted(referenced_experiment_ids),
                "suggestions": sorted(suggestion_ids), "agent_version": agent_version,
            }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
            existing = tx.run(
                "MATCH (d:Decision {decision_id:$id}) RETURN d.request_id AS request_id, d.payload_sha256 AS payload_sha256",
                id=decision_id,
            ).single()
            if existing and (existing["request_id"] != request_id or existing["payload_sha256"] != payload_hash):
                raise ValueError(f"{decision_id} 已存在且请求内容不同；不可覆盖历史决策")
            tx.run(
                """MERGE (rd:Round {round_id:$round_id})
                   ON CREATE SET rd.started_at=datetime()
                   SET rd.round_num=$round_num, rd.dataset_version=$version,
                       rd.agent_version=$agent_version
                   MERGE (m:Material {candidate_id:$candidate_id})
                   MERGE (d:Decision {decision_id:$decision_id})
                   ON CREATE SET d.created_at=datetime(), d.request_id=$request_id
                   SET d.selected_candidate_id=$candidate_id, d.expected_direction=$direction,
                       d.confidence=$confidence, d.selection_reason=$reason,
                       d.agent_version=$agent_version, d.output_schema_version='1.0',
                       d.payload_sha256=$payload_sha256
                   MERGE (rd)-[:HAS_DECISION]->(d)
                   MERGE (d)-[:SELECTS]->(m)
                   MERGE (x:Experiment {experiment_id:$experiment_id})
                   ON CREATE SET x.status='submitted', x.round_id=$round_id,
                       x.submitted_at=datetime(), x.dataset_version=$version,
                       x.request_id=$request_id
                   MERGE (d)-[:EXECUTED_AS]->(x)
                   MERGE (x)-[:TESTS]->(m)
                   WITH x
                   MATCH (c:Condition {dataset_version:$version})
                   MERGE (x)-[:USES_CONDITION]->(c)""",
                round_id=round_id, round_num=round_num, version=DATASET_VERSION,
                agent_version=agent_version, candidate_id=candidate_id,
                decision_id=decision_id, direction=expected_direction,
                confidence=confidence, reason=selection_reason,
                experiment_id=experiment_id, request_id=request_id,
                payload_sha256=payload_hash,
            ).consume()
            if round_num > 1:
                tx.run(
                    """MATCH (current:Round {round_id:$current_id})
                       MATCH (previous:Round {round_num:$previous_num, dataset_version:$version})
                       MERGE (current)-[:FOLLOWS]->(previous)""",
                    current_id=round_id, previous_num=round_num - 1,
                    version=DATASET_VERSION,
                ).consume()
            for evidence_id in resolved:
                tx.run(
                    """MATCH (d:Decision {decision_id:$decision_id}), (e:Evidence {evidence_id:$evidence_id})
                       MERGE (d)-[:REFERENCES_EVIDENCE]->(e)""",
                    decision_id=decision_id, evidence_id=evidence_id,
                ).consume()
            for experiment_ref in referenced_experiment_ids:
                tx.run(
                    """MATCH (d:Decision {decision_id:$decision_id}), (x:Experiment {experiment_id:$experiment_id})
                       MERGE (d)-[:REFERENCES_EXPERIMENT]->(x)""",
                    decision_id=decision_id, experiment_id=experiment_ref,
                ).consume()
            for suggestion_id in suggestion_ids:
                tx.run(
                    """MATCH (s:Suggestion {suggestion_id:$suggestion_id}), (d:Decision {decision_id:$decision_id})
                       MERGE (s)-[:GUIDES]->(d)""",
                    suggestion_id=suggestion_id, decision_id=decision_id,
                ).consume()
        session.execute_write(write)
    return decision_id


def write_experiment_result(
    driver: Driver, *, experiment_id: str, result_id: str, metric_value: float,
    source_row: int, source_file: str, source_sheet: str = "实验返回",
    source_column: str = RESULT_COLUMN, unit: str = "mV",
    metric_definition: str = "RC 应力前后 HER 过电位增量 Δη_RC；以正式测试方法为准",
    test_status: str = "ok", raw_data_uri: str | None = None,
) -> None:
    """Trusted callback only: append an immutable, fully sourced result."""
    if not math.isfinite(float(metric_value)):
        raise ValueError("metric_value 必须为有限数值")
    if source_column != RESULT_COLUMN:
        raise ValueError("v2 Result 只接受 Δη_RC 源列；cell_voltage_V 是独立指标")
    if unit != "mV":
        raise ValueError("Ni-RC v2 的 Δη_RC 单位必须为 mV")
    with driver.session() as session:
        row = session.run(
            """MATCH (x:Experiment {experiment_id:$experiment_id})
               MERGE (r:Result {result_id:$result_id})
               ON CREATE SET r.metric_name='delta_eta_rc', r.display_name='Δη_RC',
                   r.metric_value=$value, r.unit=$unit, r.metric_definition=$definition,
                   r.optimization_direction='minimize',
                   r.source_file=$source_file, r.source_sheet=$source_sheet,
                   r.source_column=$source_column, r.source_row=$source_row,
                   r.dataset_version=$version, r.test_status=$test_status,
                   r.raw_data_uri=$raw_data_uri, r.returned_at=datetime()
               WITH x,r WHERE r.metric_value=$value AND r.unit=$unit
                   AND r.source_column=$source_column AND r.source_row=$source_row
               MERGE (x)-[:PRODUCES]->(r)
               SET x.status='done', x.returned_at=coalesce(x.returned_at,datetime())
               RETURN r.result_id AS result_id""",
            experiment_id=experiment_id, result_id=result_id, value=float(metric_value),
            unit=unit, definition=metric_definition, source_file=source_file,
            source_sheet=source_sheet, source_column=source_column, source_row=source_row,
            version=DATASET_VERSION, test_status=test_status, raw_data_uri=raw_data_uri,
        ).single()
        if not row:
            raise ValueError("实验不存在，或 result_id 已绑定到不同的事实；进入隔离复核")


def write_diagnosis(
    driver: Driver, *, diagnosis_id: str, result_id: str,
    baseline_result_id: str | None, diagnosis_text: str,
    outcome_label: str, diagnosis_method: str = "deterministic_metric_comparison",
    human_reviewed: bool = False,
) -> None:
    """Attach an interpretation; compute numeric deltas only for compatible results."""
    with driver.session() as session:
        def write(tx):
            current = tx.run(
                """MATCH (x:Experiment)-[:PRODUCES]->(r:Result {result_id:$id})
                   RETURN x.experiment_id AS experiment_id, x.dataset_version AS dataset_version,
                          r.metric_name AS metric, r.metric_value AS value, r.unit AS unit,
                          r.metric_definition AS definition""",
                id=result_id,
            ).single()
            if not current:
                raise ValueError(f"当前结果不存在: {result_id}")
            delta = None
            comparable = False
            if baseline_result_id:
                baseline = tx.run(
                    """MATCH (bx:Experiment)-[:PRODUCES]->(br:Result {result_id:$id})
                       RETURN bx.experiment_id AS experiment_id, bx.dataset_version AS dataset_version,
                              br.metric_name AS metric, br.metric_value AS value, br.unit AS unit,
                              br.metric_definition AS definition""",
                    id=baseline_result_id,
                ).single()
                if not baseline:
                    raise ValueError(f"对照结果不存在: {baseline_result_id}")
                comparable = all(current[k] == baseline[k] for k in ("dataset_version", "metric", "unit", "definition"))
                if comparable:
                    # Ensure both experiments used the same normalized condition set.
                    condition_rows = tx.run(
                        """MATCH (x:Experiment {experiment_id:$current})-[:USES_CONDITION]->(c:Condition)
                           WITH collect(c.condition_key) AS current_conditions
                           MATCH (b:Experiment {experiment_id:$baseline})-[:USES_CONDITION]->(bc:Condition)
                           RETURN current_conditions = collect(bc.condition_key) AS same_conditions""",
                        current=current["experiment_id"], baseline=baseline["experiment_id"],
                    ).single()
                    comparable = bool(condition_rows and condition_rows["same_conditions"])
                    if comparable:
                        delta = float(current["value"]) - float(baseline["value"])
            tx.run(
                """MATCH (r:Result {result_id:$result_id})
                   MERGE (d:Diagnosis {diagnosis_id:$diagnosis_id})
                   ON CREATE SET d.created_at=datetime()
                   SET d.outcome_label=$outcome_label, d.conclusion=$diagnosis_text,
                       d.diagnosis_method=$diagnosis_method, d.human_reviewed=$human_reviewed,
                       d.comparable=$comparable, d.delta_vs_baseline=$delta,
                       d.baseline_result_id=$baseline_result_id,
                       d.metric_name=$metric_name, d.unit=$unit,
                       d.dataset_version=$dataset_version
                   MERGE (r)-[:ANALYZED_BY]->(d)""",
                result_id=result_id, diagnosis_id=diagnosis_id,
                outcome_label=outcome_label if comparable or not baseline_result_id else "not_comparable",
                diagnosis_text=diagnosis_text, diagnosis_method=diagnosis_method,
                human_reviewed=human_reviewed, comparable=comparable, delta=delta,
                baseline_result_id=baseline_result_id, metric_name=current["metric"],
                unit=current["unit"], dataset_version=current["dataset_version"],
            ).consume()
        session.execute_write(write)


def write_suggestion(
    driver: Driver, *, suggestion_id: str, diagnosis_id: str,
    adjustment_type: str, strategy: str, expected_effect: str,
    target_element: str | None = None,
) -> None:
    """Store a proposed next action; it is advice, not a measured result."""
    if not strategy.strip():
        raise ValueError("strategy 不能为空")
    with driver.session() as session:
        record = session.run(
            """MATCH (d:Diagnosis {diagnosis_id:$diagnosis_id})
               MERGE (s:Suggestion {suggestion_id:$suggestion_id})
               ON CREATE SET s.created_at=datetime()
               SET s.adjustment_type=$adjustment_type, s.target_element=$target_element,
                   s.strategy=$strategy, s.expected_effect=$expected_effect,
                   s.based_on_diagnosis_id=$diagnosis_id, s.status='proposed'
               MERGE (d)-[:GENERATES]->(s)
               RETURN s.suggestion_id AS id""",
            diagnosis_id=diagnosis_id, suggestion_id=suggestion_id,
            adjustment_type=adjustment_type, target_element=target_element,
            strategy=strategy, expected_effect=expected_effect,
        ).single()
        if not record:
            raise ValueError(f"诊断不存在: {diagnosis_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ni-RC v2 Neo4j 科研记忆图谱导入")
    parser.add_argument("--seed-candidates", action="store_true", help="仅导入掩盖结果表中的候选身份和组成")
    parser.add_argument("--import-literature", action="store_true", help="导入 v2 文献片段及待复核 Claim")
    parser.add_argument("--import-agent-v5-aliases", action="store_true", help="按 v5 registry 导入 Pxx_chunk 证据别名")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    parser.add_argument("--agent-v5-dir", type=Path, default=DEFAULT_AGENT_V5)
    args = parser.parse_args()
    if not any((args.seed_candidates, args.import_literature, args.import_agent_v5_aliases)):
        parser.error("请至少指定一个导入动作")
    driver = get_driver()
    try:
        if args.seed_candidates:
            print(f"候选池已导入: {seed_candidate_pool(driver, args.xlsx)} 条")
        if args.import_literature:
            paper_count, evidence_count = import_literature(driver, args.chunks, args.claims)
            print(f"文献已导入: {paper_count} 篇、{evidence_count} 个片段")
        if args.import_agent_v5_aliases:
            print(f"v5 引用别名已导入: {import_agent_v5_aliases(driver, args.agent_v5_dir, args.chunks)} 条")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
