# Course Readiness Prerequisite Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a teacher-gated course readiness flow where students can discover and enroll only after the teacher completes book skill selection, market skill confirmation, prerequisite graph review, and publication.

**Architecture:** Keep SQL as the publication and review-state source of truth, and keep Neo4j as the approved prerequisite graph projection. The existing prerequisite LangGraph generates a draft into SQL; the live Neo4j `PREREQUISITE` graph is replaced only when the teacher approves the draft. The teacher course hub becomes the readiness command center with deep links to agent workspaces and a dedicated prerequisite review page.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Pydantic v2, LangGraph, Neo4j Cypher, React 19, Vite, TypeScript strict, TailwindCSS v4, Shadcn UI, Vitest, Docker.

---

## Source Spec

- `docs/superpowers/specs/2026-05-20-course-readiness-prerequisite-review-design.md`

## File Structure

Backend course readiness:

- Modify `backend/app/modules/courses/models.py` for course publication status and a compact market gate marker.
- Modify `backend/app/modules/courses/schemas.py` for `CourseRead`, readiness DTOs, and publish responses.
- Modify `backend/app/modules/courses/repository.py` for published-only listing and course updates.
- Create `backend/app/modules/courses/readiness_service.py` for gate computation and publish/unpublish business rules.
- Modify `backend/app/modules/courses/service.py` so student discovery and joining use effective availability.
- Modify `backend/app/modules/courses/routes.py` for readiness, publish, unpublish, and market-waiver endpoints.
- Modify `backend/main.py` for idempotent SQL upgrades and model imports.
- Test with `backend/tests/modules/courses/test_course_readiness.py`.

Backend prerequisite review:

- Create `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/review_models.py` for one review metadata row per course.
- Create `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/review_repository.py` for SQL review draft persistence and skill snapshots.
- Create `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/validation.py` for edge validation, cycle detection, and isolated-skill calculation.
- Create `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/review_service.py` for review, save, regenerate, invalidate, and approve operations.
- Modify `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/schemas.py` for review DTOs.
- Modify `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/nodes.py` and `graph.py` so generation finalizes draft candidates instead of writing live Neo4j edges.
- Modify `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/service.py` to capture final LangGraph edges and save a SQL draft.
- Modify `backend/app/modules/curricularalignmentarchitect/api_routes/skill_prerequisites.py` for review endpoints.
- Modify `backend/app/modules/curricularalignmentarchitect/api_routes/agentic_analysis.py` and `backend/app/modules/marketdemandanalyst/routes.py` so rebuild triggers invalidate prerequisite approval.
- Test with `backend/tests/modules/test_skill_prerequisite_review.py` and update `backend/tests/modules/test_skill_prerequisite_auto_trigger.py`.

Frontend:

- Modify `frontend/src/features/courses/types.ts` for publication, readiness, and prerequisite review DTOs.
- Modify `frontend/src/features/courses/api.ts` for readiness, publish, market waiver, and prerequisite review calls.
- Modify `frontend/src/features/agents/config.ts` to add the separate Prerequisite Review launcher.
- Modify `frontend/src/features/courses/pages/AgentHubPage.tsx` to render the Course Readiness Road above agents.
- Create `frontend/src/features/courses/components/readiness/CourseReadinessRoad.tsx`.
- Create `frontend/src/features/courses/components/readiness/NextActionBanner.tsx`.
- Create `frontend/src/features/courses/components/readiness/ReadinessGateTrack.tsx`.
- Create `frontend/src/features/courses/components/readiness/PublishCourseButton.tsx`.
- Create `frontend/src/features/prerequisite-review/pages/PrerequisiteReviewPage.tsx`.
- Create `frontend/src/features/prerequisite-review/components/PrerequisiteEdgeWorklist.tsx`.
- Create `frontend/src/features/prerequisite-review/components/PrerequisiteGraphPreview.tsx`.
- Create `frontend/src/features/prerequisite-review/components/IsolatedSkillsPanel.tsx`.
- Create `frontend/src/features/prerequisite-review/components/AddPrerequisiteEdgeDialog.tsx`.
- Create `frontend/src/features/prerequisite-review/lib/prerequisiteGraph.ts`.
- Modify `frontend/src/App.tsx` to add `/courses/:id/prerequisites`.
- Test with `frontend/src/features/courses/components/readiness/CourseReadinessRoad.test.tsx`, `frontend/src/features/prerequisite-review/pages/PrerequisiteReviewPage.test.tsx`, and existing course tests.

## API Contract

Teacher readiness endpoint:

```http
GET /courses/{course_id}/readiness
```

Response:

```json
{
  "course_id": 1,
  "publication_status": "draft",
  "availability_status": "draft",
  "can_publish": false,
  "blockers": ["Complete the market skill bank.", "Review prerequisites."],
  "next_action": {
    "id": "market",
    "label": "Continue Market Demand Analyst",
    "route": "/courses/1/market-analyst"
  },
  "gates": [
    {
      "id": "book",
      "label": "Book skill bank",
      "status": "complete",
      "route": "/courses/1/architect"
    }
  ],
  "prerequisite_review": {
    "status": "needs_review",
    "edge_count": 12,
    "isolated_skill_count": 4,
    "last_generated_at": "2026-05-20T04:00:00Z"
  }
}
```

Teacher prerequisite review endpoints, under the existing `book_selection_router` prefix:

```http
GET  /book-selection/courses/{course_id}/skill-prerequisites/review
PUT  /book-selection/courses/{course_id}/skill-prerequisites/review
POST /book-selection/courses/{course_id}/skill-prerequisites/approve
POST /book-selection/courses/{course_id}/skill-prerequisites/regenerate
```

Review response:

```json
{
  "course_id": 1,
  "status": "needs_review",
  "is_rebuilding": false,
  "skills": [
    {"name": "SQL joins", "source": "book", "chapter_title": "Relational data"}
  ],
  "draft_edges": [
    {
      "prerequisite_name": "SQL basics",
      "dependent_name": "SQL joins",
      "confidence": "high",
      "reasoning": "Students need SELECT and table concepts before joins.",
      "source": "ai"
    }
  ],
  "isolated_skills": ["Database indexing"],
  "validation": {
    "is_valid": true,
    "errors": [],
    "cycle_path": []
  },
  "metadata": {
    "edge_count": 1,
    "generated_edge_count": 1,
    "added_edge_count": 0,
    "removed_edge_count": 0,
    "isolated_skill_count": 1,
    "last_generated_at": "2026-05-20T04:00:00Z",
    "last_invalidated_at": null,
    "approved_at": null
  }
}
```

---

### Task 1: Backend Publication Status And Student Visibility

**Files:**
- Modify: `backend/app/modules/courses/models.py`
- Modify: `backend/app/modules/courses/schemas.py`
- Modify: `backend/app/modules/courses/repository.py`
- Modify: `backend/app/modules/courses/service.py`
- Modify: `backend/app/modules/courses/routes.py`
- Modify: `backend/main.py`
- Create: `backend/tests/modules/courses/test_course_readiness.py`

- [ ] **Step 1: Write failing backend tests for draft visibility and join blocking**

Create `backend/tests/modules/courses/test_course_readiness.py`:

```python
from app.modules.courses.models import Course, CoursePublicationStatus


def _create_course(client, teacher_auth_headers, title="Readiness Course") -> int:
    response = client.post(
        "/courses",
        json={"title": title, "description": "Course used by readiness tests"},
        headers=teacher_auth_headers,
    )
    assert response.status_code == 201
    return int(response.json()["id"])


def _publish_course_directly(db_session, course_id: int) -> None:
    course = db_session.get(Course, course_id)
    assert course is not None
    course.publication_status = CoursePublicationStatus.PUBLISHED
    db_session.add(course)
    db_session.commit()


def test_new_course_is_draft_and_hidden_from_student_catalog(
    client,
    teacher_auth_headers,
):
    course_id = _create_course(client, teacher_auth_headers)

    teacher_response = client.get("/courses/my", headers=teacher_auth_headers)
    assert teacher_response.status_code == 200
    teacher_course = next(c for c in teacher_response.json() if c["id"] == course_id)
    assert teacher_course["publication_status"] == "draft"

    public_response = client.get("/courses")
    assert public_response.status_code == 200
    assert all(c["id"] != course_id for c in public_response.json())


def test_student_join_rejects_draft_course(
    client,
    teacher_auth_headers,
    student_auth_headers,
):
    course_id = _create_course(client, teacher_auth_headers)

    response = client.post(f"/courses/{course_id}/join", headers=student_auth_headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Course is not available for enrollment"


def test_student_catalog_and_join_allow_published_course(
    client,
    db_session,
    teacher_auth_headers,
    student_auth_headers,
):
    course_id = _create_course(client, teacher_auth_headers, title="Published Course")
    _publish_course_directly(db_session, course_id)

    public_response = client.get("/courses")
    assert public_response.status_code == 200
    assert any(c["id"] == course_id for c in public_response.json())

    join_response = client.post(
        f"/courses/{course_id}/join",
        headers=student_auth_headers,
    )
    assert join_response.status_code == 201
    assert join_response.json()["course_id"] == course_id
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
docker start lab_tutor_postgres lab_tutor_backend
docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/courses/test_course_readiness.py'
```

Expected: tests fail because `CoursePublicationStatus` and `publication_status` do not exist.

- [ ] **Step 3: Add publication status to the course model and schemas**

Modify `backend/app/modules/courses/models.py`:

```python
class CoursePublicationStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
```

Add to `Course`:

```python
    publication_status: Mapped[CoursePublicationStatus] = mapped_column(
        SqlEnum(
            CoursePublicationStatus,
            name="course_publication_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=CoursePublicationStatus.DRAFT,
        nullable=False,
    )
```

Modify `backend/app/modules/courses/schemas.py`:

```python
from .models import (
    CourseLevel,
    CoursePublicationStatus,
    ExtractionStatus,
    FileProcessingStatus,
)
```

Add to `CourseRead`:

```python
    publication_status: CoursePublicationStatus
```

- [ ] **Step 4: Add idempotent SQL upgrade for existing databases**

Modify `backend/main.py` inside `_ensure_sql_schema_upgrades()` after the existing `courses.level` check:

```python
        publication_type_exists = conn.execute(
            text("SELECT 1 FROM pg_type WHERE typname = 'course_publication_status'")
        ).fetchone()
        if not publication_type_exists:
            conn.execute(
                text("CREATE TYPE course_publication_status AS ENUM ('draft', 'published')")
            )

        publication_col_exists = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'courses' AND column_name = 'publication_status'"
            )
        ).fetchone()
        if not publication_col_exists:
            conn.execute(
                text(
                    "ALTER TABLE courses ADD COLUMN publication_status "
                    "course_publication_status NOT NULL DEFAULT 'draft'"
                )
            )
```

- [ ] **Step 5: Filter public course listing and block draft joins**

Modify `backend/app/modules/courses/repository.py`:

```python
from .models import Course, CourseEnrollment, CourseFile, CoursePublicationStatus, FileProcessingStatus
```

Add:

```python
    def list_published(self) -> Sequence[Course]:
        return self.db.scalars(
            select(Course)
            .where(Course.publication_status == CoursePublicationStatus.PUBLISHED)
            .order_by(Course.created_at.desc())
        ).all()
```

Modify `backend/app/modules/courses/service.py` imports:

```python
from .models import (
    Course,
    CourseEnrollment,
    CourseFile,
    CoursePublicationStatus,
    ExtractionStatus,
    FileProcessingStatus,
)
```

Modify `list_courses()`:

```python
    def list_courses(self) -> list[Course]:
        return list(self._repo.list_published())
```

Modify `join_course()` immediately after `course = self.get_course(course_id)`:

```python
        if course.publication_status != CoursePublicationStatus.PUBLISHED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Course is not available for enrollment",
            )
```

- [ ] **Step 6: Run the tests until Task 1 passes**

Run:

```bash
docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/courses/test_course_readiness.py'
```

Expected: 3 passed.

- [ ] **Step 7: Commit Task 1**

Run:

```bash
git add backend/app/modules/courses/models.py backend/app/modules/courses/schemas.py backend/app/modules/courses/repository.py backend/app/modules/courses/service.py backend/main.py backend/tests/modules/courses/test_course_readiness.py
git commit -m "feat: gate student course discovery by publication status"
```

---

### Task 2: Backend Prerequisite Review Model And Validation

**Files:**
- Create: `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/review_models.py`
- Create: `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/validation.py`
- Create: `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/review_repository.py`
- Modify: `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/schemas.py`
- Modify: `backend/main.py`
- Create: `backend/tests/modules/test_skill_prerequisite_review.py`

