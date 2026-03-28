# Document Extraction & Embeddings — Architecture & Design Document

> **Modules**: `backend/app/modules/document_extraction/` + `backend/app/modules/embeddings/`
> **Pattern**: Background pipeline (no agents — pure service layer)
> **Version**: 1.0

---

## 1. Purpose

These two modules form a sequential pipeline that transforms raw teacher-uploaded files into searchable, vector-indexed knowledge in the Neo4j graph:

1. **Document Extraction** — Parse uploaded files (PDF/DOCX/TXT), use LLM to extract structured concepts
2. **Embeddings** — Compute vector embeddings for documents and concept mentions, store in Neo4j

---

## 2. Pipeline Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Teacher uploads files → POST /courses/{id}/upload-presentations │
│  Files stored in Azure Blob Storage                              │
└──────────────────────────┬───────────────────────────────────────┘
                           │
              POST /courses/{id}/start-extraction
                           │
              ┌────────────▼────────────────────────────────────┐
              │         DOCUMENT EXTRACTION SERVICE              │
              │                                                 │
              │  For each CourseFile (status = PENDING/FAILED): │
              │                                                 │
              │  ┌────────────────────────────────────────────┐ │
              │  │ 1. Download blob from Azure               │ │
              │  │                                            │ │
              │  │ 2. Parse file:                            │ │
              │  │    • PDF  → pypdf                         │ │
              │  │    • DOCX → python-docx                   │ │
              │  │    • TXT  → direct read                   │ │
              │  │                                            │ │
              │  │ 3. LLM structured extraction:             │ │
              │  │    Input: plain text                      │ │
              │  │    Output (Pydantic schema):              │ │
              │  │    ├── topic: str                         │ │
              │  │    ├── summary: str                       │ │
              │  │    ├── keywords: list[str]                │ │
              │  │    └── concepts[]:                        │ │
              │  │        ├── name (raw from text)           │ │
              │  │        ├── definition                     │ │
              │  │        └── text_evidence (verbatim)       │ │
              │  │                                            │ │
              │  │ 4. Canonicalize concept names             │ │
              │  │    "JSON" → canonical: "json"             │ │
              │  └────────────────────────────────────────────┘ │
              │                                                 │
              │  Write to Neo4j:                                │
              │  ┌────────────────────────────────────────────┐ │
              │  │ CREATE (:TEACHER_UPLOADED_DOCUMENT {       │ │
              │  │   id, course_id, source_filename,          │ │
              │  │   topic, summary, keywords, original_text  │ │
              │  │ })                                         │ │
              │  │                                            │ │
              │  │ CREATE (doc)-[:MENTIONS {                  │ │
              │  │   definition, text_evidence                │ │
              │  │ }]->(concept:CONCEPT { name })             │ │
              │  └────────────────────────────────────────────┘ │
              │                                                 │
              │  Update SQL:                                    │
              │    CourseFile.status = PROCESSED                │
              │    Course.extraction_status = FINISHED          │
              └────────────────┬────────────────────────────────┘
                               │
              POST /courses/{id}/start-embeddings
                               │
              ┌────────────────▼────────────────────────────────┐
              │           EMBEDDINGS SERVICE                     │
              │                                                 │
              │  Background task with ThreadPoolExecutor:       │
              │                                                 │
              │  For each extracted document:                   │
              │  ┌────────────────────────────────────────────┐ │
              │  │ 1. Compute input_hash(text + mentions)    │ │
              │  │    Skip if hash unchanged (same model)    │ │
              │  │                                            │ │
              │  │ 2. Document-level embedding:               │ │
              │  │    embed(original_text) → vector[2048]    │ │
              │  │                                            │ │
              │  │ 3. Mention-level embeddings:               │ │
              │  │    embed(definition₁, evidence₁, ...)     │ │
              │  │    → vector per concept mention           │ │
              │  └────────────────────────────────────────────┘ │
              │                                                 │
              │  Write to Neo4j:                                │
              │  ┌────────────────────────────────────────────┐ │
              │  │ CREATE (:CHUNK {                           │ │
              │  │   document_id, embedding: [f₁..fₙ],       │ │
              │  │   embedding_model, embedding_dims           │ │
              │  │ })                                         │ │
              │  │                                            │ │
              │  │ UPDATE (doc)-[:MENTIONS]->(concept)        │ │
              │  │   SET embedding_vector = [f₁..fₙ]          │ │
              │  └────────────────────────────────────────────┘ │
              │                                                 │
              │  Update SQL:                                    │
              │    DocumentEmbeddingState.status = COMPLETED    │
              │    CourseEmbeddingStatus.status = COMPLETED     │
              └─────────────────────────────────────────────────┘
