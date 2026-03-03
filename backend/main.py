import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# Configure root logger so that all app.* loggers (service, downloader, etc.)
# emit to stderr. Without this, only uvicorn's own logger produces output and
# background-task logs are silently dropped.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
)

# Suppress the Azure SDK HTTP transport logger — it dumps full request/response
# headers for every blob operation at INFO level, which is extremely noisy.
logging.getLogger("azure").setLevel(logging.WARNING)

# Disable Uvicorn's built-in access log — our RequestTimingMiddleware already
# logs every request with timing, request-id and slow-request tagging.
logging.getLogger("uvicorn.access").disabled = True

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html  # noqa: E402
from sqlalchemy import text  # noqa: E402
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware  # noqa: E402

# Import models to ensure they are registered with Base.metadata
import app.modules.auth.models  # noqa: E402
import app.modules.concept_normalization.review_sql_models  # noqa: E402
import app.modules.courses.models  # noqa: E402
import app.modules.curricularalignmentarchitect.models  # noqa: E402
import app.modules.embeddings.course_models  # noqa: E402
import app.modules.embeddings.models  # noqa: E402
from app.core.api_schemas import (  # noqa: E402
    HealthCheckItem,
    HealthResponse,
    RootResponse,
)
from app.core.database import Base, SessionLocal, async_engine, engine  # noqa: E402
from app.core.langsmith_tracing import (  # noqa: E402
    ConditionalLangSmithTracingMiddleware,
    configure_langsmith_env,
)
from app.core.neo4j import (  # noqa: E402
    create_neo4j_driver,
    initialize_neo4j_constraints,
    verify_neo4j_connectivity,
)
from app.core.request_timing_middleware import RequestTimingMiddleware  # noqa: E402
from app.core.settings import settings  # noqa: E402
from app.modules.auth import routes as auth_routes  # noqa: E402
from app.modules.concept_normalization import (  # noqa: E402
    routes as concept_normalization_routes,
)
from app.modules.courses import routes as course_routes  # noqa: E402
from app.modules.curricularalignmentarchitect.api_routes import (  # noqa: E402
    router as book_selection_router,
)
from app.providers.storage import blob_service  # noqa: E402

logger = logging.getLogger(__name__)


def _parse_cors_origins(raw_origins: str | None) -> list[str]:
    origins = [
        origin.strip().rstrip("/")
        for origin in (raw_origins or "").split(",")
        if origin.strip()
    ]
    return list(dict.fromkeys(origins))


