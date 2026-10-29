// Neo4j 5 schema for the literature, experiment-fact and decision subgraphs.
// Apply once to the target database before running build_memory_graph.py.
CREATE CONSTRAINT paper_id_key IF NOT EXISTS FOR (p:Paper) REQUIRE p.paper_id IS UNIQUE;
CREATE CONSTRAINT evidence_id_key IF NOT EXISTS FOR (e:Evidence) REQUIRE e.evidence_id IS UNIQUE;
CREATE CONSTRAINT evidence_alias_key IF NOT EXISTS FOR (a:EvidenceAlias) REQUIRE a.alias_key IS UNIQUE;
CREATE CONSTRAINT claim_id_key IF NOT EXISTS FOR (c:Claim) REQUIRE c.claim_id IS UNIQUE;
CREATE CONSTRAINT element_symbol_key IF NOT EXISTS FOR (e:Element) REQUIRE e.symbol IS UNIQUE;
CREATE CONSTRAINT material_candidate_key IF NOT EXISTS FOR (m:Material) REQUIRE m.candidate_id IS UNIQUE;
CREATE CONSTRAINT condition_key_key IF NOT EXISTS FOR (c:Condition) REQUIRE c.condition_key IS UNIQUE;
CREATE CONSTRAINT dataset_version_key IF NOT EXISTS FOR (d:DatasetVersion) REQUIRE d.version IS UNIQUE;
CREATE CONSTRAINT experiment_id_key IF NOT EXISTS FOR (x:Experiment) REQUIRE x.experiment_id IS UNIQUE;
CREATE CONSTRAINT result_id_key IF NOT EXISTS FOR (r:Result) REQUIRE r.result_id IS UNIQUE;
CREATE CONSTRAINT diagnosis_id_key IF NOT EXISTS FOR (d:Diagnosis) REQUIRE d.diagnosis_id IS UNIQUE;
CREATE CONSTRAINT decision_id_key IF NOT EXISTS FOR (d:Decision) REQUIRE d.decision_id IS UNIQUE;
CREATE CONSTRAINT suggestion_id_key IF NOT EXISTS FOR (s:Suggestion) REQUIRE s.suggestion_id IS UNIQUE;
CREATE CONSTRAINT round_id_key IF NOT EXISTS FOR (r:Round) REQUIRE r.round_id IS UNIQUE;

CREATE INDEX material_dataset_idx IF NOT EXISTS FOR (m:Material) ON (m.dataset_version);
CREATE INDEX experiment_round_idx IF NOT EXISTS FOR (x:Experiment) ON (x.round_id);
CREATE INDEX result_metric_idx IF NOT EXISTS FOR (r:Result) ON (r.metric_name, r.unit);
CREATE INDEX decision_round_idx IF NOT EXISTS FOR (d:Decision) ON (d.round_num);
CREATE FULLTEXT INDEX evidence_content_fulltext IF NOT EXISTS
  FOR (e:Evidence) ON EACH [e.content];

// Add a vector index only after confirming the deployed embedding model,
// Neo4j version and vector dimension. Never infer its dimension from old data.
