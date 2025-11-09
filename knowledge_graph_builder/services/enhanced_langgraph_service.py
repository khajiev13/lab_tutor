"""
Enhanced Relationship Detection Service using LangGraph with Quality Metrics

This service implements an advanced iterative workflow for concept relationship detection
with comprehensive quality scoring, state history tracking, and sophisticated convergence logic.
"""

import os
import json
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from dotenv import load_dotenv

# LangSmith tracing is now enabled (token limit was the issue, not LangSmith)
# If you see "keys must be str, int..." errors, it's just logging - workflow still works

# LangChain and LangGraph imports
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from langgraph.graph import StateGraph, END

# Local imports
from services.neo4j_service import Neo4jService
from models.neo4j_models import ConceptRelationship, RelationshipBatch
from models.langgraph_state_models import (
    EnhancedRelationshipState,
    ValidationFeedback,
    WeakRelationship,
    ConceptMerge,
    WeakMerge,
    MergeValidationFeedback,
    MergeBatch,
    IterationSnapshot,
    ConvergenceMetrics,
    WorkflowConfiguration,
    make_merge_key,
    make_relationship_key,
    parse_merge_key,
    parse_relationship_key
)
from prompts.enhanced_relationship_prompts import (
    BINARY_VALIDATION_PROMPT,
    BINARY_GENERATION_PROMPT
)
from prompts.concept_normalization_prompts import (
    CONCEPT_NORMALIZATION_PROMPT,
    MERGE_VALIDATION_PROMPT
)

load_dotenv()

logger = logging.getLogger(__name__)


