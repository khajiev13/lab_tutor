"""Bounded, restart-safe importance inference over teacher-owned saved evidence."""

import asyncio
import json
import logging
import math
import re
from datetime import UTC, datetime, timedelta
from threading import BoundedSemaphore, Lock
from time import monotonic
from typing import Annotated, Literal
from uuid import UUID, uuid4
from weakref import WeakValueDictionary

from langchain_core.messages import HumanMessage, SystemMessage
from openai import APITimeoutError
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
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
PROMPT_VERSION = "10"
SCORING_BATCH_SIZE = 10
ASSESSMENT_TIMEOUT_SECONDS = 360
POLICY_VERSION = "1"
logger = logging.getLogger(__name__)


def _assessment_budget(pairs):
    # Context choice and validation are sequential; score batches share two slots.
    # Reserve one bounded repair wave, never extend a persisted/resumed deadline.
    groups = {}
    for pair in pairs:
        groups[pair.context_key] = groups.get(pair.context_key, 0) + 1
    batches = sum(math.ceil(count / SCORING_BATCH_SIZE) for count in groups.values())
    waves = math.ceil(batches / 2)
    return min(ASSESSMENT_TIMEOUT_SECONDS, max(90, 120 + 45 * (waves + 1)))


# get_skill_priority_service() constructs services per invocation. Keep actual
# transport ownership process-wide, including canceled requests still alive on
# another service instance or event loop. Weak values disappear when neither an
# assessment nor an outstanding transport retains its permits.
_MODEL_SLOTS: WeakValueDictionary[str, BoundedSemaphore] = WeakValueDictionary()
_MODEL_SLOTS_LOCK = Lock()


def _shared_model_slots(thread_id: str) -> BoundedSemaphore:
    with _MODEL_SLOTS_LOCK:
        slots = _MODEL_SLOTS.get(thread_id)
        if slots is None:
            slots = BoundedSemaphore(2)
            _MODEL_SLOTS[thread_id] = slots
        return slots


async def _acquire_model_slot(slots: BoundedSemaphore) -> None:
    # Never park a worker thread on acquire: cancellation could orphan that
    # waiter and consume a permit later. The caller bounds this await by the
    # original assessment deadline, and release is safe across event loops.
    while not slots.acquire(blocking=False):
        await asyncio.sleep(0.01)


class _ContextDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str
    soc_code: SocCode | None
    supporting_posting_ids: list[UUID] = Field(max_length=3)
    rationale: str = Field(max_length=400)
    unavailable_reason: str | None = None


class _ContextProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str
    soc_codes: list[SocCode] = Field(max_length=3)
    supporting_posting_ids: list[UUID] = Field(max_length=3)
    rationale: str = Field(max_length=400)
    unavailable_reason: str | None = None


class _Unavailable(ValueError):
    """An entire model request is unsafe, incomplete, oversized or expired."""


class _ScoringAssociation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_id: str = Field(alias="r")
    relation: Literal["equivalent", "broader", "related", "unmatched"] = Field(
        alias="k"
    )
    rationale: str = Field(alias="why", max_length=240)


