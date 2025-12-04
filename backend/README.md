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
- `GET /` – Welcome message.
- `GET /health` – Health check endpoint.
- `GET /docs` / `GET /redoc` – Interactive API documentation.

