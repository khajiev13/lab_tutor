"""
Enhanced State Models for LangGraph Relationship Detection Workflow

This module defines comprehensive state schemas for the iterative relationship
generation and validation workflow, including quality metrics, history tracking,
and convergence analysis.
"""

from typing import List, Dict, Optional, TypedDict, Tuple, Any
from datetime import datetime
from pydantic import BaseModel, Field
from models.neo4j_models import ConceptRelationship


# ============================================================================
# Helper Functions for String-Based Keys (LangSmith-compatible)
# ============================================================================

def make_merge_key(concept_a: str, concept_b: str) -> str:
    """
    Create a deterministic string key for a concept pair.
    
    Sorts concepts alphabetically to handle order variations (A,B vs B,A).
    Uses '|||' delimiter which is unlikely to appear in concept names.
    
    Args:
        concept_a: First concept name
        concept_b: Second concept name
        
    Returns:
        String key in format "concept1|||concept2" (sorted)
    """
    sorted_concepts = sorted([concept_a, concept_b])
    return f"{sorted_concepts[0]}|||{sorted_concepts[1]}"


def make_relationship_key(source: str, target: str, relation: str) -> str:
    """
    Create a deterministic string key for a relationship triple.
    
    Uses '|||' delimiter which is unlikely to appear in concept/relation names.
    Does NOT sort (direction matters for relationships).
    
    Args:
        source: Source concept name
        target: Target concept name
        relation: Relationship type
        
    Returns:
        String key in format "source|||target|||relation"
    """
    return f"{source}|||{target}|||{relation}"


def parse_merge_key(key: str) -> Tuple[str, str]:
    """
    Parse a merge key back into concept names.
    
    Args:
        key: String key in format "concept1|||concept2"
        
    Returns:
        Tuple of (concept_a, concept_b)
    """
    parts = key.split("|||")
    return parts[0], parts[1]


def parse_relationship_key(key: str) -> Tuple[str, str, str]:
    """
    Parse a relationship key back into components.
    
    Args:
        key: String key in format "source|||target|||relation"
        
    Returns:
        Tuple of (source, target, relation)
    """
    parts = key.split("|||")
    return parts[0], parts[1], parts[2]


class ConceptMerge(BaseModel):
    """Proposed merge between two similar concepts."""
    concept_a: str = Field(description="First concept name")
    concept_b: str = Field(description="Second concept name")
    canonical: str = Field(description="Canonical name to use after merge")
    variants: List[str] = Field(description="All variant names")
    r: str = Field(description="Reasoning for merge (max 80 chars)")


class WeakMerge(BaseModel):
    """A weak/incorrect merge proposal."""
    concept_a: str = Field(description="First concept name")
    concept_b: str = Field(description="Second concept name")
    canonical: str = Field(description="Proposed canonical name")
    r: str = Field(description="Original reasoning")
    w: str = Field(description="Why it's weak (max 80 chars)")


class MergeValidationFeedback(BaseModel):
    """Validation feedback for concept merges."""
    weak_merges: List[WeakMerge] = Field(
        default_factory=list,
        description="Merges that should NOT happen"
    )
    validation_notes: str = Field(default="", description="Brief assessment")
    total_validated: int = Field(default=0, description="Total merges validated")
    weak_count: int = Field(default=0, description="Number of weak merges found")


class MergeBatch(BaseModel):
    """Batch of concept merge proposals for LLM structured output."""
    merges: List[ConceptMerge] = Field(description="List of proposed concept merges")


class WeakRelationship(BaseModel):
    """A weak relationship identified during validation."""
    s: str = Field(description="Source concept")
    t: str = Field(description="Target concept")
    rel: str = Field(description="Relation type")
    r: str = Field(description="Original reasoning from generation")
    w: str = Field(description="Why it's weak (based on definitions, max 80 chars)")


