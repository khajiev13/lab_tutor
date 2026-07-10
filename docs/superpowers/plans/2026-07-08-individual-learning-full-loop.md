# Individual Learning Full Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved full individual-user loop: individual registration, CV upload and extraction, reviewed job search, market-skill selection, and personalized resources.

**Architecture:** Add `individual` as a first-class role and create a dedicated `backend/app/modules/individual_learning/` module. Reuse existing Lab Tutor primitives for Azure storage, DOCX/PDF extraction, job fetching, market skills, resource generation, and the student skill-selection UI pattern while avoiding hidden courses and position nodes.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, LangGraph interrupts, Neo4j, Azure Blob Storage, React 19, Vite, TypeScript strict, TailwindCSS v4, Shadcn UI, Vitest, pytest.

## Global Constraints

- Do not use kg-gen in the production path.
- Do not create `INTERESTED_POSITION` or position nodes in Neo4j.
- Persist individual users as `(:USER:INDIVIDUAL)`.
- Link individual users directly to `JOB_POSTING` with `INTERESTED_IN`.
- Link individual users directly to `MARKET_SKILL` with `SELECTED_SKILL`.
- Store CV-derived skills as `(:SKILL:CV_SKILL)`.
- CV skills are profile and matching evidence only; they are not selectable for learning.
- The first individual learning path uses only market skills.
- Do not create hidden personal courses.
- Run backend verification inside `lab_tutor_backend` by default.
- Run frontend verification inside `lab_tutor_frontend` by default.
- Do not install dependencies on the host machine unless explicitly requested.

---

## File Map

### Backend Files

- Modify: `backend/app/modules/auth/models.py`
  - Add `UserRole.INDIVIDUAL`.
- Modify: `backend/app/modules/auth/neo4j_repository.py`
  - Upsert `:INDIVIDUAL` label and remove it when the user is not individual.
- Modify: `backend/main.py`
  - Add idempotent PostgreSQL enum upgrade for `individual`.
  - Mount `individual_learning` routes.
- Create: `backend/app/modules/individual_learning/__init__.py`
  - Module marker.
- Create: `backend/app/modules/individual_learning/models.py`
  - SQLAlchemy models for profiles, CV docs, extraction runs, job search runs, match runs, and learning runs.
- Create: `backend/app/modules/individual_learning/schemas.py`
  - Pydantic request/response models shared by routes and services.
- Create: `backend/app/modules/individual_learning/repository.py`
  - SQL repository functions for module state.
- Create: `backend/app/modules/individual_learning/neo4j_repository.py`
  - Neo4j writes and reads for `CV_SKILL`, `JOB_POSTING`, `MARKET_SKILL`, `INTERESTED_IN`, `SELECTED_SKILL`, resources, and path reads.
- Create: `backend/app/modules/individual_learning/cv_extractor.py`
  - PDF/DOCX text parsing and structured CV extraction.
- Create: `backend/app/modules/individual_learning/job_matcher.py`
  - CV skill to job market skill coverage scoring.
- Create: `backend/app/modules/individual_learning/job_search.py`
  - Adapter around existing job fetching and market-skill extraction behavior.
- Create: `backend/app/modules/individual_learning/graph.py`
  - LangGraph workflow with `interrupt()` checkpoints.
- Create: `backend/app/modules/individual_learning/service.py`
  - Orchestrates SQL, Azure, Neo4j, graph runs, skill selection, and resource generation.
- Create: `backend/app/modules/individual_learning/routes.py`
  - FastAPI routes guarded by `UserRole.INDIVIDUAL`.
- Create: `backend/tests/modules/individual_learning/test_auth_individual.py`
  - Role and graph-label tests.
- Create: `backend/tests/modules/individual_learning/test_cv_extractor.py`
  - PDF/DOCX parsing and schema tests.
- Create: `backend/tests/modules/individual_learning/test_neo4j_repository.py`
  - Query behavior tests using mocked Neo4j sessions.
- Create: `backend/tests/modules/individual_learning/test_service.py`
  - Service validation tests.
- Create: `backend/tests/modules/individual_learning/test_routes.py`
  - Route guard and endpoint behavior tests.
- Create: `backend/tests/modules/individual_learning/test_graph.py`
  - LangGraph interrupt/resume unit tests with fake dependencies.

### Frontend Files

- Modify: `frontend/src/features/auth/types.ts`
  - Add `individual` to role unions.
- Modify: `frontend/src/features/auth/pages/Register.tsx`
  - Add individual role option.
- Modify: `frontend/src/App.tsx`
  - Add individual routes and onboarding redirect handling.
- Modify: `frontend/src/components/layout/AppSidebar.tsx`
  - Show individual navigation for individual users.
- Create: `frontend/src/features/individual-learning/api.ts`
  - API client and TypeScript types.
- Create: `frontend/src/features/individual-learning/pages/IndividualOnboardingPage.tsx`
  - CV upload and extraction status.
- Create: `frontend/src/features/individual-learning/pages/IndividualProfilePage.tsx`
  - CV profile review and target title editing.
- Create: `frontend/src/features/individual-learning/pages/IndividualJobsPage.tsx`
  - Job match and interested-job selection.
- Create: `frontend/src/features/individual-learning/pages/IndividualSkillsPage.tsx`
  - Market skill bank grouped by job posting.
- Create: `frontend/src/features/individual-learning/pages/IndividualLearningPathPage.tsx`
  - Selected-skill learning path.
- Create: `frontend/src/features/individual-learning/pages/IndividualLearningPathStudyPage.tsx`
  - Optional no-layout reading/video study surface mirroring the student study page.
- Create: `frontend/src/features/individual-learning/pages/*.test.tsx`
  - Focused page tests for upload, profile review, job selection, skill selection, and learning path.
- Create: `frontend/src/features/individual-learning/api.test.ts`
  - API client tests.

---

## Task 1: Individual Role And Graph Label Foundation

**Files:**
- Modify: `backend/app/modules/auth/models.py`
- Modify: `backend/app/modules/auth/neo4j_repository.py`
- Modify: `backend/main.py`
- Modify: `frontend/src/features/auth/types.ts`
- Modify: `frontend/src/features/auth/pages/Register.tsx`
- Test: `backend/tests/modules/individual_learning/test_auth_individual.py`
- Test: `frontend/src/features/auth/context/AuthContext.test.tsx`

**Interfaces:**
- Produces: `UserRole.INDIVIDUAL = "individual"`.
- Produces: `UserResponse.role: "student" | "teacher" | "individual"`.
- Produces: Neo4j upsert that sets exactly one of `:STUDENT`, `:TEACHER`, or `:INDIVIDUAL`.

- [ ] **Step 1: Write backend tests for the new role and Neo4j label**

Create `backend/tests/modules/individual_learning/test_auth_individual.py`:

```python
from app.modules.auth.models import UserRole
from app.modules.auth.neo4j_repository import UPSERT_USER


def test_individual_role_exists() -> None:
    assert UserRole.INDIVIDUAL.value == "individual"


def test_user_graph_upsert_handles_individual_label() -> None:
    assert "REMOVE u:STUDENT:TEACHER:INDIVIDUAL" in UPSERT_USER
    assert "$role = 'individual'" in UPSERT_USER
    assert "SET u:INDIVIDUAL" in UPSERT_USER
```

