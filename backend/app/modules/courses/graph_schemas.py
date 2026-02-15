from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field


class GraphNodeKind(StrEnum):
    CLASS = "class"
    DOCUMENT = "document"
    CONCEPT = "concept"


class GraphEdgeKind(StrEnum):
    HAS_DOCUMENT = "has_document"
    MENTIONS = "mentions"


class ClassNodeData(BaseModel):
    course_id: int
    title: str | None = None


class DocumentNodeData(BaseModel):
    document_id: str
    course_id: int
    source_filename: str | None = None
    topic: str | None = None
    extracted_at: str | None = None  # ISO string from Neo4j (stored as string today)


class ConceptNodeData(BaseModel):
    name: str


GraphNodeData = Annotated[
    ClassNodeData | DocumentNodeData | ConceptNodeData, Field(discriminator=None)
]


class GraphNode(BaseModel):
    id: str
    kind: GraphNodeKind
    label: str
    data: ClassNodeData | DocumentNodeData | ConceptNodeData


class MentionsEdgeData(BaseModel):
    definition: str | None = None
    text_evidence: str | None = None
    source_document: str | None = None


class GraphEdge(BaseModel):
    id: str
    kind: GraphEdgeKind
    source: str
    target: str
    data: MentionsEdgeData | None = None


class CourseGraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]