class ValidationFeedback(BaseModel):
    """Binary validation feedback - returns only weak relationships."""
    weak_relationships: List[WeakRelationship] = Field(
        default_factory=list,
        description="Only WEAK relationships (valid ones inferred programmatically)"
    )
    validation_notes: str = Field(default="", description="Brief assessment")
    total_validated: int = Field(default=0, description="Total relationships validated")
    weak_count: int = Field(default=0, description="Number of weak relationships found")
    
    @property
    def has_weak_relationships(self) -> bool:
        """Check if any weak relationships were found."""
        return len(self.weak_relationships) > 0


class IterationSnapshot(BaseModel):
    """
    Snapshot of state at a specific iteration.
    
    Maintains complete history of relationships and feedback for analysis.
    """
    iteration_number: int = Field(description="Iteration number (0-indexed)")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO timestamp of this iteration"
    )
    valid_count: int = Field(description="Number of valid relationships in this iteration")
    weak_count: int = Field(description="Number of weak relationships in this iteration")
    total_accumulated: int = Field(description="Total accumulated valid relationships")
    feedback: Optional[ValidationFeedback] = Field(
        None,
        description="Validation feedback for this iteration"
    )
    
    class Config:
        # Allow arbitrary types for datetime
        arbitrary_types_allowed = True


class ConvergenceMetrics(BaseModel):
    """
    Metrics for tracking convergence progress (binary approach).
    
    Helps determine when the iterative process should terminate.
    """
    # Relationship metrics
    valid_count_trend: List[int] = Field(
        default_factory=list,
        description="Valid relationships per iteration"
    )
    weak_count_trend: List[int] = Field(
        default_factory=list,
        description="Weak relationships per iteration"
    )
    total_accumulated_trend: List[int] = Field(
        default_factory=list,
        description="Total accumulated valid relationships"
    )
    
    # Merge metrics
    merge_count_trend: List[int] = Field(
        default_factory=list,
        description="Merge proposals per iteration"
    )
    valid_merge_trend: List[int] = Field(
        default_factory=list,
        description="Valid merges per iteration"
    )
    weak_merge_trend: List[int] = Field(
        default_factory=list,
        description="Weak merges per iteration"
    )
    total_merges_trend: List[int] = Field(
        default_factory=list,
        description="Total accumulated merges"
    )
    
    # New unique discovery trends (what matters for convergence)
    new_unique_merges_trend: List[int] = Field(
        default_factory=list,
        description="New unique merges added per iteration"
    )
    new_unique_relationships_trend: List[int] = Field(
        default_factory=list,
        description="New unique relationships added per iteration"
    )
    
    # Independent convergence flags
    merges_converged: bool = Field(
        default=False,
        description="Whether merge generation has converged"
    )
    relationships_converged: bool = Field(
        default=False,
        description="Whether relationship generation has converged"
    )
    
    is_converged: bool = Field(
        default=False,
        description="Whether convergence criteria are met"
    )
    convergence_reason: str = Field(
        default="",
        description="Reason for convergence (or lack thereof)"
    )
    
    def update_trends(self, valid_count: int, weak_count: int, total_accumulated: int, new_unique_relationships: int = 0):
        """Update relationship trend metrics with new iteration data."""
        self.valid_count_trend.append(valid_count)
        self.weak_count_trend.append(weak_count)
        self.total_accumulated_trend.append(total_accumulated)
        self.new_unique_relationships_trend.append(new_unique_relationships)
    
    def update_merge_trends(self, merge_count: int, valid_merge_count: int, weak_merge_count: int, total_merges: int, new_unique_merges: int = 0):
        """Update merge trend metrics with new iteration data."""
        self.merge_count_trend.append(merge_count)
        self.valid_merge_trend.append(valid_merge_count)
        self.weak_merge_trend.append(weak_merge_count)
        self.total_merges_trend.append(total_merges)
        self.new_unique_merges_trend.append(new_unique_merges)
    
    def check_convergence(
        self,
        feedback: ValidationFeedback,
        iteration_count: int,
        max_iterations: int
    ) -> tuple[bool, str]:
        """
        Check if convergence criteria are met (binary approach).
        
        Returns:
            Tuple of (is_converged, reason)
        """
        # Check if no weak relationships found
        if feedback.weak_count == 0:
            return True, "No weak relationships found - all valid!"
        
        # Check if generation is failing (no progress after 3 iterations)
        if len(self.total_accumulated_trend) >= 3:
            last_three = self.total_accumulated_trend[-3:]
            if all(count == 0 for count in last_three):
                return True, "No relationships generated after 3 iterations - stopping"
            # Check if stuck (no progress for 3 iterations)
            if len(set(last_three)) == 1 and last_three[0] > 0:
                return True, "No new relationships for 3 iterations - converged"
        
        # Check max iterations
        if iteration_count >= max_iterations:
            return True, f"Maximum iterations ({max_iterations}) reached"
        
        return False, f"{feedback.weak_count} weak relationships found"