class _ScoringDecision(BaseModel):
    """Compact transport only; canonical evidence validation remains mandatory."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(alias="c")
    basis: Literal["onet", "ai_estimate", "unavailable"] = Field(alias="b")
    direct_reference_id: str | None = Field(alias="d")
    estimate: Annotated[int, Field(strict=True, ge=1, le=5)] | None = Field(alias="v")
    associations: list[_ScoringAssociation] = Field(alias="a", max_length=2)
    supporting_evidence_ids: list[str] = Field(alias="e", max_length=3)
    explanation: str = Field(alias="why", max_length=480)
    limitations: list[Annotated[str, Field(max_length=240)]] = Field(
        alias="limits", max_length=3
    )
    unavailable_reason: str | None = Field(default=None, alias="missing")


def _scoring_record_schema_reason(error: ValidationError) -> str:
    fields = {"c", "b", "d", "v", "a", "e", "why", "limits", "missing", "r", "k"}
    details = []
    for item in error.errors(
        include_input=False, include_context=False, include_url=False
    )[:3]:
        location = ".".join(
            part
            if type(part) is str and part in fields
            else "[]"
            if type(part) is int
            else "field"
            for part in item["loc"]
        )
        details.append(f"{location}:{item['type']}")
    return f"Model scoring record failed schema validation ({'; '.join(details)})"


def _parse_scoring_records(records, candidates):
    # Returned records must have unique owned IDs. Missing owned records can be
    # repaired independently; foreign/duplicate identities still reject a batch.
    aliases = [row.get("c") if type(row) is dict else None for row in records]
    if (
        any(type(alias) is not str for alias in aliases)
        or len(set(aliases)) != len(aliases)
        or not set(aliases) <= set(candidates)
    ):
        raise _Unavailable("Incomplete, duplicate or foreign scoring batch")
    valid, rejected = (
        [],
        {
            alias: "Model omitted an owned scoring record"
            for alias in candidates
            if alias not in aliases
        },
    )
    for alias, row in zip(aliases, records, strict=True):
        try:
            valid.append(_ScoringDecision.model_validate(row))
        except ValidationError as exc:
            rejected[alias] = _scoring_record_schema_reason(exc)
    return valid, rejected


def _compact_scoring_payload(payload):
    candidates = {
        f"C{i}": row["candidate_id"] for i, row in enumerate(payload["candidates"], 1)
    }
    references = {f"R{i}": row["id"] for i, row in enumerate(payload["references"], 1)}
    evidence = {f"E{i}": key for i, key in enumerate(payload["passages"], 1)}
    candidate_aliases = {value: key for key, value in candidates.items()}
    reference_aliases = {value: key for key, value in references.items()}
    payload = {
        **payload,
        "pairs": [
            {**row, "candidate_id": candidate_aliases[row["candidate_id"]]}
            for row in payload["pairs"]
        ],
        "candidates": [
            {**row, "candidate_id": candidate_aliases[row["candidate_id"]]}
            for row in payload["candidates"]
        ],
        "references": [
            {**row, "id": reference_aliases[row["id"]]} for row in payload["references"]
        ],
        "passages": {
            alias: {
                **payload["passages"][key],
                "candidate_ids": [
                    candidate_aliases[value]
                    for value in payload["passages"][key]["candidate_ids"]
                    if value in candidate_aliases
                ],
            }
            for alias, key in evidence.items()
        },
        "transport_instruction": (
            "Use only this request's exact C candidate, R reference and E passage aliases. "
            "Output keys: c candidate_id, b basis, d direct_reference_id, v estimate, "
            "a associations (r reference_id, k relation, why rationale), e supporting_evidence_ids, "
            "why explanation, limits limitations, missing unavailable_reason. "
            "The server supplies this batch's occupation code. Use one minimal sufficient anchor and passage, "
            "at most two relevant anchors and three passages. Keep each explanation within about 20 words and association rationale "
            "within about 12 words; preserve concrete evidence reasoning. In prose use actual competency and "
            "descriptor names, never C/E/R aliases; aliases belong only in ID fields. Do not output canonical IDs."
        ),
    }
    return payload, candidates, references, evidence


def _expand_scoring_text(value, names):
    def replace(match):
        alias = match["alias"]
        if alias not in names:
            raise _Unavailable("Model prose cites an unknown scoring alias")
        label = names[alias]
        prefix = match["prefix"] or ""
        if prefix and alias.startswith("E"):
            return ("The " if prefix[0].isupper() else "the ") + label
        return prefix + label

    # Exact lexical tokens only: C1 cannot replace C10 or characters within words.
    return re.sub(r"\b(?P<prefix>[Pp]assage )?(?P<alias>[CER]\d+)\b", replace, value)


def _expand_scoring_decisions(
    decisions, candidates, references, evidence, soc_code, payload
):
    names = {
        **{row["candidate_id"]: row["display_name"] for row in payload["candidates"]},
        **{row["id"]: row["label"] for row in payload["references"]},
        **{key: "verified job passage" for key in payload["passages"]},
    }
    try:
        return [
            PriorityDecision(
                **{
                    **row.model_dump(
                        exclude={
                            "candidate_id",
                            "direct_reference_id",
                            "associations",
                            "supporting_evidence_ids",
                        }
                    ),
                    "candidate_id": candidates[row.candidate_id],
                    "soc_code": soc_code,
                    "explanation": _expand_scoring_text(row.explanation, names),
                    "limitations": [
                        _expand_scoring_text(value, names) for value in row.limitations
                    ],
                    "unavailable_reason": _expand_scoring_text(
                        row.unavailable_reason, names
                    )
                    if row.unavailable_reason is not None
                    else None,
                    "direct_reference_id": references[row.direct_reference_id]
                    if row.direct_reference_id is not None
                    else None,
                    "associations": [
                        {
                            **item.model_dump(),
                            "reference_id": references[item.reference_id],
                            "rationale": _expand_scoring_text(item.rationale, names),
                        }
                        for item in row.associations
                    ],
                    "supporting_evidence_ids": [
                        evidence[key] for key in row.supporting_evidence_ids
                    ],
                }
            )
            for row in decisions
        ]
    except KeyError as exc:
        raise _Unavailable("Model returned an unknown scoring alias") from exc


def configured_priority_model() -> str:
    """One configured identity for the actual transport and cache fingerprint."""
    return settings.market_skill_priority_model or settings.llm_agent_model


def _get_priority_llm(timeout_seconds: float = 20):
    model = configured_priority_model()
    thinking = (
        {"thinking": {"type": "disabled"}}
        if model.casefold().startswith("deepseek")
        else {"enable_thinking": False}
    )
    return _get_extraction_llm(timeout_seconds=timeout_seconds).bind(
        model=model, response_format={"type": "json_object"}, extra_body=thinking
    )


class SkillPriorityService:
    def __init__(self, session_factory=SessionLocal, llm_factory=_get_priority_llm):
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

    async def _request(
        self, payload, prompt, adapter, deadline, slots, *, scoring_records=False
    ):
        records_schema = adapter.json_schema()
        definitions = records_schema.pop("$defs", None)
        response_schema = {
            "type": "object",
            "properties": {"results": records_schema},
            "required": ["results"],
            "additionalProperties": False,
        }
        if definitions:
            response_schema["$defs"] = definitions
        payload = {
            **payload,
            "response_schema": response_schema,
            "response_instruction": (
                'Return exactly one JSON object, e.g. {"results": []}, matching response_schema. '
                "The only root key is results; use no code fence or prose. "
                "Account for every supplied group or pair. Use one concise sentence per rationale or explanation, "
                "only the minimal sufficient reference and passage IDs, and brief limitations."
            ),
        }
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode()) > MAX_INPUT_BYTES:
            raise _Unavailable("Complete source input exceeds the request budget")
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise _Unavailable("Assessment deadline expired")
        try:
            await asyncio.wait_for(_acquire_model_slot(slots), timeout=remaining)
        except TimeoutError as exc:
            raise _Unavailable("Assessment deadline expired while queued") from exc
        request = None
        request_started = monotonic()
        phase = payload.get("phase", "unknown")
        try:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise _Unavailable("Assessment deadline expired")
            limit = (
                min(60.0, max(45.0, 30.0 + 3 * len(payload.get("pairs", []))))
                if phase == "score"
                else 60.0
            )
            timeout = min(limit, remaining)
            logger.info(
                "Priority request phase=%s pairs=%d input_bytes=%d timeout=%.1f remaining=%.1f",
                phase,
                len(payload.get("pairs", [])),
                len(encoded.encode()),
                timeout,
                remaining,
            )
            llm = self._llm_factory(timeout_seconds=timeout)
            request = asyncio.create_task(
                llm.ainvoke(
                    [SystemMessage(content=prompt), HumanMessage(content=encoded)],
                    config={"callbacks": [], "tags": ["nostream"]},
                )
            )
            completed, _ = await asyncio.wait({request}, timeout=timeout)
            if not completed:
                raise _Unavailable("Model request timed out")
            response = request.result()
            usage = getattr(response, "usage_metadata", None) or {}
            metadata = getattr(response, "response_metadata", None) or {}
            logger.info(
                "Priority response phase=%s elapsed=%.1f output_tokens=%s finish_reason=%s",
                phase,
                monotonic() - request_started,
                usage.get("output_tokens"),
                metadata.get("finish_reason"),
            )
            if monotonic() >= deadline:
                raise _Unavailable("Assessment deadline expired")
            if (
                not isinstance(response.content, str)
                or len(response.content.encode()) > MAX_OUTPUT_BYTES
            ):
                raise _Unavailable("Model output exceeds the response budget")
            # Exact JSON only: no code fences, extraction regex or prose repair.
            try:
                raw = json.loads(
                    response.content,
                    parse_constant=lambda _: (_ for _ in ()).throw(
                        ValueError("Non-finite JSON")
                    ),
                )
            except ValueError as exc:
                raise _Unavailable("Model returned invalid JSON") from exc
            if type(raw) is not dict or set(raw) != {"results"}:
                raise _Unavailable("Model response must contain only the results array")
            if scoring_records:
                if type(raw["results"]) is not list:
                    raise _Unavailable(
                        "Model response failed schema validation (results:list_type)"
                    )
                return raw["results"]
            return adapter.validate_python(raw["results"])
        except asyncio.CancelledError:
            raise
        except _Unavailable as exc:
            logger.warning(
                "Priority request failed phase=%s elapsed=%.1f reason=%s",
                phase,
                monotonic() - request_started,
                str(exc),
            )
            raise
        except (TimeoutError, APITimeoutError) as exc:
            logger.warning(
                "Priority transport timed out phase=%s elapsed=%.1f",
                phase,
                monotonic() - request_started,
            )
            raise _Unavailable("Model request timed out") from exc
        except ValidationError as exc:
            raise _Unavailable("Model response failed schema validation") from exc
        except Exception as exc:
            raise _Unavailable("Model provider request failed") from exc
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
        # Short aliases prevent lossy copying of long immutable hashes. Only
        # these exact request-local IDs may round-trip; storage keeps originals.
        alias_to_group = {f"G{index}": group for index, group in enumerate(groups, 1)}
        transport_groups = [
            {**group, "group_id": alias} for alias, group in alias_to_group.items()
        ]
        payload = {
            "phase": "choose",
            "groups": transport_groups,
            "responsibilities": responsibilities,
            "catalog": [
                {"soc_code": item.soc_code, "title": item.title} for item in catalog
            ],
        }
        try:
            chosen = await self._request(
                payload,
                SKILL_PRIORITY_CONTEXT_PROMPT,
                TypeAdapter(list[_ContextProposal]),
                deadline,
                slots,
            )
            allowed = {item.soc_code for item in catalog}
            proposals = {item.group_id: item.soc_codes for item in chosen}
            if len(proposals) != len(chosen) or set(proposals) != set(alias_to_group):
                raise _Unavailable("Incomplete or duplicate occupation group scan")
            for item in chosen:
                if (
                    len(item.soc_codes) != len(set(item.soc_codes))
                    or not set(item.soc_codes) <= allowed
                ):
                    raise _Unavailable(
                        "Occupation proposals contain duplicate or foreign codes"
                    )
            self._check_context_decisions(
                [
                    _ContextDecision(
                        group_id=item.group_id,
                        soc_code=item.soc_codes[0] if item.soc_codes else None,
                        supporting_posting_ids=item.supporting_posting_ids,
                        rationale=item.rationale,
                        unavailable_reason=item.unavailable_reason,
                    )
                    for item in chosen
                ],
                transport_groups,
                allowed,
                verified_postings,
            )
            codes = list({code for item in chosen for code in item.soc_codes})
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
                    "groups": transport_groups,
                    "responsibilities": responsibilities,
                    "proposals": [item.model_dump(mode="json") for item in chosen],
                    "occupations": [
                        item.model_dump(mode="json") for item in occupations
                    ],
                },
                SKILL_PRIORITY_CONTEXT_PROMPT,
                TypeAdapter(list[_ContextDecision]),
                deadline,
                slots,
            )
            self._check_context_decisions(
                checked,
                transport_groups,
                {item.soc_code for item in occupations},
                verified_postings,
            )
            if any(
                item.soc_code is not None
                and item.soc_code not in proposals[item.group_id]
                for item in checked
            ):
                raise _Unavailable(
                    "Validated occupation is outside this group's proposals"
                )
            titles = {item.soc_code: item.title for item in occupations}
            by_group = {item.group_id: item for item in checked}
            contexts = []
            for alias, group in alias_to_group.items():
                item = by_group[alias]
                code = item.soc_code
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
        model_id = configured_priority_model()
        assessment = PriorityAssessment(
            assessment_id=uuid4(),
            run_id=scope.run_id,
            candidate_revision=scope.expected_candidate_revision,
            input_fingerprint="",
            model_id=model_id,
            prompt_version=PROMPT_VERSION,
            policy_version=POLICY_VERSION,
            release=None,
            started_at=started,
            updated_at=started,
            deadline_at=started + timedelta(seconds=ASSESSMENT_TIMEOUT_SECONDS),
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
                defaults = self._unmapped(
                    inputs["groups"], "Pending occupation context"
                )
                assessment.deadline_at = started + timedelta(
                    seconds=_assessment_budget(self._pairs(inputs, defaults))
                )
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
                0.0,
                min(
                    ASSESSMENT_TIMEOUT_SECONDS,
                    (assessment.deadline_at - started).total_seconds(),
                ),
            )
            slots = _shared_model_slots(lease.thread_id)
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

            async def score(batch, *, repair=False):
                ids = {pair.candidate_id for pair in batch}
                codes = {pair.soc_code for pair in batch}
                try:
                    payload = {
                        "phase": "score",
                        "repair_instruction": (
                            "Return only these previously failed or missing owned records. "
                            "Use the exact compact schema and independently recheck evidence; "
                            "unavailable remains correct when evidence is insufficient."
                            if repair
                            else None
                        ),
                        "scoring_rubric": {
                            "1": "Little importance to the role.",
                            "2": "Supporting or secondary to the role's primary responsibilities.",
                            "3": "Important to the role.",
                            "4": "Central to multiple primary responsibilities.",
                            "5": "Essential: core work cannot be performed without this capability.",
                        },
                        "evidence_consistency_rules": [
                            "An equivalent association requires the same complete action, object, outcome and scope as the candidate competency, compared by meaning.",
                            "Related concepts or partial overlap are broader/related associations, not an official rating; shared words or tools do not establish equivalence.",
                            "For basis ai_estimate, cite only broader/related anchors, never equivalent associations, and keep direct_reference_id null.",
                            "For basis onet, cite exactly one equivalent direct reference for the complete competency and return its ID, never an official numeric value.",
                            "A missing or suppressed measurement is distinct from no suitable direct descriptor. Do not reconstruct that withheld measurement; only independently supported specific competencies may use other valid broader/related anchors.",
                            "Assess importance to the whole validated occupation, not urgency in one posting. Use independent occupation context and anchors to assess the specific capability.",
                            "Do not escalate a skill merely because a posting mentions it. Mention or use does not itself establish essential importance, and core technologies do not all deserve 5.",
                            "When the evidence cannot establish defensible occupational importance, return unavailable rather than choosing a high rating.",
                        ],
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
                            & {UUID(candidate) for candidate in value["candidate_ids"]}
                        },
                    }
                    payload, candidate_ids, reference_ids, evidence_ids = (
                        _compact_scoring_payload(payload)
                    )
                    records = await self._request(
                        payload,
                        SKILL_PRIORITY_ANALYST_PROMPT,
                        TypeAdapter(list[_ScoringDecision]),
                        deadline,
                        slots,
                        scoring_records=True,
                    )
                    wire, rejected = _parse_scoring_records(records, candidate_ids)
                    decisions = []
                    for row in wire:
                        try:
                            decisions.extend(
                                _expand_scoring_decisions(
                                    [row],
                                    candidate_ids,
                                    reference_ids,
                                    evidence_ids,
                                    batch[0].soc_code,
                                    payload,
                                )
                            )
                        except _Unavailable as exc:
                            rejected[row.candidate_id] = str(exc)
                    results = validate_priority_decisions(
                        decisions,
                        pairs=batch,
                        references=references,
                        passages=inputs["passages"],
                        candidates=inputs["candidates"],
                    )
                    reasons = {
                        candidate_ids[key]: reason for key, reason in rejected.items()
                    }
                    for result in results:
                        reason = reasons.get(str(result.candidate_id))
                        if result.value is None and reason:
                            result.unavailable_reason = reason
                            result.limitations = [reason]
                    explicit_unavailable = {
                        decision.candidate_id
                        for decision in decisions
                        if decision.basis == "unavailable"
                    }
                    failed_ids = {
                        result.candidate_id
                        for result in results
                        if result.value is None
                        and result.candidate_id not in explicit_unavailable
                    }
                    retry = [pair for pair in batch if pair.candidate_id in failed_ids]
                    diagnostics = list(dict.fromkeys(rejected.values()))
                    if retry and not diagnostics:
                        diagnostics = [
                            result.unavailable_reason
                            for result in results
                            if result.candidate_id in failed_ids
                            and result.unavailable_reason
                        ]
                    return results, diagnostics, retry
                except _Unavailable as exc:
                    return [], [str(exc)], batch

            # Share complete occupation anchors across a bounded group of pairs,
            # rather than spending the common deadline on many tiny requests.
            for attempt in range(2):
                by_occupation = {}
                for pair in pending:
                    by_occupation.setdefault(pair.soc_code, []).append(pair)
                tasks = [
                    asyncio.create_task(
                        score(group[i : i + SCORING_BATCH_SIZE], repair=bool(attempt))
                    )
                    for group in by_occupation.values()
                    for i in range(0, len(group), SCORING_BATCH_SIZE)
                ]
                pending = []
                for completed in asyncio.as_completed(tasks):
                    results, diagnostics, retry = await completed
                    if attempt:
                        errors.extend(diagnostics)
                    else:
                        pending.extend(retry)
                        failed = {
                            (pair.candidate_id, pair.context_key) for pair in retry
                        }
                        results = [
                            result
                            for result in results
                            if (result.candidate_id, result.context_key) not in failed
                        ]
                    if results:
                        assessment.results.extend(results)
                        assessment.completed_pair_count = len(assessment.results)
                        assessment.updated_at = datetime.now(UTC)
                        self._save(scope, lease, assessment, assessment.assessment_id)
                if not pending:
                    break
                logger.info("Priority repair pending_pairs=%d", len(pending))
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
