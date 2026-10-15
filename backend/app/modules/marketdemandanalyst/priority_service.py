"""Bounded, restart-safe importance inference over teacher-owned saved evidence."""

import asyncio
import json
import math
import os
from datetime import UTC, datetime, timedelta
from time import monotonic
from uuid import UUID, uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.settings import settings
from app.modules.occupation_reference.importer import release_url
from app.modules.occupation_reference.repository import OccupationReferenceRepository
from app.modules.occupation_reference.schemas import (
    OccupationChoice,
    OnetEvidence,
    SocCode,
)

from .extractor import _get_extraction_llm
from .priority import (
    build_priority_summaries,
    priority_input_fingerprint,
    validate_priority_decisions,
)
from .prompts import SKILL_PRIORITY_ANALYST_PROMPT, SKILL_PRIORITY_CONTEXT_PROMPT
from .repository import MarketReviewRepository, RevisionConflict
from .schemas import (
    PriorityAssessment,
    PriorityContext,
    PriorityDecision,
    PriorityPair,
    PriorityScope,
    PrioritySummarySet,
)
from .thread_state_service import ThreadLease

# A complete oversized input abstains rather than silently truncating a catalog.
MAX_INPUT_BYTES = 200_000
MAX_OUTPUT_BYTES = 200_000
PROMPT_VERSION = "1"
POLICY_VERSION = "1"


class _ContextDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str
    soc_code: SocCode | None
    supporting_posting_ids: list[UUID]
    rationale: str
    unavailable_reason: str | None = None


class _Unavailable(ValueError):
    """An entire model request is unsafe, incomplete, oversized or expired."""