- [ ] **Step 2: Run backend role test and verify it fails**

Run:

```bash
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/individual_learning/test_auth_individual.py'
```

Expected: FAIL because `UserRole.INDIVIDUAL` and `:INDIVIDUAL` upsert support do not exist.

- [ ] **Step 3: Implement backend role and graph label**

In `backend/app/modules/auth/models.py`, change `UserRole` to:

```python
class UserRole(StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    INDIVIDUAL = "individual"
```

In `backend/app/modules/auth/neo4j_repository.py`, update `UPSERT_USER` label handling:

```cypher
REMOVE u.role
REMOVE u:STUDENT:TEACHER:INDIVIDUAL
FOREACH (_ IN CASE WHEN $role = 'student' THEN [1] ELSE [] END | SET u:STUDENT)
FOREACH (_ IN CASE WHEN $role = 'teacher' THEN [1] ELSE [] END | SET u:TEACHER)
FOREACH (_ IN CASE WHEN $role = 'individual' THEN [1] ELSE [] END | SET u:INDIVIDUAL)
```

In `backend/main.py`, add an idempotent enum upgrade inside `_ensure_sql_schema_upgrades()` next to the existing enum upgrades:

```python
has_individual_role = conn.execute(
    text(
        "SELECT 1 FROM pg_enum e "
        "JOIN pg_type t ON t.oid = e.enumtypid "
        "WHERE t.typname = 'user_role' "
        "AND e.enumlabel = 'individual'"
    )
).fetchone()
if not has_individual_role:
    conn.execute(text("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'individual'"))
```

- [ ] **Step 4: Update frontend role types and registration**

In `frontend/src/features/auth/types.ts`, change both role unions to:

```ts
role: 'student' | 'teacher' | 'individual';
```

In `frontend/src/features/auth/pages/Register.tsx`, change the zod enum:

```ts
role: z.enum(['student', 'teacher', 'individual'], {
  message: 'Please select a role',
}),
```

Add `BriefcaseBusiness` to the lucide import and add the role option:

```tsx
<SelectItem value="individual">
  <div className="flex items-center">
    <BriefcaseBusiness className="mr-2 h-4 w-4" />
    Individual
  </div>
</SelectItem>
```

- [ ] **Step 5: Run targeted verification**

Run:

```bash
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/individual_learning/test_auth_individual.py'
docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/auth/context/AuthContext.test.tsx'
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/auth/models.py backend/app/modules/auth/neo4j_repository.py backend/main.py frontend/src/features/auth/types.ts frontend/src/features/auth/pages/Register.tsx backend/tests/modules/individual_learning/test_auth_individual.py
git commit -m "feat: add individual user role"
```

---

## Task 2: Individual Learning SQL Models And Route Skeleton

**Files:**
- Create: `backend/app/modules/individual_learning/__init__.py`
- Create: `backend/app/modules/individual_learning/models.py`
- Create: `backend/app/modules/individual_learning/schemas.py`
- Create: `backend/app/modules/individual_learning/repository.py`
- Create: `backend/app/modules/individual_learning/routes.py`
- Create: `backend/app/modules/individual_learning/service.py`
- Modify: `backend/main.py`
- Test: `backend/tests/modules/individual_learning/test_routes.py`
- Test: `backend/tests/modules/individual_learning/test_service.py`

**Interfaces:**
- Produces: `IndividualLearningService.get_profile(user_id: int) -> IndividualProfileRead`.
- Produces: `APIRouter(prefix="/individual-learning", tags=["individual-learning"])`.
- Produces: `GET /individual-learning/profile`.

- [ ] **Step 1: Write route guard and profile tests**

Create `backend/tests/modules/individual_learning/test_routes.py` with tests that assert the route module uses the individual role guard:

```python
from app.modules.auth.models import UserRole
from app.modules.individual_learning import routes


def test_individual_learning_router_prefix() -> None:
    assert routes.router.prefix == "/individual-learning"


def test_individual_learning_uses_individual_role() -> None:
    assert routes.INDIVIDUAL_ROLE == UserRole.INDIVIDUAL
```

Create `backend/tests/modules/individual_learning/test_service.py`:

```python
from app.modules.individual_learning.service import IndividualLearningService


def test_get_profile_returns_default_onboarding_state() -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)
    profile = service.get_profile(user_id=42)

    assert profile.user_id == 42
    assert profile.onboarding_status == "needs_cv"
    assert profile.target_titles == []
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/individual_learning/test_routes.py tests/modules/individual_learning/test_service.py'
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Create schemas**

Create `backend/app/modules/individual_learning/schemas.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


OnboardingStatus = Literal[
    "needs_cv",
    "extracting",
    "needs_profile_review",
    "needs_jobs",
    "needs_skill_selection",
    "ready",
    "error",
]


class IndividualProfileRead(BaseModel):
    user_id: int
    onboarding_status: OnboardingStatus
    target_titles: list[str] = Field(default_factory=list)
    preferred_country: str | None = None
    preferred_location: str | None = None
    reviewed_at: datetime | None = None
```

- [ ] **Step 4: Create models**

Create `backend/app/modules/individual_learning/models.py` with SQLAlchemy models:

```python
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class IndividualRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"
    FAILED = "failed"


class IndividualProfile(Base):
    __tablename__ = "individual_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    onboarding_status: Mapped[str] = mapped_column(String(50), default="needs_cv")
    preferred_country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    preferred_location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_titles_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class CVDocument(Base):
    __tablename__ = "cv_documents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    blob_path: Mapped[str] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="uploaded")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CVExtractionRun(Base):
    __tablename__ = "cv_extraction_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    cv_document_id: Mapped[int] = mapped_column(ForeignKey("cv_documents.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    model_provider: Mapped[str] = mapped_column(String(100), default="")
    model_name: Mapped[str] = mapped_column(String(200), default="")
    raw_text_hash: Mapped[str] = mapped_column(String(64), default="")
    extracted_profile_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    target_title_suggestions_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    confidence_summary_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(50), default=IndividualRunStatus.PENDING.value)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IndividualJobSearchRun(Base):
    __tablename__ = "individual_job_search_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    target_titles_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    country: Mapped[str] = mapped_column(String(100), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(50), default=IndividualRunStatus.PENDING.value)
    fetched_jobs_json: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    selected_posting_urls_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IndividualJobMatchRun(Base):
    __tablename__ = "individual_job_match_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    job_search_run_id: Mapped[int] = mapped_column(ForeignKey("individual_job_search_runs.id"), index=True)
    scores_json: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    skill_gap_json: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(50), default=IndividualRunStatus.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IndividualLearningRun(Base):
    __tablename__ = "individual_learning_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    selected_skill_names_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(50), default=IndividualRunStatus.PENDING.value)
    run_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 5: Create repository and service skeleton**

Create `backend/app/modules/individual_learning/repository.py`:

```python
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import IndividualProfile


class IndividualLearningRepository:
    def __init__(self, db: Session | None) -> None:
        self._db = db

    def get_profile(self, user_id: int) -> IndividualProfile | None:
        if self._db is None:
            return None
        return (
            self._db.query(IndividualProfile)
            .filter(IndividualProfile.user_id == user_id)
            .one_or_none()
        )
```

Create `backend/app/modules/individual_learning/service.py`:

