### Backend environment variables (docker-compose `.env`)

`docker-compose.yml` loads a repo-root `.env` into the `backend` service via `env_file: .env`.

The backend configuration uses `LAB_TUTOR_*` variables (see `backend/app/core/settings.py`).

#### Required for extraction (`POST /courses/{course_id}/extract`)

- **LLM (required)**
  - `LAB_TUTOR_LLM_API_KEY` (required)
  - `LAB_TUTOR_LLM_BASE_URL` (optional; default `https://api.xiaocaseai.com/v1`)
  - `LAB_TUTOR_LLM_MODEL` (optional; default `deepseek-v3.2`)

#### Required for full pipeline (downloading uploads + writing to Neo4j)

- **Azure Blob Storage**
  - `LAB_TUTOR_AZURE_STORAGE_CONNECTION_STRING`
  - `LAB_TUTOR_AZURE_CONTAINER_NAME` (default `class-presentations`)

- **Neo4j**
  - `LAB_TUTOR_NEO4J_URI`
  - `LAB_TUTOR_NEO4J_USERNAME`
  - `LAB_TUTOR_NEO4J_PASSWORD`
  - `LAB_TUTOR_NEO4J_DATABASE` (default `neo4j`)

#### Legacy fallback (optional)

If `LAB_TUTOR_LLM_*` is not set, the backend will fall back to:

- `XIAO_CASE_API_KEY` / `XIAOCASE_API_KEY`
- `XIAO_CASE_API_BASE` / `XIAOCASE_API_BASE`
- `XIAO_CASE_MODEL` / `XIAOCASE_MODEL`


