// ============================================================
// 00_constraints.cypher
// Neo4j 科研记忆图谱 - 主键约束、索引、向量索引
// 在 Neo4j Browser / cypher-shell 中按顺序执行一次即可
// ============================================================

// ---------- 主键唯一性约束（自动建唯一索引） ----------
CREATE CONSTRAINT paper_id_key         FOR (p:Paper)      REQUIRE p.paper_id    IS UNIQUE;
CREATE CONSTRAINT evidence_id_key      FOR (e:Evidence)   REQUIRE e.evidence_id   IS UNIQUE;
CREATE CONSTRAINT element_symbol_key FOR (el:Element)    REQUIRE el.symbol        IS UNIQUE;
CREATE CONSTRAINT material_comp_key   FOR (m:Material)    REQUIRE m.composition    IS UNIQUE;
CREATE CONSTRAINT cond_key_key         FOR (c:Condition)  REQUIRE c.cond_key       IS UNIQUE;
CREATE CONSTRAINT experiment_id_key   FOR (x:Experiment)  REQUIRE x.experiment_id  IS UNIQUE;
CREATE CONSTRAINT result_id_key       FOR (r:Result)     REQUIRE r.result_id      IS UNIQUE;
CREATE CONSTRAINT diagnosis_id_key     FOR (d:Diagnosis)  REQUIRE d.diagnosis_id   IS UNIQUE;
CREATE CONSTRAINT decision_id_key     FOR (d:Decision)   REQUIRE d.decision_id     IS UNIQUE;
CREATE CONSTRAINT suggestion_id_key    FOR (s:Suggestion) REQUIRE s.suggestion_id   IS UNIQUE;
CREATE CONSTRAINT round_num_key       FOR (rd:Round)      REQUIRE rd.round_num       IS UNIQUE;

// ---------- 普通检索加速索引 ----------
CREATE INDEX material_n_elements_idx FOR (m:Material) ON (m.n_elements);
CREATE INDEX result_voltage_idx      FOR (r:Result)   ON (r.cell_voltage_V);
CREATE INDEX exp_round_idx           FOR (x:Experiment) ON (x.round_num);
CREATE INDEX decision_round_idx      FOR (d:Decision)  ON (d.round_num);

// ---------- 文献证据向量索引（BGE-M3 输出 1024 维） ----------
CREATE VECTOR INDEX evidence_vec_idx FOR (e:Evidence) ON (e.embedding)
OPTIONS { indexConfig: {
  `vector.dimensions`: 1024,
  `vector.similarity_function`: 'cosine'
} };
