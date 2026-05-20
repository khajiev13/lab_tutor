from app.modules.curricularalignmentarchitect.skill_prerequisites.repository import (
    replace_skill_prerequisites,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.review_models import (
    PrerequisiteReview,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.review_repository import (
    PrerequisiteReviewRepository,
    skill_names_from_rows,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.review_service import (
    PrerequisiteReviewService,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.schemas import (
    PrerequisiteDraftEdge,
    PrerequisiteReviewStatus,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.validation import (
    compute_isolated_skills,
    validate_prerequisite_edges,
)

SKILLS = ["SQL basics", "SQL joins", "Indexes"]


class FakeCourse:
    id = 42
    teacher_id = 7


class FakeCourseRepository:
    def get_by_id(self, course_id: int):
        return FakeCourse() if course_id == 42 else None


class FakeReview:
    def __init__(self, course_id: int) -> None:
        self.course_id = course_id
        self.review_status = PrerequisiteReviewStatus.NOT_STARTED
        self.is_rebuilding = False
        self.draft_edges: list[dict] = []
        self.isolated_skills_viewed = False
        self.generated_edge_count = 0
        self.added_edge_count = 0
        self.removed_edge_count = 0
        self.isolated_skill_count = 0
        self.last_generated_at = None
        self.last_invalidated_at = None
        self.approved_at = None


class FakeReviewRepository:
    def __init__(self) -> None:
        self.review: FakeReview | None = None

    def get(self, course_id: int):
        if self.review is not None and self.review.course_id == course_id:
            return self.review
        return None

    def _get_or_create(self, course_id: int) -> FakeReview:
        review = self.get(course_id)
        if review is None:
            review = FakeReview(course_id)
            self.review = review
        return review

    def mark_generated(
        self,
        *,
        course_id: int,
        edges: list[PrerequisiteDraftEdge],
        isolated_skill_count: int,
    ):
        review = self._get_or_create(course_id)
        review.review_status = PrerequisiteReviewStatus.NEEDS_REVIEW
        review.draft_edges = [draft_edge.model_dump() for draft_edge in edges]
        review.generated_edge_count = len(edges)
        review.isolated_skill_count = isolated_skill_count
        review.isolated_skills_viewed = False
        review.is_rebuilding = False
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
    ):
        review = self._get_or_create(course_id)
        review.review_status = status
        review.draft_edges = [draft_edge.model_dump() for draft_edge in edges]
        review.isolated_skill_count = isolated_skill_count
        if generated_edge_count is not None:
            review.generated_edge_count = generated_edge_count
        if added_edge_count is not None:
            review.added_edge_count = added_edge_count
        if removed_edge_count is not None:
            review.removed_edge_count = removed_edge_count
        if isolated_skills_viewed is not None:
            review.isolated_skills_viewed = isolated_skills_viewed
        return review

    def mark_approved(
        self,
        *,
        course_id: int,
        teacher_id: int,
        added_edge_count: int,
        removed_edge_count: int,
    ):
        review = self._get_or_create(course_id)
        review.review_status = PrerequisiteReviewStatus.APPROVED
        review.approved_by = teacher_id
        review.added_edge_count = added_edge_count
        review.removed_edge_count = removed_edge_count
        return review


class FakeNeo4jRepository:
    def __init__(self) -> None:
        self.written_edges: list[dict] | None = None

    def load_skills(self, course_id: int) -> list[dict]:
        assert course_id == 42
        return [
            {"name": "SQL basics", "source": "book", "chapter_title": "Intro"},
            {"name": "SQL joins", "source": "book", "chapter_title": "Queries"},
            {"name": "Indexes", "source": "market", "chapter_title": "Performance"},
        ]

    def replace_approved_edges(self, course_id: int, edges: list[dict]) -> int:
        assert course_id == 42
        self.written_edges = edges
        return len(edges)


class FakeSession:
    def __init__(self, review: PrerequisiteReview | None = None) -> None:
        self.review = review
        self.added: list[PrerequisiteReview] = []
        self.flushed = 0
        self.refreshed: list[PrerequisiteReview] = []

    def get(
        self, model: type[PrerequisiteReview], course_id: int
    ) -> PrerequisiteReview | None:
        if model is not PrerequisiteReview:
            return None
        if self.review is not None and self.review.course_id == course_id:
            return self.review
        return None

    def add(self, review: PrerequisiteReview) -> None:
        self.review = review
        self.added.append(review)

    def flush(self) -> None:
        self.flushed += 1

    def refresh(self, review: PrerequisiteReview) -> None:
        self.refreshed.append(review)


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
    assert compute_isolated_skills(SKILLS, [edge("SQL basics", "SQL joins")]) == [
        "Indexes"
    ]


def test_review_repository_exposes_public_db_and_save_draft_preserves_optional_counts():
    review = PrerequisiteReview(
        course_id=1,
        generated_edge_count=7,
        added_edge_count=2,
        removed_edge_count=1,
        isolated_skills_viewed=True,
    )
    session = FakeSession(review)
    repo = PrerequisiteReviewRepository(session)  # type: ignore[arg-type]

    result = repo.save_draft(
        1,
        [edge("SQL basics", "SQL joins")],
        PrerequisiteReviewStatus.STALE,
        3,
    )

    assert repo.db is session
    assert result.review_status == PrerequisiteReviewStatus.STALE
    assert result.edge_count == 1
    assert result.isolated_skill_count == 3
    assert result.generated_edge_count == 7
    assert result.added_edge_count == 2
    assert result.removed_edge_count == 1
    assert result.isolated_skills_viewed is True
    assert session.flushed == 1
    assert session.refreshed == [review]


def test_review_repository_mark_generated_uses_planned_counters_and_clears_approval():
    review = PrerequisiteReview(
        course_id=1,
        review_status=PrerequisiteReviewStatus.APPROVED,
        is_rebuilding=True,
        approved_by=42,
        isolated_skills_viewed=True,
    )
    repo = PrerequisiteReviewRepository(FakeSession(review))  # type: ignore[arg-type]

    result = repo.mark_generated(1, [edge("SQL basics", "SQL joins")], 1)

    assert result.review_status == PrerequisiteReviewStatus.NEEDS_REVIEW
    assert result.generated_edge_count == 1
    assert result.is_rebuilding is False
    assert result.isolated_skills_viewed is False
    assert result.approved_by is None
    assert result.approved_at is None
    assert result.last_generated_at is not None


def test_review_repository_mark_stale_only_changes_approved_reviews():
    review = PrerequisiteReview(
        course_id=1,
        review_status=PrerequisiteReviewStatus.NEEDS_REVIEW,
    )
    repo = PrerequisiteReviewRepository(FakeSession(review))  # type: ignore[arg-type]

    result = repo.mark_stale(1)

    assert result.review_status == PrerequisiteReviewStatus.NEEDS_REVIEW
    assert result.last_invalidated_at is not None

    review.review_status = PrerequisiteReviewStatus.APPROVED
    result = repo.mark_stale(1)

    assert result.review_status == PrerequisiteReviewStatus.STALE


def test_review_repository_mark_approved_sets_teacher_and_delta_counts():
    review = PrerequisiteReview(course_id=1, is_rebuilding=True)
    repo = PrerequisiteReviewRepository(FakeSession(review))  # type: ignore[arg-type]

    result = repo.mark_approved(1, 9, 4, 2)

    assert result.review_status == PrerequisiteReviewStatus.APPROVED
    assert result.approved_by == 9
    assert result.approved_at is not None
    assert result.added_edge_count == 4
    assert result.removed_edge_count == 2
    assert result.is_rebuilding is False


def test_review_repository_mark_rebuild_failed_clears_rebuilding_flag():
    review = PrerequisiteReview(course_id=1, is_rebuilding=True)
    repo = PrerequisiteReviewRepository(FakeSession(review))  # type: ignore[arg-type]

    result = repo.mark_rebuild_failed(1)

    assert result.is_rebuilding is False


def test_skill_names_from_rows_returns_sorted_unique_names():
    assert skill_names_from_rows(
        [
            {"name": "SQL joins"},
            {"name": "SQL basics"},
            {"name": "SQL joins"},
            {"name": ""},
            {},
        ]
    ) == ["SQL basics", "SQL joins"]


def test_review_service_saves_generated_draft_not_live_graph():
    graph_repo = FakeNeo4jRepository()
    service = PrerequisiteReviewService(
        FakeCourseRepository(),  # type: ignore[arg-type]
        FakeReviewRepository(),  # type: ignore[arg-type]
        graph_repo,
    )

    review = service.save_generated_draft(
        course_id=42,
        edges=[edge("SQL basics", "SQL joins")],
    )

    assert review.status == PrerequisiteReviewStatus.NEEDS_REVIEW
    assert graph_repo.written_edges is None
    assert review.draft_edges[0].prerequisite_name == "SQL basics"
    assert review.isolated_skills == ["Indexes"]


def test_review_service_approval_validates_and_writes_live_graph():
    graph_repo = FakeNeo4jRepository()
    service = PrerequisiteReviewService(
        FakeCourseRepository(),  # type: ignore[arg-type]
        FakeReviewRepository(),  # type: ignore[arg-type]
        graph_repo,
    )

    service.save_generated_draft(
        course_id=42,
        edges=[edge("SQL basics", "SQL joins")],
    )
    review = service.save_teacher_draft(
        course_id=42,
        edges=[
            edge("SQL basics", "SQL joins"),
            edge("SQL joins", "Indexes"),
        ],
        isolated_skills_viewed=True,
    )

    assert review.validation.is_valid is True

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


def test_review_service_approval_allows_zero_edge_draft_and_clears_live_graph():
    graph_repo = FakeNeo4jRepository()
    service = PrerequisiteReviewService(
        FakeCourseRepository(),  # type: ignore[arg-type]
        FakeReviewRepository(),  # type: ignore[arg-type]
        graph_repo,
    )

    service.save_generated_draft(course_id=42, edges=[])
    service.save_teacher_draft(course_id=42, edges=[], isolated_skills_viewed=True)

    approved = service.approve(course_id=42, teacher_id=7)

    assert approved.status == PrerequisiteReviewStatus.APPROVED
    assert graph_repo.written_edges == []


def test_replace_skill_prerequisites_uses_single_write_transaction():
    calls: list[tuple[str, object]] = []

    class FakeResult:
        def single(self):
            return {"written": 2}

    class FakeTx:
        def run(self, query, **params):
            calls.append(("run", query))
            calls.append(("params", params))
            return FakeResult()

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute_write(self, fn, course_id, edges):
            calls.append(("execute_write", (course_id, edges)))
            return fn(FakeTx(), course_id, edges)

    class FakeDriver:
        def session(self, *, database):
            calls.append(("database", database))
            return FakeSession()

    written = replace_skill_prerequisites(
        FakeDriver(),  # type: ignore[arg-type]
        42,
        [
            {
                "prereq_name": "SQL basics",
                "dependent_name": "SQL joins",
                "confidence": "high",
                "reasoning": "test edge",
            }
        ],
    )

    assert written == 2
    assert calls[1][0] == "execute_write"
    query = calls[2][1]
    assert "MATCH (cl:CLASS {id: $course_id})" in query
    assert "WHERE a IN course_skills" in query
    assert "WHERE b IN course_skills" in query