class SkillPriorityService:
    def __init__(self, session_factory=SessionLocal, llm_factory=_get_extraction_llm):
        self._session_factory = session_factory
        self._llm_factory = llm_factory

    @staticmethod
    def _enrich(inputs: dict, contexts: list[PriorityContext]) -> None:
        for passage in inputs["passages"].values():
            passage["context_keys"] = sorted(
                {
                    context.soc_code or f"unmapped:{context.group_id}"
                    for context in contexts
                    if passage["snapshot_id"]
                    in {str(value) for value in context.posting_ids}
                }
            )

    @staticmethod
    def _fingerprint(inputs, contexts, release, model_id):
        return priority_input_fingerprint(
            inputs,
            contexts,
            release=release,
            model_id=model_id,
            prompt_version=PROMPT_VERSION,
            policy_version=POLICY_VERSION,
        )

    def _read(self, scope):
        with self._session_factory() as db:
            inputs = MarketReviewRepository(db).load_priority_inputs(scope)
        inputs.update(
            run_id=scope.run_id, candidate_revision=scope.expected_candidate_revision
        )
        return inputs

    @staticmethod
    def _require_lease(lease, thread_id):
        connection = lease.connection
        if (
            not lease.active
            or lease.thread_id != thread_id
            or connection.closed
            or connection.invalidated
        ):
            raise RevisionConflict("The priority execution lease was lost")
        try:
            owns = connection.scalar(
                text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_locks
                    WHERE locktype = 'advisory' AND granted AND pid = pg_backend_pid()
                    AND database = (SELECT oid FROM pg_database WHERE datname = current_database())
                    AND classid = ((lock_key >> 32) & 4294967295)::oid
                    AND objid = (lock_key & 4294967295)::oid AND objsubid = 1
                ) FROM (SELECT hashtextextended(:thread_id, 0) AS lock_key) AS requested
            """),
                {"thread_id": thread_id},
            )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            raise RevisionConflict(
                "The priority lease connection is unavailable"
            ) from exc
        if not owns:
            raise RevisionConflict(
                "The live SQL session no longer owns the priority lease"
            )

    def _save(self, scope, lease, assessment, expected_id):
        # Bind the short write transaction to the *same* session holding the lock.
        # A reconnected or merely active Python lease never authorizes a write.
        self._require_lease(lease, f"mda-{scope.teacher_id}-course-{scope.course_id}")
        with Session(bind=lease.connection) as db:
            repo = MarketReviewRepository(db)
            repo.lock_vacancy_lifecycle()
            current = repo.load_priority_inputs(scope)
            current.update(
                run_id=scope.run_id,
                candidate_revision=scope.expected_candidate_revision,
            )
            self._enrich(current, assessment.contexts)
            if (
                self._fingerprint(
                    current,
                    assessment.contexts,
                    assessment.release,
                    assessment.model_id,
                )
                != assessment.input_fingerprint
            ):
                raise RevisionConflict("Priority inputs changed during inference")
            repo.save_priority_assessment(
                scope, assessment, expected_assessment_id=expected_id
            )
            db.commit()

    def _catalog(self, release):
        with self._session_factory() as db:
            repo = OccupationReferenceRepository(db)
            ready = repo.get_release(release) if release else repo.active_release()
            if ready is None:
                return release, []
            return ready.version, repo.list_priority_occupations(ready.version)

    def _references(self, release, codes):
        if not release or not codes:
            return [], []
        with self._session_factory() as db:
            repo = OccupationReferenceRepository(db)
            ready = repo.get_release(release)
            if ready is None:
                return [], []
            occupations = [
                OccupationChoice.model_validate(row)
                for row in repo.get_occupations(release, codes)
            ]
            titles = {item.soc_code: item.title for item in occupations}
            references = []
            for row in repo.get_evidence(release, codes):
                # Validate JSON types before the legacy Metric DTO can coerce bool/string.
                metric = (
                    row.ratings.get("IM", {}) if isinstance(row.ratings, dict) else {}
                )
                if not isinstance(metric, dict):
                    continue
                if (
                    row.family not in {"essential", "transferable"}
                    or metric.get("scale_id") != "IM"
                    or metric.get("status") != "reported"
                    or not all(
                        type(metric.get(key)) in {int, float}
                        and math.isfinite(metric[key])
                        for key in ("value", "minimum", "maximum")
                    )
                    or metric["minimum"] != 1
                    or metric["maximum"] != 5
                    or not 1 <= metric["value"] <= 5
                    or row.soc_code not in titles
                ):
                    continue
                try:
                    reference = OnetEvidence(
                        id=row.id,
                        release=row.release,
                        soc_code=row.soc_code,
                        occupation_title=titles[row.soc_code],
                        family=row.family,
                        element_id=row.element_id,
                        label=row.label,
                        definition=row.definition,
                        workplace_example=row.workplace_example,
                        ratings={"IM": metric},
                        flags=row.flags,
                        source_url=release_url(row.release, f"{row.family}_skills.csv"),
                        attribution=ready.attribution,
                    )
                except ValidationError:
                    continue
                references.append(reference)
            return occupations, references

    @staticmethod
    def _unmapped(groups, reason):
        return [
            PriorityContext(
                group_id=group["group_id"],
                soc_code=None,
                occupation_title=None,
                posting_ids=group["posting_ids"],
                rationale=reason,
                inferred=True,
                unavailable_reason=reason,
            )
            for group in groups
        ]

    @staticmethod
    def _pairs(inputs, contexts):
        pairs = {}
        for candidate in inputs["candidates"]:
            postings = {
                str(ref["snapshot_id"])
                for ref in candidate.evidence_references
                if ref.get("snapshot_id")
                and ref.get("evidence_kind") in {"extracted_text", "provider_tag"}
                and ref.get("status") not in {"purged", "removed", "unavailable"}
                and str(ref["snapshot_id"]) in inputs["posting_hashes"]
            }
            for context in contexts:
                if postings & {str(posting) for posting in context.posting_ids}:
                    key = context.soc_code or f"unmapped:{context.group_id}"
                    pairs[candidate.candidate_id, key] = PriorityPair(
                        candidate_id=candidate.candidate_id,
                        context_key=key,
                        soc_code=context.soc_code,
                    )
        return list(pairs.values())

    @staticmethod
    def _discard_response(task, slots):
        # A transport ignoring cancellation may finish later, but has no write path.
        # Retain its permit until then so even abandoned calls cannot exceed two.
        if not task.cancelled():
            task.exception()
        slots.release()

    async def _request(self, payload, prompt, adapter, deadline, slots):
        payload = {
            **payload,
            "response_schema": adapter.json_schema(),
            "response_instruction": "Return a bare JSON array matching response_schema, without a wrapper, code fence or prose.",
        }
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode()) > MAX_INPUT_BYTES:
            raise _Unavailable("Complete source input exceeds the request budget")
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise _Unavailable("Assessment deadline expired")
        try:
            await asyncio.wait_for(slots.acquire(), timeout=remaining)
        except TimeoutError as exc:
            raise _Unavailable("Assessment deadline expired while queued") from exc
        request = None
        try:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise _Unavailable("Assessment deadline expired")
            timeout = min(20.0, remaining)
            llm = self._llm_factory(timeout_seconds=timeout)
            request = asyncio.create_task(
                llm.ainvoke(
                    [SystemMessage(content=prompt), HumanMessage(content=encoded)],
                    config={"callbacks": []},
                )
            )
            completed, _ = await asyncio.wait({request}, timeout=timeout)
            if not completed:
                raise _Unavailable("Model request timed out")
            response = request.result()
            if monotonic() >= deadline:
                raise _Unavailable("Assessment deadline expired")
            if (
                not isinstance(response.content, str)
                or len(response.content.encode()) > MAX_OUTPUT_BYTES
            ):
                raise _Unavailable("Model output exceeds the response budget")
            # Exact JSON only: no code fences, extraction regex or prose repair.
            raw = json.loads(
                response.content,
                parse_constant=lambda _: (_ for _ in ()).throw(
                    ValueError("Non-finite JSON")
                ),
            )
            return adapter.validate_python(raw)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise _Unavailable(
                "Model request failed, timed out or returned invalid JSON"
            ) from exc
        finally:
            if request is not None and not request.done():
                request.cancel()
                request.add_done_callback(
                    lambda task: self._discard_response(task, slots)
                )
            else:
                slots.release()

    async def _contexts(self, inputs, catalog, release, deadline, slots):
        all_groups = inputs["groups"]
        verified_postings = {
            passage["snapshot_id"] for passage in inputs["passages"].values()
        }
        groups = [
            group
            for group in all_groups
            if set(group["posting_ids"]) & verified_postings
        ]
        unsupported = self._unmapped(
            [
                group
                for group in all_groups
                if not set(group["posting_ids"]) & verified_postings
            ],
            "No verified saved job responsibilities for this group",
        )

        def restore_order(contexts):
            indexed = {item.group_id: item for item in [*contexts, *unsupported]}
            return [indexed[group["group_id"]] for group in all_groups]

        if not groups:
            return unsupported
        if not catalog:
            return self._unmapped(
                all_groups, "No imported occupation catalog is available"
            )
        responsibilities = [
            {"id": key, **value} for key, value in inputs["passages"].items()
        ]
        payload = {
            "phase": "choose",
            "groups": groups,
            "responsibilities": responsibilities,
            "catalog": [
                {"soc_code": item.soc_code, "title": item.title} for item in catalog
            ],
        }
        adapter = TypeAdapter(list[_ContextDecision])
        try:
            chosen = await self._request(
                payload, SKILL_PRIORITY_CONTEXT_PROMPT, adapter, deadline, slots
            )
            allowed = {item.soc_code for item in catalog}
            self._check_context_decisions(chosen, groups, allowed, verified_postings)
            proposed = {item.group_id: item.soc_code for item in chosen}
            codes = list({item.soc_code for item in chosen if item.soc_code})
            if not codes:
                return restore_order(
                    self._unmapped(groups, "No occupation fits the selected work")
                )
            # Load only the proposed complete descriptions for the mandatory second pass.
            with self._session_factory() as db:
                occupations = [
                    OccupationChoice.model_validate(row)
                    for row in OccupationReferenceRepository(db).get_occupations(
                        release, codes
                    )
                ]
            checked = await self._request(
                {
                    "phase": "validate",
                    "groups": groups,
                    "responsibilities": responsibilities,
                    "proposals": [item.model_dump(mode="json") for item in chosen],
                    "occupations": [
                        item.model_dump(mode="json") for item in occupations
                    ],
                },
                SKILL_PRIORITY_CONTEXT_PROMPT,
                adapter,
                deadline,
                slots,
            )
            self._check_context_decisions(
                checked,
                groups,
                {item.soc_code for item in occupations},
                verified_postings,
            )
            titles = {item.soc_code: item.title for item in occupations}
            by_group = {item.group_id: item for item in checked}
            contexts = []
            for group in groups:
                item = by_group[group["group_id"]]
                code = (
                    item.soc_code
                    if item.soc_code == proposed[group["group_id"]]
                    else None
                )
                contexts.append(
                    PriorityContext(
                        group_id=group["group_id"],
                        soc_code=code,
                        occupation_title=titles.get(code),
                        posting_ids=group["posting_ids"],
                        rationale=item.rationale,
                        inferred=True,
                        unavailable_reason=None
                        if code
                        else item.unavailable_reason
                        or "Occupation description did not validate the proposed match",
                    )
                )
            return restore_order(contexts)
        except _Unavailable as exc:
            return self._unmapped(all_groups, str(exc))

    @staticmethod
    def _check_context_decisions(decisions, groups, allowed, verified_postings):
        index = {item.group_id: item for item in decisions}
        if len(index) != len(decisions) or set(index) != {
            group["group_id"] for group in groups
        }:
            raise _Unavailable("Incomplete or duplicate occupation group scan")
        for group in groups:
            item = index[group["group_id"]]
            if (
                (item.soc_code is not None and item.soc_code not in allowed)
                or not item.rationale.strip()
                or (
                    item.soc_code is not None
                    and not {str(value) for value in item.supporting_posting_ids}
                    & verified_postings
                )
                or not {str(value) for value in item.supporting_posting_ids}
                <= set(group["posting_ids"])
            ):
                raise _Unavailable("Occupation context cites invalid evidence or codes")

    @staticmethod
    def _terminal(assessment, inputs, pairs, references, reason):
        done = {(item.candidate_id, item.context_key) for item in assessment.results}
        missing = [
            pair for pair in pairs if (pair.candidate_id, pair.context_key) not in done
        ]
        unavailable = validate_priority_decisions(
            [],
            pairs=missing,
            references=references,
            passages=inputs["passages"],
            candidates=inputs["candidates"],
        )
        for item in unavailable:
            item.unavailable_reason = reason
            item.limitations = [reason]
        assessment.results.extend(unavailable)
        order = {
            (pair.candidate_id, pair.context_key): i for i, pair in enumerate(pairs)
        }
        assessment.results.sort(
            key=lambda item: order[item.candidate_id, item.context_key]
        )
        scored = sum(item.value is not None for item in assessment.results)
        assessment.status = (
            "ready" if scored == len(pairs) else "partial" if scored else "unavailable"
        )
        assessment.completed_pair_count = len(assessment.results)
        assessment.expected_pair_count = len(pairs)
        assessment.summaries = build_priority_summaries(
            inputs["candidates"],
            inputs["categories"],
            assessment.contexts,
            assessment.results,
        )
        used_ids = set()
        for result in assessment.results:
            if result.value is None:
                continue
            if result.direct_reference_id:
                used_ids.add(result.direct_reference_id)
            # Include considered references too, so evidence details never show bare UUIDs.
            used_ids.update(
                association.reference_id for association in result.associations
            )
        assessment.references = [
            reference for reference in references if reference.id in used_ids
        ]
        assessment.updated_at = assessment.completed_at = datetime.now(UTC)

    async def assess(
        self, scope: PriorityScope, lease: ThreadLease
    ) -> PriorityAssessment:
        started = datetime.now(UTC)
        start_clock = monotonic()
        model_id = os.environ.get(
            "LAB_TUTOR_LLM_MODEL", os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        )
        assessment = PriorityAssessment(
            assessment_id=uuid4(),
            run_id=scope.run_id,
            candidate_revision=scope.expected_candidate_revision,
            input_fingerprint="",
            model_id=model_id,
            release=None,
            started_at=started,
            updated_at=started,
            deadline_at=started + timedelta(seconds=60),
            status="unavailable",
        )
        if not settings.market_skill_priority_enabled:
            assessment.error_reasons = ["Skill priority is disabled"]
            return assessment
        tasks = []
        try:
            self._require_lease(
                lease, f"mda-{scope.teacher_id}-course-{scope.course_id}"
            )
            inputs = self._read(scope)
            prior = inputs["prior_assessment"]
            if prior:
                self._enrich(inputs, prior.contexts)
                fingerprint = self._fingerprint(
                    inputs, prior.contexts, prior.release, model_id
                )
                if (
                    fingerprint == prior.input_fingerprint
                    and prior.policy_version == POLICY_VERSION
                    and prior.prompt_version == PROMPT_VERSION
                ):
                    if prior.status in {"ready", "partial", "unavailable"}:
                        return prior
                    if prior.status == "running":
                        assessment = prior
            expected_id = prior.assessment_id if prior else None
            resuming = assessment.status == "running"
            if not resuming:
                assessment.release, catalog = self._catalog(
                    inputs["configured_release"]
                )
                assessment.status = "running"
                assessment.posting_hashes = inputs["posting_hashes"]
                self._enrich(inputs, [])
                assessment.input_fingerprint = self._fingerprint(
                    inputs, [], assessment.release, model_id
                )
                self._save(scope, lease, assessment, expected_id)
            else:
                catalog = (
                    self._catalog(assessment.release)[1] if assessment.release else []
                )
            deadline = start_clock + max(
                0.0, min(60.0, (assessment.deadline_at - started).total_seconds())
            )
            slots = asyncio.Semaphore(2)
            if not assessment.contexts:
                # No inference is needed for an empty eligible set.
                defaults = self._unmapped(
                    inputs["groups"], "No validated occupation context"
                )
                initial_pairs = self._pairs(inputs, defaults)
                assessment.contexts = (
                    await self._contexts(
                        inputs, catalog, assessment.release, deadline, slots
                    )
                    if initial_pairs
                    else defaults
                )
            # Missing saved grouping remains explicitly unavailable, never a semantic guess.
            covered = {
                str(value)
                for context in assessment.contexts
                for value in context.posting_ids
            }
            uncovered = sorted(set(inputs["posting_hashes"]) - covered)
            if uncovered:
                assessment.contexts.extend(
                    self._unmapped(
                        [{"group_id": "ungrouped", "posting_ids": uncovered}],
                        "Selected posting has no saved job group",
                    )
                )
            self._enrich(inputs, assessment.contexts)
            assessment.input_fingerprint = self._fingerprint(
                inputs, assessment.contexts, assessment.release, model_id
            )
            pairs = self._pairs(inputs, assessment.contexts)
            assessment.expected_pair_count = len(pairs)
            self._save(scope, lease, assessment, assessment.assessment_id)
            occupations, references = self._references(
                assessment.release,
                list(
                    {
                        context.soc_code
                        for context in assessment.contexts
                        if context.soc_code
                    }
                ),
            )
            done = {
                (item.candidate_id, item.context_key) for item in assessment.results
            }
            pending = [
                pair
                for pair in pairs
                if pair.soc_code
                and (pair.candidate_id, pair.context_key) not in done
                and any(ref.soc_code == pair.soc_code for ref in references)
            ]
            errors = []

            async def score(batch):
                ids = {pair.candidate_id for pair in batch}
                codes = {pair.soc_code for pair in batch}
                try:
                    decisions = await self._request(
                        {
                            "phase": "score",
                            "release": assessment.release,
                            "pairs": [pair.model_dump(mode="json") for pair in batch],
                            "candidates": [
                                candidate.model_dump(
                                    mode="json",
                                    include={
                                        "candidate_id",
                                        "display_name",
                                        "category_id",
                                        "original_labels",
                                        "aliases",
                                    },
                                )
                                for candidate in inputs["candidates"]
                                if candidate.candidate_id in ids
                            ],
                            "contexts": [
                                context.model_dump(mode="json")
                                for context in assessment.contexts
                                if context.soc_code in codes
                            ],
                            "occupations": [
                                item.model_dump(mode="json")
                                for item in occupations
                                if item.soc_code in codes
                            ],
                            "references": [
                                {
                                    **ref.model_dump(
                                        mode="json",
                                        include={
                                            "id",
                                            "soc_code",
                                            "family",
                                            "element_id",
                                            "label",
                                            "definition",
                                        },
                                    ),
                                    "ratings": {
                                        "IM": ref.ratings["IM"].model_dump(
                                            include={
                                                "scale_id",
                                                "value",
                                                "minimum",
                                                "maximum",
                                                "status",
                                            }
                                        )
                                    },
                                }
                                for ref in references
                                if ref.soc_code in codes
                            ],
                            "passages": {
                                key: value
                                for key, value in inputs["passages"].items()
                                if ids
                                & {
                                    UUID(candidate)
                                    for candidate in value["candidate_ids"]
                                }
                            },
                        },
                        SKILL_PRIORITY_ANALYST_PROMPT,
                        TypeAdapter(list[PriorityDecision]),
                        deadline,
                        slots,
                    )
                    expected = {(pair.candidate_id, pair.soc_code) for pair in batch}
                    if {
                        (item.candidate_id, item.soc_code) for item in decisions
                    } != expected or len(decisions) != len(expected):
                        raise _Unavailable(
                            "Incomplete, duplicate or foreign scoring batch"
                        )
                    return validate_priority_decisions(
                        decisions,
                        pairs=batch,
                        references=references,
                        passages=inputs["passages"],
                        candidates=inputs["candidates"],
                    ), None
                except _Unavailable as exc:
                    return [], str(exc)

            tasks = [
                asyncio.create_task(score(pending[i : i + 8]))
                for i in range(0, len(pending), 8)
            ]
            for completed in asyncio.as_completed(tasks):
                results, error = await completed
                if error:
                    errors.append(error)
                    continue
                assessment.results.extend(results)
                assessment.completed_pair_count = len(assessment.results)
                assessment.updated_at = datetime.now(UTC)
                self._save(scope, lease, assessment, assessment.assessment_id)
            assessment.error_reasons = list(dict.fromkeys(errors))[:20]
            reason = (
                errors[0]
                if errors
                else "No validated occupation, reported IM anchor or sufficient evidence"
            )
            self._terminal(assessment, inputs, pairs, references, reason)
            self._save(scope, lease, assessment, assessment.assessment_id)
            return assessment
        except (LookupError, RevisionConflict):
            assessment.status = "stale"
            assessment.results = []
            assessment.references = []
            assessment.summaries = PrioritySummarySet()
            assessment.completed_pair_count = 0
            assessment.error_reasons = [
                "The owned inputs or live execution lease changed; the result was discarded"
            ]
            return assessment
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)


def get_skill_priority_service() -> SkillPriorityService:
    return SkillPriorityService()
