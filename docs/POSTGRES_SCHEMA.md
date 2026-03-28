# PostgreSQL Schema

## Entity-Relationship Diagram

```mermaid
erDiagram
    users {
        int id PK
        string first_name
        string last_name
        enum role
        string email
        string hashed_password
        bool is_active
        bool is_superuser
        bool is_verified
        timestamp created_at
    }

    courses {
        int id PK
        string title
        string description
        int teacher_id FK
        enum extraction_status
        string level
        timestamp created_at
    }

    course_enrollments {
        int id PK
        int course_id FK
        int student_id FK
        timestamp created_at
    }

    course_files {
        int id PK
        int course_id FK
        string filename
        string blob_path
        string content_hash
        enum status
        timestamp uploaded_at
    }

    book_selection_sessions {
        int id PK
        int course_id FK
        string thread_id
        enum status
        string course_level
        int progress_scored
        int progress_total
        timestamp created_at
    }

    course_books {
        int id PK
        int session_id FK
        int course_id FK
        string title
        string authors
        float s_final
        bool selected_by_teacher
        enum download_status
        string blob_path
        string source_url
        timestamp created_at
    }

    course_selected_books {
        int id PK
        int course_id FK
        int source_book_id FK
        string title
        string authors
        enum status
        string blob_path
        timestamp created_at
    }

    book_extraction_runs {
        int id PK
        int course_id FK
        enum status
        string embedding_model
        int embedding_dims
        timestamp created_at
        timestamp updated_at
    }

    book_chapters {
        int id PK
        int run_id FK
        int selected_book_id FK
        string chapter_title
        int chapter_index
        int total_concept_count
        timestamp created_at
    }

    book_sections {
        int id PK
        int chapter_id FK
        string section_title
        int section_index
        timestamp created_at
    }

    book_concepts {
        int id PK
        int section_id FK
        int run_id FK
        string name
        text description
        text text_evidence
        enum relevance
        vector name_embedding
        vector evidence_embedding
        timestamp created_at
    }

    book_chunks {
        int id PK
        int run_id FK
        int selected_book_id FK
        text chunk_text
        int chunk_index
        vector embedding
        timestamp created_at
    }

    book_analysis_summaries {
        int id PK
        int run_id FK
        int selected_book_id FK
        enum strategy
        string book_title
        float s_final_name
        float s_final_evidence
        int total_book_concepts
        int chapter_count
        timestamp created_at
    }

    book_document_summary_scores {
        int id PK
        int summary_id FK
        string document_neo4j_id
        string topic
        text summary_text
        float sim_score
        timestamp created_at
    }

    course_concept_caches {
        int id PK
        int run_id FK
        string concept_name
        text text_evidence
        string doc_topic
        vector name_embedding
        vector evidence_embedding
        timestamp created_at
    }

    course_document_summary_caches {
        int id PK
        int run_id FK
        string document_neo4j_id
        string topic
        text summary_text
        vector summary_embedding
        timestamp created_at
    }

    course_embeddings_state {
        int course_id PK
        enum status
        timestamp started_at
        timestamp finished_at
        text last_error
    }

    document_embeddings_state {
        string document_id PK
        int course_id
        string content_hash
        enum embedding_status
        string embedding_model
        int embedding_dim
        timestamp embedded_at
    }

    concept_normalization_review_items {
        int id PK
        int course_id FK
        string proposal_id
        string concept_a
        string concept_b
        string canonical
        enum decision
        text comment
        timestamp created_at
    }

    users ||--o{ courses : "teaches"
    users ||--o{ course_enrollments : "enrolls"
    courses ||--o{ course_enrollments : "has"
    courses ||--o{ course_files : "has"
    courses ||--o{ book_selection_sessions : "has"
    courses ||--o{ course_books : "has"
    courses ||--o{ course_selected_books : "has"
    courses ||--o{ book_extraction_runs : "has"
    book_selection_sessions ||--o{ course_books : "discovers"
    course_books ||--o{ course_selected_books : "becomes"
    book_extraction_runs ||--o{ book_chapters : "produces"
    book_extraction_runs ||--o{ book_chunks : "produces"
    book_extraction_runs ||--o{ book_concepts : "produces"
    book_extraction_runs ||--o{ book_analysis_summaries : "produces"
    book_extraction_runs ||--o{ course_concept_caches : "caches"
    book_extraction_runs ||--o{ course_document_summary_caches : "caches"
    course_selected_books ||--o{ book_chapters : "contains"
    course_selected_books ||--o{ book_chunks : "contains"
    course_selected_books ||--o{ book_analysis_summaries : "summarized by"
    book_chapters ||--o{ book_sections : "has"
    book_sections ||--o{ book_concepts : "has"
    book_analysis_summaries ||--o{ book_document_summary_scores : "has"
```

---

## Data Flow

1. A `users` (teacher) creates `courses`.
2. Students join via `course_enrollments`.
3. Teacher uploads `course_files` (presentations/docs → processed into Neo4j).
4. AI runs a `book_selection_session` → discovers candidate `course_books` → teacher picks → `course_selected_books`.
5. A `book_extraction_run` processes a selected book:
   - Splits into `book_chunks` (for vector search)
   - Extracts `book_chapters` → `book_sections` → `book_concepts`
   - Builds `course_concept_caches` and `course_document_summary_caches`
6. `book_analysis_summaries` scores each book against course Neo4j documents → `book_document_summary_scores` per document.

---

## Sample Entities (from production DB)

### `users`
```json
{
  "id": 1,
  "first_name": "Roma",
  "last_name": "Khajiev",
  "role": "TEACHER",
  "email": "raxmon1710@gmail.com",
  "is_active": true
}
```

### `courses`
```json
{
  "id": 1,
  "title": "Big Data",
  "teacher_id": 1,
  "level": "bachelor",
  "extraction_status": "finished"
}
```

### `course_files`
```json
{
  "id": 1,
  "course_id": 1,
  "filename": "4 types of NoSQL.docx",
  "status": "processed"
}
```

### `book_selection_sessions`
```json
{
  "id": 1,
  "course_id": 1,
  "thread_id": "bs-1-ece08d3bd682",
  "status": "completed",
  "course_level": "bachelor"
}
```

### `course_books`
```json
{
  "id": 1,
  "session_id": 1,
  "course_id": 1,
  "title": "Data Science from Scratch",
  "download_status": "pending"
}
```

### `course_selected_books`
```json
{
  "id": 10,
  "course_id": 1,
  "source_book_id": 26,
  "title": "Big Data: Concepts, Technology, and Architecture",
  "status": "downloaded"
}
```

### `book_extraction_runs`
```json
{
  "id": 3,
  "course_id": 1,
  "status": "embedding",
  "embedding_model": "text-embedding-v4",
  "embedding_dims": 2048
}
```

---

## Enum Types

| Enum | Values |
|------|--------|
| `user_role` | `TEACHER`, `STUDENT` |
| `extraction_status` | `pending`, `running`, `finished`, `failed` |
| `file_processing_status` | `pending`, `processing`, `processed`, `failed` |
| `book_session_status` | `pending`, `running`, `completed`, `failed` |
| `book_download_status` | `pending`, `downloading`, `downloaded`, `failed` |
| `book_status` | `pending`, `downloading`, `downloaded`, `failed` |
| `extraction_run_status` | `pending`, `running`, `embedding`, `finished`, `failed` |
| `analysis_strategy` | varies |
| `concept_relevance` | varies |
| `normalization_merge_decision` | varies |
| `embedding_status` | `pending`, `running`, `done`, `failed` |
| `course_embedding_status` | varies |