class EnhancedRelationshipState(TypedDict):
    """
    Enhanced state schema for LangGraph relationship detection workflow (binary approach).
    
    This state maintains comprehensive tracking of the iterative accumulation process,
    using binary valid/weak classification without scoring.
    
    State Flow:
    1. Initialize with concepts and configuration
    2. Generation node creates NEW batch of merges + relationships (avoiding weak patterns)
    3. Validation node classifies as valid/weak, accumulates valid ones programmatically
    4. Convergence checker evaluates termination criteria (no weak OR max iterations)
    5. Repeat 2-4 until convergence
    """
    # Core data
    concepts: List[Dict[str, str]]
    """All concepts from Neo4j to process"""
    
    # Concept merge tracking
    all_merges: Dict[str, ConceptMerge]
    """All valid concept merges accumulated. Key: string from make_merge_key(concept_a, concept_b)"""
    
    weak_merges: Dict[str, str]
    """All weak merge patterns to avoid. Key: string from make_merge_key(concept_a, concept_b), Value: weakness_reason"""
    
    new_merge_batch: List[ConceptMerge]
    """New merge proposals generated in current iteration"""
    
    current_merge_feedback: Optional[MergeValidationFeedback]
    """Latest merge validation feedback"""
    
    # Relationship tracking
    all_relationships: Dict[str, ConceptRelationship]
    """All valid relationships accumulated across iterations. Key: string from make_relationship_key(source, target, relation)"""
    
    weak_relationships: Dict[str, str]
    """All weak patterns to avoid. Key: string from make_relationship_key(source, target, relation), Value: weakness_reason"""
    
    new_batch: List[ConceptRelationship]
    """New relationships generated in current iteration"""
    
    # Feedback
    current_feedback: Optional[ValidationFeedback]
    """Latest validation feedback (only weak relationships)"""
    
    # History tracking
    iteration_history: List[IterationSnapshot]
    """Complete history of all iterations for analysis"""
    
    # Convergence tracking
    convergence_metrics: ConvergenceMetrics
    """Metrics for tracking convergence progress"""
    
    # Configuration
    iteration_count: int
    """Current iteration number (0-indexed)"""
    
    max_iterations: int
    """Maximum allowed iterations"""
    
    relationship_types: List[str]
    """Allowed relationship types"""
    
    # Metadata
    processing_start_time: float
    """Start time for performance tracking"""
    
    workflow_metadata: Dict[str, Any]
    """Additional metadata for tracking and debugging"""


class WorkflowConfiguration(BaseModel):
    """
    Configuration for the enhanced relationship detection workflow (binary approach).
    
    Centralizes all configurable parameters for easy tuning.
    """
    max_iterations: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Maximum number of generation iterations"
    )
    relationship_types: Dict[str, str] = Field(
        description="Allowed relationship types with descriptions"
    )
    enable_history_tracking: bool = Field(
        default=True,
        description="Whether to maintain full iteration history"
    )
    verbose_logging: bool = Field(
        default=True,
        description="Enable detailed logging output"
    )
    
    class Config:
        # Allow arbitrary types
        arbitrary_types_allowed = True

