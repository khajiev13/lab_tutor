from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterator
from typing import cast

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from neo4j import Session as Neo4jSession
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.settings import settings

from .models import (
    ConceptNormalizationState,
    ConvergenceMetrics,
    IterationSnapshot,
    WorkflowConfiguration,
    make_merge_key,
    parse_merge_key,
)
from .prompts import CONCEPT_NORMALIZATION_PROMPT, MERGE_VALIDATION_PROMPT
from .repository import ConceptNormalizationRepository
from .review_sql_repository import ConceptNormalizationReviewSqlRepository
from .schemas import (
    ConceptMerge,
    MergeProposal,
    MergeProposalDecision,
    MergeBatch,
    MergeValidationFeedback,
    NormalizationStreamEvent,
    WeakMerge,
)

logger = logging.getLogger(__name__)

try:
    from langsmith import traceable
except Exception:  # pragma: no cover
    # Keep runtime functional even if LangSmith isn't installed/enabled.
    def traceable(*_args, **_kwargs):  # type: ignore[no-redef]
        def _decorator(fn):
            return fn

        # Supports both `@traceable` and `@traceable(...)`.
        if _args and callable(_args[0]) and len(_args) == 1 and not _kwargs:
            return _args[0]
        return _decorator


def _summarize_state_for_trace(state: ConceptNormalizationState) -> dict:
    meta = state.get("workflow_metadata", {}) if isinstance(state, dict) else {}
    concepts = state.get("concepts", []) if isinstance(state, dict) else []
    all_merges = state.get("all_merges", {}) if isinstance(state, dict) else {}
    weak_merges = state.get("weak_merges", {}) if isinstance(state, dict) else {}
    return {
        "model": meta.get("model"),
        "last_phase": meta.get("last_phase"),
        "agent_activity": meta.get("agent_activity"),
        "concepts_count": len(concepts) if isinstance(concepts, list) else None,
        "iteration": state.get("iteration_count") if isinstance(state, dict) else None,
        "total_merges": len(all_merges) if isinstance(all_merges, dict) else None,
        "total_weak": len(weak_merges) if isinstance(weak_merges, dict) else None,
    }


def _process_trace_inputs(inputs: dict) -> dict:
    state = inputs.get("state")
    if isinstance(state, dict):
        return _summarize_state_for_trace(cast(ConceptNormalizationState, state))
    return {"inputs": list(inputs.keys())}


def _process_trace_outputs(outputs):
    if isinstance(outputs, dict):
        try:
            return _summarize_state_for_trace(cast(ConceptNormalizationState, outputs))
        except Exception:
            return {"output_keys": list(outputs.keys())}
    return {"output_type": type(outputs).__name__}