```python
from __future__ import annotations

from neo4j import Driver as Neo4jDriver
from sqlalchemy.orm import Session

from .repository import IndividualLearningRepository
from .schemas import IndividualProfileRead


class IndividualLearningService:
    def __init__(self, db: Session | None, neo4j_driver: Neo4jDriver | None) -> None:
        self._repo = IndividualLearningRepository(db)
        self._neo4j_driver = neo4j_driver

    def get_profile(self, user_id: int) -> IndividualProfileRead:
        profile = self._repo.get_profile(user_id)
        if profile is None:
            return IndividualProfileRead(user_id=user_id, onboarding_status="needs_cv")
        return IndividualProfileRead(
            user_id=user_id,
            onboarding_status=profile.onboarding_status,
            target_titles=list(profile.target_titles_json or []),
            preferred_country=profile.preferred_country,
            preferred_location=profile.preferred_location,
            reviewed_at=profile.reviewed_at,
        )
```

- [ ] **Step 6: Create routes and mount them**

Create `backend/app/modules/individual_learning/routes.py`:

```python
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from neo4j import Driver as Neo4jDriver
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.neo4j import get_neo4j_driver
from app.modules.auth.dependencies import current_active_user, require_role
from app.modules.auth.models import User, UserRole

from .schemas import IndividualProfileRead
from .service import IndividualLearningService

router = APIRouter(prefix="/individual-learning", tags=["individual-learning"])
INDIVIDUAL_ROLE = UserRole.INDIVIDUAL

IndividualDep = Annotated[
    User,
    Depends(require_role(current_active_user, role=INDIVIDUAL_ROLE)),
]
DbDep = Annotated[Session, Depends(get_db)]


def _service(db: Session, request: Request) -> IndividualLearningService:
    return IndividualLearningService(db, get_neo4j_driver(request))


@router.get("/profile", response_model=IndividualProfileRead)
def get_profile(user: IndividualDep, db: DbDep, request: Request) -> IndividualProfileRead:
    return _service(db, request).get_profile(user.id)
```

In `backend/main.py`, import and include the router:

```python
from app.modules.individual_learning.routes import router as individual_learning_router
```

```python
app.include_router(individual_learning_router)
```

- [ ] **Step 7: Run targeted backend tests**

Run:

```bash
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/individual_learning/test_routes.py tests/modules/individual_learning/test_service.py'
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/main.py backend/app/modules/individual_learning backend/tests/modules/individual_learning/test_routes.py backend/tests/modules/individual_learning/test_service.py
git commit -m "feat: scaffold individual learning module"
```

---

## Task 3: CV Upload, PDF/DOCX Parsing, And Structured Extraction

**Files:**
- Modify: `backend/app/modules/individual_learning/schemas.py`
- Modify: `backend/app/modules/individual_learning/models.py`
- Modify: `backend/app/modules/individual_learning/repository.py`
- Create: `backend/app/modules/individual_learning/cv_extractor.py`
- Modify: `backend/app/modules/individual_learning/service.py`
- Modify: `backend/app/modules/individual_learning/routes.py`
- Test: `backend/tests/modules/individual_learning/test_cv_extractor.py`
- Test: `backend/tests/modules/individual_learning/test_routes.py`

**Interfaces:**
- Produces: `extract_cv_text(filename: str, content_type: str | None, data: bytes) -> str`.
- Produces: `CVProfileExtraction` Pydantic schema.
- Produces: `POST /individual-learning/cv`.

- [ ] **Step 1: Write CV extractor tests**

Create `backend/tests/modules/individual_learning/test_cv_extractor.py`:

```python
import io
import zipfile

import pytest

from app.modules.individual_learning.cv_extractor import extract_cv_text


def _docx_bytes(text: str) -> bytes:
    payload = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", payload)
    return buf.getvalue()


def test_extract_cv_text_supports_docx() -> None:
    cv_text = (
        "Python SQL Azure FastAPI PostgreSQL Docker React TypeScript data analysis "
        "machine learning dashboards APIs cloud deployment testing architecture "
        "collaboration documentation monitoring orchestration pipelines"
    )
    text = extract_cv_text(
        filename="roma-cv.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        data=_docx_bytes(cv_text),
    )
    assert "Python SQL Azure FastAPI" in text


def test_extract_cv_text_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="Only PDF and DOCX CV files are supported"):
        extract_cv_text(filename="cv.txt", content_type="text/plain", data=b"hello")
```

- [ ] **Step 2: Run extractor tests and verify they fail**

Run:

```bash
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/individual_learning/test_cv_extractor.py'
```

Expected: FAIL because `cv_extractor.py` does not exist.

- [ ] **Step 3: Implement PDF/DOCX text parsing**

Create `backend/app/modules/individual_learning/cv_extractor.py`:

```python
from __future__ import annotations

import io

import pypdf

from app.modules.courses.file_processing import handle_docx_bytes


PDF_CONTENT_TYPES = {"application/pdf"}
DOCX_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
}


def _extract_pdf_text(data: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(data))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n\n".join(page for page in pages if page).strip()


def extract_cv_text(*, filename: str, content_type: str | None, data: bytes) -> str:
    name = filename.lower().strip()
    ct = (content_type or "").lower().strip()
    if name.endswith(".pdf") or ct in PDF_CONTENT_TYPES:
        text = _extract_pdf_text(data)
    elif name.endswith(".docx") or ct in DOCX_CONTENT_TYPES:
        text = handle_docx_bytes(data)
    else:
        raise ValueError("Only PDF and DOCX CV files are supported")

    if len(text.split()) < 20:
        raise ValueError("CV text is too short to analyze")
    return text
```

- [ ] **Step 4: Add structured extraction schemas**

In `backend/app/modules/individual_learning/schemas.py`, add:

```python
class CVSkillExtraction(BaseModel):
    name: str
    category: str = ""
    evidence: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class CVExperienceExtraction(BaseModel):
    title: str = ""
    organization: str = ""
    start_date: str = ""
    end_date: str = ""
    summary: str = ""


class CVProfileExtraction(BaseModel):
    summary: str = ""
    skills: list[CVSkillExtraction] = Field(default_factory=list)
    experience: list[CVExperienceExtraction] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    seniority_signals: list[str] = Field(default_factory=list)
    target_title_suggestions: list[str] = Field(default_factory=list)
```

- [ ] **Step 5: Add CV upload route**

In `routes.py`, add:

```python
from fastapi import File, UploadFile, status

from .schemas import CVDocumentRead


@router.post("/cv", response_model=CVDocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_cv(
    user: IndividualDep,
    db: DbDep,
    request: Request,
    file: UploadFile = File(...),
) -> CVDocumentRead:
    return await _service(db, request).upload_cv(user.id, file)
```

Add `CVDocumentRead` to `schemas.py`:

```python
class CVDocumentRead(BaseModel):
    id: int
    user_id: int
    original_filename: str
    content_type: str | None = None
    status: str
```

In `service.py`, implement `upload_cv()` using `blob_service.upload_bytes()` with blob path:

```python
blob_path = f"users/{user_id}/cv/{content_hash}/{safe_filename}"
```

Store a `CVDocument` row with status `uploaded`.

- [ ] **Step 6: Run targeted backend tests**

Run:

