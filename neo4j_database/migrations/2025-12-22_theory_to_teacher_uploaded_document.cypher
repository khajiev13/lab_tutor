// One-time migration: rename :THEORY nodes to :TEACHER_UPLOADED_DOCUMENT
//
// Assumptions:
// - You are on Neo4j 5.x+ (supports IF EXISTS/IF NOT EXISTS for schema ops)
// - Relationship types stay the same (e.g., :HAS_TEACHER_UPLOADED_DOCUMENT, :MENTIONS, :HAS_QUESTION)
// - Node properties (id, name, source, compressed_text, original_text, embedding, etc.) are unchanged
//
// Recommended safety step: take a DB backup / snapshot before running.

// --- 1) Drop old schema objects tied to :THEORY (safe/no-op if missing) ---
DROP CONSTRAINT theory_id_unique IF EXISTS;
DROP INDEX theory_source_idx IF EXISTS;
DROP INDEX theory_embedding_idx IF EXISTS;

// --- 2) Relabel nodes ---
// Convert nodes that currently have :THEORY
MATCH (t:THEORY)
SET t:TEACHER_UPLOADED_DOCUMENT
REMOVE t:THEORY;

// If you have any nodes that accidentally have both labels, normalize them
MATCH (t:TEACHER_UPLOADED_DOCUMENT:THEORY)
REMOVE t:THEORY;

// --- 3) Create new schema objects for :TEACHER_UPLOADED_DOCUMENT ---
CREATE CONSTRAINT teacher_uploaded_document_id_unique IF NOT EXISTS
FOR (d:TEACHER_UPLOADED_DOCUMENT)
REQUIRE d.id IS UNIQUE;

CREATE INDEX teacher_uploaded_document_source_idx IF NOT EXISTS
FOR (d:TEACHER_UPLOADED_DOCUMENT)
ON (d.source);

// Vector index (dimensions must match your embedding model; code uses 1536)
CREATE VECTOR INDEX teacher_uploaded_document_embedding_idx IF NOT EXISTS
FOR (d:TEACHER_UPLOADED_DOCUMENT)
ON (d.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 1536,
  `vector.similarity_function`: 'cosine'
}};

// --- 4) Verification ---
// Counts
MATCH (t:THEORY) RETURN count(t) AS theory_nodes_should_be_0;
MATCH (d:TEACHER_UPLOADED_DOCUMENT) RETURN count(d) AS teacher_uploaded_document_nodes;

// Spot-check that quiz links still work
MATCH (d:TEACHER_UPLOADED_DOCUMENT)-[:HAS_QUESTION]->(q:QUIZ_QUESTION)
RETURN count(q) AS questions_linked_to_documents;

// Spot-check mentions still work
MATCH (d:TEACHER_UPLOADED_DOCUMENT)-[:MENTIONS]->(c:CONCEPT)
RETURN count(*) AS mentions_edges;
