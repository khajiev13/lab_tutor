### Authentication & JWT

- **Secret key (required)**
  - `LAB_TUTOR_SECRET_KEY` — used to sign both access tokens and refresh tokens.
    **Change this in production.** Default: `change-this-secret`
- **Token lifetimes (optional)**
  - `LAB_TUTOR_ACCESS_TOKEN_EXPIRE_MINUTES` — access token lifetime. Default: `60`
  - `LAB_TUTOR_REFRESH_TOKEN_EXPIRE_DAYS` — refresh token lifetime. Default: `7`

> Login endpoint: `POST /auth/jwt/login` (form-encoded `username` + `password`)
> Refresh endpoint: `POST /auth/jwt/refresh` (JSON `{"refresh_token": "..."}`)
> Register endpoint: `POST /auth/register` (JSON, returns 201 on success)
> **Note:** Every successful registration also creates or updates a `USER` node in Neo4j via the `on_after_register` hook. If Neo4j is unavailable at registration time, the error is logged but registration still succeeds.

### Backend environment variables (docker-compose `.env`)

`docker-compose.yml` loads a repo-root `.env` into the `backend` service via `env_file: .env`.

The backend configuration uses `LAB_TUTOR_*` variables (see `backend/app/core/settings.py`).

#### Required for extraction (`POST /courses/{course_id}/extract`)

- **LLM (required)**
  - `LAB_TUTOR_LLM_API_KEY` (required)
  - `LAB_TUTOR_LLM_BASE_URL` (optional; default `https://api.silra.cn/v1/`)
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

#### LangSmith (observability; optional)

If you want **LangSmith traces** for selected parts of the backend (e.g. concept normalization),
set:

- `LAB_TUTOR_LANGSMITH_API_KEY`
- `LAB_TUTOR_LANGSMITH_PROJECT` (default: `lab-tutor-backend`)

Notes:
- These map to the standard LangSmith/LangChain environment variables (`LANGSMITH_*` / `LANGCHAIN_*`)
  at runtime.
- If `LAB_TUTOR_LANGSMITH_API_KEY` is not set, tracing is disabled.