```bash
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/individual_learning/test_cv_extractor.py tests/modules/individual_learning/test_routes.py'
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/individual_learning backend/tests/modules/individual_learning/test_cv_extractor.py backend/tests/modules/individual_learning/test_routes.py
git commit -m "feat: add individual CV upload and parsing"
```

---

## Task 4: Individual Neo4j Repository For CV, Jobs, And Skills

**Files:**
- Create: `backend/app/modules/individual_learning/neo4j_repository.py`
- Test: `backend/tests/modules/individual_learning/test_neo4j_repository.py`

**Interfaces:**
- Produces: `upsert_cv_skills(session, user_id: int, skills: list[CVSkillExtraction], cv_document_id: int, extraction_run_id: int) -> int`.
- Produces: `upsert_job_postings_and_market_skills(session, jobs: list[dict], skills_by_job_url: dict[str, list[dict]]) -> dict[str, int]`.
- Produces: `select_market_skills(session, user_id: int, skill_names: list[str], source: str = "individual_market_skill") -> int`.
- Produces: `get_individual_skill_bank(session, user_id: int) -> list[dict]`.

- [ ] **Step 1: Write repository query tests**

Create `backend/tests/modules/individual_learning/test_neo4j_repository.py` with a fake session that captures query text and params:

```python
from app.modules.individual_learning import neo4j_repository
from app.modules.individual_learning.schemas import CVSkillExtraction


class FakeResult:
    def single(self):
        return {"written": 1}


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def run(self, query: str, **params):
        self.calls.append((query, params))
        return FakeResult()


def test_upsert_cv_skills_uses_cv_skill_label_and_has_skill() -> None:
    session = FakeSession()
    count = neo4j_repository.upsert_cv_skills(
        session,
        user_id=7,
        skills=[CVSkillExtraction(name="Python", evidence="Built APIs", confidence=0.9)],
        cv_document_id=3,
        extraction_run_id=5,
    )

    query = session.calls[0][0]
    assert count == 1
    assert "MATCH (u:USER:INDIVIDUAL {id: $user_id})" in query
    assert "MERGE (sk:SKILL:CV_SKILL" in query
    assert "MERGE (u)-[r:HAS_SKILL]->(sk)" in query


def test_select_market_skills_rejects_cv_skill_label() -> None:
    session = FakeSession()
    neo4j_repository.select_market_skills(session, user_id=7, skill_names=["Python"])
    query = session.calls[0][0]
    assert "MATCH (sk:SKILL:MARKET_SKILL" in query
    assert "CV_SKILL" not in query
    assert "MERGE (u)-[r:SELECTED_SKILL]->(sk)" in query
```

- [ ] **Step 2: Run repository tests and verify they fail**

Run:

```bash
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/individual_learning/test_neo4j_repository.py'
```

Expected: FAIL because repository functions do not exist.

- [ ] **Step 3: Implement CV skill upsert**

Create `backend/app/modules/individual_learning/neo4j_repository.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime

from neo4j import Session as Neo4jSession

from .schemas import CVSkillExtraction


def upsert_cv_skills(
    session: Neo4jSession,
    *,
    user_id: int,
    skills: list[CVSkillExtraction],
    cv_document_id: int,
    extraction_run_id: int,
) -> int:
    result = session.run(
        """
        UNWIND $skills AS skill
        MATCH (u:USER:INDIVIDUAL {id: $user_id})
        MERGE (sk:SKILL:CV_SKILL {name: skill.name})
        ON CREATE SET sk.created_at = datetime($now)
        SET sk.category = coalesce(skill.category, sk.category, ''),
            sk.source = 'cv'
        MERGE (u)-[r:HAS_SKILL]->(sk)
        SET r.source = 'cv',
            r.confidence = skill.confidence,
            r.evidence = skill.evidence,
            r.cv_document_id = $cv_document_id,
            r.extraction_run_id = $extraction_run_id,
            r.updated_at = datetime($now)
        RETURN count(DISTINCT sk) AS written
        """,
        user_id=user_id,
        skills=[skill.model_dump() for skill in skills],
        cv_document_id=cv_document_id,
        extraction_run_id=extraction_run_id,
        now=datetime.now(UTC).isoformat(),
    )
    record = result.single()
    return int(record["written"] if record else 0)
```

- [ ] **Step 4: Implement job and market skill upserts**

Add:

```python
def upsert_job_postings_and_market_skills(
    session: Neo4jSession,
    *,
    jobs: list[dict],
    skills_by_job_url: dict[str, list[dict]],
) -> dict[str, int]:
    job_result = session.run(
        """
        UNWIND $jobs AS job
        MERGE (jp:JOB_POSTING {url: job.url})
        SET jp.title = coalesce(job.title, ''),
            jp.company = coalesce(job.company, ''),
            jp.site = coalesce(job.site, ''),
            jp.search_term = coalesce(job.search_term, ''),
            jp.country = coalesce(job.country, ''),
            jp.location = coalesce(job.location, ''),
            jp.description = coalesce(job.description, '')
        RETURN count(DISTINCT jp) AS written
        """,
        jobs=jobs,
    )
    jobs_written = int(job_result.single()["written"])

    pairs = [
        {"url": url, **skill}
        for url, skills in skills_by_job_url.items()
        for skill in skills
        if skill.get("name")
    ]
    skill_result = session.run(
        """
        UNWIND $pairs AS pair
        MATCH (jp:JOB_POSTING {url: pair.url})
        MERGE (sk:SKILL:MARKET_SKILL {name: pair.name})
        ON CREATE SET sk.created_at = datetime($now)
        SET sk.category = coalesce(pair.category, sk.category, ''),
            sk.description = coalesce(pair.description, sk.description, ''),
            sk.source = 'individual_job_search'
        MERGE (sk)-[:SOURCED_FROM]->(jp)
        RETURN count(DISTINCT sk) AS written
        """,
        pairs=pairs,
        now=datetime.now(UTC).isoformat(),
    )
    return {"jobs": jobs_written, "market_skills": int(skill_result.single()["written"])}
```

- [ ] **Step 5: Implement direct job and skill selection**

Add:

```python
def select_job_postings(session: Neo4jSession, *, user_id: int, posting_urls: list[str], run_id: str) -> int:
    result = session.run(
        """
        UNWIND $posting_urls AS url
        MATCH (u:USER:INDIVIDUAL {id: $user_id})
        MATCH (jp:JOB_POSTING {url: url})
        MERGE (u)-[r:INTERESTED_IN]->(jp)
        ON CREATE SET r.selected_at = datetime($now)
        SET r.source = 'individual_job_search',
            r.job_search_run_id = $run_id
        RETURN count(DISTINCT jp) AS written
        """,
        user_id=user_id,
        posting_urls=posting_urls,
        run_id=run_id,
        now=datetime.now(UTC).isoformat(),
    )
    return int(result.single()["written"])


def select_market_skills(
    session: Neo4jSession,
    *,
    user_id: int,
    skill_names: list[str],
    source: str = "individual_market_skill",
) -> int:
    result = session.run(
        """
        UNWIND $skill_names AS skill_name
        MATCH (u:USER:INDIVIDUAL {id: $user_id})
        MATCH (sk:SKILL:MARKET_SKILL {name: skill_name})
        MERGE (u)-[r:SELECTED_SKILL]->(sk)
        ON CREATE SET r.selected_at = datetime($now)
        SET r.source = $source
        RETURN count(DISTINCT sk) AS written
        """,
        user_id=user_id,
        skill_names=skill_names,
        source=source,
        now=datetime.now(UTC).isoformat(),
    )
    return int(result.single()["written"])
```