def _ensure_sql_schema_upgrades() -> None:
    """Idempotent schema upgrades for PostgreSQL.

    `Base.metadata.create_all()` does not alter existing tables, so new columns
    and vector-dimension changes are applied here on every startup (safe no-ops
    when already up to date).
    """
    if not str(engine.url).startswith("postgresql"):
        return

    with engine.connect() as conn:
        # Idempotent ALTER: add `level` column if missing.
        col_exists = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'courses' AND column_name = 'level'"
            )
        ).fetchone()
        if not col_exists:
            conn.execute(
                text(
                    "ALTER TABLE courses ADD COLUMN level VARCHAR(20) "
                    "NOT NULL DEFAULT 'bachelor'"
                )
            )

        # Idempotent ALTER: add `discovered_books_json` column if missing.
        col_exists2 = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'book_selection_sessions' "
                "AND column_name = 'discovered_books_json'"
            )
        ).fetchone()
        if not col_exists2:
            conn.execute(
                text(
                    "ALTER TABLE book_selection_sessions "
                    "ADD COLUMN discovered_books_json TEXT"
                )
            )

        # Idempotent ALTER: add progress_scored column if missing.
        col_exists3 = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'book_selection_sessions' "
                "AND column_name = 'progress_scored'"
            )
        ).fetchone()
        if not col_exists3:
            conn.execute(
                text(
                    "ALTER TABLE book_selection_sessions "
                    "ADD COLUMN progress_scored INTEGER NOT NULL DEFAULT 0"
                )
            )

        # Idempotent ALTER: add progress_total column if missing.
        col_exists4 = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'book_selection_sessions' "
                "AND column_name = 'progress_total'"
            )
        ).fetchone()
        if not col_exists4:
            conn.execute(
                text(
                    "ALTER TABLE book_selection_sessions "
                    "ADD COLUMN progress_total INTEGER NOT NULL DEFAULT 0"
                )
            )

        # Idempotent ALTER: add error_message column if missing.
        col_exists5 = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'book_selection_sessions' "
                "AND column_name = 'error_message'"
            )
        ).fetchone()
        if not col_exists5:
            conn.execute(
                text(
                    "ALTER TABLE book_selection_sessions ADD COLUMN error_message TEXT"
                )
            )

        # Migrate vector columns to the correct dimension (2048).
        # text-embedding-v4 actually returns 2048-dim vectors.
        # Previous deployments may have used 2536 or 3072 — fix both.
        _VECTOR_MIGRATIONS = [
            ("book_concepts", "name_embedding"),
            ("book_concepts", "evidence_embedding"),
            ("book_chunks", "embedding"),
            ("course_concept_caches", "name_embedding"),
            ("course_concept_caches", "evidence_embedding"),
        ]
        for tbl, col in _VECTOR_MIGRATIONS:
            row = conn.execute(
                text(
                    "SELECT atttypmod FROM pg_attribute "
                    "JOIN pg_class ON pg_class.oid = pg_attribute.attrelid "
                    "WHERE pg_class.relname = :tbl AND pg_attribute.attname = :col "
                    "AND pg_attribute.attnum > 0"
                ),
                {"tbl": tbl, "col": col},
            ).fetchone()
            if row and row[0] not in (2048, -1, None):
                logger.info(
                    "Migrating %s.%s from vector(%d) to vector(2048)",
                    tbl,
                    col,
                    row[0],
                )
                conn.execute(
                    text(f"ALTER TABLE {tbl} ALTER COLUMN {col} TYPE vector(2048)")
                )

        # Idempotent: add 'chunking' value to extraction_run_status enum
        # if it doesn't already exist (PostgreSQL enums cannot use IF NOT EXISTS).
        has_chunking = conn.execute(
            text(
                "SELECT 1 FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = 'extraction_run_status' "
                "AND e.enumlabel = 'chunking'"
            )
        ).fetchone()
        if not has_chunking:
            conn.execute(
                text(
                    "ALTER TYPE extraction_run_status "
                    "ADD VALUE IF NOT EXISTS 'chunking' AFTER 'extracting'"
                )
            )

        # Idempotent: add agentic extraction enum values
        for val in ("agentic_extracting", "agentic_completed"):
            has_val = conn.execute(
                text(
                    "SELECT 1 FROM pg_enum e "
                    "JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = 'extraction_run_status' "
                    "AND e.enumlabel = :label"
                ),
                {"label": val},
            ).fetchone()
            if not has_val:
                conn.execute(
                    text(
                        f"ALTER TYPE extraction_run_status "
                        f"ADD VALUE IF NOT EXISTS '{val}'"
                    )
                )

        # Idempotent: add chapter_text column to book_chapters
        has_chapter_text = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'book_chapters' "
                "AND column_name = 'chapter_text'"
            )
        ).fetchone()
        if not has_chapter_text:
            conn.execute(text("ALTER TABLE book_chapters ADD COLUMN chapter_text TEXT"))

        # Idempotent: add chapter_summary column to book_chapters
        has_chapter_summary = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'book_chapters' "
                "AND column_name = 'chapter_summary'"
            )
        ).fetchone()
        if not has_chapter_summary:
            conn.execute(
                text("ALTER TABLE book_chapters ADD COLUMN chapter_summary TEXT")
            )

        # Idempotent: add skills_json column to book_chapters
        has_skills_json = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'book_chapters' "
                "AND column_name = 'skills_json'"
            )
        ).fetchone()
        if not has_skills_json:
            conn.execute(text("ALTER TABLE book_chapters ADD COLUMN skills_json TEXT"))

        conn.commit()


