"""
Pydantic models for Neo4j graph data structures.

These models provide type safety and validation for Neo4j nodes and relationships,
replacing raw dictionary-based data structures in the ingestion pipeline.
"""

from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field


class Neo4jNodeProperties(BaseModel):
    """Base class for Neo4j node properties."""
    pass


class TopicNodeProperties(Neo4jNodeProperties):
    """Properties for TOPIC nodes."""
    name: str = Field(description="Topic name")


class TheoryNodeProperties(Neo4jNodeProperties):
    """Properties for THEORY nodes."""
    name: str = Field(description="Theory name (same as topic)")
    original_text: str = Field(description="Original document text")
    compressed_text: str = Field(description="Compressed/summary text")
    embedding: List[float] = Field(description="Vector embedding", default_factory=list)
    keywords: List[str] = Field(description="Keywords from extraction", default_factory=list)
    source: str = Field(description="Source filename")


class ConceptNodeProperties(Neo4jNodeProperties):
    """Properties for CONCEPT nodes (canonical approach - only name)."""
    name: str = Field(description="Canonical concept name")


class QuizQuestionNodeProperties(Neo4jNodeProperties):
    """Properties for QUIZ_QUESTION nodes."""
    question_text: str = Field(description="The question text")
    option_a: str = Field(description="Choice A")
    option_b: str = Field(description="Choice B")
    option_c: str = Field(description="Choice C")
    option_d: str = Field(description="Choice D")
    correct_answer: str = Field(description="Correct answer (A, B, C, or D)")
    concept_name: str = Field(description="Name of the concept this question is for")
    theory_name: str = Field(description="Name of the theory this question is based on")
    theory_id: str = Field(description="ID of the theory node this question is linked to")
    text_evidence: str = Field(description="The source text evidence used")


class Neo4jNode(BaseModel):
    """Represents a Neo4j node with type safety."""
    id: str = Field(description="Unique node identifier")
    label: str = Field(description="Node label (TOPIC, THEORY, CONCEPT, QUIZ_QUESTION)")
    properties: Neo4jNodeProperties = Field(description="Node properties")

    class Config:
        # Allow subclasses of Neo4jNodeProperties
        arbitrary_types_allowed = True


class Neo4jRelationshipProperties(BaseModel):
    """Base class for Neo4j relationship properties."""
    pass


class HasTheoryRelationshipProperties(Neo4jRelationshipProperties):
    """Properties for HAS_THEORY relationships (TOPIC -> THEORY)."""
    pass  # No additional properties needed


class MentionsRelationshipProperties(Neo4jRelationshipProperties):
    """Properties for MENTIONS relationships (THEORY -> CONCEPT)."""
    original_name: str = Field(description="Original extracted concept name")
    definition: str = Field(description="Context-specific definition")
    text_evidence: str = Field(description="Text evidence from extraction")
    source_document: str = Field(description="Source document filename")


class HasQuestionRelationshipProperties(Neo4jRelationshipProperties):
    """Properties for HAS_QUESTION relationships (CONCEPT -> QUIZ_QUESTION)."""
    pass  # No additional properties needed


class Neo4jRelationship(BaseModel):
    """Represents a Neo4j relationship with type safety."""
    id: str = Field(description="Unique relationship identifier")
    relationship_type: str = Field(description="Relationship type (HAS_THEORY, MENTIONS, HAS_QUESTION)")
    start_node_id: str = Field(description="Source node ID")
    end_node_id: str = Field(description="Target node ID")
    properties: Neo4jRelationshipProperties = Field(description="Relationship properties")

    class Config:
        # Allow subclasses of Neo4jRelationshipProperties
        arbitrary_types_allowed = True


class Neo4jGraphData(BaseModel):
    """Complete Neo4j graph data structure with nodes and relationships."""
    nodes: List[Neo4jNode] = Field(description="List of nodes")
    relationships: List[Neo4jRelationship] = Field(description="List of relationships")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for backward compatibility with existing Neo4j service."""
        return {
            "nodes": [
                {
                    "id": node.id,
                    "label": node.label,
                    "properties": node.properties.dict()
                }
                for node in self.nodes
            ],
            "relationships": [
                {
                    "id": rel.id,
                    "relationship_type": rel.relationship_type,
                    "start_node_id": rel.start_node_id,
                    "end_node_id": rel.end_node_id,
                    "properties": rel.properties.dict()
                }
                for rel in self.relationships
            ]
        }


class Neo4jInsertionResult(BaseModel):
    """Result of Neo4j insertion operation."""
    success: bool = Field(description="Whether insertion was successful")
    nodes_created: int = Field(description="Number of nodes created", default=0)
    relationships_created: int = Field(description="Number of relationships created", default=0)
    source_file: str = Field(description="Source file path")
    error: Optional[str] = Field(description="Error message if failed", default=None)


class ConceptRelationship(BaseModel):
    """Semantic relationship between two concepts."""
    s: str = Field(description="Source concept")
    t: str = Field(description="Target concept")
    rel: str = Field(description="SAME_AS, USED_FOR, or RELATED_TO")
    r: str = Field(description="Concise explanation (max 80 chars)")

    class Config:
        # Enable validation
        validate_assignment = True


class RelationshipBatch(BaseModel):
    """Batch of relationship proposals for LLM structured output."""
    relationships: List[ConceptRelationship] = Field(description="List of proposed relationships")


class RelationshipOperation(BaseModel):
    """Modify or delete operation on a relationship."""
    source: str = Field(description="Source concept (exact, case-sensitive)")
    relation: str = Field(description="Current relation type")
    target: str = Field(description="Target concept (exact, case-sensitive)")
    action: Literal["modify", "delete"] = Field(description="modify or delete")
    new_relation: Optional[str] = Field(None, description="New relation if modifying")
    new_target: Optional[str] = Field(None, description="New target if modifying")
    new_source: Optional[str] = Field(None, description="New source if modifying")
    reason: str = Field(description="Why this change is needed (max 80 chars)")


class RelationshipAddition(BaseModel):
    """New relationship to add."""
    source: str = Field(description="Source concept")
    target: str = Field(description="Target concept")
    relation: str = Field(description="SAME_AS, USED_FOR, or RELATED_TO")
    reasoning: str = Field(description="Why critical to add (max 80 chars)")


class FeedbackResult(BaseModel):
    """Validation feedback with operations. Empty lists = convergence."""
    modify: List[RelationshipOperation] = Field(
        default_factory=list,
        description="Fix relation type/direction. Empty = none needed"
    )
    delete: List[RelationshipOperation] = Field(
        default_factory=list,
        description="Remove duplicates/wrong relationships. Empty = none needed"
    )
    add: List[RelationshipAddition] = Field(
        default_factory=list,
        description="Add critical missing relationships. Empty = none needed"
    )