- [ ] **Step 6: Run targeted repository tests**

Run:

```bash
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/individual_learning/test_neo4j_repository.py'
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/individual_learning/neo4j_repository.py backend/tests/modules/individual_learning/test_neo4j_repository.py
git commit -m "feat: add individual Neo4j repository"
```

---

## Task 5: LangGraph HITL Workflow For CV Review And Skill Selection

**Files:**
- Create: `backend/app/modules/individual_learning/graph.py`
- Modify: `backend/app/modules/individual_learning/schemas.py`
- Modify: `backend/app/modules/individual_learning/service.py`
- Modify: `backend/app/modules/individual_learning/routes.py`
- Test: `backend/tests/modules/individual_learning/test_graph.py`

**Interfaces:**
- Produces: `start_individual_graph(user_id: int, cv_document_id: int) -> IndividualGraphStartResponse`.
- Produces: `resume_individual_graph(user_id: int, thread_id: str, payload: dict) -> IndividualGraphResumeResponse`.
- Uses LangGraph `interrupt()` and `Command(resume=...)`.

- [ ] **Step 1: Write graph interrupt tests**

Create `backend/tests/modules/individual_learning/test_graph.py`:

```python
from langgraph.types import Command

from app.modules.individual_learning.graph import build_individual_learning_graph


def test_graph_interrupts_for_profile_review() -> None:
    graph = build_individual_learning_graph()
    config = {"configurable": {"thread_id": "individual-7"}}

    result = graph.invoke(
        {
            "user_id": 7,
            "cv_document_id": 3,
            "profile": {"skills": [], "target_title_suggestions": ["Data Analyst"]},
            "target_titles": [],
            "selected_posting_urls": [],
            "selected_skill_names": [],
        },
        config,
    )

    assert "__interrupt__" in result
    interrupt_value = result["__interrupt__"][0].value
    assert interrupt_value["kind"] == "review_profile_and_roles"


def test_graph_resumes_to_skill_selection_interrupt() -> None:
    graph = build_individual_learning_graph()
    config = {"configurable": {"thread_id": "individual-7"}}
    graph.invoke(
        {
            "user_id": 7,
            "cv_document_id": 3,
            "profile": {"skills": [], "target_title_suggestions": ["Data Analyst"]},
            "target_titles": [],
            "selected_posting_urls": [],
            "selected_skill_names": [],
        },
        config,
    )

    result = graph.invoke(
        Command(resume={"approved": True, "target_titles": ["Data Analyst"]}),
        config,
    )

    assert "__interrupt__" in result
    assert result["__interrupt__"][0].value["kind"] == "choose_jobs_and_skills"
```

- [ ] **Step 2: Run graph tests and verify they fail**

Run:

```bash
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/individual_learning/test_graph.py'
```

Expected: FAIL because `graph.py` does not exist.

- [ ] **Step 3: Implement graph state and interrupt nodes**

Create `backend/app/modules/individual_learning/graph.py`:

```python
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class IndividualLearningState(TypedDict, total=False):
    user_id: int
    cv_document_id: int
    profile: dict[str, Any]
    target_titles: list[str]
    candidate_jobs: list[dict[str, Any]]
    skill_bank: list[dict[str, Any]]
    selected_posting_urls: list[str]
    selected_skill_names: list[str]


def review_profile_and_roles(state: IndividualLearningState) -> dict:
    decision = interrupt(
        {
            "kind": "review_profile_and_roles",
            "profile": state.get("profile", {}),
            "target_title_suggestions": state.get("profile", {}).get("target_title_suggestions", []),
        }
    )
    return {"target_titles": list(decision.get("target_titles", []))}


def load_candidate_jobs(state: IndividualLearningState) -> dict:
    return {"candidate_jobs": state.get("candidate_jobs", [])}


def choose_jobs_and_skills(state: IndividualLearningState) -> dict:
    decision = interrupt(
        {
            "kind": "choose_jobs_and_skills",
            "candidate_jobs": state.get("candidate_jobs", []),
            "skill_bank": state.get("skill_bank", []),
        }
    )
    return {
        "selected_posting_urls": list(decision.get("selected_posting_urls", [])),
        "selected_skill_names": list(decision.get("selected_skill_names", [])),
    }


def build_individual_learning_graph():
    builder = StateGraph(IndividualLearningState)
    builder.add_node("review_profile_and_roles", review_profile_and_roles)
    builder.add_node("search_jobs", load_candidate_jobs)
    builder.add_node("choose_jobs_and_skills", choose_jobs_and_skills)
    builder.add_edge(START, "review_profile_and_roles")
    builder.add_edge("review_profile_and_roles", "search_jobs")
    builder.add_edge("search_jobs", "choose_jobs_and_skills")
    builder.add_edge("choose_jobs_and_skills", END)
    return builder.compile(checkpointer=InMemorySaver())
```

- [ ] **Step 4: Expose graph start/resume routes**

Add schemas:

```python
class IndividualGraphStartRequest(BaseModel):
    cv_document_id: int


class IndividualGraphStartResponse(BaseModel):
    thread_id: str
    status: Literal["interrupted", "completed"]
    interrupt: dict | None = None


class IndividualGraphResumeRequest(BaseModel):
    thread_id: str
    payload: dict
```

In service, use stable thread ids:

```python
thread_id = f"individual-{user_id}-cv-{cv_document_id}"
config = {"configurable": {"thread_id": thread_id}}
```

Resume with:

```python
result = graph.invoke(Command(resume=payload), config)
```

- [ ] **Step 5: Run targeted graph tests**

Run:

```bash
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/individual_learning/test_graph.py'
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/individual_learning/graph.py backend/app/modules/individual_learning/schemas.py backend/app/modules/individual_learning/service.py backend/app/modules/individual_learning/routes.py backend/tests/modules/individual_learning/test_graph.py
git commit -m "feat: add individual learning HITL graph"
```

---

## Task 6: Job Search, Market Skills, Matching, And Skill Bank Endpoints

**Files:**
- Create: `backend/app/modules/individual_learning/job_search.py`
- Create: `backend/app/modules/individual_learning/job_matcher.py`
- Modify: `backend/app/modules/individual_learning/neo4j_repository.py`
- Modify: `backend/app/modules/individual_learning/service.py`
- Modify: `backend/app/modules/individual_learning/routes.py`
- Modify: `backend/app/modules/individual_learning/schemas.py`
- Test: `backend/tests/modules/individual_learning/test_service.py`
- Test: `backend/tests/modules/individual_learning/test_neo4j_repository.py`

**Interfaces:**
- Produces: `search_jobs_for_titles(target_titles: list[str], country: str, location: str) -> list[dict]`.
- Produces: `extract_market_skills_for_jobs(jobs: list[dict]) -> dict[str, list[dict]]`.
- Produces: `score_market_skill_coverage(cv_skill_names: list[str], market_skill_names: list[str]) -> list[SkillGapRead]`.
- Produces: `GET /individual-learning/skill-banks`.
- Produces: `POST /individual-learning/interested-jobs`.