- [ ] **Step 1: Write failing validation tests**

Create `backend/tests/modules/test_skill_prerequisite_review.py`:

```python
from app.modules.curricularalignmentarchitect.skill_prerequisites.schemas import (
    PrerequisiteDraftEdge,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.validation import (
    compute_isolated_skills,
    validate_prerequisite_edges,
)


SKILLS = ["SQL basics", "SQL joins", "Indexes"]


def edge(prereq: str, dependent: str) -> PrerequisiteDraftEdge:
    return PrerequisiteDraftEdge(
        prerequisite_name=prereq,
        dependent_name=dependent,
        confidence="high",
        reasoning="test edge",
        source="teacher",
    )


def test_validate_prerequisite_edges_rejects_unknown_skill():
    result = validate_prerequisite_edges(
        skill_names=SKILLS,
        edges=[edge("SQL basics", "Missing skill")],
    )

    assert result.is_valid is False
    assert result.errors == ["Unknown skill in edge: SQL basics -> Missing skill"]


def test_validate_prerequisite_edges_rejects_self_edge():
    result = validate_prerequisite_edges(
        skill_names=SKILLS,
        edges=[edge("SQL basics", "SQL basics")],
    )

    assert result.is_valid is False
    assert result.errors == ["Self prerequisite is not allowed: SQL basics"]


def test_validate_prerequisite_edges_rejects_duplicate_edges():
    result = validate_prerequisite_edges(
        skill_names=SKILLS,
        edges=[edge("SQL basics", "SQL joins"), edge("SQL basics", "SQL joins")],
    )

    assert result.is_valid is False
    assert result.errors == ["Duplicate prerequisite edge: SQL basics -> SQL joins"]


def test_validate_prerequisite_edges_rejects_cycle_with_path():
    result = validate_prerequisite_edges(
        skill_names=SKILLS,
        edges=[
            edge("SQL basics", "SQL joins"),
            edge("SQL joins", "Indexes"),
            edge("Indexes", "SQL basics"),
        ],
    )

    assert result.is_valid is False
    assert result.cycle_path == ["SQL basics", "SQL joins", "Indexes", "SQL basics"]


def test_compute_isolated_skills_keeps_standalone_skills_visible_not_invalid():
    result = validate_prerequisite_edges(
        skill_names=SKILLS,
        edges=[edge("SQL basics", "SQL joins")],
    )

    assert result.is_valid is True
    assert compute_isolated_skills(SKILLS, [edge("SQL basics", "SQL joins")]) == ["Indexes"]
```

- [ ] **Step 2: Run validation tests and confirm they fail**

Run:

```bash
docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/test_skill_prerequisite_review.py'
```

Expected: import failure for `PrerequisiteDraftEdge` or `validation`.

- [ ] **Step 3: Add review schemas**

Modify `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/schemas.py`:

```python
from datetime import datetime
from enum import StrEnum
```

Add below existing schema classes:

```python
class PrerequisiteReviewStatus(StrEnum):
    NOT_STARTED = "not_started"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    STALE = "stale"


class PrerequisiteDraftEdge(BaseModel):
    prerequisite_name: str
    dependent_name: str
    confidence: Literal["high", "medium", "low"]
    reasoning: str
    source: Literal["ai", "teacher"] = "ai"


class PrerequisiteSkillRead(BaseModel):
    name: str
    source: str
    chapter_title: str | None = None


class PrerequisiteValidationRead(BaseModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    cycle_path: list[str] = Field(default_factory=list)


class PrerequisiteReviewMetadata(BaseModel):
    edge_count: int
    generated_edge_count: int
    added_edge_count: int
    removed_edge_count: int
    isolated_skill_count: int
    last_generated_at: datetime | None = None
    last_invalidated_at: datetime | None = None
    approved_at: datetime | None = None


class PrerequisiteReviewRead(BaseModel):
    course_id: int
    status: PrerequisiteReviewStatus
    is_rebuilding: bool
    skills: list[PrerequisiteSkillRead]
    draft_edges: list[PrerequisiteDraftEdge]
    isolated_skills: list[str]
    validation: PrerequisiteValidationRead
    metadata: PrerequisiteReviewMetadata


class PrerequisiteReviewUpdate(BaseModel):
    draft_edges: list[PrerequisiteDraftEdge]
    isolated_skills_viewed: bool = False
```

- [ ] **Step 4: Add pure validation helpers**

Create `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/validation.py`:

```python
from __future__ import annotations

from .schemas import PrerequisiteDraftEdge, PrerequisiteValidationRead


def compute_isolated_skills(
    skill_names: list[str],
    edges: list[PrerequisiteDraftEdge],
) -> list[str]:
    connected: set[str] = set()
    for edge in edges:
        connected.add(edge.prerequisite_name)
        connected.add(edge.dependent_name)
    return sorted(name for name in skill_names if name not in connected)


def validate_prerequisite_edges(
    *,
    skill_names: list[str],
    edges: list[PrerequisiteDraftEdge],
) -> PrerequisiteValidationRead:
    errors: list[str] = []
    skill_set = set(skill_names)
    seen: set[tuple[str, str]] = set()

    for edge in edges:
        pair = (edge.prerequisite_name, edge.dependent_name)
        if edge.prerequisite_name not in skill_set or edge.dependent_name not in skill_set:
            errors.append(
                f"Unknown skill in edge: {edge.prerequisite_name} -> {edge.dependent_name}"
            )
            continue
        if edge.prerequisite_name == edge.dependent_name:
            errors.append(f"Self prerequisite is not allowed: {edge.prerequisite_name}")
            continue
        if pair in seen:
            errors.append(
                f"Duplicate prerequisite edge: {edge.prerequisite_name} -> {edge.dependent_name}"
            )
            continue
        seen.add(pair)

    cycle_path = _find_cycle_path(edges)
    if cycle_path:
        errors.append(f"Cycle detected: {' -> '.join(cycle_path)}")

    return PrerequisiteValidationRead(
        is_valid=not errors,
        errors=errors,
        cycle_path=cycle_path,
    )


def _find_cycle_path(edges: list[PrerequisiteDraftEdge]) -> list[str]:
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge.prerequisite_name, []).append(edge.dependent_name)

    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> list[str]:
        if node in visiting:
            start = stack.index(node)
            return stack[start:] + [node]
        if node in visited:
            return []

        visiting.add(node)
        stack.append(node)
        for neighbor in adjacency.get(node, []):
            cycle = visit(neighbor)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return []

    for node in sorted(adjacency):
        cycle = visit(node)
        if cycle:
            return cycle
    return []
```

- [ ] **Step 5: Add SQL review model and import it at startup**

Create `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/review_models.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .schemas import PrerequisiteReviewStatus


class PrerequisiteReview(Base):
    __tablename__ = "prerequisite_reviews"

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id"),
        primary_key=True,
    )
    review_status: Mapped[PrerequisiteReviewStatus] = mapped_column(
        SqlEnum(
            PrerequisiteReviewStatus,
            name="prerequisite_review_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=PrerequisiteReviewStatus.NOT_STARTED,
        nullable=False,
    )
    is_rebuilding: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    draft_edges: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    isolated_skills_viewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    edge_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generated_edge_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    added_edge_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    removed_edge_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    isolated_skill_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
```

Modify `backend/main.py` imports:

```python
import app.modules.curricularalignmentarchitect.skill_prerequisites.review_models  # noqa: E402
```

- [ ] **Step 6: Add review repository**

Create `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/review_repository.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .review_models import PrerequisiteReview
from .schemas import PrerequisiteDraftEdge, PrerequisiteReviewStatus


class PrerequisiteReviewRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, course_id: int) -> PrerequisiteReview | None:
        return self.db.get(PrerequisiteReview, course_id)

    def get_or_create(self, course_id: int) -> PrerequisiteReview:
        review = self.get(course_id)
        if review is not None:
            return review
        review = PrerequisiteReview(course_id=course_id)
        self.db.add(review)
        self.db.flush()
        self.db.refresh(review)
        return review

    def save_draft(
        self,
        *,
        course_id: int,
        edges: list[PrerequisiteDraftEdge],
        status: PrerequisiteReviewStatus,
        isolated_skill_count: int,
        generated_edge_count: int | None = None,
        added_edge_count: int | None = None,
        removed_edge_count: int | None = None,
        isolated_skills_viewed: bool | None = None,
    ) -> PrerequisiteReview:
        review = self.get_or_create(course_id)
        review.review_status = status
        review.draft_edges = [edge.model_dump() for edge in edges]
        review.edge_count = len(edges)
        review.isolated_skill_count = isolated_skill_count
        if generated_edge_count is not None:
            review.generated_edge_count = generated_edge_count
        if added_edge_count is not None:
            review.added_edge_count = added_edge_count
        if removed_edge_count is not None:
            review.removed_edge_count = removed_edge_count
        if isolated_skills_viewed is not None:
            review.isolated_skills_viewed = isolated_skills_viewed
        self.db.add(review)
        self.db.flush()
        self.db.refresh(review)
        return review

    def mark_generated(
        self,
        *,
        course_id: int,
        edges: list[PrerequisiteDraftEdge],
        isolated_skill_count: int,
    ) -> PrerequisiteReview:
        review = self.save_draft(
            course_id=course_id,
            edges=edges,
            status=PrerequisiteReviewStatus.NEEDS_REVIEW,
            isolated_skill_count=isolated_skill_count,
            generated_edge_count=len(edges),
            isolated_skills_viewed=False,
        )
        review.is_rebuilding = False
        review.last_generated_at = datetime.now(UTC)
        review.approved_at = None
        review.approved_by = None
        self.db.add(review)
        self.db.flush()
        self.db.refresh(review)
        return review

    def mark_rebuilding(self, course_id: int) -> PrerequisiteReview:
        review = self.get_or_create(course_id)
        review.is_rebuilding = True
        self.db.add(review)
        self.db.flush()
        self.db.refresh(review)
        return review

    def mark_stale(self, course_id: int) -> PrerequisiteReview:
        review = self.get_or_create(course_id)
        if review.review_status == PrerequisiteReviewStatus.APPROVED:
            review.review_status = PrerequisiteReviewStatus.STALE
        review.last_invalidated_at = datetime.now(UTC)
        self.db.add(review)
        self.db.flush()
        self.db.refresh(review)
        return review

    def mark_approved(
        self,
        *,
        course_id: int,
        teacher_id: int,
        added_edge_count: int,
        removed_edge_count: int,
    ) -> PrerequisiteReview:
        review = self.get_or_create(course_id)
        review.review_status = PrerequisiteReviewStatus.APPROVED
        review.approved_by = teacher_id
        review.approved_at = datetime.now(UTC)
        review.added_edge_count = added_edge_count
        review.removed_edge_count = removed_edge_count
        review.is_rebuilding = False
        self.db.add(review)
        self.db.flush()
        self.db.refresh(review)
        return review


def draft_edges_from_review(review: PrerequisiteReview | None) -> list[PrerequisiteDraftEdge]:
    if review is None:
        return []
    return [PrerequisiteDraftEdge.model_validate(edge) for edge in review.draft_edges]


def skill_names_from_rows(rows: Sequence[dict]) -> list[str]:
    return sorted({str(row["name"]) for row in rows if row.get("name")})
```

- [ ] **Step 7: Add idempotent SQL upgrade for review table**

Modify `backend/main.py` inside `_ensure_sql_schema_upgrades()` near other enum checks:

```python
        review_type_exists = conn.execute(
            text("SELECT 1 FROM pg_type WHERE typname = 'prerequisite_review_status'")
        ).fetchone()
        if not review_type_exists:
            conn.execute(
                text(
                    "CREATE TYPE prerequisite_review_status AS ENUM "
                    "('not_started', 'needs_review', 'approved', 'stale')"
                )
            )

        review_table_exists = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'prerequisite_reviews'"
            )
        ).fetchone()
        if not review_table_exists:
            conn.execute(
                text(
                    "CREATE TABLE prerequisite_reviews ("
                    "course_id INTEGER PRIMARY KEY REFERENCES courses(id), "
                    "review_status prerequisite_review_status NOT NULL DEFAULT 'not_started', "
                    "is_rebuilding BOOLEAN NOT NULL DEFAULT false, "
                    "draft_edges JSONB NOT NULL DEFAULT '[]'::jsonb, "
                    "isolated_skills_viewed BOOLEAN NOT NULL DEFAULT false, "
                    "approved_by INTEGER REFERENCES users(id), "
                    "approved_at TIMESTAMPTZ, "
                    "edge_count INTEGER NOT NULL DEFAULT 0, "
                    "generated_edge_count INTEGER NOT NULL DEFAULT 0, "
                    "added_edge_count INTEGER NOT NULL DEFAULT 0, "
                    "removed_edge_count INTEGER NOT NULL DEFAULT 0, "
                    "isolated_skill_count INTEGER NOT NULL DEFAULT 0, "
                    "last_generated_at TIMESTAMPTZ, "
                    "last_invalidated_at TIMESTAMPTZ, "
                    "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                    "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                    ")"
                )
            )
```

