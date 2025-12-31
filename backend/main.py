import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from sqlalchemy import text
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

# Import models to ensure they are registered with Base.metadata
import app.modules.auth.models  # noqa
import app.modules.concept_normalization.review_sql_models  # noqa
import app.modules.courses.models  # noqa
from app.core.api_schemas import HealthCheckItem, HealthResponse, RootResponse
from app.core.database import Base, engine
from app.core.langsmith_tracing import (
    ConditionalLangSmithTracingMiddleware,
    configure_langsmith_env,
)
from app.core.neo4j import (
    create_neo4j_driver,
    initialize_neo4j_constraints,
    verify_neo4j_connectivity,
)
from app.core.settings import settings
from app.modules.auth import routes as auth_routes
from app.modules.concept_normalization import routes as concept_normalization_routes
from app.modules.courses import routes as course_routes
from app.providers.storage import blob_service

logger = logging.getLogger(__name__)


def _ensure_sql_schema_upgrades() -> None:
    """Best-effort schema upgrades for environments without migrations.

    The app currently uses `Base.metadata.create_all()`, which does not alter existing
    tables. For local SQLite (and similar lightweight deployments), we apply minimal,
    idempotent ALTERs to keep the schema compatible with new releases.
    """
    if not str(engine.url).startswith("sqlite"):
        return

    with engine.connect() as conn:
        # Ensure `course_files.content_hash` exists (used for duplicate detection).
        cols = conn.execute(text("PRAGMA table_info(course_files)")).mappings().all()
        col_names = {c["name"] for c in cols}
        if "content_hash" not in col_names:
            conn.execute(
                text("ALTER TABLE course_files ADD COLUMN content_hash VARCHAR(64)")
            )

        # Enforce per-course uniqueness for non-null hashes.
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_course_content_hash "
                "ON course_files(course_id, content_hash)"
            )
        )
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Configure LangSmith auth/project (does not enable global tracing by itself).
    configure_langsmith_env(
        api_key=settings.langsmith_api_key, project=settings.langsmith_project
    )

    Base.metadata.create_all(bind=engine)
    _ensure_sql_schema_upgrades()

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

# Trust proxy headers (X-Forwarded-Proto, X-Forwarded-For) from Azure Container Apps
# This ensures FastAPI generates HTTPS URLs in redirects when behind a proxy
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# LangSmith tracing (scoped): only `/normalization/*` requests are traced.
app.add_middleware(
    ConditionalLangSmithTracingMiddleware, path_prefixes=("/normalization",)
)

# Configure CORS
origins = [
    o.strip() for o in (settings.cors_allow_origins or "").split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(course_routes.router)
app.include_router(concept_normalization_routes.router)


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
    checks: list[HealthCheckItem] = []

    # SQL
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks.append(HealthCheckItem(name="sql", status="ok"))
    except Exception as e:
        checks.append(HealthCheckItem(name="sql", status="error", detail=str(e)))

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
        try:
            with driver.session(database=settings.neo4j_database) as session:
                session.run("RETURN 1").consume()
            checks.append(HealthCheckItem(name="neo4j", status="ok"))
        except Exception as e:
            checks.append(HealthCheckItem(name="neo4j", status="error", detail=str(e)))

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
        try:
            if blob_service.container_client is None:
                raise RuntimeError("Blob service is not initialized")

            # HEAD request; validates auth + container existence.
            blob_service.container_client.get_container_properties()
            checks.append(HealthCheckItem(name="azure_blob", status="ok"))
        except Exception as e:
            checks.append(
                HealthCheckItem(name="azure_blob", status="error", detail=str(e))
            )

    any_error = any(c.status == "error" for c in checks)
    any_skipped = any(c.status == "skipped" for c in checks)
    overall_status = (
        "unhealthy" if any_error else ("degraded" if any_skipped else "healthy")
    )

    return HealthResponse(status=overall_status, checks=checks)


# Alias for common PaaS health probes.
@app.get("/healthz", response_model=HealthResponse, include_in_schema=False)
def healthz() -> HealthResponse:
    return health_check()