class ConceptNormalizationService:
    """LangGraph-driven concept normalization (generator-evaluator loop) with SSE streaming."""

    _repo: ConceptNormalizationRepository
    _review_repo: ConceptNormalizationReviewSqlRepository
    _config: WorkflowConfiguration
    _model_id: str

    def __init__(
        self,
        *,
        repo: ConceptNormalizationRepository,
        review_repo: ConceptNormalizationReviewSqlRepository,
        config: WorkflowConfiguration,
        model_id: str,
    ) -> None:
        self._repo = repo
        self._review_repo = review_repo
        self._config = config
        self._model_id = model_id

        if not settings.llm_api_key:
            raise ValueError(
                "LLM API key is required (set LAB_TUTOR_LLM_API_KEY / XIAO_CASE_API_KEY / OPENAI_API_KEY)"
            )

        llm = ChatOpenAI(
            model=model_id,
            base_url=settings.llm_base_url,
            api_key=SecretStr(settings.llm_api_key),
            temperature=0,
            timeout=settings.llm_timeout_seconds,
            max_completion_tokens=settings.llm_max_completion_tokens,
        )

        # Prefer json_mode for GPT-4o via proxies; otherwise default tooling.
        if "gpt-4o" in model_id:
            self._structured_output_method = "json_mode"
            self._merge_chain = llm.with_structured_output(
                MergeBatch, method="json_mode"
            )
            self._merge_validation_chain = llm.with_structured_output(
                MergeValidationFeedback, method="json_mode"
            )
        else:
            self._structured_output_method = "default"
            self._merge_chain = llm.with_structured_output(MergeBatch)
            self._merge_validation_chain = llm.with_structured_output(
                MergeValidationFeedback
            )

        self._workflow = self._create_workflow()

    def _create_workflow(self):
        """Create generator-evaluator loop workflow."""
        workflow = StateGraph(ConceptNormalizationState)
        workflow.add_node("generation", self._generation_node)
        workflow.add_node("validation", self._validation_node)
        workflow.set_entry_point("generation")
        workflow.add_edge("generation", "validation")
        workflow.add_conditional_edges(
            "validation",
            self._convergence_checker,
            {
                "continue": "generation",
                "complete": END
            }
        )
        return workflow.compile()

    @traceable(
        name="concept_normalization.generation",
        run_type="chain",
        tags=["concept_normalization", "agent:generator"],
        process_inputs=_process_trace_inputs,
        process_outputs=_process_trace_outputs,
    )
    def _generation_node(
        self, state: ConceptNormalizationState
    ) -> ConceptNormalizationState:
        """Generator node: propose merges on full concept list."""
        iteration = state["iteration_count"]
        concepts = state["concepts"]
        
        if self._config.verbose_logging:
            logger.info(
                f"ITERATION {iteration + 1}/{state['max_iterations']} - Generation Phase"
            )

        state["workflow_metadata"]["last_phase"] = "generation"
        state["workflow_metadata"]["agent_activity"] = (
            f"Generator: iteration {iteration + 1}, proposing merges for {len(concepts)} concepts"
        )
        
        # Build concept list (full list, not batched)
        concept_list = "\n".join([f"- {c['name']}" for c in concepts if c.get("name")])
        
        # Format weak merges to avoid
        weak_merges_list = self._format_weak_merges(state["weak_merges"])
        num_weak = len(state["weak_merges"])
        
        # Format prompt
        messages = CONCEPT_NORMALIZATION_PROMPT.format_messages(
            num_concepts=len(concepts),
            concept_list=concept_list,
            num_weak=num_weak,
            weak_merges_list=weak_merges_list,
        )
        
        if self._config.verbose_logging:
            logger.debug("Invoking LLM for merge generation")
        
        try:
            # Use structured output - returns MergeBatch directly
            batch = self._merge_chain.invoke(messages)  # type: ignore
            
            if self._config.verbose_logging:
                logger.info(f"Generated {len(batch.merges)} merge proposals")  # type: ignore
            
            return {
                **state,
                "new_merge_batch": batch.merges,  # type: ignore
            }
        
        except Exception as e:
            logger.error(f"Error in merge generation: {e}")
            import traceback
            traceback.print_exc()
        return {
            **state,
                "new_merge_batch": [],
        }

    @traceable(
        name="concept_normalization.validation",
        run_type="chain",
        tags=["concept_normalization", "agent:evaluator"],
        process_inputs=_process_trace_inputs,
        process_outputs=_process_trace_outputs,
    )
    def _validation_node(
        self, state: ConceptNormalizationState
    ) -> ConceptNormalizationState:
        """Evaluator node: validate merges, accumulate valid ones programmatically."""
        iteration = state["iteration_count"]
        new_merge_batch = state["new_merge_batch"]
        
        all_merges = state["all_merges"]
        weak_merges = state["weak_merges"]
        
        if not new_merge_batch:
            logger.warning("Nothing to validate")
            return {
                **state,
                "iteration_count": iteration + 1,
            }
        
        if self._config.verbose_logging:
            logger.info(f"ITERATION {iteration + 1} - Validation Phase")
            logger.debug(f"Validating {len(new_merge_batch)} merge proposals")
        
        state["workflow_metadata"]["last_phase"] = "validation"
        state["workflow_metadata"]["agent_activity"] = (
            f"Evaluator: iteration {iteration + 1}, validating {len(new_merge_batch)} proposals"
        )
        
        # Get course_id from metadata (we'll need it for definitions)
        course_id = state["workflow_metadata"].get("course_id")
        if not course_id:
            logger.error("course_id not found in workflow_metadata")
            return {
                **state,
                "iteration_count": iteration + 1,
            }
        
        # Validate merges
        feedback = self._validate_merges(course_id=course_id, batch=new_merge_batch)
        
        # Process validation - accumulate weak merges first
        for weak_merge in feedback.weak_merges:
            key = make_merge_key(weak_merge.concept_a, weak_merge.concept_b)
            weak_merges[key] = weak_merge.w
        
        # Calculate valid merges - filter against ALL accumulated weak merges
        valid_merges = []
        for m in new_merge_batch:
            key = make_merge_key(m.concept_a, m.concept_b)
            if key not in weak_merges:
                valid_merges.append(m)
        
        # Add to accumulated merges (auto-deduplicate)
        new_unique_merges = 0
        latest_merges: list[ConceptMerge] = []
        for merge in valid_merges:
            key = make_merge_key(merge.concept_a, merge.concept_b)
            if key not in all_merges:
                new_unique_merges += 1
                latest_merges.append(merge)
            all_merges[key] = merge
        
        if self._config.verbose_logging:
            logger.info(
                f"Validation - Total: {feedback.total_validated}, "
                f"Weak: {feedback.weak_count}, Valid: {len(valid_merges)}, "
                f"New unique: {new_unique_merges}, Accumulated: {len(all_merges)}"
            )
        
        # Update convergence metrics
        metrics = state["convergence_metrics"]
        metrics.update_merge_trends(
            merge_count=len(new_merge_batch),
            valid_merge_count=len(valid_merges),
            weak_merge_count=feedback.weak_count,
            total_merges=len(all_merges),
            new_unique_merges=new_unique_merges,
        )
        
        # Create iteration snapshot if history tracking is enabled
        new_history = state["iteration_history"]
        if self._config.enable_history_tracking:
            snapshot = IterationSnapshot(
                iteration_number=iteration,
                valid_merge_count=len(valid_merges),
                weak_merge_count=feedback.weak_count,
                total_merges=len(all_merges),
                feedback=feedback,
            )
            new_history = new_history + [snapshot]
        
        return {
            **state,
            "all_merges": all_merges,
            "weak_merges": weak_merges,
            "new_merge_batch": [],  # Clear for next iteration
            "current_merge_feedback": feedback,
            "convergence_metrics": metrics,
            "iteration_history": new_history,
            "iteration_count": iteration + 1,
            "workflow_metadata": {
                **state["workflow_metadata"],
                "latest_merges": [
                    {"concept_a": m.concept_a, "concept_b": m.concept_b, "canonical": m.canonical}
                    for m in latest_merges
                ],
                "new_unique_merges": new_unique_merges,
            },
        }
    
    def _convergence_checker(self, state: ConceptNormalizationState) -> str:
        """Check if we should continue or stop."""
        iteration = state["iteration_count"]
        max_iterations = state["max_iterations"]
        metrics = state["convergence_metrics"]
        
        # Check max iterations
        if iteration >= max_iterations:
            metrics.is_converged = True
            metrics.convergence_reason = f"Maximum iterations ({max_iterations}) reached"
            if self._config.verbose_logging:
                logger.info(f"CONVERGENCE: {metrics.convergence_reason}")
            return "complete"
        
        # Check if last two iterations both had < 3 new unique merges
        trend = metrics.new_unique_merges_trend
        if len(trend) >= 2:
            if trend[-1] < 3 and trend[-2] < 3:
                metrics.is_converged = True
                metrics.convergence_reason = (
                    f"Convergence achieved: < 3 new unique merges for 2 consecutive iterations"
                )
                if self._config.verbose_logging:
                    logger.info(
                        f"CONVERGENCE: {metrics.convergence_reason}, "
                        f"Total merges: {len(state['all_merges'])}"
                    )
                return "complete"
        
        # Continue
        if self._config.verbose_logging:
            latest_new = trend[-1] if trend else 0
            logger.info(f"Continuing - New unique merges: {latest_new}")
        
        return "continue"
    
    def _format_weak_merges(self, weak_dict: dict[str, str]) -> str:
        """Format weak merges for prompt."""
        if not weak_dict:
            return "(none yet)"
        
        weak_list = sorted(list(weak_dict.items()))
        formatted = []
        for i, (key, reason) in enumerate(weak_list, 1):
            concept_a, concept_b = parse_merge_key(key)
            formatted.append(f"{i}. {concept_a} + {concept_b}")
            formatted.append(f"   Reason: {reason}")
        
        return "\n".join(formatted)

    @traceable(
        name="concept_normalization.merge_validation",
        run_type="llm",
        tags=["concept_normalization", "agent:evaluator"],
        process_inputs=lambda inputs: {
            "merges_count": inputs.get("merges_count"),
            "model": settings.llm_model,
            "structured_output_method": getattr(
                inputs.get("self"), "_structured_output_method", None
            ),
        },
        process_outputs=lambda outputs: {
            "weak_count": len(getattr(outputs, "weak_merges", []) or []),
            "total_validated": getattr(outputs, "total_validated", None),
        },
    )
    def _invoke_merge_validation_chain(
        self, *, messages, merges_count: int
    ) -> MergeValidationFeedback:
        return self._merge_validation_chain.invoke(messages)  # type: ignore[no-any-return]

    def _validate_merges(
        self, *, course_id: int, batch: list[ConceptMerge]
    ) -> MergeValidationFeedback:
        concept_names: set[str] = set()
        for m in batch:
            concept_names.update([m.concept_a, m.concept_b])

        definitions = self._repo.get_concept_definitions_for_course(
            names=sorted(concept_names),
            course_id=course_id,
        )
        definitions_text = self._format_definitions(definitions)

        merges_summary = "\n".join(
            [
                f"{i + 1}. {m.concept_a} + {m.concept_b} → {m.canonical}\n   Reasoning: {m.r}"
                for i, m in enumerate(batch)
            ]
        )

        messages = MERGE_VALIDATION_PROMPT.format_messages(
            num_merges=len(batch),
            merges_summary=merges_summary,
            definitions_text=definitions_text,
        )

        try:
            return self._invoke_merge_validation_chain(
                messages=messages, merges_count=len(batch)
            )
        except Exception:
            logger.exception("Merge validation failed")
            return MergeValidationFeedback(
                weak_merges=[],
                validation_notes="Error during merge validation",
                total_validated=len(batch),
                weak_count=0,
            )

    def _format_definitions(self, definitions: dict[str, list[str]]) -> str:
        if not definitions:
            return "(no definitions available)"

        formatted: list[str] = []
        for concept, defs in definitions.items():
            if not defs:
                continue
            formatted.append(f"\n**{concept}**:")
            for i, d in enumerate(defs, 1):
                formatted.append(f"  {i}. {d}")
        return "\n".join(formatted) if formatted else "(no definitions available)"

    def normalize_concepts_stream(
        self, *, course_id: int, created_by_user_id: int | None = None
    ) -> Iterator[NormalizationStreamEvent]:
        """Stream normalization events using generator-evaluator loop."""
        concepts = self._repo.list_concepts_for_course(course_id=course_id)

        initial_state: ConceptNormalizationState = {
            "concepts": concepts,
            "all_merges": {},
            "weak_merges": {},
            "new_merge_batch": [],
            "current_merge_feedback": None,
            "iteration_history": [],
            "convergence_metrics": ConvergenceMetrics(),
            "iteration_count": 0,
            "max_iterations": self._config.max_iterations,
            "processing_start_time": time.time(),
            "workflow_metadata": {
                "model": self._model_id,
                "course_id": course_id,
                "total_concepts": len(concepts),
                "last_phase": "generation",
                "agent_activity": "Starting",
                "latest_merges": [],
                "new_unique_merges": 0,
            },
        }

        last_state: ConceptNormalizationState = initial_state

        try:
            stream = self._workflow.stream(
                initial_state,
                {"recursion_limit": 100},
                stream_mode="values",
            )
            for state in stream:
                typed_state = cast(ConceptNormalizationState, state)
                last_state = typed_state
                last_phase = str(
                    typed_state["workflow_metadata"].get("last_phase") or ""
                )
                activity = str(
                    typed_state["workflow_metadata"].get("agent_activity") or ""
                )
                
                # Extract latest merges from metadata
                latest_merges_data = typed_state["workflow_metadata"].get("latest_merges", [])
                latest_merges = []
                for m in latest_merges_data:
                    if isinstance(m, dict):
                        latest_merges.append(
                            {
                                "concept_a": m.get("concept_a", ""),
                                "concept_b": m.get("concept_b", ""),
                                "canonical": m.get("canonical", ""),
                                "variants": [m.get("concept_a", ""), m.get("concept_b", "")],
                                "r": "",
                            }
                        )
                
                new_unique = typed_state["workflow_metadata"].get("new_unique_merges", 0)

                yield NormalizationStreamEvent(
                    type="update",
                    iteration=typed_state.get("iteration_count", 0),
                    phase=(
                        "validation"
                        if last_phase == "validation"
                        else ("generation" if last_phase == "generation" else "generation")
                    ),
                    agent_activity=activity,
                    concepts_count=len(typed_state["concepts"]),
                    merges_found=new_unique,
                    relationships_found=0,
                    latest_merges=latest_merges,
                    latest_relationships=[],
                    total_merges=len(typed_state.get("all_merges", {})),
                    total_relationships=0,
                )

            # stream finished; persist a review session (if any merges) and emit a final completion.
            requires_review = False
            review_id: str | None = None
            completion_reason = "Complete"

            if last_state["all_merges"]:
                try:
                    review_id = f"normrev_{uuid.uuid4().hex}"
                    proposals = []
                    
                    # Convert accumulated merges to proposals
                    for merge in last_state["all_merges"].values():
                        proposals.append(
                        MergeProposal(
                            id=f"mergeprop_{uuid.uuid4().hex}",
                                concept_a=merge.concept_a,
                                concept_b=merge.concept_b,
                                canonical=merge.canonical,
                                variants=list(merge.variants),
                                r=merge.r or "",
                            decision=MergeProposalDecision.PENDING,
                            comment="",
                            applied=False,
                            )
                        )
                    
                    self._review_repo.replace_course_review(
                        course_id=int(course_id),
                        review_id=review_id,
                        created_by_user_id=created_by_user_id,
                        proposals=proposals,
                    )
                    requires_review = True
                except Exception:
                    # If persistence fails, we still complete the run; review can be retried later.
                    logger.exception("Failed to persist normalization review session")
                    requires_review = False
                    review_id = None

            yield NormalizationStreamEvent(
                type="complete",
                iteration=last_state.get("iteration_count", 0),
                phase="complete",
                agent_activity=(
                    f"{completion_reason} — Review required"
                    if requires_review
                    else completion_reason
                ),
                requires_review=requires_review,
                review_id=review_id,
                concepts_count=len(last_state["concepts"]),
                merges_found=0,
                relationships_found=0,
                latest_merges=[],
                latest_relationships=[],
                total_merges=len(last_state.get("all_merges", {})),
                total_relationships=0,
            )
        except Exception as e:
            logger.exception("Normalization stream failed")
            yield NormalizationStreamEvent(
                type="error",
                iteration=0,
                phase="complete",
                agent_activity=str(e) or "Normalization failed",
                requires_review=False,
                review_id=None,
                concepts_count=len(concepts),
                merges_found=0,
                relationships_found=0,
                latest_merges=[],
                latest_relationships=[],
                total_merges=0,
                total_relationships=0,
            )


def _default_workflow_config() -> WorkflowConfiguration:
    # Merge-only: we propose near-duplicate concept merges; no DB writes.
    return WorkflowConfiguration(
        max_iterations=8,
        enable_history_tracking=True,
        verbose_logging=True,
    )


def get_concept_normalization_service(
    *,
    neo4j_session: Neo4jSession,
    db: Session,
) -> ConceptNormalizationService:
    repo = ConceptNormalizationRepository(neo4j_session)
    review_repo = ConceptNormalizationReviewSqlRepository(db)
    config = _default_workflow_config()
    return ConceptNormalizationService(
        repo=repo,
        review_repo=review_repo,
        config=config,
        model_id=settings.llm_model,
    )