- [ ] **Step 8: Run validation tests until Task 2 passes**

Run:

```bash
docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/test_skill_prerequisite_review.py'
```

Expected: 5 passed.

- [ ] **Step 9: Commit Task 2**

Run:

```bash
git add backend/app/modules/curricularalignmentarchitect/skill_prerequisites/review_models.py backend/app/modules/curricularalignmentarchitect/skill_prerequisites/review_repository.py backend/app/modules/curricularalignmentarchitect/skill_prerequisites/validation.py backend/app/modules/curricularalignmentarchitect/skill_prerequisites/schemas.py backend/main.py backend/tests/modules/test_skill_prerequisite_review.py
git commit -m "feat: add prerequisite review draft model"
```

---

### Task 3: Backend Review Service, Routes, Draft Generation, And Approval

**Files:**
- Modify: `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/repository.py`
- Modify: `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/nodes.py`
- Modify: `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/graph.py`
- Modify: `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/service.py`
- Create: `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/review_service.py`
- Modify: `backend/app/modules/curricularalignmentarchitect/api_routes/skill_prerequisites.py`
- Modify: `backend/tests/modules/test_skill_prerequisite_auto_trigger.py`
- Modify: `backend/tests/modules/test_skill_prerequisite_review.py`

- [ ] **Step 1: Add failing tests for draft save and approval writes**

Append to `backend/tests/modules/test_skill_prerequisite_review.py`:

```python
from app.modules.curricularalignmentarchitect.skill_prerequisites.review_service import (
    PrerequisiteReviewService,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.schemas import (
    PrerequisiteReviewStatus,
)


class FakeCourse:
    id = 42
    teacher_id = 7


class FakeCourseRepository:
    def get_by_id(self, course_id: int):
        assert course_id == 42
        return FakeCourse()


class FakeReviewRepository:
    def __init__(self):
        self.review = None

    def get(self, course_id: int):
        return self.review

    def mark_generated(self, *, course_id: int, edges, isolated_skill_count: int):
        self.review = type(
            "Review",
            (),
            {
                "course_id": course_id,
                "review_status": PrerequisiteReviewStatus.NEEDS_REVIEW,
                "is_rebuilding": False,
                "draft_edges": [edge.model_dump() for edge in edges],
                "isolated_skills_viewed": False,
                "edge_count": len(edges),
                "generated_edge_count": len(edges),
                "added_edge_count": 0,
                "removed_edge_count": 0,
                "isolated_skill_count": isolated_skill_count,
                "last_generated_at": None,
                "last_invalidated_at": None,
                "approved_at": None,
            },
        )()
        return self.review

    def save_draft(
        self,
        *,
        course_id: int,
        edges,
        status,
        isolated_skill_count: int,
        isolated_skills_viewed: bool,
        added_edge_count: int = 0,
        removed_edge_count: int = 0,
    ):
        self.review.draft_edges = [edge.model_dump() for edge in edges]
        self.review.review_status = status
        self.review.isolated_skills_viewed = isolated_skills_viewed
        self.review.edge_count = len(edges)
        self.review.isolated_skill_count = isolated_skill_count
        self.review.added_edge_count = added_edge_count
        self.review.removed_edge_count = removed_edge_count
        return self.review

    def mark_approved(self, *, course_id: int, teacher_id: int, added_edge_count: int, removed_edge_count: int):
        self.review.review_status = PrerequisiteReviewStatus.APPROVED
        self.review.approved_by = teacher_id
        return self.review


class FakeNeo4jRepository:
    def __init__(self):
        self.written_edges = []

    def load_skills(self, course_id: int):
        assert course_id == 42
        return [
            {"name": "SQL basics", "source": "book", "chapter_title": "Intro"},
            {"name": "SQL joins", "source": "book", "chapter_title": "Queries"},
            {"name": "Indexes", "source": "market", "chapter_title": "Performance"},
        ]

    def replace_approved_edges(self, course_id: int, edges):
        self.written_edges = list(edges)
        return len(self.written_edges)


def test_review_service_saves_generated_draft_not_live_graph():
    review_repo = FakeReviewRepository()
    graph_repo = FakeNeo4jRepository()
    service = PrerequisiteReviewService(
        course_repo=FakeCourseRepository(),
        review_repo=review_repo,
        graph_repo=graph_repo,
    )

    result = service.save_generated_draft(
        course_id=42,
        edges=[edge("SQL basics", "SQL joins")],
    )

    assert result.status == PrerequisiteReviewStatus.NEEDS_REVIEW
    assert graph_repo.written_edges == []
    assert result.draft_edges[0].prerequisite_name == "SQL basics"
    assert result.isolated_skills == ["Indexes"]


def test_review_service_approval_validates_and_writes_live_graph():
    review_repo = FakeReviewRepository()
    graph_repo = FakeNeo4jRepository()
    service = PrerequisiteReviewService(
        course_repo=FakeCourseRepository(),
        review_repo=review_repo,
        graph_repo=graph_repo,
    )
    service.save_generated_draft(course_id=42, edges=[edge("SQL basics", "SQL joins")])

    result = service.save_teacher_draft(
        course_id=42,
        edges=[
            edge("SQL basics", "SQL joins"),
            edge("SQL joins", "Indexes"),
        ],
        isolated_skills_viewed=True,
    )
    assert result.validation.is_valid is True

    approved = service.approve(course_id=42, teacher_id=7)

    assert approved.status == PrerequisiteReviewStatus.APPROVED
    assert graph_repo.written_edges == [
        {
            "prereq_name": "SQL basics",
            "dependent_name": "SQL joins",
            "confidence": "high",
            "reasoning": "test edge",
        },
        {
            "prereq_name": "SQL joins",
            "dependent_name": "Indexes",
            "confidence": "high",
            "reasoning": "test edge",
        },
    ]
```

- [ ] **Step 2: Run tests and confirm review service is missing**

Run:

```bash
docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/test_skill_prerequisite_review.py'
```

Expected: import failure for `review_service`.

- [ ] **Step 3: Add Neo4j helpers for review service**

Modify `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/repository.py`:

```python
def replace_skill_prerequisites(driver: Driver, course_id: int, edges: list[dict]) -> int:
    clear_skill_prerequisites(driver, course_id)
    return write_skill_prerequisites(driver, edges)


def load_review_skills_for_course(driver: Driver, course_id: int) -> list[dict]:
    skills = load_all_skills_for_course(driver, course_id)
    rows: dict[str, dict] = {}
    for skill in skills:
        name = skill.get("name")
        if not name:
            continue
        rows[str(name)] = {
            "name": str(name),
            "source": str(skill.get("skill_type") or "unknown"),
            "chapter_title": skill.get("chapter_title"),
        }
    return sorted(rows.values(), key=lambda row: row["name"].lower())
```

- [ ] **Step 4: Change LangGraph persist node into a draft-finalize node**

Modify `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/nodes.py` imports by removing live write imports:

```python
from .repository import (
    load_all_skills_for_course,
    load_skills_without_embeddings,
    merge_skill_into_canonical,
    write_skill_embeddings,
)
```

Replace `persist()` with:

```python
def finalize_generation(state: SkillPrerequisiteState) -> dict:
    write = get_stream_writer()
    final_edges = state.get("final_edges", [])
    write(
        {
            "type": "prerequisite_generated",
            "edge_count": len(final_edges),
            "final_edges": final_edges,
        }
    )
    logger.info(
        "Course %d: generated %d prerequisite draft edges.",
        state["course_id"],
        len(final_edges),
    )
    return {}
```

Modify `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/graph.py` imports and nodes:

```python
from .nodes import (
    api_retry_policy,
    build_cluster_fanout,
    embed_missing,
    enforce_dag,
    finalize_generation,
    find_and_merge_dupes,
    judge_cluster,
    load_skills_for_clustering,
    synthesize,
)
```

Replace node registration and edge:

```python
    builder.add_node("finalize_generation", finalize_generation)
    builder.add_edge("enforce_dag", "finalize_generation")
    builder.add_edge("finalize_generation", END)
```

- [ ] **Step 5: Add review service**

Create `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/review_service.py`:

```python
from __future__ import annotations

from fastapi import HTTPException, status
from neo4j import Driver

from app.modules.courses.repository import CourseRepository

from .repository import load_review_skills_for_course, replace_skill_prerequisites
from .review_repository import (
    PrerequisiteReviewRepository,
    draft_edges_from_review,
    skill_names_from_rows,
)
from .schemas import (
    PrerequisiteDraftEdge,
    PrerequisiteReviewMetadata,
    PrerequisiteReviewRead,
    PrerequisiteReviewStatus,
)
from .validation import compute_isolated_skills, validate_prerequisite_edges


class PrerequisiteReviewGraphRepository:
    def load_skills(self, course_id: int) -> list[dict]:
        raise NotImplementedError

    def replace_approved_edges(self, course_id: int, edges: list[dict]) -> int:
        raise NotImplementedError


class Neo4jPrerequisiteReviewRepository(PrerequisiteReviewGraphRepository):
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def load_skills(self, course_id: int) -> list[dict]:
        return load_review_skills_for_course(self._driver, course_id)

    def replace_approved_edges(self, course_id: int, edges: list[dict]) -> int:
        return replace_skill_prerequisites(self._driver, course_id, edges)


class PrerequisiteReviewService:
    def __init__(
        self,
        *,
        course_repo: CourseRepository,
        review_repo: PrerequisiteReviewRepository,
        graph_repo: PrerequisiteReviewGraphRepository,
    ) -> None:
        self._course_repo = course_repo
        self._review_repo = review_repo
        self._graph_repo = graph_repo

    def _load_course(self, course_id: int):
        course = self._course_repo.get_by_id(course_id)
        if course is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        return course

    def require_teacher(self, course_id: int, teacher_id: int) -> None:
        course = self._load_course(course_id)
        if course.teacher_id != teacher_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this course")

    def get_review(self, course_id: int) -> PrerequisiteReviewRead:
        self._load_course(course_id)
        review = self._review_repo.get(course_id)
        skills = self._graph_repo.load_skills(course_id)
        skill_names = skill_names_from_rows(skills)
        draft_edges = draft_edges_from_review(review)
        isolated = compute_isolated_skills(skill_names, draft_edges)
        validation = validate_prerequisite_edges(skill_names=skill_names, edges=draft_edges)
        status_value = review.review_status if review else PrerequisiteReviewStatus.NOT_STARTED
        return PrerequisiteReviewRead(
            course_id=course_id,
            status=status_value,
            is_rebuilding=bool(review.is_rebuilding) if review else False,
            skills=skills,
            draft_edges=draft_edges,
            isolated_skills=isolated,
            validation=validation,
            metadata=PrerequisiteReviewMetadata(
                edge_count=len(draft_edges),
                generated_edge_count=review.generated_edge_count if review else 0,
                added_edge_count=review.added_edge_count if review else 0,
                removed_edge_count=review.removed_edge_count if review else 0,
                isolated_skill_count=len(isolated),
                last_generated_at=review.last_generated_at if review else None,
                last_invalidated_at=review.last_invalidated_at if review else None,
                approved_at=review.approved_at if review else None,
            ),
        )

    def save_generated_draft(
        self,
        *,
        course_id: int,
        edges: list[PrerequisiteDraftEdge],
    ) -> PrerequisiteReviewRead:
        self._load_course(course_id)
        skills = self._graph_repo.load_skills(course_id)
        skill_names = skill_names_from_rows(skills)
        isolated = compute_isolated_skills(skill_names, edges)
        self._review_repo.mark_generated(
            course_id=course_id,
            edges=edges,
            isolated_skill_count=len(isolated),
        )
        return self.get_review(course_id)

    def save_teacher_draft(
        self,
        *,
        course_id: int,
        edges: list[PrerequisiteDraftEdge],
        isolated_skills_viewed: bool,
    ) -> PrerequisiteReviewRead:
        self._load_course(course_id)
        skills = self._graph_repo.load_skills(course_id)
        skill_names = skill_names_from_rows(skills)
        isolated = compute_isolated_skills(skill_names, edges)
        current = self._review_repo.get(course_id)
        generated_count = current.generated_edge_count if current else 0
        added_count = max(len(edges) - generated_count, 0)
        removed_count = max(generated_count - len(edges), 0)
        self._review_repo.save_draft(
            course_id=course_id,
            edges=edges,
            status=PrerequisiteReviewStatus.NEEDS_REVIEW,
            isolated_skill_count=len(isolated),
            isolated_skills_viewed=isolated_skills_viewed,
            added_edge_count=added_count,
            removed_edge_count=removed_count,
        )
        return self.get_review(course_id)

    def approve(self, *, course_id: int, teacher_id: int) -> PrerequisiteReviewRead:
        self.require_teacher(course_id, teacher_id)
        review = self._review_repo.get(course_id)
        if review is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No prerequisite draft to approve")
        if review.is_rebuilding:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Prerequisites are still rebuilding")
        edges = draft_edges_from_review(review)
        skills = self._graph_repo.load_skills(course_id)
        skill_names = skill_names_from_rows(skills)
        validation = validate_prerequisite_edges(skill_names=skill_names, edges=edges)
        if not validation.is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=validation.model_dump())
        if compute_isolated_skills(skill_names, edges) and not review.isolated_skills_viewed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Review isolated skills before approval")

        normalized = [
            {
                "prereq_name": edge.prerequisite_name,
                "dependent_name": edge.dependent_name,
                "confidence": edge.confidence,
                "reasoning": edge.reasoning,
            }
            for edge in edges
        ]
        self._graph_repo.replace_approved_edges(course_id, normalized)
        self._review_repo.mark_approved(
            course_id=course_id,
            teacher_id=teacher_id,
            added_edge_count=review.added_edge_count,
            removed_edge_count=review.removed_edge_count,
        )
        return self.get_review(course_id)

    def invalidate(self, course_id: int) -> None:
        self._review_repo.mark_stale(course_id)
```

