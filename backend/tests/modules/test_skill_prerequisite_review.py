from app.modules.curricularalignmentarchitect.skill_prerequisites.review_models import (
    PrerequisiteReview,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.review_repository import (
    PrerequisiteReviewRepository,
    skill_names_from_rows,
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
