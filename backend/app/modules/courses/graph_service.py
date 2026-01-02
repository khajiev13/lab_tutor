from __future__ import annotations

from fastapi import Depends, HTTPException, status
from neo4j import Session as Neo4jSession
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.neo4j import require_neo4j_session
from app.modules.auth.models import User

from .graph_schemas import CourseGraphResponse, GraphNodeKind
from .neo4j_repository import CourseGraphRepository
from .repository import CourseRepository


def get_course_repository(db: Session = Depends(get_db)) -> CourseRepository:
    return CourseRepository(db)


class CourseGraphService:
    _repo: CourseRepository
    _graph_repo: CourseGraphRepository

    def __init__(self, repo: CourseRepository, neo4j_session: Neo4jSession) -> None:
        self._repo = repo
        self._graph_repo = CourseGraphRepository(neo4j_session)

    def _require_teacher_owns_course(self, *, course_id: int, teacher: User) -> None:
        course = self._repo.get_by_id(course_id)
        if course is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )
        if course.teacher_id != teacher.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this course graph",
            )

    def get_snapshot(
        self,
        *,
        course_id: int,
        teacher: User,
        max_documents: int,
        max_concepts: int,
    ) -> CourseGraphResponse:
        self._require_teacher_owns_course(course_id=course_id, teacher=teacher)

        bounded_docs = max(1, min(int(max_documents), 250))
        bounded_concepts = max(1, min(int(max_concepts), 5_000))

        return self._graph_repo.get_course_graph_snapshot(
            course_id=course_id,
            max_documents=bounded_docs,
            max_concepts=bounded_concepts,
        )

    def expand(
        self,
        *,
        course_id: int,
        teacher: User,
        node_kind: GraphNodeKind,
        node_key: str,
        limit: int,
        max_concepts: int,
    ) -> CourseGraphResponse:
        self._require_teacher_owns_course(course_id=course_id, teacher=teacher)

        bounded_limit = max(1, min(int(limit), 500))
        bounded_concepts = max(1, min(int(max_concepts), 5_000))
        node_key_clean = str(node_key or "").strip()
        if not node_key_clean and node_kind != GraphNodeKind.CLASS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="node_key must be provided for this node_kind",
            )

        return self._graph_repo.expand_course_graph_node(
            course_id=course_id,
            node_kind=node_kind,
            node_key=node_key_clean,
            limit=bounded_limit,
            max_concepts=bounded_concepts,
        )


def get_course_graph_service(
    repo: CourseRepository = Depends(get_course_repository),
    neo4j_session: Neo4jSession = Depends(require_neo4j_session),
) -> CourseGraphService:
    return CourseGraphService(repo, neo4j_session)

