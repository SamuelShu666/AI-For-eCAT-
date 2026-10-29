// Parameterized reference templates for the Python importer after 00_constraints.
// This file documents the import transactions; it is not a standalone cypher-shell
// script because $papers/$evidence/$aliases/$claims must be supplied by a caller.
// Each statement is idempotent; the Python importer supplies rows in bounded batches.

// 1) Paper identity comes from a normalized source path, never from a bare P01/P02.
UNWIND $papers AS row
MERGE (p:Paper {paper_id:row.paper_id})
SET p.source_file=row.source_file,
    p.title=coalesce(p.title,row.title),
    p.topic=row.topic,
    p.identity_scheme=row.identity_scheme,
    p.parse_status=row.parse_status,
    p.updated_at=datetime();

// 2) Evidence stores the verbatim extracted span and its exact source location.
UNWIND $evidence AS row
MATCH (p:Paper {paper_id:row.paper_id})
MERGE (e:Evidence {evidence_id:row.evidence_id})
SET e.page_start=row.page_start,
    e.page_end=row.page_end,
    e.content=row.content,
    e.content_sha256=row.content_sha256,
    e.source_file=row.source_file,
    e.chunk_version=row.chunk_version,
    e.evidence_kind='verbatim_source_chunk',
    e.updated_at=datetime()
MERGE (p)-[:CONTAINS]->(e);

// 3) Legacy chunk IDs are namespaced aliases. P03 in one registry is not
// automatically the same paper as P03 in another registry.
UNWIND $aliases AS row
MATCH (e:Evidence {evidence_id:row.evidence_id})
MERGE (a:EvidenceAlias {alias_key:row.alias_key})
SET a.namespace=row.namespace,
    a.source_id=row.source_id,
    a.source_file=row.source_file,
    a.page_num=row.page_num,
    a.mapping_status='exact_source_chunk'
MERGE (a)-[:RESOLVES_TO]->(e);

// 4) Extracted propositions remain pending until a person verifies them.
UNWIND $claims AS row
MATCH (e:Evidence {evidence_id:row.source_evidence_id})
MERGE (c:Claim {claim_id:row.claim_id})
SET c.text=row.claim_text,
    c.effect=row.effect,
    c.elements=row.elements,
    c.review_status='pending_human_review',
    c.source_quote=row.source_quote
MERGE (c)-[:GROUNDED_IN]->(e);

// Audit aliases that could not be resolved before a decision references them.
MATCH (a:EvidenceAlias)
WHERE a.namespace IN ['member_a_agent_v5','demo_v2_lit_chunks']
  AND NOT (a)-[:RESOLVES_TO]->(:Evidence)
RETURN a.namespace, a.source_id, a.source_file, a.page_num, a.mapping_status;