- [ ] **Step 6: Wire real graph repository and review routes**

Modify `backend/app/modules/curricularalignmentarchitect/api_routes/skill_prerequisites.py` imports:

```python
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.courses.repository import CourseRepository
from ..skill_prerequisites.repository import get_skill_prerequisites
from ..skill_prerequisites.review_repository import PrerequisiteReviewRepository
from ..skill_prerequisites.review_service import (
    Neo4jPrerequisiteReviewRepository,
    PrerequisiteReviewService,
)
from ..skill_prerequisites.schemas import PrerequisiteReviewRead, PrerequisiteReviewUpdate
from ..skill_prerequisites.service import (
    run_skill_prerequisites,
    schedule_skill_prerequisite_rebuild,
)
```

Add helper dependency:

```python
def _review_service(db: Session) -> PrerequisiteReviewService:
    driver = create_neo4j_driver()
    if driver is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j is not configured",
        )
    return PrerequisiteReviewService(
        course_repo=CourseRepository(db),
        review_repo=PrerequisiteReviewRepository(db),
        graph_repo=Neo4jPrerequisiteReviewRepository(driver),
    )
```

Inside `register_routes(router)`, add:

```python
    @router.get(
        "/courses/{course_id}/skill-prerequisites/review",
        response_model=PrerequisiteReviewRead,
    )
    def get_prerequisite_review(
        course_id: int,
        teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ):
        service = _review_service(db)
        service.require_teacher(course_id, teacher.id)
        return service.get_review(course_id)

    @router.put(
        "/courses/{course_id}/skill-prerequisites/review",
        response_model=PrerequisiteReviewRead,
    )
    def save_prerequisite_review(
        course_id: int,
        body: PrerequisiteReviewUpdate,
        teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ):
        service = _review_service(db)
        service.require_teacher(course_id, teacher.id)
        result = service.save_teacher_draft(
            course_id=course_id,
            edges=body.draft_edges,
            isolated_skills_viewed=body.isolated_skills_viewed,
        )
        db.commit()
        return result

    @router.post(
        "/courses/{course_id}/skill-prerequisites/approve",
        response_model=PrerequisiteReviewRead,
    )
    def approve_prerequisite_review(
        course_id: int,
        teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ):
        service = _review_service(db)
        result = service.approve(course_id=course_id, teacher_id=teacher.id)
        db.commit()
        return result

    @router.post(
        "/courses/{course_id}/skill-prerequisites/regenerate",
        status_code=status.HTTP_202_ACCEPTED,
    )
    def regenerate_prerequisite_review(
        course_id: int,
        teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ):
        service = _review_service(db)
        service.require_teacher(course_id, teacher.id)
        PrerequisiteReviewRepository(db).mark_rebuilding(course_id)
        db.commit()
        schedule_skill_prerequisite_rebuild(course_id, "manual_regenerate")
        return {"message": "Prerequisite regeneration started"}
```

- [ ] **Step 7: Save generated LangGraph edges as review draft**

Modify `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/service.py` imports:

```python
from app.core.database import SessionLocal
from app.core.neo4j import create_neo4j_driver
from app.modules.courses.repository import CourseRepository

from .review_repository import PrerequisiteReviewRepository
from .review_service import Neo4jPrerequisiteReviewRepository, PrerequisiteReviewService
from .schemas import PrerequisiteDraftEdge
```

Inside `run_skill_prerequisites()`, capture final edges from custom events:

```python
        generated_edges: list[PrerequisiteDraftEdge] = []
        async for mode, chunk in graph.astream(
            _initial_state(course_id),
            stream_mode=["custom", "updates"],
            config={"max_concurrency": MAX_CONCURRENCY},
        ):
            if mode != "custom":
                continue
            payload = dict(chunk) if isinstance(chunk, dict) else {"value": chunk}
            if payload.get("type") == "prerequisite_generated":
                generated_edges = [
                    PrerequisiteDraftEdge(
                        prerequisite_name=edge["prerequisite_skill"],
                        dependent_name=edge["dependent_skill"],
                        confidence=edge["confidence"],
                        reasoning=edge["reasoning"],
                        source="ai",
                    )
                    for edge in payload.get("final_edges", [])
                ]
            event_type = str(payload.get("type") or "prerequisite_progress")
            payload.setdefault("course_id", course_id)
            payload["trigger_reason"] = trigger_reason
            payload["auto_triggered"] = auto_triggered
            await _emit(emit_event, event_type, payload)

        _save_generated_review_draft(course_id, generated_edges)
        await _emit(
            emit_event,
            "prerequisite_completed",
            {**event_context, "draft_edges": len(generated_edges)},
        )
        return True
```

Add helper in the same file:

```python
def _save_generated_review_draft(
    course_id: int,
    generated_edges: list[PrerequisiteDraftEdge],
) -> None:
    driver = create_neo4j_driver()
    if driver is None:
        return
    db = SessionLocal()
    try:
        service = PrerequisiteReviewService(
            course_repo=CourseRepository(db),
            review_repo=PrerequisiteReviewRepository(db),
            graph_repo=Neo4jPrerequisiteReviewRepository(driver),
        )
        service.save_generated_draft(course_id=course_id, edges=generated_edges)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        driver.close()
```

- [ ] **Step 8: Update auto-trigger tests for draft semantics**

Modify `backend/tests/modules/test_skill_prerequisite_auto_trigger.py`, `test_run_skill_prerequisites_emits_auto_trigger_metadata`, fake graph chunk:

```python
            yield "custom", {
                "type": "prerequisite_generated",
                "final_edges": [
                    {
                        "prerequisite_skill": "A",
                        "dependent_skill": "B",
                        "confidence": "high",
                        "reasoning": "A before B",
                    }
                ],
            }
```

Add monkeypatch before calling service:

```python
    saved: list[tuple[int, int]] = []
    monkeypatch.setattr(
        service_mod,
        "_save_generated_review_draft",
        lambda course_id, generated_edges: saved.append((course_id, len(generated_edges))),
    )
```

Update assertions:

```python
    assert events[-1][0] == "prerequisite_completed"
    assert events[-1][1]["draft_edges"] == 1
    assert saved == [(11, 1)]
```

- [ ] **Step 9: Run prerequisite tests**

Run:

```bash
docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/test_skill_prerequisite_review.py tests/modules/test_skill_prerequisite_auto_trigger.py'
```

Expected: all selected tests pass.

- [ ] **Step 10: Commit Task 3**

Run:

```bash
git add backend/app/modules/curricularalignmentarchitect/skill_prerequisites backend/app/modules/curricularalignmentarchitect/api_routes/skill_prerequisites.py backend/tests/modules/test_skill_prerequisite_review.py backend/tests/modules/test_skill_prerequisite_auto_trigger.py
git commit -m "feat: review prerequisites before graph approval"
```

---

### Task 4: Backend Readiness Gates, Publish, Unpublish, And Invalidation

**Files:**
- Modify: `backend/app/modules/courses/models.py`
- Modify: `backend/app/modules/courses/schemas.py`
- Create: `backend/app/modules/courses/readiness_service.py`
- Modify: `backend/app/modules/courses/service.py`
- Modify: `backend/app/modules/courses/routes.py`
- Modify: `backend/app/modules/curricularalignmentarchitect/api_routes/agentic_analysis.py`
- Modify: `backend/app/modules/marketdemandanalyst/routes.py`
- Modify: `backend/main.py`
- Modify: `backend/tests/modules/courses/test_course_readiness.py`
- Modify: `backend/tests/modules/test_skill_prerequisite_auto_trigger.py`

- [ ] **Step 1: Add failing readiness and publish tests**

Append to `backend/tests/modules/courses/test_course_readiness.py`:

```python
from app.modules.courses.models import CourseMarketGateStatus
from app.modules.curricularalignmentarchitect.models import BookSelectionSession, SessionStatus
from app.modules.curricularalignmentarchitect.skill_prerequisites.review_models import (
    PrerequisiteReview,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.schemas import (
    PrerequisiteReviewStatus,
)


def _mark_book_gate_complete(db_session, course_id: int) -> None:
    db_session.add(
        BookSelectionSession(
            course_id=course_id,
            thread_id=f"book-session-{course_id}",
            status=SessionStatus.COMPLETED,
        )
    )
    db_session.commit()


def _mark_market_gate_complete(db_session, course_id: int) -> None:
    course = db_session.get(Course, course_id)
    assert course is not None
    course.market_gate_status = CourseMarketGateStatus.COMPLETED
    db_session.add(course)
    db_session.commit()


def _mark_prerequisites_approved(db_session, course_id: int) -> None:
    db_session.add(
        PrerequisiteReview(
            course_id=course_id,
            review_status=PrerequisiteReviewStatus.APPROVED,
            draft_edges=[],
            isolated_skills_viewed=True,
        )
    )
    db_session.commit()


def test_readiness_returns_next_action_and_blockers(
    client,
    teacher_auth_headers,
):
    course_id = _create_course(client, teacher_auth_headers)

    response = client.get(
        f"/courses/{course_id}/readiness",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["can_publish"] is False
    assert data["next_action"]["id"] == "book"
    assert "Complete the book skill bank." in data["blockers"]
    assert data["gates"][0]["id"] == "book"


def test_publish_rejects_incomplete_gates(
    client,
    teacher_auth_headers,
):
    course_id = _create_course(client, teacher_auth_headers)

    response = client.post(
        f"/courses/{course_id}/publish",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 400
    assert "Complete the book skill bank." in response.json()["detail"]["blockers"]


def test_publish_succeeds_when_all_required_gates_pass(
    client,
    db_session,
    teacher_auth_headers,
):
    course_id = _create_course(client, teacher_auth_headers)
    _mark_book_gate_complete(db_session, course_id)
    _mark_market_gate_complete(db_session, course_id)
    _mark_prerequisites_approved(db_session, course_id)

    response = client.post(
        f"/courses/{course_id}/publish",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["publication_status"] == "published"


def test_stale_prerequisites_pause_new_enrollment_without_removing_existing_student(
    client,
    db_session,
    teacher_auth_headers,
    student_auth_headers,
):
    course_id = _create_course(client, teacher_auth_headers)
    _mark_book_gate_complete(db_session, course_id)
    _mark_market_gate_complete(db_session, course_id)
    _mark_prerequisites_approved(db_session, course_id)
    publish_response = client.post(f"/courses/{course_id}/publish", headers=teacher_auth_headers)
    assert publish_response.status_code == 200
    join_response = client.post(f"/courses/{course_id}/join", headers=student_auth_headers)
    assert join_response.status_code == 201

    review = db_session.get(PrerequisiteReview, course_id)
    assert review is not None
    review.review_status = PrerequisiteReviewStatus.STALE
    db_session.add(review)
    db_session.commit()

    public_response = client.get("/courses")
    assert all(c["id"] != course_id for c in public_response.json())

    enrolled_response = client.get("/courses/enrolled", headers=student_auth_headers)
    assert any(c["id"] == course_id for c in enrolled_response.json())
```