def _backfill_course_selected_books() -> None:
    """One-time migration: promote existing course_books to course_selected_books.

    Books that were selected/downloaded before the course_selected_books table
    existed need to be copied over so the new UI can display them.
    Idempotent: skips rows that already have a matching source_book_id.
    """
    from sqlalchemy import select

    from app.modules.curricularalignmentarchitect.models import (
        BookStatus,
        CourseBook,
        CourseSelectedBook,
        DownloadStatus,
    )

    with SessionLocal() as db:
        # Find all selected course_books that don't yet have a course_selected_books entry
        existing_source_ids_subq = select(CourseSelectedBook.source_book_id).where(
            CourseSelectedBook.source_book_id.isnot(None)
        )
        candidates = (
            db.query(CourseBook)
            .filter(
                CourseBook.selected_by_teacher.is_(True),
                CourseBook.id.notin_(existing_source_ids_subq),
            )
            .all()
        )

        if not candidates:
            return

        count = 0
        for cb in candidates:
            # Map old download_status → new BookStatus
            if cb.download_status in (DownloadStatus.SUCCESS,):
                status = BookStatus.DOWNLOADED
            elif cb.download_status in (DownloadStatus.MANUAL_UPLOAD,):
                status = BookStatus.UPLOADED
            else:
                status = BookStatus.FAILED

            selected_book = CourseSelectedBook(
                course_id=cb.course_id,
                source_book_id=cb.id,
                title=cb.title,
                authors=cb.authors,
                publisher=cb.publisher,
                year=cb.year,
                status=status,
                blob_path=cb.blob_path,
                error_message=cb.download_error,
            )
            db.add(selected_book)
            count += 1

        db.commit()
        logger.info("Backfilled %d books into course_selected_books", count)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Configure LangSmith auth/project (does not enable global tracing by itself).
    configure_langsmith_env(
        api_key=settings.langsmith_api_key, project=settings.langsmith_project
    )

    # Wait for the database to become reachable.  Azure Container Apps with
    # VNET / private endpoints can take a few seconds after the container
    # starts before the network path is ready.
    _max_retries = 5
    _retry_delay = 3  # seconds
    for _attempt in range(1, _max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database reachable (attempt %d/%d)", _attempt, _max_retries)
            break
        except Exception:
            if _attempt == _max_retries:
                logger.exception(
                    "Database unreachable after %d attempts — aborting startup",
                    _max_retries,
                )
                raise
            logger.warning(
                "Database not reachable (attempt %d/%d), retrying in %ds…",
                _attempt,
                _max_retries,
                _retry_delay,
            )
            time.sleep(_retry_delay)

    # Enable pgvector extension before creating tables (idempotent).
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(bind=engine)
    _ensure_sql_schema_upgrades()
    _backfill_course_selected_books()

    # Warm up both connection pools so the first real request doesn't pay
    # the cold TCP+SSL handshake cost (~5s against Azure Postgres).
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Sync DB pool warmed up")
    except Exception:
        logger.exception("Sync DB pool warm-up failed")

    try:
        from sqlalchemy import text as atext

        async with async_engine.connect() as aconn:
            await aconn.execute(atext("SELECT 1"))
        logger.info("Async DB pool warmed up")
    except Exception:
        logger.exception("Async DB pool warm-up failed")

    # Recover any extraction runs that were left in-progress when the server
    # was last stopped/restarted (their background tasks are now gone).
    try:
        from app.modules.curricularalignmentarchitect.chunking_analysis.repository import (
            recover_orphaned_runs,
        )

        with SessionLocal() as db:
            recovered = recover_orphaned_runs(db)
            if recovered:
                logger.info(
                    "Marked %d orphaned analysis run(s) as FAILED on startup", recovered
                )
    except Exception:
        logger.exception("Failed to recover orphaned analysis runs on startup")

    neo4j_driver = create_neo4j_driver()
    app.state.neo4j_driver = neo4j_driver
    if neo4j_driver is not None:
        try:
            verify_neo4j_connectivity(neo4j_driver)
            initialize_neo4j_constraints(neo4j_driver)
            logger.info("Neo4j connectivity verified")
        except Exception:
            logger.exception("Neo4j connectivity verification failed")
            raise
    yield

    if app.state.neo4j_driver is not None:
        app.state.neo4j_driver.close()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

# Lightweight per-request timing instrumentation (headers + optional logging).
app.add_middleware(
    RequestTimingMiddleware,
    add_timing_header=settings.request_timing_header_enabled,
    log_timings=settings.request_timing_log_enabled,
    slow_request_ms=settings.slow_request_ms,
)

# Trust proxy headers (X-Forwarded-Proto, X-Forwarded-For) from Azure Container Apps
# This ensures FastAPI generates HTTPS URLs in redirects when behind a proxy
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# LangSmith tracing (scoped): only `/normalization/*` requests are traced.
app.add_middleware(
    ConditionalLangSmithTracingMiddleware,
    path_prefixes=("/normalization", "/book-selection"),
)

# Configure CORS
origins = _parse_cors_origins(settings.cors_allow_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(course_routes.router)
app.include_router(concept_normalization_routes.router)
app.include_router(book_selection_router)


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css",
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url="https://unpkg.com/redoc@next/bundles/redoc.standalone.js",
    )


@app.get("/", response_model=RootResponse)
def read_root() -> RootResponse:
    return RootResponse(message="Welcome to Lab Tutor")


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Health check — verifies services are configured without making DB calls.

    No connections are opened.  External monitoring (Azure alerts) handles
    database availability; this endpoint just confirms the process is up and
    its dependencies are wired.
    """
    checks: list[HealthCheckItem] = []

    # SQL — engine exists (configured at import time)
    checks.append(HealthCheckItem(name="sql", status="ok"))

    # Neo4j
    driver = getattr(app.state, "neo4j_driver", None)
    if driver is None:
        checks.append(
            HealthCheckItem(
                name="neo4j",
                status="skipped",
                detail="Neo4j is not configured",
            )
        )
    else:
        checks.append(HealthCheckItem(name="neo4j", status="ok"))

    # Azure Blob Storage
    if not settings.azure_storage_connection_string:
        checks.append(
            HealthCheckItem(
                name="azure_blob",
                status="skipped",
                detail="Azure Storage is not configured",
            )
        )
    else:
        if blob_service.container_client is not None:
            checks.append(HealthCheckItem(name="azure_blob", status="ok"))
        else:
            checks.append(
                HealthCheckItem(
                    name="azure_blob",
                    status="error",
                    detail="Blob service not initialized",
                )
            )

    any_error = any(c.status == "error" for c in checks)
    any_skipped = any(c.status == "skipped" for c in checks)
    overall_status = (
        "unhealthy" if any_error else ("degraded" if any_skipped else "healthy")
    )

    return HealthResponse(status=overall_status, checks=checks)


# Lightweight probe for platform startup/liveness checks.
# No DB or external calls — just proves the process is alive and accepting HTTP.
@app.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok"}