- [ ] **Step 1: Write matching test**

In `backend/tests/modules/individual_learning/test_service.py`, add:

```python
from app.modules.individual_learning.job_matcher import score_market_skill_coverage


def test_score_market_skill_coverage_marks_existing_and_gap_skills() -> None:
    scores = score_market_skill_coverage(
        cv_skill_names=["Build APIs with FastAPI", "Query PostgreSQL databases"],
        market_skill_names=["Query PostgreSQL databases", "Deploy services with Docker"],
    )

    by_name = {score.skill_name: score for score in scores}
    assert by_name["Query PostgreSQL databases"].coverage == "covered"
    assert by_name["Deploy services with Docker"].coverage == "gap"
```

- [ ] **Step 2: Run matching test and verify it fails**

Run:

```bash
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/individual_learning/test_service.py::test_score_market_skill_coverage_marks_existing_and_gap_skills'
```

Expected: FAIL because `job_matcher.py` does not exist.

- [ ] **Step 3: Implement deterministic first-pass matcher**

Create `backend/app/modules/individual_learning/job_matcher.py`:

```python
from __future__ import annotations

from pydantic import BaseModel


class SkillGapRead(BaseModel):
    skill_name: str
    coverage: str
    reason: str


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def score_market_skill_coverage(
    *,
    cv_skill_names: list[str],
    market_skill_names: list[str],
) -> list[SkillGapRead]:
    cv_norms = {_norm(name) for name in cv_skill_names}
    scores: list[SkillGapRead] = []
    for skill_name in market_skill_names:
        covered = _norm(skill_name) in cv_norms
        scores.append(
            SkillGapRead(
                skill_name=skill_name,
                coverage="covered" if covered else "gap",
                reason="Exact normalized CV skill match" if covered else "No exact CV skill match",
            )
        )
    return scores
```

Later implementation can replace exact matching with LLM/embedding judging while preserving this return shape.

- [ ] **Step 4: Add skill bank schemas**

In `schemas.py`, add:

```python
class IndividualSkillBankSkill(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None
    is_selected: bool = False
    coverage: Literal["covered", "gap", "partial", "unknown"] = "unknown"


class IndividualSkillBankJobPosting(BaseModel):
    url: str
    title: str
    company: str = ""
    site: str | None = None
    search_term: str | None = None
    is_interested: bool = False
    match_score: float | None = None
    skills: list[IndividualSkillBankSkill] = Field(default_factory=list)


class IndividualSkillBanksResponse(BaseModel):
    market_skill_bank: list[IndividualSkillBankJobPosting] = Field(default_factory=list)
    selected_skill_names: list[str] = Field(default_factory=list)
    interested_posting_urls: list[str] = Field(default_factory=list)
```

- [ ] **Step 5: Implement skill bank Neo4j read**

In `neo4j_repository.py`, add `get_individual_skill_bank()`:

```python
def get_individual_skill_bank(session: Neo4jSession, *, user_id: int) -> dict:
    interested_result = session.run(
        """
        MATCH (u:USER:INDIVIDUAL {id: $user_id})-[r:INTERESTED_IN]->(jp:JOB_POSTING)
        RETURN jp.url AS url
        """,
        user_id=user_id,
    )
    interested_urls = [record["url"] for record in interested_result]

    selected_result = session.run(
        """
        MATCH (:USER:INDIVIDUAL {id: $user_id})-[:SELECTED_SKILL]->(sk:MARKET_SKILL)
        RETURN sk.name AS name
        """,
        user_id=user_id,
    )
    selected_names = [record["name"] for record in selected_result]

    bank_result = session.run(
        """
        MATCH (jp:JOB_POSTING)<-[:SOURCED_FROM]-(ms:MARKET_SKILL)
        WHERE jp.url IN $interested_urls
        RETURN jp {
            .url, .title, .company, .site, .search_term,
            skills: collect(ms { .name, .description, .category })
        } AS posting
        ORDER BY jp.title, jp.company, jp.url
        """,
        interested_urls=interested_urls,
    )
    return {
        "postings": [record["posting"] for record in bank_result],
        "selected_skill_names": selected_names,
        "interested_posting_urls": interested_urls,
    }
```

- [ ] **Step 6: Wire service and routes**

Add endpoints:

```python
@router.get("/skill-banks", response_model=IndividualSkillBanksResponse)
def get_skill_banks(user: IndividualDep, db: DbDep, request: Request) -> IndividualSkillBanksResponse:
    return _service(db, request).get_skill_banks(user.id)


@router.post("/interested-jobs")
def select_interested_jobs(body: SelectInterestedJobsRequest, user: IndividualDep, db: DbDep, request: Request) -> dict:
    count = _service(db, request).select_interested_jobs(user.id, body.posting_urls)
    return {"postings_linked": count}
```

- [ ] **Step 7: Run targeted backend tests**

Run:

```bash
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/individual_learning/test_service.py tests/modules/individual_learning/test_neo4j_repository.py'
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/individual_learning backend/tests/modules/individual_learning/test_service.py backend/tests/modules/individual_learning/test_neo4j_repository.py
git commit -m "feat: add individual job skill bank"
```

---

## Task 7: Individual Skill Selection And Resource Generation

**Files:**
- Modify: `backend/app/modules/individual_learning/neo4j_repository.py`
- Modify: `backend/app/modules/individual_learning/service.py`
- Modify: `backend/app/modules/individual_learning/routes.py`
- Modify: `backend/app/modules/individual_learning/schemas.py`
- Test: `backend/tests/modules/individual_learning/test_service.py`
- Test: `backend/tests/modules/individual_learning/test_routes.py`

**Interfaces:**
- Produces: `POST /individual-learning/select-skills`.
- Produces: `DELETE /individual-learning/select-skills`.
- Produces: `POST /individual-learning/build`.
- Produces: `GET /individual-learning/path`.
- Uses: existing `fetch_readings_for_skill`, `fetch_videos_for_skill`, `generate_questions_for_skill`, `write_resources`, and `write_questions`.

- [ ] **Step 1: Write service validation test**

In `backend/tests/modules/individual_learning/test_service.py`, add:

```python
import pytest

from app.modules.individual_learning.service import IndividualLearningService


def test_select_skills_requires_market_skills() -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)
    with pytest.raises(ValueError, match="Select at least one market skill"):
        service.validate_selected_skill_names([])
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/individual_learning/test_service.py::test_select_skills_requires_market_skills'
```

Expected: FAIL because `validate_selected_skill_names` does not exist.

- [ ] **Step 3: Implement selection validation**

In `service.py`, add:

```python
def validate_selected_skill_names(self, skill_names: list[str]) -> None:
    if not skill_names:
        raise ValueError("Select at least one market skill before building")
    if len(skill_names) > 20:
        raise ValueError("Select no more than 20 market skills before building")
```

Use `neo4j_repository.select_market_skills()` for persistence.

- [ ] **Step 4: Implement individual path read**

In `neo4j_repository.py`, add:

