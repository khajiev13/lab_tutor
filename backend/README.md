# Lab Tutor Backend

FastAPI backend service for Lab Tutor application.

## Environment

| Variable | Default | Description |
| --- | --- | --- |
| `LAB_TUTOR_SECRET_KEY` | `change-this-secret` | JWT signing secret. Override in production. |
| `LAB_TUTOR_DATABASE_URL` | `sqlite:///./data/app.db` | SQLAlchemy connection string. |
| `LAB_TUTOR_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token lifetime in minutes. |

Create a `.env` file if you prefer storing these values locally.

## Development

### Local Development

1. Install dependencies (updates `.venv` and `uv.lock`):
```bash
uv sync
```

2. Run the application with hot reload:
```bash
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Testing

```bash
uv run --group dev pytest
```

### Docker

Build and run with docker-compose:
```bash
docker-compose up backend
```

The API will be available at `http://localhost:8000`

## Deployment (Azure Container Apps)

This repo is set up for:
- Local development on your machine (Docker / uvicorn reload)
- Production deployments to Azure via GitHub Actions

### Rollout / rollback (revisions + traffic splitting)

Azure Container Apps supports multiple active revisions and traffic weights. This lets you roll
out a new backend revision safely and instantly roll back if needed.

Useful commands (prod):

```bash
# List revisions
az containerapp revision list -n backend -g lab_tutor -o table

# Label a revision (optional, makes traffic changes easier to read)
az containerapp revision label add -n backend -g lab_tutor --label canary --revision <REVISION_NAME>

# Send 10% traffic to the latest revision, keep 90% on the previous labeled revision
az containerapp ingress traffic set -n backend -g lab_tutor \
  --traffic-weight canary=10 latest=90

# Roll back: send 100% traffic back to the previous revision (example label)
az containerapp ingress traffic set -n backend -g lab_tutor \
  --traffic-weight stable=100 latest=0
```

Notes:
- The backend health endpoint is `GET /health` (and `GET /healthz` alias).
- The Container App ingress target port should match the container port (commonly 8000).

#### Hot Reload (Development Mode)

The backend is configured with **hot reload enabled by default** when running via docker-compose. This means:

- ✅ **Code changes are automatically detected** - Edit any Python file and the server will reload
- ✅ **No need to rebuild** - Just save your changes and uvicorn will restart automatically
- ✅ **Fast development cycle** - See your changes instantly

**How it works:**
- Source code is mounted as a volume (`./backend:/app`)
- Uvicorn runs with `--reload` flag enabled
- Virtual environment (`.venv`) is excluded from volume mount to preserve dependencies

**To disable hot reload** (production mode), remove or set `UVICORN_RELOAD=false` in docker-compose.yml

## Key API Endpoints

- `POST /auth/register` – Register a student or teacher.
- `POST /auth/login` – Obtain a JWT access token.
- `POST /courses` – Teacher-only course creation.
- `GET /courses` – List available courses.
- `POST /courses/{course_id}/join` – Student enrollment.
- `GET /normalization/stream` – Start concept normalization (SSE). Returns a `review_id` when merges require human review.
- `GET /normalization/reviews/{review_id}` – Get staged merge proposals for review (stored in SQL).
- `POST /normalization/reviews/{review_id}/decisions` – Approve/reject staged proposals (stored in SQL).
- `POST /normalization/reviews/{review_id}/apply` – Apply **approved** merges to Neo4j, then delete staged SQL rows for that review.
- `GET /` – Welcome message.
- `GET /health` – Health check endpoint.
- `GET /docs` / `GET /redoc` – Interactive API documentation.

## Neo4j Cleanup (legacy normalization review nodes)

Normalization review/proposal state is now staged in SQL and should **not** exist as Neo4j nodes.
If your Neo4j already contains legacy nodes, you can remove them with:

```cypher
MATCH (n:MERGE_PROPOSAL) DETACH DELETE n;
MATCH (n:NORMALIZATION_REVIEW) DETACH DELETE n;
```