In the existing `test_student_catalog_and_join_allow_published_course`, add the three gate helpers before `_publish_course_directly(db_session, course_id)` so the test still represents an effectively available course after this task:

```python
    _mark_book_gate_complete(db_session, course_id)
    _mark_market_gate_complete(db_session, course_id)
    _mark_prerequisites_approved(db_session, course_id)
```

- [ ] **Step 2: Run tests and confirm readiness endpoints fail**

Run:

```bash
docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/courses/test_course_readiness.py'
```

Expected: failures for missing `CourseMarketGateStatus` and `/readiness`.

- [ ] **Step 3: Add compact market gate status to course**

Modify `backend/app/modules/courses/models.py`:

```python
class CourseMarketGateStatus(StrEnum):
    NOT_STARTED = "not_started"
    COMPLETED = "completed"
    WAIVED = "waived"
```

Add to `Course`:

```python
    market_gate_status: Mapped[CourseMarketGateStatus] = mapped_column(
        SqlEnum(
            CourseMarketGateStatus,
            name="course_market_gate_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=CourseMarketGateStatus.NOT_STARTED,
        nullable=False,
    )
```

Modify `backend/app/modules/courses/schemas.py` imports and `CourseRead`:

```python
from .models import (
    CourseLevel,
    CourseMarketGateStatus,
    CoursePublicationStatus,
    ExtractionStatus,
    FileProcessingStatus,
)
```

```python
    market_gate_status: CourseMarketGateStatus
```

- [ ] **Step 4: Add readiness DTOs**

Modify `backend/app/modules/courses/schemas.py`:

```python
from typing import Literal
```

Add:

```python
GateStatus = Literal["locked", "ready", "complete", "blocked"]
AvailabilityStatus = Literal["draft", "published", "publishing_paused"]
NextActionId = Literal["book", "market", "prerequisites", "publish", "none"]


class ReadinessNextAction(BaseModel):
    id: NextActionId
    label: str
    route: str | None = None


class ReadinessGate(BaseModel):
    id: Literal["book", "market", "prerequisites", "publish"]
    label: str
    status: GateStatus
    route: str | None = None
    detail: str


class PrerequisiteReviewSummary(BaseModel):
    status: str
    edge_count: int
    isolated_skill_count: int
    last_generated_at: datetime | None = None


class CourseReadinessRead(BaseModel):
    course_id: int
    publication_status: CoursePublicationStatus
    availability_status: AvailabilityStatus
    can_publish: bool
    blockers: list[str]
    next_action: ReadinessNextAction
    gates: list[ReadinessGate]
    prerequisite_review: PrerequisiteReviewSummary
```

- [ ] **Step 5: Implement readiness service**

Create `backend/app/modules/courses/readiness_service.py`:

```python
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.curricularalignmentarchitect.models import (
    BookSelectionSession,
    SessionStatus,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.review_models import (
    PrerequisiteReview,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.schemas import (
    PrerequisiteReviewStatus,
)

from .models import Course, CourseMarketGateStatus, CoursePublicationStatus
from .schemas import (
    CourseReadinessRead,
    PrerequisiteReviewSummary,
    ReadinessGate,
    ReadinessNextAction,
)


class CourseReadinessService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _get_course(self, course_id: int) -> Course:
        course = self._db.get(Course, course_id)
        if course is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        return course

    def require_teacher(self, course_id: int, teacher_id: int) -> Course:
        course = self._get_course(course_id)
        if course.teacher_id != teacher_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this course")
        return course

    def get_readiness(self, course_id: int) -> CourseReadinessRead:
        course = self._get_course(course_id)
        book_complete = self._book_gate_complete(course_id)
        market_complete = course.market_gate_status in (
            CourseMarketGateStatus.COMPLETED,
            CourseMarketGateStatus.WAIVED,
        )
        review = self._db.get(PrerequisiteReview, course_id)
        prereq_status = review.review_status if review else PrerequisiteReviewStatus.NOT_STARTED
        prereq_complete = prereq_status == PrerequisiteReviewStatus.APPROVED

        blockers: list[str] = []
        if not book_complete:
            blockers.append("Complete the book skill bank.")
        if not market_complete:
            blockers.append("Complete the market skill bank.")
        if not prereq_complete:
            blockers.append("Review prerequisites.")

        can_publish = not blockers
        availability_status = "published"
        if course.publication_status == CoursePublicationStatus.DRAFT:
            availability_status = "draft"
        elif not can_publish:
            availability_status = "publishing_paused"

        next_action = self._next_action(course_id, book_complete, market_complete, prereq_complete, can_publish)
        gates = [
            ReadinessGate(
                id="book",
                label="Book skill bank",
                status="complete" if book_complete else "ready",
                route=f"/courses/{course_id}/architect",
                detail="Selected book skills are ready." if book_complete else "Choose books and finish skill mapping.",
            ),
            ReadinessGate(
                id="market",
                label="Job market skills",
                status="complete" if market_complete else ("ready" if book_complete else "locked"),
                route=f"/courses/{course_id}/market-analyst",
                detail="Market skill input is complete." if market_complete else "Confirm job-market skills for this course.",
            ),
            ReadinessGate(
                id="prerequisites",
                label="Prerequisite review",
                status="complete" if prereq_complete else ("ready" if book_complete and market_complete else "locked"),
                route=f"/courses/{course_id}/prerequisites",
                detail="Teacher-approved prerequisite graph." if prereq_complete else "Review the AI-generated prerequisite draft.",
            ),
            ReadinessGate(
                id="publish",
                label="Publish course",
                status="complete" if course.publication_status == CoursePublicationStatus.PUBLISHED and can_publish else ("ready" if can_publish else "locked"),
                route=None,
                detail="Students can discover and enroll." if course.publication_status == CoursePublicationStatus.PUBLISHED and can_publish else "Publish when all readiness gates pass.",
            ),
        ]

        return CourseReadinessRead(
            course_id=course_id,
            publication_status=course.publication_status,
            availability_status=availability_status,
            can_publish=can_publish,
            blockers=blockers,
            next_action=next_action,
            gates=gates,
            prerequisite_review=PrerequisiteReviewSummary(
                status=str(prereq_status.value),
                edge_count=review.edge_count if review else 0,
                isolated_skill_count=review.isolated_skill_count if review else 0,
                last_generated_at=review.last_generated_at if review else None,
            ),
        )

    def publish(self, course_id: int, teacher_id: int) -> Course:
        course = self.require_teacher(course_id, teacher_id)
        readiness = self.get_readiness(course_id)
        if not readiness.can_publish:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"blockers": readiness.blockers},
            )
        course.publication_status = CoursePublicationStatus.PUBLISHED
        self._db.add(course)
        self._db.commit()
        self._db.refresh(course)
        return course

    def unpublish(self, course_id: int, teacher_id: int) -> Course:
        course = self.require_teacher(course_id, teacher_id)
        course.publication_status = CoursePublicationStatus.DRAFT
        self._db.add(course)
        self._db.commit()
        self._db.refresh(course)
        return course

    def mark_market_gate_complete(self, course_id: int) -> None:
        course = self._get_course(course_id)
        course.market_gate_status = CourseMarketGateStatus.COMPLETED
        self._db.add(course)
        self._db.commit()

    def waive_market_gate(self, course_id: int, teacher_id: int) -> Course:
        course = self.require_teacher(course_id, teacher_id)
        course.market_gate_status = CourseMarketGateStatus.WAIVED
        self._db.add(course)
        self._db.commit()
        self._db.refresh(course)
        return course

    def is_effectively_available(self, course_id: int) -> bool:
        course = self._get_course(course_id)
        if course.publication_status != CoursePublicationStatus.PUBLISHED:
            return False
        return self.get_readiness(course_id).can_publish

    def _book_gate_complete(self, course_id: int) -> bool:
        session = self._db.scalar(
            select(BookSelectionSession)
            .where(BookSelectionSession.course_id == course_id)
            .order_by(BookSelectionSession.created_at.desc())
        )
        return bool(session and session.status == SessionStatus.COMPLETED)

    def _next_action(
        self,
        course_id: int,
        book_complete: bool,
        market_complete: bool,
        prereq_complete: bool,
        can_publish: bool,
    ) -> ReadinessNextAction:
        if not book_complete:
            return ReadinessNextAction(id="book", label="Continue Curricular Alignment Architect", route=f"/courses/{course_id}/architect")
        if not market_complete:
            return ReadinessNextAction(id="market", label="Continue Market Demand Analyst", route=f"/courses/{course_id}/market-analyst")
        if not prereq_complete:
            return ReadinessNextAction(id="prerequisites", label="Review prerequisites", route=f"/courses/{course_id}/prerequisites")
        if can_publish:
            return ReadinessNextAction(id="publish", label="Publish course", route=None)
        return ReadinessNextAction(id="none", label="Course is ready", route=None)
```

- [ ] **Step 6: Wire readiness routes and effective availability**

Modify `backend/app/modules/courses/routes.py` imports:

```python
from .readiness_service import CourseReadinessService
from .schemas import (
    CourseCreate,
    CourseFileRead,
    CourseRead,
    CourseReadinessRead,
    EnrollmentRead,
    StartExtractionResponse,
    UploadPresentationsResponse,
)
```

Add routes after `get_course()`:

```python
@router.get("/{course_id}/readiness", response_model=CourseReadinessRead)
def get_course_readiness(
    course_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    service = CourseReadinessService(db)
    service.require_teacher(course_id, teacher.id)
    return service.get_readiness(course_id)


@router.post("/{course_id}/publish", response_model=CourseRead)
def publish_course(
    course_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    return CourseReadinessService(db).publish(course_id, teacher.id)


@router.post("/{course_id}/unpublish", response_model=CourseRead)
def unpublish_course(
    course_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    return CourseReadinessService(db).unpublish(course_id, teacher.id)


@router.post("/{course_id}/market-gate/waive", response_model=CourseRead)
def waive_market_gate(
    course_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    return CourseReadinessService(db).waive_market_gate(course_id, teacher.id)
```

Add `Session` and `get_db` imports to `routes.py`:

```python
from sqlalchemy.orm import Session
from app.core.database import get_db
```

Modify `backend/app/modules/courses/service.py` constructor to accept db already available through repo. Inside `join_course()` replace publication-only check with:

```python
        from .readiness_service import CourseReadinessService

        if not CourseReadinessService(self._repo.db).is_effectively_available(course.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Course is not available for enrollment",
            )
```

Modify `list_courses()`:

```python
    def list_courses(self) -> list[Course]:
        readiness = CourseReadinessService(self._repo.db)
        return [
            course
            for course in self._repo.list_published()
            if readiness.is_effectively_available(course.id)
        ]
```

- [ ] **Step 7: Add market gate SQL upgrade**

Modify `backend/main.py` near the publication status upgrade:

```python
        market_gate_type_exists = conn.execute(
            text("SELECT 1 FROM pg_type WHERE typname = 'course_market_gate_status'")
        ).fetchone()
        if not market_gate_type_exists:
            conn.execute(
                text(
                    "CREATE TYPE course_market_gate_status AS ENUM "
                    "('not_started', 'completed', 'waived')"
                )
            )

        market_gate_col_exists = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'courses' AND column_name = 'market_gate_status'"
            )
        ).fetchone()
        if not market_gate_col_exists:
            conn.execute(
                text(
                    "ALTER TABLE courses ADD COLUMN market_gate_status "
                    "course_market_gate_status NOT NULL DEFAULT 'not_started'"
                )
            )
```

- [ ] **Step 8: Mark prerequisites stale and market gate complete on input changes**

Modify `backend/app/modules/curricularalignmentarchitect/api_routes/agentic_analysis.py` where `schedule_skill_prerequisite_rebuild(course_id, "book_skill_mapping")` is called. Add before scheduling:

```python
            from app.modules.curricularalignmentarchitect.skill_prerequisites.review_repository import (
                PrerequisiteReviewRepository,
            )

            PrerequisiteReviewRepository(db).mark_stale(course_id)
            db.commit()
```

Modify `backend/app/modules/marketdemandanalyst/routes.py` inside `_schedule_skill_prerequisite_rebuild()`:

```python
    from app.core.database import SessionLocal
    from app.modules.courses.readiness_service import CourseReadinessService
    from app.modules.curricularalignmentarchitect.skill_prerequisites.review_repository import (
        PrerequisiteReviewRepository,
    )

    db = SessionLocal()
    try:
        CourseReadinessService(db).mark_market_gate_complete(course_id)
        PrerequisiteReviewRepository(db).mark_stale(course_id)
        db.commit()
    finally:
        db.close()
```