```python
def get_individual_learning_path(session: Neo4jSession, *, user_id: int) -> dict:
    result = session.run(
        """
        MATCH (u:USER:INDIVIDUAL {id: $user_id})-[sel:SELECTED_SKILL]->(sk:MARKET_SKILL)
        OPTIONAL MATCH (sk)-[:HAS_READING]->(rr:READING_RESOURCE)
        OPTIONAL MATCH (sk)-[:HAS_VIDEO]->(vr:VIDEO_RESOURCE)
        OPTIONAL MATCH (sk)-[:HAS_QUESTION]->(q:QUESTION)
        RETURN sk {
            .name,
            .description,
            source: sel.source,
            selected_at: toString(sel.selected_at),
            readings: collect(DISTINCT rr { .id, .title, .url, .domain, .snippet, .search_content, .resource_type, .final_score }),
            videos: collect(DISTINCT vr { .id, .title, .url, .domain, .snippet, .search_content, .video_id, .resource_type, .final_score }),
            questions: collect(DISTINCT q { .id, .text, .difficulty, options: coalesce(q.options, []) })
        } AS skill
        ORDER BY sk.name
        """,
        user_id=user_id,
    )
    skills = [record["skill"] for record in result]
    return {
        "user_id": user_id,
        "selected_skills": skills,
        "total_selected_skills": len(skills),
        "skills_with_resources": sum(
            1 for skill in skills if skill.get("readings") or skill.get("videos")
        ),
    }
```

- [ ] **Step 5: Implement build pipeline service method**

In `service.py`, add `build_learning_path(user_id: int, selected_skill_names: list[str])` that:

1. validates selection count,
2. writes `SELECTED_SKILL` to `MARKET_SKILL`,
3. loads selected market skills from Neo4j,
4. creates `SkillProfile(skill_type="market", ...)`,
5. calls existing readings/videos/question generation functions,
6. writes resources and questions with existing repositories,
7. returns `{"status": "completed"}` for the first synchronous version.

Use async background/SSE only after this synchronous path has targeted tests.

- [ ] **Step 6: Add routes**

Add:

```python
@router.post("/select-skills")
def select_skills(body: SelectIndividualSkillsRequest, user: IndividualDep, db: DbDep, request: Request) -> dict:
    count = _service(db, request).select_skills(user.id, body.skill_names)
    return {"selected": count}


@router.post("/build")
def build_learning_path(body: SelectIndividualSkillsRequest, user: IndividualDep, db: DbDep, request: Request) -> dict:
    return _service(db, request).build_learning_path(user.id, body.skill_names)


@router.get("/path", response_model=IndividualLearningPathResponse)
def get_learning_path(user: IndividualDep, db: DbDep, request: Request) -> IndividualLearningPathResponse:
    return _service(db, request).get_learning_path(user.id)
```

- [ ] **Step 7: Run targeted backend tests**

Run:

```bash
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/individual_learning/test_service.py tests/modules/individual_learning/test_routes.py'
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/individual_learning backend/tests/modules/individual_learning/test_service.py backend/tests/modules/individual_learning/test_routes.py
git commit -m "feat: build individual market skill learning path"
```

---

## Task 8: Frontend Individual Routes, API, And Navigation

**Files:**
- Create: `frontend/src/features/individual-learning/api.ts`
- Create: `frontend/src/features/individual-learning/api.test.ts`
- Create: `frontend/src/features/individual-learning/pages/IndividualOnboardingPage.tsx`
- Create: `frontend/src/features/individual-learning/pages/IndividualProfilePage.tsx`
- Create: `frontend/src/features/individual-learning/pages/IndividualJobsPage.tsx`
- Create: `frontend/src/features/individual-learning/pages/IndividualSkillsPage.tsx`
- Create: `frontend/src/features/individual-learning/pages/IndividualLearningPathPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppSidebar.tsx`
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- Produces: `individualLearningApi.getProfile()`.
- Produces: routes under `/individual/*`.
- Consumes: backend `/individual-learning/*` routes.

- [ ] **Step 1: Write API test**

Create `frontend/src/features/individual-learning/api.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import api from '@/services/api';
import { getIndividualProfile } from './api';

vi.mock('@/services/api', () => ({
  default: {
    get: vi.fn(),
  },
}));

describe('individual learning api', () => {
  it('loads the individual profile', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({
      data: { user_id: 7, onboarding_status: 'needs_cv', target_titles: [] },
    });

    const profile = await getIndividualProfile();

    expect(api.get).toHaveBeenCalledWith('/individual-learning/profile');
    expect(profile.onboarding_status).toBe('needs_cv');
  });
});
```

- [ ] **Step 2: Run API test and verify it fails**

Run:

```bash
docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/individual-learning/api.test.ts'
```

Expected: FAIL because `api.ts` does not exist.

- [ ] **Step 3: Implement API client**

Create `frontend/src/features/individual-learning/api.ts`:

```ts
import api from '@/services/api';

const BASE = '/individual-learning';

export interface IndividualProfile {
  user_id: number;
  onboarding_status:
    | 'needs_cv'
    | 'extracting'
    | 'needs_profile_review'
    | 'needs_jobs'
    | 'needs_skill_selection'
    | 'ready'
    | 'error';
  target_titles: string[];
  preferred_country?: string | null;
  preferred_location?: string | null;
  reviewed_at?: string | null;
}

export async function getIndividualProfile(): Promise<IndividualProfile> {
  const { data } = await api.get(`${BASE}/profile`);
  return data;
}

export interface IndividualSkillBankSkill {
  name: string;
  description?: string | null;
  category?: string | null;
  is_selected?: boolean;
  coverage?: 'covered' | 'gap' | 'partial' | 'unknown';
}

export interface IndividualSkillBankJobPosting {
  url: string;
  title: string;
  company: string;
  site?: string | null;
  search_term?: string | null;
  is_interested: boolean;
  match_score?: number | null;
  skills: IndividualSkillBankSkill[];
}

export interface IndividualSkillBanksResponse {
  market_skill_bank: IndividualSkillBankJobPosting[];
  selected_skill_names: string[];
  interested_posting_urls: string[];
}

export interface IndividualLearningPathResponse {
  user_id: number;
  selected_skills: Array<{
    name: string;
    description?: string | null;
    source?: string | null;
    readings: Array<{ id: string; title: string; url: string; domain?: string | null }>;
    videos: Array<{ id: string; title: string; url: string; domain?: string | null; video_id?: string | null }>;
    questions: Array<{ id: string; text: string; difficulty: 'easy' | 'medium' | 'hard'; options: string[] }>;
  }>;
  total_selected_skills: number;
  skills_with_resources: number;
}

export async function uploadCv(file: File): Promise<{ id: number; status: string }> {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await api.post(`${BASE}/cv`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function getIndividualSkillBanks(): Promise<IndividualSkillBanksResponse> {
  const { data } = await api.get(`${BASE}/skill-banks`);
  return data;
}

export async function selectInterestedJobs(postingUrls: string[]): Promise<{ postings_linked: number }> {
  const { data } = await api.post(`${BASE}/interested-jobs`, { posting_urls: postingUrls });
  return data;
}

export async function selectIndividualSkills(skillNames: string[]): Promise<{ selected: number }> {
  const { data } = await api.post(`${BASE}/select-skills`, { skill_names: skillNames });
  return data;
}

export async function buildIndividualLearningPath(skillNames: string[]): Promise<{ status: string }> {
  const { data } = await api.post(`${BASE}/build`, { skill_names: skillNames });
  return data;
}

export async function getIndividualLearningPath(): Promise<IndividualLearningPathResponse> {
  const { data } = await api.get(`${BASE}/path`);
  return data;
}
```

