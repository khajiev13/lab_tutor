"""
Pydantic models for Neo4j graph data structures.

These models provide type safety and validation for Neo4j nodes and relationships,
replacing raw dictionary-based data structures in the ingestion pipeline.
"""

from typing import List, Dict, Any, Optional
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


class Neo4jNode(BaseModel):
    """Represents a Neo4j node with type safety."""
    id: str = Field(description="Unique node identifier")
    label: str = Field(description="Node label (TOPIC, THEORY, CONCEPT)")
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


class Neo4jRelationship(BaseModel):
    """Represents a Neo4j relationship with type safety."""
    id: str = Field(description="Unique relationship identifier")
    relationship_type: str = Field(description="Relationship type (HAS_THEORY, MENTIONS)")
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