```

---

## 3. Module Structure

### Document Extraction

| File | Responsibility |
|------|---------------|
| `service.py` | `DocumentExtractionService` — orchestrates per-file extraction |
| `llm_extractor.py` | `DocumentLLMExtractor` — LLM prompt wrapper, structured output |
| `neo4j_repository.py` | `DocumentExtractionGraphRepository` — Neo4j write operations |
| `schemas.py` | `ConceptExtraction`, `ExtractionRunResult` |
| `prompts/` | LLM extraction prompt templates |

### Embeddings

| File | Responsibility |
|------|---------------|
| `embedding_service.py` | OpenAI embedding client (batching + retry) |
| `orchestrator.py` | `EmbeddingOrchestrator` — per-document embedding logic |
| `course_orchestrator.py` | `run_course_embedding_background()` — parallel workers |
| `repository.py` | `DocumentEmbeddingStateRepository` (SQL state tracking) |
| `course_repository.py` | `CourseEmbeddingStateRepository` |
| `models.py` | `DocumentEmbeddingState` SQLAlchemy model |
| `course_models.py` | `CourseEmbeddingStatus` SQLAlchemy model |
| `schemas.py` | API response schemas |

---

## 4. Data Models

### Document Extraction

```python
ConceptExtraction
  ├── name: str           # Raw concept name from text
  ├── definition: str     # Context-specific definition
  └── text_evidence: str  # Verbatim quote from document

ExtractionRunResult
  ├── course_id: int
  ├── processed_files: int
  ├── failed_files: int
  └── errors: list[FileError]
```

### Embeddings

```python
DocumentEmbeddingState
  ├── document_id: str (PK)
  ├── course_id: int
  ├── content_hash: str          # Document content hash
  ├── embedding_status: EmbeddingStatus
  ├── embedding_input_hash: str  # Hash of (text + mentions) for change detection
  ├── embedding_model: str
  ├── embedding_dim: int
  ├── embedded_at: datetime
  └── last_error: str

CourseEmbeddingStatus
  ├── course_id: int (PK)
  ├── embedding_status: EmbeddingStatus
  ├── embedding_started_at / finished_at: datetime
  └── embedding_last_error: str
```

---

## 5. Change Detection

The embeddings module uses content hashing to avoid redundant re-embedding:

```
input_hash = sha256(original_text + sorted(mentions))

if stored_hash == input_hash AND stored_model == current_model:
    → SKIP (no changes)
else:
    → RE-EMBED (content or model changed)
```

---

## 6. API Endpoints

### Extraction (via Courses routes)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/courses/{id}/start-extraction` | Trigger background extraction job |
| `GET` | `/courses/{id}/extraction-status` | Check extraction progress |

### Embeddings (via Courses routes)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/courses/{id}/start-embeddings` | Trigger background embedding |
| `GET` | `/courses/{id}/embedding-status` | Check embedding progress |
| `GET` | `/courses/{id}/embedding-status/stream` | SSE: stream progress |

---

## 7. External Dependencies

| Service | Module | Usage |
|---------|--------|-------|
| **Azure Blob Storage** | Extraction | Download uploaded files |
| **OpenAI-compatible LLM** | Extraction | Structured concept extraction |
| **OpenAI Embeddings API** | Embeddings | Vector computation (configurable model + dims) |
| **Neo4j** | Both | DOCUMENT, CONCEPT, CHUNK nodes + MENTIONS edges |
| **PostgreSQL** | Both | Status tracking, state persistence |
| **pypdf** | Extraction | PDF parsing |
| **python-docx** | Extraction | DOCX parsing |