Keep the existing scheduling call after this block.

- [ ] **Step 9: Run readiness tests**

Run:

```bash
docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/courses/test_course_readiness.py tests/modules/test_skill_prerequisite_auto_trigger.py'
```

Expected: all selected tests pass.

- [ ] **Step 10: Commit Task 4**

Run:

```bash
git add backend/app/modules/courses backend/app/modules/curricularalignmentarchitect/api_routes/agentic_analysis.py backend/app/modules/marketdemandanalyst/routes.py backend/main.py backend/tests/modules/courses/test_course_readiness.py backend/tests/modules/test_skill_prerequisite_auto_trigger.py
git commit -m "feat: add course readiness publication gates"
```

---

### Task 5: Frontend Readiness API And Course Hub Road

**Files:**
- Modify: `frontend/src/features/courses/types.ts`
- Modify: `frontend/src/features/courses/api.ts`
- Modify: `frontend/src/features/agents/config.ts`
- Modify: `frontend/src/features/courses/pages/AgentHubPage.tsx`
- Create: `frontend/src/features/courses/components/readiness/CourseReadinessRoad.tsx`
- Create: `frontend/src/features/courses/components/readiness/NextActionBanner.tsx`
- Create: `frontend/src/features/courses/components/readiness/ReadinessGateTrack.tsx`
- Create: `frontend/src/features/courses/components/readiness/PublishCourseButton.tsx`
- Create: `frontend/src/features/courses/components/readiness/CourseReadinessRoad.test.tsx`

- [ ] **Step 1: Write failing readiness road tests**

Create `frontend/src/features/courses/components/readiness/CourseReadinessRoad.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { CourseReadinessRoad } from './CourseReadinessRoad';
import { coursesApi } from '../../api';
import type { CourseReadiness } from '../../types';

vi.mock('../../api', () => ({
  coursesApi: {
    publish: vi.fn(),
    unpublish: vi.fn(),
    getReadiness: vi.fn(),
  },
}));

const readiness: CourseReadiness = {
  course_id: 7,
  publication_status: 'draft',
  availability_status: 'draft',
  can_publish: false,
  blockers: ['Review prerequisites.'],
  next_action: {
    id: 'prerequisites',
    label: 'Review prerequisites',
    route: '/courses/7/prerequisites',
  },
  gates: [
    {
      id: 'book',
      label: 'Book skill bank',
      status: 'complete',
      route: '/courses/7/architect',
      detail: 'Selected book skills are ready.',
    },
    {
      id: 'market',
      label: 'Job market skills',
      status: 'complete',
      route: '/courses/7/market-analyst',
      detail: 'Market skill input is complete.',
    },
    {
      id: 'prerequisites',
      label: 'Prerequisite review',
      status: 'ready',
      route: '/courses/7/prerequisites',
      detail: 'Review the AI-generated prerequisite draft.',
    },
    {
      id: 'publish',
      label: 'Publish course',
      status: 'locked',
      route: null,
      detail: 'Publish when all readiness gates pass.',
    },
  ],
  prerequisite_review: {
    status: 'needs_review',
    edge_count: 12,
    isolated_skill_count: 3,
    last_generated_at: null,
  },
};

function renderRoad(value: CourseReadiness = readiness) {
  return render(
    <MemoryRouter>
      <CourseReadinessRoad readiness={value} onRefresh={vi.fn()} />
    </MemoryRouter>,
  );
}

describe('CourseReadinessRoad', () => {
  it('shows next action and separate prerequisite launcher', () => {
    renderRoad();

    expect(screen.getByText('Course readiness')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Review prerequisites/i })).toHaveAttribute(
      'href',
      '/courses/7/prerequisites',
    );
    expect(screen.getByText('Prerequisite review')).toBeInTheDocument();
    expect(screen.getByText('Review prerequisites.')).toBeInTheDocument();
  });

  it('disables publish when blockers exist', () => {
    renderRoad();

    expect(screen.getByRole('button', { name: /Publish course/i })).toBeDisabled();
  });

  it('publishes when all gates pass', async () => {
    vi.mocked(coursesApi.publish).mockResolvedValue({
      id: 7,
      title: 'Course',
      description: 'Desc',
      teacher_id: 1,
      created_at: '2026-05-20T00:00:00Z',
      extraction_status: 'finished',
      publication_status: 'published',
      market_gate_status: 'completed',
      level: 'bachelor',
    });
    const onRefresh = vi.fn();
    render(
      <MemoryRouter>
        <CourseReadinessRoad
          readiness={{ ...readiness, can_publish: true, blockers: [], next_action: { id: 'publish', label: 'Publish course', route: null } }}
          onRefresh={onRefresh}
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: /Publish course/i }));

    await waitFor(() => expect(coursesApi.publish).toHaveBeenCalledWith(7));
    expect(onRefresh).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run frontend test and confirm it fails**

Run:

```bash
docker start lab_tutor_frontend
docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/courses/components/readiness/CourseReadinessRoad.test.tsx'
```

Expected: import failure for `CourseReadinessRoad`.

- [ ] **Step 3: Add frontend types and API methods**

Modify `frontend/src/features/courses/types.ts`:

```ts
export type PublicationStatus = 'draft' | 'published';
export type MarketGateStatus = 'not_started' | 'completed' | 'waived';
export type AvailabilityStatus = 'draft' | 'published' | 'publishing_paused';
export type GateStatus = 'locked' | 'ready' | 'complete' | 'blocked';
export type ReadinessGateId = 'book' | 'market' | 'prerequisites' | 'publish';
export type NextActionId = ReadinessGateId | 'none';
```

Add to `Course`:

```ts
  publication_status: PublicationStatus;
  market_gate_status: MarketGateStatus;
```

Add:

```ts
export interface ReadinessNextAction {
  id: NextActionId;
  label: string;
  route: string | null;
}

export interface ReadinessGate {
  id: ReadinessGateId;
  label: string;
  status: GateStatus;
  route: string | null;
  detail: string;
}

export interface PrerequisiteReviewSummary {
  status: 'not_started' | 'needs_review' | 'approved' | 'stale';
  edge_count: number;
  isolated_skill_count: number;
  last_generated_at: string | null;
}

export interface CourseReadiness {
  course_id: number;
  publication_status: PublicationStatus;
  availability_status: AvailabilityStatus;
  can_publish: boolean;
  blockers: string[];
  next_action: ReadinessNextAction;
  gates: ReadinessGate[];
  prerequisite_review: PrerequisiteReviewSummary;
}
```

Modify `frontend/src/features/courses/api.ts` imports:

```ts
  CourseReadiness,
```

Add methods to `coursesApi`:

```ts
  getReadiness: async (id: number): Promise<CourseReadiness> => {
    const response = await api.get<CourseReadiness>(`/courses/${id}/readiness`);
    return response.data;
  },
  publish: async (id: number): Promise<Course> => {
    const response = await api.post<Course>(`/courses/${id}/publish`);
    return response.data;
  },
  unpublish: async (id: number): Promise<Course> => {
    const response = await api.post<Course>(`/courses/${id}/unpublish`);
    return response.data;
  },
  waiveMarketGate: async (id: number): Promise<Course> => {
    const response = await api.post<Course>(`/courses/${id}/market-gate/waive`);
    return response.data;
  },
```

- [ ] **Step 4: Add separate prerequisite launcher to agent config**

Modify `frontend/src/features/agents/config.ts` imports:

```ts
  GitBranch,
```

Add to `AGENTS` after market analyst:

```ts
  {
    id: "prerequisites",
    name: "Prerequisite Review",
    description:
      "Review and approve the skill prerequisite graph before students can enroll.",
    icon: GitBranch,
    route: "prerequisites",
    enabled: true,
    color: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
  },
```

- [ ] **Step 5: Build readiness components**

Create `frontend/src/features/courses/components/readiness/NextActionBanner.tsx`:

```tsx
import { Link } from 'react-router-dom';
import { ArrowRight, Info } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { CourseReadiness } from '../../types';

interface NextActionBannerProps {
  readiness: CourseReadiness;
}

export function NextActionBanner({ readiness }: NextActionBannerProps) {
  const action = readiness.next_action;
  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-background p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-3">
        <Info className="mt-0.5 h-5 w-5 text-primary" />
        <div>
          <p className="text-sm font-medium">Next step</p>
          <p className="text-sm text-muted-foreground">{action.label}</p>
        </div>
      </div>
      {action.route ? (
        <Button asChild size="sm">
          <Link to={action.route}>
            {action.label}
            <ArrowRight className="h-4 w-4" />
          </Link>
        </Button>
      ) : null}
    </div>
  );
}
```

Create `frontend/src/features/courses/components/readiness/ReadinessGateTrack.tsx`:

```tsx
import { Link } from 'react-router-dom';
import { CheckCircle2, Circle, Lock, AlertCircle } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { ReadinessGate } from '../../types';

const iconByStatus = {
  complete: CheckCircle2,
  ready: Circle,
  locked: Lock,
  blocked: AlertCircle,
} as const;

export function ReadinessGateTrack({ gates }: { gates: ReadinessGate[] }) {
  return (
    <div className="grid gap-3 md:grid-cols-4">
      {gates.map((gate) => {
        const Icon = iconByStatus[gate.status];
        const content = (
          <div
            className={cn(
              'h-full rounded-lg border bg-background p-4 transition-colors',
              gate.route && gate.status !== 'locked' && 'hover:border-primary/60',
            )}
          >
            <div className="flex items-center justify-between gap-3">
              <Icon className="h-4 w-4 text-muted-foreground" />
              <Badge variant={gate.status === 'complete' ? 'default' : 'outline'}>
                {gate.status.replace('_', ' ')}
              </Badge>
            </div>
            <p className="mt-3 text-sm font-medium">{gate.label}</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{gate.detail}</p>
          </div>
        );
        if (!gate.route || gate.status === 'locked') {
          return <div key={gate.id}>{content}</div>;
        }
        return (
          <Link key={gate.id} to={gate.route} aria-label={gate.label}>
            {content}
          </Link>
        );
      })}
    </div>
  );
}
```

Create `frontend/src/features/courses/components/readiness/PublishCourseButton.tsx`:

```tsx
import { useState } from 'react';
import { Loader2, Rocket } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { coursesApi } from '../../api';
import type { CourseReadiness } from '../../types';

interface PublishCourseButtonProps {
  readiness: CourseReadiness;
  onRefresh: () => void | Promise<void>;
}

export function PublishCourseButton({ readiness, onRefresh }: PublishCourseButtonProps) {
  const [isPublishing, setIsPublishing] = useState(false);

  const handlePublish = async () => {
    setIsPublishing(true);
    try {
      await coursesApi.publish(readiness.course_id);
      toast.success('Course published');
      await onRefresh();
    } catch {
      toast.error('Course is not ready to publish');
    } finally {
      setIsPublishing(false);
    }
  };

  return (
    <Button onClick={handlePublish} disabled={!readiness.can_publish || isPublishing}>
      {isPublishing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
      Publish course
    </Button>
  );
}
```

Create `frontend/src/features/courses/components/readiness/CourseReadinessRoad.tsx`:

```tsx
import { Badge } from '@/components/ui/badge';
import type { CourseReadiness } from '../../types';
import { NextActionBanner } from './NextActionBanner';
import { PublishCourseButton } from './PublishCourseButton';
import { ReadinessGateTrack } from './ReadinessGateTrack';

interface CourseReadinessRoadProps {
  readiness: CourseReadiness;
  onRefresh: () => void | Promise<void>;
}

function availabilityLabel(status: CourseReadiness['availability_status']) {
  if (status === 'publishing_paused') return 'Publishing paused';
  if (status === 'published') return 'Published';
  return 'Draft';
}

export function CourseReadinessRoad({ readiness, onRefresh }: CourseReadinessRoadProps) {
  return (
    <section className="space-y-4 rounded-lg border bg-card p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">Course readiness</h2>
            <Badge variant={readiness.availability_status === 'published' ? 'default' : 'outline'}>
              {availabilityLabel(readiness.availability_status)}
            </Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Complete each gate to make this course discoverable and enrollable by students.
          </p>
        </div>
        <PublishCourseButton readiness={readiness} onRefresh={onRefresh} />
      </div>

      <NextActionBanner readiness={readiness} />

      {readiness.blockers.length > 0 ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100">
          {readiness.blockers.map((blocker) => (
            <p key={blocker}>{blocker}</p>
          ))}
        </div>
      ) : null}

      <ReadinessGateTrack gates={readiness.gates} />
    </section>
  );
}
```

- [ ] **Step 6: Render readiness road in the teacher hub**

Modify `frontend/src/features/courses/pages/AgentHubPage.tsx` imports:

```tsx
import type { CourseReadiness } from "../types";
import { CourseReadinessRoad } from "../components/readiness/CourseReadinessRoad";
```

Inside `HubContent()` add state and fetch:

```tsx
  const [readiness, setReadiness] = useState<CourseReadiness | null>(null);

  const refreshReadiness = useCallback(async () => {
    const data = await coursesApi.getReadiness(courseId);
    setReadiness(data);
  }, [courseId]);

  useEffect(() => {
    refreshReadiness().catch((error) => {
      console.error("Failed to fetch course readiness", error);
    });
  }, [refreshReadiness]);