class EnhancedRelationshipService:
    """
    Enhanced relationship detection service with binary classification and iterative accumulation.
    
    Key Features:
    - Binary valid/weak classification (no scoring)
    - Iterative accumulation of valid relationships across iterations
    - Dict-based storage with automatic deduplication
    - Weak pattern avoidance in generation
    - Convergence when no weak relationships found or max iterations reached
    """
    
    def __init__(
        self,
        neo4j_service: Neo4jService,
        config: WorkflowConfiguration,
        model_id: str = "gpt-4o-2024-08-06"
    ):
        """
        Initialize the EnhancedRelationshipService.
        
        Args:
            neo4j_service: Neo4j service for graph operations
            config: Workflow configuration with quality thresholds and parameters
            model_id: LLM model identifier
        """
        load_dotenv()
        
        self.neo4j_service = neo4j_service
        self.config = config
        self.model_id = model_id
        self.relationship_types = config.relationship_types
        self.relationship_type_names = list(config.relationship_types.keys())
        
        # Create debug output directory for iteration logging
        self.debug_dir = "iteration_logs"
        os.makedirs(self.debug_dir, exist_ok=True)
        
        # Initialize LLM
        self.api_key = os.getenv("XIAO_CASE_API_KEY")
        self.api_base = os.getenv("XIAO_CASE_API_BASE", "https://api.xiaocaseai.com/v1")
        
        if not self.api_key:
            raise ValueError("XIAO_CASE_API_KEY environment variable is required")
        
        self.llm = ChatOpenAI(
            model=model_id,
            base_url=self.api_base,
            api_key=SecretStr(self.api_key),
            temperature=0,
            timeout=600,  # 10 minutes timeout to prevent indefinite hanging
            max_completion_tokens=8192  # Allow longer outputs for relationship generation
        )

        # Use structured output to force proper JSON formatting
        # For GPT-4o through proxy API, use json_mode to avoid parsing issues
        if "gpt-4o" in model_id:
            # Use json_mode for GPT-4o (more compatible with proxy APIs)
            self.relationship_chain = self.llm.with_structured_output(RelationshipBatch, method="json_mode")
            self.validation_chain = self.llm.with_structured_output(ValidationFeedback, method="json_mode")
            self.merge_chain = self.llm.with_structured_output(MergeBatch, method="json_mode")
            self.merge_validation_chain = self.llm.with_structured_output(MergeValidationFeedback, method="json_mode")
        else:
            # Use default function_calling for other models (DeepSeek, etc.)
            self.relationship_chain = self.llm.with_structured_output(RelationshipBatch)
            self.validation_chain = self.llm.with_structured_output(ValidationFeedback)
            self.merge_chain = self.llm.with_structured_output(MergeBatch)
            self.merge_validation_chain = self.llm.with_structured_output(MergeValidationFeedback)
        
        # Compile LangGraph workflow
        self.workflow = self._create_workflow()
        
        if self.config.verbose_logging:
            logger.info(f"EnhancedRelationshipService initialized - Model: {model_id}, Max iterations: {config.max_iterations}")
    
    def _create_workflow(self):
        """
        Create and compile the enhanced LangGraph workflow.
        
        Workflow Structure:
        1. Entry → Generation Node
        2. Generation → Validation Node
        3. Validation → Convergence Checker
        4. Convergence → Either continue (back to Generation) or END
        
        Returns:
            Compiled StateGraph workflow
        """
        # Create state graph with enhanced state schema
        workflow = StateGraph(EnhancedRelationshipState)
        
        # Add nodes
        workflow.add_node("generation", self._generation_node)
        workflow.add_node("validation", self._validation_node)
        
        # Define edges
        workflow.set_entry_point("generation")
        workflow.add_edge("generation", "validation")
        
        # Conditional edge from validation
        workflow.add_conditional_edges(
            "validation",
            self._convergence_checker,
            {
                "continue": "generation",
                "complete": END
            }
        )
        
        return workflow.compile()
    
    def detect_relationships(
        self,
        output_file: str = "enhanced_relationships.json",
        langsmith_run_name: str = "enhanced_relationship_detection",
        langsmith_tags: Optional[List[str]] = None,
        langsmith_metadata: Optional[Dict] = None
    ) -> tuple[List[ConceptRelationship], str, Dict]:
        """
        Detect relationships with quality metrics and comprehensive tracking.
        
        Args:
            output_file: Output JSON filename
            langsmith_run_name: LangSmith run name for tracing
            langsmith_tags: Tags for LangSmith filtering
            langsmith_metadata: Additional metadata for LangSmith
            
        Returns:
            Tuple of (relationships, output_path, workflow_stats)
        """
        if self.config.verbose_logging:
            print(f"\n{'='*80}")
            print(f"🚀 ENHANCED RELATIONSHIP DETECTION (Binary Approach)")
            print(f"{'='*80}")
            print(f"Max iterations: {self.config.max_iterations}")
            print(f"Relationship types: {', '.join(self.relationship_type_names)}")
        
        # Get all concepts
        concepts = self._get_all_concepts()
        
        if self.config.verbose_logging:
            print(f"Total concepts: {len(concepts)}")
        
        # Initialize state (binary approach with concept normalization)
        initial_state: EnhancedRelationshipState = {
            "concepts": concepts,
            # Merge tracking
            "all_merges": {},  # Dict[(concept_a, concept_b)] -> ConceptMerge
            "weak_merges": {},  # Dict[(concept_a, concept_b)] -> weakness_reason
            "new_merge_batch": [],
            "current_merge_feedback": None,
            # Relationship tracking
            "all_relationships": {},  # Dict[(source, target, relation)] -> ConceptRelationship
            "weak_relationships": {},  # Dict[(source, target, relation)] -> weakness_reason
            "new_batch": [],
            "current_feedback": None,
            # History and metrics
            "iteration_history": [],
            "convergence_metrics": ConvergenceMetrics(),
            "iteration_count": 0,
            "max_iterations": self.config.max_iterations,
            "relationship_types": self.relationship_type_names,
            "processing_start_time": time.time(),
            "workflow_metadata": {
                "model": self.model_id,
                "total_concepts": len(concepts),
                "langsmith_run_name": langsmith_run_name
            }
        }
        
        # Execute workflow
        final_state = self.workflow.invoke(initial_state,{'recursion_limit':100})
        
        # Extract results (convert dict to list)
        relationships = list(final_state["all_relationships"].values())
        processing_time = time.time() - final_state["processing_start_time"]
        
        # Compile workflow statistics
        workflow_stats = self._compile_workflow_stats(final_state, processing_time)
        
        # Save results
        output_path = self._save_results(
            relationships,
            output_file,
            workflow_stats,
            final_state
        )
        
        if self.config.verbose_logging:
            self._print_summary(workflow_stats, output_path)
        
        return relationships, output_path, workflow_stats
    
    def _get_all_concepts(self) -> List[Dict[str, str]]:
        """Get all concepts from Neo4j."""
        return self.neo4j_service.get_all_concepts()

    def _log_prompt_length(self, messages, context: str = ""):
        """
        Log the length of prompts being sent to LLM.

        Args:
            messages: List of message objects (BaseMessage) or dicts with 'role' and 'content'
            context: Optional context string (e.g., "Initial Generation", "Validation")
        """
        if not self.config.verbose_logging:
            return

        total_chars = 0
        breakdown = []

        for msg in messages:
            # Handle both BaseMessage objects and dict messages
            if hasattr(msg, 'type') and hasattr(msg, 'content'):
                # BaseMessage object (from ChatPromptTemplate)
                role = msg.type
                content = msg.content
            elif isinstance(msg, dict):
                # Dict message
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
            else:
                continue

            char_count = len(str(content))
            total_chars += char_count

            # Map role names for display
            role_display = {
                'system': 'System',
                'human': 'User',
                'user': 'User',
                'assistant': 'Assistant'
            }.get(role, role.capitalize())

            breakdown.append(f"{role_display}: {char_count:,} chars")

        # Estimate tokens (rough approximation: 1 token ≈ 4 characters)
        estimated_tokens = total_chars // 4

        context_str = f" ({context})" if context else ""
        print(f"   📏 Prompt Length{context_str}: {total_chars:,} characters (~{estimated_tokens:,} tokens)")
        if len(breakdown) > 1:
            print(f"      {', '.join(breakdown)}")
    
    def _generation_node(self, state: EnhancedRelationshipState) -> EnhancedRelationshipState:
        """
        Generation node: Generate merges AND relationships with smart LLM calling.
        
        Makes two LLM calls:
        1. Find similar concepts (if not converged)
        2. Generate relationships (if not converged)
        """
        iteration = state["iteration_count"]
        concepts = state["concepts"]

        if self.config.verbose_logging:
            logger.info(f"ITERATION {iteration + 1}/{state['max_iterations']} - Generation Phase - Concepts: {len(concepts)}")

        # Get convergence status from metrics
        metrics = state["convergence_metrics"]
        merges_converged = metrics.merges_converged
        relationships_converged = metrics.relationships_converged
        
        # === LLM CALL 1: Find Similar Concepts (if not converged) ===
        new_merges = []
        if not merges_converged:
            if self.config.verbose_logging:
                logger.debug(f"Finding similar concepts - Weak merge patterns to avoid: {len(state['weak_merges'])}")
            
            new_merges = self._find_similar_concepts(
                concepts=concepts,
                weak_merges=state["weak_merges"]
            )
            
            if self.config.verbose_logging:
                logger.info(f"Found {len(new_merges)} merge proposals")
        else:
            if self.config.verbose_logging:
                logger.info("Merge detection converged - skipping")
        
        # === LLM CALL 2: Generate Relationships (if not converged) ===
        new_batch = []
        if not relationships_converged:
            if self.config.verbose_logging:
                logger.debug(f"Generating relationships - Weak patterns to avoid: {len(state['weak_relationships'])}")
            
            weak_patterns_list = self._format_weak_patterns(state["weak_relationships"])
            new_batch = self._generate_relationships(
                concepts=concepts,
                weak_patterns=weak_patterns_list
            )
            
            if self.config.verbose_logging:
                logger.info(f"Generated {len(new_batch)} relationships")
        else:
            if self.config.verbose_logging:
                logger.info("Relationship generation converged - skipping")

        updated_state = {
            **state,
            "new_merge_batch": new_merges,
            "new_batch": new_batch
        }
        
        # Save iteration state after generation
        self._save_iteration_state(updated_state, iteration, "generation")
        
        return updated_state  # type: ignore

    def _format_weak_patterns(self, weak_dict: Dict) -> str:
        """Format weak relationships for prompt."""
        if not weak_dict:
            return "(none yet)"
        
        weak_list = sorted(list(weak_dict.items()))
        formatted = []
        for i, (key, reason) in enumerate(weak_list, 1):
            src, tgt, rel = parse_relationship_key(key)
            formatted.append(f"{i}. {src} --[{rel}]--> {tgt}")
            formatted.append(f"   Reason: {reason}")
        
        return "\n".join(formatted)
    
    def _format_weak_merges(self, weak_dict: Dict) -> str:
        """Format weak merge patterns for prompt."""
        if not weak_dict:
            return "(none yet)"
        
        weak_list = sorted(list(weak_dict.items()))
        formatted = []
        for i, (key, reason) in enumerate(weak_list, 1):
            concept_a, concept_b = parse_merge_key(key)
            formatted.append(f"{i}. {concept_a} + {concept_b}")
            formatted.append(f"   Reason: {reason}")
        
        return "\n".join(formatted)
    
    def _find_similar_concepts(
        self,
        concepts: List[Dict],
        weak_merges: Dict
    ) -> List[ConceptMerge]:
        """Call LLM to find similar concepts that should be merged (name-based only)."""
        
        # Create concept list (names only, no definitions)
        concept_list = "\n".join([f"- {c['name']}" for c in concepts])
        
        # Format weak merges to avoid
        weak_merges_list = self._format_weak_merges(weak_merges)
        num_weak = len(weak_merges)
        
        # Format prompt
        messages = CONCEPT_NORMALIZATION_PROMPT.format_messages(
            num_concepts=len(concepts),
            concept_list=concept_list,
            num_weak=num_weak,
            weak_merges_list=weak_merges_list
        )
        
        # Log prompt length
        self._log_prompt_length(messages, "Merge Generation")
        
        if self.config.verbose_logging:
            logger.debug("Invoking LLM for merge detection")
        
        try:
            # Use structured output - returns MergeBatch directly
            batch = self.merge_chain.invoke(messages)  # type: ignore
            
            if self.config.verbose_logging:
                logger.debug(f"Received {len(batch.merges)} merge proposals")  # type: ignore
            
            return batch.merges  # type: ignore
        
        except Exception as e:
            logger.error(f"Error in merge generation: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _save_iteration_state(self, state: Dict[str, Any], iteration: int, phase: str):
        """Save iteration state to JSON file for debugging."""
        if not self.config.verbose_logging:
            return
        
        try:
            # Convert state to serializable format
            serializable_state = {
                "iteration": iteration,
                "phase": phase,
                "timestamp": datetime.now().isoformat(),
                # Merge tracking
                "all_merges": [
                    {
                        "concept_a": merge.concept_a,
                        "concept_b": merge.concept_b,
                        "canonical": merge.canonical,
                        "variants": merge.variants,
                        "r": merge.r
                    }
                    for merge in state.get("all_merges", {}).values()
                ],
                "weak_merges": [
                    {"concept_a": parse_merge_key(key)[0], "concept_b": parse_merge_key(key)[1], "reason": reason}
                    for key, reason in state.get("weak_merges", {}).items()
                ],
                "new_merge_batch": [
                    {
                        "concept_a": merge.concept_a,
                        "concept_b": merge.concept_b,
                        "canonical": merge.canonical,
                        "variants": merge.variants,
                        "r": merge.r
                    }
                    for merge in state.get("new_merge_batch", [])
                ],
                # Relationship tracking
                "all_relationships": [
                    {"s": rel.s, "t": rel.t, "rel": rel.rel, "r": rel.r}
                    for rel in state["all_relationships"].values()
                ],
                "weak_patterns": [
                    {"s": parse_relationship_key(key)[0], "t": parse_relationship_key(key)[1], "rel": parse_relationship_key(key)[2], "reason": reason}
                    for key, reason in state["weak_relationships"].items()
                ],
                "new_batch": [
                    {"s": rel.s, "t": rel.t, "rel": rel.rel, "r": rel.r}
                    for rel in state.get("new_batch", [])
                ],
                # Metrics
                "metrics": {
                    "total_merges": len(state.get("all_merges", {})),
                    "total_weak_merges": len(state.get("weak_merges", {})),
                    "new_merge_batch_size": len(state.get("new_merge_batch", [])),
                    "total_valid": len(state["all_relationships"]),
                    "total_weak_patterns": len(state["weak_relationships"]),
                    "new_batch_size": len(state.get("new_batch", [])),
                },
                # Feedback
                "merge_feedback": {
                    "weak_count": state.get("current_merge_feedback", {}).weak_count if state.get("current_merge_feedback") else 0,
                    "validation_notes": state.get("current_merge_feedback", {}).validation_notes if state.get("current_merge_feedback") else ""
                } if state.get("current_merge_feedback") else None,
                "relationship_feedback": {
                    "weak_count": state.get("current_feedback", {}).weak_count if state.get("current_feedback") else 0,
                    "validation_notes": state.get("current_feedback", {}).validation_notes if state.get("current_feedback") else ""
                } if state.get("current_feedback") else None
            }
            
            filename = f"{self.debug_dir}/iteration_{iteration:02d}_{phase}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(serializable_state, f, indent=2, ensure_ascii=False)
            
            if self.config.verbose_logging:
                logger.debug(f"Saved state to {filename}")
        
        except Exception as e:
            logger.warning(f"Failed to save iteration state: {e}")
    
    def _generate_relationships(
        self,
        concepts: List[Dict],
        weak_patterns: str
    ) -> List[ConceptRelationship]:
        """Call LLM to generate relationships."""
        
        # Create concept list
        concept_list = "\n".join([f"- {c['name']}" for c in concepts])
        
        # Create relationship types description
        relationship_types_desc = "\n".join([
            f"- **{rel_type}**: {desc}"
            for rel_type, desc in self.relationship_types.items()
        ])
        
        # Count weak patterns
        num_weak = len(weak_patterns.split('\n')) if weak_patterns != "(none yet)" else 0
        
        # Format prompt
        messages = BINARY_GENERATION_PROMPT.format_messages(
            num_concepts=len(concepts),
            concept_list=concept_list,
            relationship_types_desc=relationship_types_desc,
            num_weak=num_weak,
            weak_patterns_list=weak_patterns
        )
        
        # Log prompt length
        self._log_prompt_length(messages, "Generation")
        
        if self.config.verbose_logging:
            logger.debug("Invoking LLM with structured output")
        
        try:
            # Use structured output - returns RelationshipBatch directly
            batch = self.relationship_chain.invoke(messages)  # type: ignore
            
            if self.config.verbose_logging:
                logger.debug(f"Received {len(batch.relationships)} relationships")  # type: ignore
            
            return batch.relationships  # type: ignore
        
        except Exception as e:
            logger.error(f"Error in generation: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _validation_node(self, state: EnhancedRelationshipState) -> EnhancedRelationshipState:
        """
        Validation node: Validate merges AND relationships, accumulate valid ones programmatically.
        
        Binary classification - returns only weak items, valid ones calculated programmatically.
        """
        new_merge_batch = state["new_merge_batch"]
        new_relationship_batch = state["new_batch"]
        
        all_merges = state["all_merges"]
        weak_merges = state["weak_merges"]
        all_relationships = state["all_relationships"]
        weak_relationships = state["weak_relationships"]

        if not new_merge_batch and not new_relationship_batch:
            logger.warning("Nothing to validate")
            return {**state, "iteration_count": state["iteration_count"] + 1}  # type: ignore

        if self.config.verbose_logging:
            logger.info("Validation Phase")
        
        # === VALIDATE MERGES ===
        merge_feedback = None
        valid_merge_count = 0
        if new_merge_batch:
            if self.config.verbose_logging:
                logger.debug(f"Validating {len(new_merge_batch)} merge proposals")
            
            merge_feedback = self._validate_merges(new_merge_batch)
            
            # Process merge validation - accumulate weak merges first
            for weak_merge in merge_feedback.weak_merges:
                # Use string key (automatically sorts for normalization)
                key = make_merge_key(weak_merge.concept_a, weak_merge.concept_b)
                weak_merges[key] = weak_merge.w
            
            # Calculate valid merges - filter against ALL accumulated weak merges (not just current iteration)
            valid_merges = []
            for m in new_merge_batch:
                # Use string key to match weak_merges format
                key = make_merge_key(m.concept_a, m.concept_b)
                # Check against accumulated weak_merges dict (includes all iterations)
                if key not in weak_merges:
                    valid_merges.append(m)
            
            # Add to accumulated merges (auto-deduplicate)
            new_unique_merges = 0
            for merge in valid_merges:
                # Use string key (automatically sorts for normalization)
                key = make_merge_key(merge.concept_a, merge.concept_b)
                if key not in all_merges:
                    new_unique_merges += 1
                all_merges[key] = merge
            
            valid_merge_count = len(valid_merges)
            
            if self.config.verbose_logging:
                logger.info(f"Merge validation - Total: {merge_feedback.total_validated}, Weak: {merge_feedback.weak_count}, Valid: {valid_merge_count}, New unique: {new_unique_merges}, Accumulated: {len(all_merges)}")

        # === VALIDATE RELATIONSHIPS ===
        rel_feedback = None
        valid_rel_count = 0
        if new_relationship_batch:
            if self.config.verbose_logging:
                logger.debug(f"Validating {len(new_relationship_batch)} relationships")

            # Get concept definitions from Neo4j
            concept_names = set()
            for rel in new_relationship_batch:
                concept_names.update([rel.s, rel.t])

            definitions = self.neo4j_service.get_concept_definitions(list(concept_names))

            # Validate relationships
            rel_feedback = self._validate_relationships(new_relationship_batch, definitions)

            if self.config.verbose_logging:
                logger.debug(f"Relationship validation - Total: {rel_feedback.total_validated}, Weak: {rel_feedback.weak_count}, Valid: {rel_feedback.total_validated - rel_feedback.weak_count}")

            # === PROGRAMMATIC PROCESSING ===
            
            # 1. Extract weak keys and update weak_relationships dict
            weak_keys = set()
            for weak_rel in rel_feedback.weak_relationships:
                key = make_relationship_key(weak_rel.s, weak_rel.t, weak_rel.rel)
                weak_keys.add(key)
                
                # Add/update weak_relationships dict
                weak_relationships[key] = weak_rel.w

            # 2. Calculate valid relationships (new_batch - weak)
            valid_rels = [
                rel for rel in new_relationship_batch
                if make_relationship_key(rel.s, rel.t, rel.rel) not in weak_keys
            ]

            # 3. Add valid relationships to all_relationships (auto-deduplicate)
            new_unique_count = 0
            for rel in valid_rels:
                key = make_relationship_key(rel.s, rel.t, rel.rel)
                if key not in all_relationships:
                    new_unique_count += 1
                all_relationships[key] = rel

            valid_rel_count = len(valid_rels)

            if self.config.verbose_logging:
                logger.info(f"New unique valid relationships: {new_unique_count}, Total accumulated: {len(all_relationships)}")

        # Update convergence metrics
        metrics = state["convergence_metrics"]
        
        # Track new unique counts for convergence checking
        new_unique_rels = 0
        new_unique_merges_count = 0
        
        # Update relationship trends
        if new_relationship_batch:
            new_unique_rels = new_unique_count
            metrics.update_trends(
                valid_count=valid_rel_count,
                weak_count=rel_feedback.weak_count if rel_feedback else 0,
                total_accumulated=len(all_relationships),
                new_unique_relationships=new_unique_count
            )
        
        # Update merge trends
        if new_merge_batch:
            new_unique_merges_count = new_unique_merges
            metrics.update_merge_trends(
                merge_count=len(new_merge_batch),
                valid_merge_count=valid_merge_count,
                weak_merge_count=merge_feedback.weak_count if merge_feedback else 0,
                total_merges=len(all_merges),
                new_unique_merges=new_unique_merges
            )
        
        # Update convergence flags based on new unique counts
        # Only mark as converged if we have at least one iteration of data
        if new_relationship_batch and new_unique_rels == 0 and len(metrics.new_unique_relationships_trend) > 0:
            metrics.relationships_converged = True
        if new_merge_batch and new_unique_merges_count == 0 and len(metrics.new_unique_merges_trend) > 0:
            metrics.merges_converged = True

        # Create iteration snapshot
        snapshot = IterationSnapshot(
            iteration_number=state["iteration_count"],
            valid_count=valid_rel_count if new_relationship_batch else 0,
            weak_count=rel_feedback.weak_count if rel_feedback else 0,
            total_accumulated=len(all_relationships),
            feedback=rel_feedback
        )

        # Update iteration history
        new_history = state["iteration_history"] + [snapshot] if self.config.enable_history_tracking else []

        updated_state = {
            **state,
            "all_merges": all_merges,
            "weak_merges": weak_merges,
            "new_merge_batch": [],  # Clear for next iteration
            "current_merge_feedback": merge_feedback,
            "all_relationships": all_relationships,
            "weak_relationships": weak_relationships,
            "new_batch": [],  # Clear for next iteration
            "current_feedback": rel_feedback,
            "convergence_metrics": metrics,
            "iteration_history": new_history,
            "iteration_count": state["iteration_count"] + 1
        }
        
        # Save iteration state after validation
        self._save_iteration_state(updated_state, state["iteration_count"], "validation")
        
        return updated_state  # type: ignore
    
    def _validate_relationships(
        self,
        batch: List[ConceptRelationship],
        definitions: Dict[str, List[str]]
    ) -> ValidationFeedback:
        """Call LLM to validate relationships."""
        
        # Format relationships
        relationships_summary = "\n".join([
            f"{i+1}. {rel.s} --[{rel.rel}]--> {rel.t}\n   Reasoning: {rel.r}"
            for i, rel in enumerate(batch)
        ])
        
        # Format definitions
        definitions_text = self._format_definitions(definitions)
        
        # Create relationship types string
        relationship_types = ", ".join(self.relationship_type_names)
        
        # Format prompt
        messages = BINARY_VALIDATION_PROMPT.format_messages(
            num_relationships=len(batch),
            relationships_summary=relationships_summary,
            definitions_text=definitions_text,
            relationship_types=relationship_types
        )
        
        # Log prompt length
        self._log_prompt_length(messages, "Validation")
        
        try:
            # Use structured output - returns ValidationFeedback directly
            feedback = self.validation_chain.invoke(messages)  # type: ignore
            
            if self.config.verbose_logging:
                logger.debug(f"Validation complete: {feedback.weak_count} weak relationships found")  # type: ignore
            
            return feedback  # type: ignore
        
        except Exception as e:
            logger.error(f"Error in validation: {e}")
            import traceback
            traceback.print_exc()
            
            # Return default feedback (all valid)
            return ValidationFeedback(
                weak_relationships=[],
                validation_notes="Error during validation",
                total_validated=len(batch),
                weak_count=0
            )
    
    def _validate_merges(
        self,
        batch: List[ConceptMerge]
    ) -> MergeValidationFeedback:
        """Call LLM to validate merge proposals using definitions."""
        
        # Get definitions for all concepts in batch
        concept_names = set()
        for merge in batch:
            concept_names.update([merge.concept_a, merge.concept_b])
        
        definitions = self.neo4j_service.get_concept_definitions(list(concept_names))
        
        if self.config.verbose_logging:
            logger.debug(f"Retrieved definitions for {len(concept_names)} concepts")
        
        # Format merges summary
        merges_summary = "\n".join([
            f"{i+1}. {merge.concept_a} + {merge.concept_b} → {merge.canonical}\n   Reasoning: {merge.r}"
            for i, merge in enumerate(batch)
        ])
        
        # Format definitions
        definitions_text = self._format_definitions(definitions)
        
        # Format prompt
        messages = MERGE_VALIDATION_PROMPT.format_messages(
            num_merges=len(batch),
            merges_summary=merges_summary,
            definitions_text=definitions_text
        )
        
        # Log prompt length
        self._log_prompt_length(messages, "Merge Validation")
        
        try:
            # Use structured output - returns MergeValidationFeedback directly
            feedback = self.merge_validation_chain.invoke(messages)  # type: ignore
            
            if self.config.verbose_logging:
                logger.debug(f"Merge validation complete: {feedback.weak_count} weak merges found")  # type: ignore
            
            return feedback  # type: ignore
        
        except Exception as e:
            logger.error(f"Error in merge validation: {e}")
            import traceback
            traceback.print_exc()
            
            # Return default feedback (all valid)
            return MergeValidationFeedback(
                weak_merges=[],
                validation_notes="Error during merge validation",
                total_validated=len(batch),
                weak_count=0
            )
    
    def _convergence_checker(self, state: EnhancedRelationshipState) -> str:
        """
        Convergence checker: Determine if workflow should continue or complete.
        
        Convergence criteria:
        - Both merges AND relationships produce 0 new unique items
        - Maximum iterations reached
        """
        iteration = state["iteration_count"]
        max_iterations = state["max_iterations"]
        metrics = state["convergence_metrics"]

        # Get latest new unique counts (default to 1 if no data yet)
        latest_merges = metrics.new_unique_merges_trend[-1] if metrics.new_unique_merges_trend else 1
        latest_rels = metrics.new_unique_relationships_trend[-1] if metrics.new_unique_relationships_trend else 1
        
        # Determine convergence
        is_converged = False
        reason = ""
        
        # Convergence: Both tasks produced 0 new items
        if latest_merges == 0 and latest_rels == 0:
            is_converged = True
            reason = "Both tasks exhausted - no new discoveries"
        elif iteration >= max_iterations:
            is_converged = True
            reason = f"Maximum iterations ({max_iterations}) reached"
        else:
            # Continue - at least one task is productive
            status = f"merges: {latest_merges} new, relationships: {latest_rels} new"
            reason = status

        # Update convergence state
        metrics.is_converged = is_converged
        metrics.convergence_reason = reason

        if self.config.verbose_logging:
            if is_converged:
                logger.info(f"CONVERGENCE ACHIEVED - Reason: {reason}, Total merges: {len(state['all_merges'])}, Total relationships: {len(state['all_relationships'])}")
            else:
                logger.info(f"Continuing iteration - Reason: {reason}")

        return "complete" if is_converged else "continue"
    
    def _format_definitions(self, definitions: Dict[str, List[str]]) -> str:
        """Format concept definitions for prompt."""
        if not definitions:
            return "(no definitions available)"
        
        formatted = []
        for concept, defs in definitions.items():
            if defs:
                formatted.append(f"\n**{concept}**:")
                for i, definition in enumerate(defs, 1):
                    formatted.append(f"  {i}. {definition}")
        
        return "\n".join(formatted) if formatted else "(no definitions available)"
    
    def _compile_workflow_stats(
        self,
        final_state: Dict[str, Any],
        processing_time: float
    ) -> Dict:
        """Compile comprehensive workflow statistics including merges and relationships."""
        convergence = final_state["convergence_metrics"]

        return {
            "timestamp": datetime.now().isoformat(),
            "processing_time_seconds": round(processing_time, 2),
            "total_iterations": final_state["iteration_count"],
            "total_concept_merges": len(final_state["all_merges"]),
            "total_weak_merges": len(final_state["weak_merges"]),
            "total_valid_relationships": len(final_state["all_relationships"]),
            "total_weak_patterns": len(final_state["weak_relationships"]),
            "convergence": {
                "achieved": convergence.is_converged,
                "reason": convergence.convergence_reason,
                "merge_count_trend": convergence.merge_count_trend,
                "valid_merge_trend": convergence.valid_merge_trend,
                "weak_merge_trend": convergence.weak_merge_trend,
                "total_merges_trend": convergence.total_merges_trend,
                "valid_count_trend": convergence.valid_count_trend,
                "weak_count_trend": convergence.weak_count_trend,
                "total_accumulated_trend": convergence.total_accumulated_trend,
                # Add quality_trend and operations_trend for backward compatibility
                # (These were removed from binary classification approach)
                "quality_trend": None,
                "operations_trend": None
            },
            "configuration": {
                "model": self.model_id,
                "max_iterations": self.config.max_iterations,
                "relationship_types": list(self.relationship_types.keys())
            }
        }

    def _save_results(
        self,
        relationships: List[ConceptRelationship],
        output_file: str,
        workflow_stats: Dict,
        final_state: Dict[str, Any]
    ) -> str:
        """Save results to JSON for review. Does NOT update database."""
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, output_file)

        # Convert merges to readable format
        merges_dict = [
            {
                "concept_a": merge.concept_a,
                "concept_b": merge.concept_b,
                "canonical": merge.canonical,
                "variants": merge.variants,
                "reasoning": merge.r
            }
            for merge in final_state["all_merges"].values()
        ]
        
        # Convert relationships to dicts (with original names)
        relationships_dict = [
            {"s": rel.s, "t": rel.t, "rel": rel.rel, "r": rel.r}
            for rel in relationships
        ]
        
        # Show what relationships WOULD look like with canonical names
        canonical_preview = []
        for rel in relationships:
            canonical_s = self._map_to_canonical(rel.s, final_state["all_merges"])
            canonical_t = self._map_to_canonical(rel.t, final_state["all_merges"])
            
            canonical_preview.append({
                "original": {"s": rel.s, "t": rel.t},
                "canonical": {"s": canonical_s, "t": canonical_t},
                "rel": rel.rel,
                "r": rel.r,
                "was_mapped": (canonical_s != rel.s or canonical_t != rel.t)
            })
        
        # Prepare output data
        output_data = {
            "metadata": workflow_stats,
            "concept_merges": {
                "total": len(merges_dict),
                "merges": merges_dict,
                "weak_merges": [
                    {
                        "concept_a": parse_merge_key(key)[0],
                        "concept_b": parse_merge_key(key)[1],
                        "reason": reason
                    }
                    for key, reason in final_state["weak_merges"].items()
                ]
            },
            "relationships": {
                "total": len(relationships_dict),
                "original": relationships_dict,
                "canonical_preview": canonical_preview
            }
        }

        # Add iteration history if enabled
        if self.config.enable_history_tracking and final_state["iteration_history"]:
            output_data["iteration_history"] = [
                {
                    "iteration": snapshot.iteration_number,
                    "timestamp": snapshot.timestamp,
                    "valid_count": snapshot.valid_count,
                    "weak_count": snapshot.weak_count,
                    "total_accumulated": snapshot.total_accumulated
                }
                for snapshot in final_state["iteration_history"]
            ]

        # Save to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print(f"\n{'='*80}")
        print(f"📁 Results saved to: {output_path}")
        print(f"👀 REVIEW THE FILE BEFORE APPLYING TO DATABASE")
        print(f"{'='*80}")

        return output_path
    
    def _map_to_canonical(
        self,
        concept_name: str,
        merge_state: Dict
    ) -> str:
        """Map original concept name to canonical name if merged."""
        for merge_info in merge_state.values():
            if concept_name in merge_info.variants:
                return merge_info.canonical
        return concept_name  # Not merged

    def _print_summary(self, workflow_stats: Dict, output_path: str):
        """Print workflow summary including merges and relationships."""
        print(f"\n{'='*80}")
        print(f"📊 WORKFLOW SUMMARY")
        print(f"{'='*80}")
        print(f"🔀 Concept Merges:")
        print(f"   Total Valid Merges: {workflow_stats['total_concept_merges']}")
        print(f"   Total Weak Merges: {workflow_stats['total_weak_merges']}")
        print(f"🔗 Relationships:")
        print(f"   Total Valid Relationships: {workflow_stats['total_valid_relationships']}")
        print(f"   Total Weak Patterns: {workflow_stats['total_weak_patterns']}")
        print(f"🔄 Iterations: {workflow_stats['total_iterations']}")
        print(f"⏱️  Processing Time: {workflow_stats['processing_time_seconds']}s")
        print(f"🎯 Convergence: {workflow_stats['convergence']['achieved']}")
        print(f"   Reason: {workflow_stats['convergence']['reason']}")
        print(f"📁 Output File: {output_path}")
        print(f"{'='*80}")