- [ ] **Step 4: Add page shells that call real APIs**

Create each page with a minimal real UI:

```tsx
export default function IndividualOnboardingPage() {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <h1 className="text-2xl font-semibold">CV onboarding</h1>
    </main>
  );
}
```

Use imports from `@/` and Shadcn components. Avoid inline styles.

- [ ] **Step 5: Wire routes**

In `frontend/src/App.tsx`, import pages and add protected routes:

```tsx
<Route path="/individual/onboarding" element={<ProtectedRoute><IndividualOnboardingPage /></ProtectedRoute>} />
<Route path="/individual/profile" element={<ProtectedRoute><IndividualProfilePage /></ProtectedRoute>} />
<Route path="/individual/jobs" element={<ProtectedRoute><IndividualJobsPage /></ProtectedRoute>} />
<Route path="/individual/skills" element={<ProtectedRoute><IndividualSkillsPage /></ProtectedRoute>} />
<Route path="/individual/learning-path" element={<ProtectedRoute><IndividualLearningPathPage /></ProtectedRoute>} />
```

- [ ] **Step 6: Update sidebar**

In `AppSidebar.tsx`, add individual menu items when `user?.role === "individual"`:

```ts
const individualItems = [
  { title: "Dashboard", url: "/home", icon: LayoutDashboard },
  { title: "CV Profile", url: "/individual/profile", icon: User },
  { title: "Job Matches", url: "/individual/jobs", icon: BriefcaseBusiness },
  { title: "Skill Selection", url: "/individual/skills", icon: ListChecks },
  { title: "Learning Path", url: "/individual/learning-path", icon: Route },
];
```

Render `individualItems` instead of `globalItems` for individual users.

- [ ] **Step 7: Run targeted frontend tests**

Run:

```bash
docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/individual-learning/api.test.ts src/App.test.tsx'
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/features/individual-learning frontend/src/App.tsx frontend/src/components/layout/AppSidebar.tsx
git commit -m "feat: add individual learning frontend shell"
```

---

## Task 9: Frontend CV Review, Job Selection, Skill Selection, And Learning Path

**Files:**
- Modify: `frontend/src/features/individual-learning/pages/IndividualOnboardingPage.tsx`
- Modify: `frontend/src/features/individual-learning/pages/IndividualProfilePage.tsx`
- Modify: `frontend/src/features/individual-learning/pages/IndividualJobsPage.tsx`
- Modify: `frontend/src/features/individual-learning/pages/IndividualSkillsPage.tsx`
- Modify: `frontend/src/features/individual-learning/pages/IndividualLearningPathPage.tsx`
- Test: `frontend/src/features/individual-learning/pages/IndividualOnboardingPage.test.tsx`
- Test: `frontend/src/features/individual-learning/pages/IndividualSkillsPage.test.tsx`
- Test: `frontend/src/features/individual-learning/pages/IndividualLearningPathPage.test.tsx`

**Interfaces:**
- Consumes: `individual-learning/api.ts`.
- Reuses: student skill-selection mental model from `StudentLearningPathPage.tsx`.

- [ ] **Step 1: Write skill-selection UI test**

Create `frontend/src/features/individual-learning/pages/IndividualSkillsPage.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import IndividualSkillsPage from './IndividualSkillsPage';

vi.mock('../api', () => ({
  getIndividualSkillBanks: vi.fn().mockResolvedValue({
    market_skill_bank: [
      {
        url: 'https://example.test/job',
        title: 'Data Analyst',
        company: 'ExampleCo',
        is_interested: true,
        skills: [{ name: 'Query relational databases using SQL', is_selected: false }],
      },
    ],
    selected_skill_names: [],
    interested_posting_urls: ['https://example.test/job'],
  }),
}));

describe('IndividualSkillsPage', () => {
  it('renders market skills grouped by job posting', async () => {
    render(<IndividualSkillsPage />);
    expect(await screen.findByText('Data Analyst')).toBeInTheDocument();
    expect(await screen.findByText('Query relational databases using SQL')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run page test and verify it fails**

Run:

```bash
docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/individual-learning/pages/IndividualSkillsPage.test.tsx'
```

Expected: FAIL because the page shell does not render the market skill bank yet.

- [ ] **Step 3: Implement onboarding upload**

Use `FileUpload` or the existing file input pattern. Accept:

```ts
accept=".pdf,.docx"
```

Call:

```ts
await uploadCv(file)
```

Navigate to `/individual/profile` when upload succeeds.

- [ ] **Step 4: Implement profile review**

Render extracted CV profile data, target title suggestions, and editable target titles. The submit button should call graph resume with:

```ts
{
  approved: true,
  target_titles: editedTitles,
}
```

Navigate to `/individual/jobs` after resume.

- [ ] **Step 5: Implement job and skill screens**

For jobs:

- render `JOB_POSTING` cards
- show title, company, site/search term, score, and skill gaps
- allow interested-job selection

For skills:

- render postings as accordion items
- include "Select all skills" button
- render skill chips
- keep draft selected skill state local until build
- persist only `MARKET_SKILL` names

- [ ] **Step 6: Implement learning path screen**

Render selected skills as top-level sections with:

- readings
- videos
- questions
- pending/empty states

Do not render course chapters.

- [ ] **Step 7: Run targeted frontend tests**

Run:

```bash
docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/individual-learning/pages/IndividualSkillsPage.test.tsx src/features/individual-learning/pages/IndividualLearningPathPage.test.tsx'
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/features/individual-learning
git commit -m "feat: build individual learning UI"
```

---

## Task 10: Full Verification And Integration

**Files:**
- Modify only files needed to fix integration failures from the previous tasks.

**Interfaces:**
- Verifies full backend and frontend behavior.
- Produces final implementation-ready branch state.

- [ ] **Step 1: Run backend targeted tests**

Run:

```bash
docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/individual_learning'
```

Expected: PASS.

- [ ] **Step 2: Run backend lint and format checks**

Run:

```bash
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/ruff check . && /app/.venv/bin/ruff format --check .'
```

Expected: PASS.

- [ ] **Step 3: Run frontend targeted tests**

Run:

```bash
docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/individual-learning src/App.test.tsx'
```

Expected: PASS.

- [ ] **Step 4: Run frontend lint and build**

Run:

```bash
docker exec lab_tutor_frontend sh -lc 'cd /app && npm run lint && npm run build'
```

Expected: PASS.

- [ ] **Step 5: Manual smoke path**

Run the app locally or in the existing Docker environment and verify:

1. Register page shows `Individual`.
2. New individual user can sign in.
3. Individual sidebar shows CV Profile, Job Matches, Skill Selection, and Learning Path.
4. PDF CV upload reaches profile review.
5. DOCX CV upload reaches profile review.
6. User can add target titles.
7. User can select interested job postings.
8. User can select market skills from postings.
9. Learning path groups resources by selected market skill.
10. CV skills are visible as profile evidence and are not selectable for learning.

- [ ] **Step 6: Commit integration fixes**

If Step 1 through Step 5 required changes:

```bash
git add backend frontend
git commit -m "fix: integrate individual learning flow"
```

If no changes were needed, do not create an empty commit.