```

Render after `<CourseHeader />`:

```tsx
      {readiness ? (
        <CourseReadinessRoad readiness={readiness} onRefresh={refreshReadiness} />
      ) : null}
```

Update statuses:

```tsx
  const statuses: Record<string, { status: AgentStatus; progress?: number; lastActivity?: string }> = {
    architect: architectInfo,
    prerequisites: readiness?.prerequisite_review.status === "approved"
      ? { status: "completed", progress: 100, lastActivity: "Teacher approved" }
      : readiness?.prerequisite_review.status === "needs_review" || readiness?.prerequisite_review.status === "stale"
        ? { status: "in-progress", progress: 60, lastActivity: "Needs teacher review" }
        : { status: "not-started", progress: 0, lastActivity: "" },
  };
```

- [ ] **Step 7: Run readiness road tests**

Run:

```bash
docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/courses/components/readiness/CourseReadinessRoad.test.tsx'
```

Expected: tests pass.

- [ ] **Step 8: Commit Task 5**

Run:

```bash
git add frontend/src/features/courses/types.ts frontend/src/features/courses/api.ts frontend/src/features/agents/config.ts frontend/src/features/courses/pages/AgentHubPage.tsx frontend/src/features/courses/components/readiness
git commit -m "feat: show course readiness road"
```

---

### Task 6: Frontend Prerequisite Review Page

**Files:**
- Modify: `frontend/src/features/courses/types.ts`
- Modify: `frontend/src/features/courses/api.ts`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/features/prerequisite-review/lib/prerequisiteGraph.ts`
- Create: `frontend/src/features/prerequisite-review/components/PrerequisiteEdgeWorklist.tsx`
- Create: `frontend/src/features/prerequisite-review/components/AddPrerequisiteEdgeDialog.tsx`
- Create: `frontend/src/features/prerequisite-review/components/IsolatedSkillsPanel.tsx`
- Create: `frontend/src/features/prerequisite-review/components/PrerequisiteGraphPreview.tsx`
- Create: `frontend/src/features/prerequisite-review/pages/PrerequisiteReviewPage.tsx`
- Create: `frontend/src/features/prerequisite-review/pages/PrerequisiteReviewPage.test.tsx`

- [ ] **Step 1: Write failing prerequisite review page test**

Create `frontend/src/features/prerequisite-review/pages/PrerequisiteReviewPage.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { coursesApi } from '@/features/courses/api';
import type { PrerequisiteReview } from '@/features/courses/types';
import PrerequisiteReviewPage from './PrerequisiteReviewPage';

vi.mock('@/features/courses/api', () => ({
  coursesApi: {
    getPrerequisiteReview: vi.fn(),
    savePrerequisiteReview: vi.fn(),
    approvePrerequisiteReview: vi.fn(),
    regeneratePrerequisites: vi.fn(),
  },
}));

const review: PrerequisiteReview = {
  course_id: 9,
  status: 'needs_review',
  is_rebuilding: false,
  skills: [
    { name: 'SQL basics', source: 'book', chapter_title: 'Intro' },
    { name: 'SQL joins', source: 'book', chapter_title: 'Queries' },
    { name: 'Indexes', source: 'market', chapter_title: 'Performance' },
  ],
  draft_edges: [
    {
      prerequisite_name: 'SQL basics',
      dependent_name: 'SQL joins',
      confidence: 'high',
      reasoning: 'Basics before joins.',
      source: 'ai',
    },
  ],
  isolated_skills: ['Indexes'],
  validation: { is_valid: true, errors: [], cycle_path: [] },
  metadata: {
    edge_count: 1,
    generated_edge_count: 1,
    added_edge_count: 0,
    removed_edge_count: 0,
    isolated_skill_count: 1,
    last_generated_at: null,
    last_invalidated_at: null,
    approved_at: null,
  },
};

function renderPage() {
  vi.mocked(coursesApi.getPrerequisiteReview).mockResolvedValue(review);
  vi.mocked(coursesApi.savePrerequisiteReview).mockResolvedValue({
    ...review,
    draft_edges: [],
    isolated_skills: ['SQL basics', 'SQL joins', 'Indexes'],
  });
  vi.mocked(coursesApi.approvePrerequisiteReview).mockResolvedValue({
    ...review,
    status: 'approved',
  });

  return render(
    <MemoryRouter initialEntries={['/courses/9/prerequisites']}>
      <Routes>
        <Route path="/courses/:id/prerequisites" element={<PrerequisiteReviewPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('PrerequisiteReviewPage', () => {
  it('shows edge worklist, graph preview, and isolated skills', async () => {
    renderPage();

    expect(await screen.findByText('Prerequisite Review')).toBeInTheDocument();
    expect(screen.getByText('SQL basics')).toBeInTheDocument();
    expect(screen.getByText('SQL joins')).toBeInTheDocument();
    expect(screen.getByText('Indexes')).toBeInTheDocument();
    expect(screen.getByText('Graph preview')).toBeInTheDocument();
  });

  it('removes an edge and saves the draft', async () => {
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: /Remove edge/i }));

    await waitFor(() => expect(coursesApi.savePrerequisiteReview).toHaveBeenCalled());
  });

  it('blocks approval when cycle warning is present', async () => {
    vi.mocked(coursesApi.getPrerequisiteReview).mockResolvedValue({
      ...review,
      validation: {
        is_valid: false,
        errors: ['Cycle detected: SQL basics -> SQL joins -> SQL basics'],
        cycle_path: ['SQL basics', 'SQL joins', 'SQL basics'],
      },
    });

    render(
      <MemoryRouter initialEntries={['/courses/9/prerequisites']}>
        <Routes>
          <Route path="/courses/:id/prerequisites" element={<PrerequisiteReviewPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Cycle detected/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Approve graph/i })).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run failing page test**

Run:

```bash
docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/prerequisite-review/pages/PrerequisiteReviewPage.test.tsx'
```

Expected: import failure for prerequisite review page.

- [ ] **Step 3: Add prerequisite review types and API methods**

Modify `frontend/src/features/courses/types.ts`:

```ts
export type PrerequisiteReviewStatus = 'not_started' | 'needs_review' | 'approved' | 'stale';
export type PrerequisiteEdgeConfidence = 'high' | 'medium' | 'low';
export type PrerequisiteEdgeSource = 'ai' | 'teacher';

export interface PrerequisiteSkill {
  name: string;
  source: string;
  chapter_title: string | null;
}

export interface PrerequisiteDraftEdge {
  prerequisite_name: string;
  dependent_name: string;
  confidence: PrerequisiteEdgeConfidence;
  reasoning: string;
  source: PrerequisiteEdgeSource;
}

export interface PrerequisiteValidation {
  is_valid: boolean;
  errors: string[];
  cycle_path: string[];
}

export interface PrerequisiteReviewMetadata {
  edge_count: number;
  generated_edge_count: number;
  added_edge_count: number;
  removed_edge_count: number;
  isolated_skill_count: number;
  last_generated_at: string | null;
  last_invalidated_at: string | null;
  approved_at: string | null;
}

export interface PrerequisiteReview {
  course_id: number;
  status: PrerequisiteReviewStatus;
  is_rebuilding: boolean;
  skills: PrerequisiteSkill[];
  draft_edges: PrerequisiteDraftEdge[];
  isolated_skills: string[];
  validation: PrerequisiteValidation;
  metadata: PrerequisiteReviewMetadata;
}
```

Modify `frontend/src/features/courses/api.ts` imports:

```ts
  PrerequisiteDraftEdge,
  PrerequisiteReview,
```

Add methods to `coursesApi`:

```ts
  getPrerequisiteReview: async (id: number): Promise<PrerequisiteReview> => {
    const response = await api.get<PrerequisiteReview>(
      `/book-selection/courses/${id}/skill-prerequisites/review`,
    );
    return response.data;
  },
  savePrerequisiteReview: async (
    id: number,
    payload: { draft_edges: PrerequisiteDraftEdge[]; isolated_skills_viewed: boolean },
  ): Promise<PrerequisiteReview> => {
    const response = await api.put<PrerequisiteReview>(
      `/book-selection/courses/${id}/skill-prerequisites/review`,
      payload,
    );
    return response.data;
  },
  approvePrerequisiteReview: async (id: number): Promise<PrerequisiteReview> => {
    const response = await api.post<PrerequisiteReview>(
      `/book-selection/courses/${id}/skill-prerequisites/approve`,
    );
    return response.data;
  },
  regeneratePrerequisites: async (id: number): Promise<void> => {
    await api.post(`/book-selection/courses/${id}/skill-prerequisites/regenerate`);
  },
```

- [ ] **Step 4: Add graph helper**

Create `frontend/src/features/prerequisite-review/lib/prerequisiteGraph.ts`:

```ts
import type { PrerequisiteDraftEdge, PrerequisiteSkill } from '@/features/courses/types';

export interface GraphNode {
  id: string;
  label: string;
  x: number;
  y: number;
}

export interface GraphEdge {
  id: string;
  from: string;
  to: string;
}

export function buildGraphPreview(
  skills: PrerequisiteSkill[],
  edges: PrerequisiteDraftEdge[],
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodeNames = new Set<string>();
  for (const skill of skills) nodeNames.add(skill.name);
  for (const edge of edges) {
    nodeNames.add(edge.prerequisite_name);
    nodeNames.add(edge.dependent_name);
  }
  const sortedNames = [...nodeNames].sort((a, b) => a.localeCompare(b));
  const columns = Math.max(1, Math.ceil(Math.sqrt(sortedNames.length)));
  const nodes = sortedNames.map((name, index) => ({
    id: name,
    label: name,
    x: 80 + (index % columns) * 180,
    y: 70 + Math.floor(index / columns) * 110,
  }));
  return {
    nodes,
    edges: edges.map((edge) => ({
      id: `${edge.prerequisite_name}->${edge.dependent_name}`,
      from: edge.prerequisite_name,
      to: edge.dependent_name,
    })),
  };
}
```

- [ ] **Step 5: Add review components**

Create `frontend/src/features/prerequisite-review/components/PrerequisiteEdgeWorklist.tsx`:

```tsx
import { Trash2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { PrerequisiteDraftEdge } from '@/features/courses/types';

interface PrerequisiteEdgeWorklistProps {
  edges: PrerequisiteDraftEdge[];
  onRemove: (index: number) => void;
}

export function PrerequisiteEdgeWorklist({ edges, onRemove }: PrerequisiteEdgeWorklistProps) {
  if (edges.length === 0) {
    return <p className="rounded-lg border p-4 text-sm text-muted-foreground">No prerequisite edges in this draft.</p>;
  }
  return (
    <div className="space-y-3">
      {edges.map((edge, index) => (
        <div key={`${edge.prerequisite_name}-${edge.dependent_name}-${index}`} className="rounded-lg border bg-background p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium">{edge.prerequisite_name} -> {edge.dependent_name}</p>
                <Badge variant="outline">{edge.confidence}</Badge>
                <Badge variant={edge.source === 'teacher' ? 'default' : 'secondary'}>{edge.source}</Badge>
              </div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{edge.reasoning}</p>
            </div>
            <Button type="button" variant="ghost" size="sm" onClick={() => onRemove(index)}>
              <Trash2 className="h-4 w-4" />
              Remove edge
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}
```

Create `frontend/src/features/prerequisite-review/components/IsolatedSkillsPanel.tsx`:

```tsx
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

export function IsolatedSkillsPanel({
  skills,
  reviewed,
  onMarkReviewed,
}: {
  skills: string[];
  reviewed: boolean;
  onMarkReviewed: () => void;
}) {
  return (
    <div className="rounded-lg border bg-background p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium">Isolated skills</p>
          <p className="mt-1 text-sm text-muted-foreground">
            These skills have no prerequisite edge yet. That can be valid for standalone topics.
          </p>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={onMarkReviewed} disabled={reviewed}>
          {reviewed ? 'Reviewed' : 'Mark reviewed'}
        </Button>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {skills.length > 0 ? skills.map((skill) => (
          <Badge key={skill} variant="secondary">{skill}</Badge>
        )) : <span className="text-sm text-muted-foreground">No isolated skills.</span>}
      </div>
    </div>
  );
}
```

Create `frontend/src/features/prerequisite-review/components/PrerequisiteGraphPreview.tsx`:

```tsx
import type { PrerequisiteDraftEdge, PrerequisiteSkill } from '@/features/courses/types';
import { buildGraphPreview } from '../lib/prerequisiteGraph';

interface PrerequisiteGraphPreviewProps {
  skills: PrerequisiteSkill[];
  edges: PrerequisiteDraftEdge[];
}

export function PrerequisiteGraphPreview({ skills, edges }: PrerequisiteGraphPreviewProps) {
  const graph = buildGraphPreview(skills, edges);
  const width = 720;
  const height = Math.max(260, ...graph.nodes.map((node) => node.y + 70));
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));

  return (
    <div className="rounded-lg border bg-background p-4">
      <p className="text-sm font-medium">Graph preview</p>
      <div className="mt-3 overflow-auto">
        <svg width={width} height={height} role="img" aria-label="Prerequisite graph preview">
          <defs>
            <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
              <path d="M0,0 L0,6 L9,3 z" fill="currentColor" />
            </marker>
          </defs>
          {graph.edges.map((edge) => {
            const from = nodeById.get(edge.from);
            const to = nodeById.get(edge.to);
            if (!from || !to) return null;
            return (
              <line
                key={edge.id}
                x1={from.x + 120}
                y1={from.y + 18}
                x2={to.x}
                y2={to.y + 18}
                className="stroke-muted-foreground"
                strokeWidth="1.5"
                markerEnd="url(#arrow)"
              />
            );
          })}
          {graph.nodes.map((node) => (
            <g key={node.id} transform={`translate(${node.x}, ${node.y})`}>
              <rect width="130" height="42" rx="8" className="fill-background stroke-border" />
              <text x="10" y="25" className="fill-foreground text-xs">
                {node.label.length > 18 ? `${node.label.slice(0, 17)}...` : node.label}
              </text>
            </g>
          ))}
        </svg>
      </div>
    </div>
  );
}
```

Create `frontend/src/features/prerequisite-review/components/AddPrerequisiteEdgeDialog.tsx`:

```tsx
import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import type { PrerequisiteDraftEdge, PrerequisiteSkill } from '@/features/courses/types';

interface AddPrerequisiteEdgeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  skills: PrerequisiteSkill[];
  onAdd: (edge: PrerequisiteDraftEdge) => void;
}

export function AddPrerequisiteEdgeDialog({ open, onOpenChange, skills, onAdd }: AddPrerequisiteEdgeDialogProps) {
  const [prerequisiteName, setPrerequisiteName] = useState('');
  const [dependentName, setDependentName] = useState('');
  const names = useMemo(() => skills.map((skill) => skill.name), [skills]);
  const canAdd = names.includes(prerequisiteName) && names.includes(dependentName) && prerequisiteName !== dependentName;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add prerequisite edge</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Input list="skill-names" placeholder="Prerequisite skill" value={prerequisiteName} onChange={(event) => setPrerequisiteName(event.target.value)} />
          <Input list="skill-names" placeholder="Dependent skill" value={dependentName} onChange={(event) => setDependentName(event.target.value)} />
          <datalist id="skill-names">
            {names.map((name) => <option key={name} value={name} />)}
          </datalist>
        </div>
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            type="button"
            disabled={!canAdd}
            onClick={() => {
              onAdd({
                prerequisite_name: prerequisiteName,
                dependent_name: dependentName,
                confidence: 'medium',
                reasoning: 'Teacher-added prerequisite edge.',
                source: 'teacher',
              });
              setPrerequisiteName('');
              setDependentName('');
              onOpenChange(false);
            }}
          >
            Add edge
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 6: Add review page**

Create `frontend/src/features/prerequisite-review/pages/PrerequisiteReviewPage.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, GitBranch, Loader2, Plus, RefreshCcw } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { coursesApi } from '@/features/courses/api';
import type { PrerequisiteDraftEdge, PrerequisiteReview } from '@/features/courses/types';
import { AddPrerequisiteEdgeDialog } from '../components/AddPrerequisiteEdgeDialog';
import { IsolatedSkillsPanel } from '../components/IsolatedSkillsPanel';
import { PrerequisiteEdgeWorklist } from '../components/PrerequisiteEdgeWorklist';
import { PrerequisiteGraphPreview } from '../components/PrerequisiteGraphPreview';

export default function PrerequisiteReviewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const courseId = Number(id);
  const [review, setReview] = useState<PrerequisiteReview | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isolatedViewed, setIsolatedViewed] = useState(false);
  const [addOpen, setAddOpen] = useState(false);

  const refresh = useCallback(async () => {
    const data = await coursesApi.getPrerequisiteReview(courseId);
    setReview(data);
  }, [courseId]);

  useEffect(() => {
    if (!id || Number.isNaN(courseId)) {
      navigate('/courses');
      return;
    }
    refresh().catch(() => toast.error('Failed to load prerequisite review')).finally(() => setIsLoading(false));
  }, [courseId, id, navigate, refresh]);

  const saveEdges = async (edges: PrerequisiteDraftEdge[], viewed = isolatedViewed) => {
    const saved = await coursesApi.savePrerequisiteReview(courseId, {
      draft_edges: edges,
      isolated_skills_viewed: viewed,
    });
    setReview(saved);
  };

  const removeEdge = async (index: number) => {
    if (!review) return;
    await saveEdges(review.draft_edges.filter((_, idx) => idx !== index));
    toast.success('Prerequisite edge removed');
  };

  const addEdge = async (edge: PrerequisiteDraftEdge) => {
    if (!review) return;
    await saveEdges([...review.draft_edges, edge]);
    toast.success('Prerequisite edge added');
  };

  const markIsolatedReviewed = async () => {
    if (!review || isolatedViewed) return;
    setIsolatedViewed(true);
    await saveEdges(review.draft_edges, true);
  };

  const approve = async () => {
    const approved = await coursesApi.approvePrerequisiteReview(courseId);
    setReview(approved);
    toast.success('Prerequisite graph approved');
  };

  const regenerate = async () => {
    await coursesApi.regeneratePrerequisites(courseId);
    toast.success('Prerequisite regeneration started');
    await refresh();
  };

  if (isLoading || !review) {
    return <div className="flex h-full items-center justify-center"><Loader2 className="h-8 w-8 animate-spin" /></div>;
  }

  const approveDisabled = !review.validation.is_valid || review.is_rebuilding || (review.isolated_skills.length > 0 && !isolatedViewed);

  return (
    <div className="space-y-6">
      <Button variant="ghost" className="pl-0 hover:bg-transparent hover:text-primary" onClick={() => navigate(`/courses/${courseId}`)}>
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to course
      </Button>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <GitBranch className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-semibold">Prerequisite Review</h1>
            <Badge variant={review.status === 'approved' ? 'default' : 'outline'}>{review.status.replace('_', ' ')}</Badge>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            Review AI-generated prerequisite edges, adjust the draft, then approve the graph for student learning paths.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={regenerate}>
            <RefreshCcw className="h-4 w-4" />
            Regenerate
          </Button>
          <Button type="button" variant="outline" onClick={() => setAddOpen(true)}>
            <Plus className="h-4 w-4" />
            Add edge
          </Button>
          <Button type="button" disabled={approveDisabled} onClick={approve}>
            Approve graph
          </Button>
        </div>
      </div>

      {review.validation.errors.length > 0 ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
          {review.validation.errors.map((error) => <p key={error}>{error}</p>)}
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(24rem,0.8fr)]">
        <div className="space-y-4">
          <PrerequisiteEdgeWorklist edges={review.draft_edges} onRemove={removeEdge} />
        </div>
        <div className="space-y-4">
          <PrerequisiteGraphPreview skills={review.skills} edges={review.draft_edges} />
          <IsolatedSkillsPanel
            skills={review.isolated_skills}
            reviewed={isolatedViewed}
            onMarkReviewed={markIsolatedReviewed}
          />
        </div>
      </div>

      <AddPrerequisiteEdgeDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        skills={review.skills}
        onAdd={addEdge}
      />
    </div>
  );
}
```

- [ ] **Step 7: Add route**

Modify `frontend/src/App.tsx` imports:

```tsx
import PrerequisiteReviewPage from '@/features/prerequisite-review/pages/PrerequisiteReviewPage';
```

Add route after `/courses/:id/market-analyst`:

```tsx
      <Route
        path="/courses/:id/prerequisites"
        element={
          <ProtectedRoute>
            <PrerequisiteReviewPage />
          </ProtectedRoute>
        }
      />
```

- [ ] **Step 8: Run prerequisite review frontend test**

Run:

```bash
docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/prerequisite-review/pages/PrerequisiteReviewPage.test.tsx'
```

Expected: tests pass.

- [ ] **Step 9: Commit Task 6**

Run:

```bash
git add frontend/src/features/courses/types.ts frontend/src/features/courses/api.ts frontend/src/App.tsx frontend/src/features/prerequisite-review
git commit -m "feat: add teacher prerequisite review page"
```

---

### Task 7: Full Verification And UX Pass

**Files:**
- Modify only files that fail verification from previous tasks.

- [ ] **Step 1: Run backend lint and formatting checks**

Run:

```bash
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/ruff check . && /app/.venv/bin/ruff format --check .'
```

Expected: command exits with status 0.

- [ ] **Step 2: Run targeted backend tests**

Run:

```bash
docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/courses/test_course_readiness.py tests/modules/test_skill_prerequisite_review.py tests/modules/test_skill_prerequisite_auto_trigger.py'
```

Expected: selected tests pass.

- [ ] **Step 3: Run frontend lint and build**

Run:

```bash
docker exec lab_tutor_frontend sh -lc 'cd /app && npm run lint && npm run build'
```

Expected: command exits with status 0.

- [ ] **Step 4: Run targeted frontend tests**

Run:

```bash
docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/courses/components/readiness/CourseReadinessRoad.test.tsx src/features/prerequisite-review/pages/PrerequisiteReviewPage.test.tsx'
```

Expected: selected tests pass.

- [ ] **Step 5: Browser verify teacher road and prerequisite review**

Start or reuse the app:

```bash
docker start lab_tutor_postgres lab_tutor_backend lab_tutor_frontend
```

Open:

```text
http://localhost:59684/
```

Manual checks:

- Teacher course hub shows Course Readiness Road above agent icons.
- Prerequisite Review appears as a separate clickable agent card.
- Publish button is disabled until blockers clear.
- `/courses/:id/prerequisites` shows edge worklist, graph preview, and isolated skills.
- Removing an edge updates the worklist and graph preview.
- Adding an edge through skill pickers updates the worklist and graph preview.
- Cycle errors disable approval.
- Student course list omits draft and stale-published courses.

- [ ] **Step 6: Commit verification fixes**

If Task 7 required changes, run:

```bash
git add backend frontend
git commit -m "fix: polish course readiness prerequisite review"
```

If Task 7 required no changes, run:

```bash
git status --short
```

Expected: only unrelated pre-existing workspace changes remain.

## Self-Review

Spec coverage:

- Required publication gate: Task 1 and Task 4.
- Public means discoverable and enrollable by any student: Task 1 and Task 4.
- Course Readiness Road with deep links: Task 5.
- Agent icons remain primary launchers: Task 5 updates `AGENTS` and `AgentHubPage`.
- Separate Prerequisite Review launcher: Task 5.
- Edge worklist plus live graph preview: Task 6.
- Teacher can approve, remove, and add edges: Task 3 and Task 6.
- Isolated skills visible and not automatically blocking as defects: Task 2 and Task 6.
- Approval invalidated when book or market skill inputs change: Task 4.
- AI drafts do not replace live Neo4j graph until approval: Task 3.
- Existing enrolled students stay enrolled when published course becomes stale: Task 4 test.

Placeholder scan:

- No unresolved placeholder markers are present.
- Every task lists exact files, commands, expected outcomes, and concrete code snippets for changed behavior.

Type consistency:

- Backend review statuses use `not_started`, `needs_review`, `approved`, and `stale`.
- Frontend `PrerequisiteReviewStatus` matches backend `PrerequisiteReviewStatus`.
- Backend and frontend draft edge fields use `prerequisite_name`, `dependent_name`, `confidence`, `reasoning`, and `source`.
- Backend and frontend readiness fields use `publication_status`, `availability_status`, `can_publish`, `blockers`, `next_action`, `gates`, and `prerequisite_review`.
