"""Coordinate selected sources and persist run-local extraction evidence.

Network and model work happen outside SQL transactions. Source branches own
execution-local sessions; only this coordinator commits source/manifest results.
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import UUID

from app.core.database import SessionLocal
from app.modules.occupation_reference.repository import OccupationReferenceRepository
from app.modules.occupation_reference.service import OccupationReferenceService

from .associations import (
    enrich_observations,
    map_associations,
    normalized_competency,
)
from .countries import normalize_job_search_country
from .evidence import (
    calculate_job_metrics,
    onet_candidates,
    reconcile_candidates,
    reference_fingerprint,
)
from .extractor import merge_evidenced_skills
from .job_sources import SOURCES, get_job_source_service
from .repository import MarketReviewRepository, RevisionConflict
from .schemas import SourceOutcome

# Advance when corrected extraction/grouping rules require one fresh assessment.
_EXTRACTION_VERSION = 6


class MarketSourceService:
    def __init__(self, *, jobs=None, session_factory=SessionLocal):
        self._jobs = jobs or get_job_source_service()
        self._sessions = session_factory

    def load_config(self, state: dict) -> dict:
        with self._sessions() as db:
            run = MarketReviewRepository(db).get_run(
                UUID(state["run_id"]), state["course_id"], state["teacher_id"]
            )
            if run is None:
                raise LookupError("Analysis run not found")
            return {
                "run_id": str(run.id),
                "course_id": run.course_id,
                "teacher_id": run.teacher_id,
                **deepcopy(run.config),
            }

    def configure_country(self, state: dict, country: str) -> dict:
        """Apply chat confirmation through the same durable rules as source settings."""
        configured = deepcopy(state)
        with self._sessions() as db:
            service = MarketConfigurationService(
                MarketReviewRepository(db),
                self._jobs,
                OccupationReferenceService(OccupationReferenceRepository(db)),
            )
            service.configure(
                state["course_id"],
                state["teacher_id"],
                configured,
                {"country": country},
            )
            db.commit()
        return {
            key: configured[key]
            for key in (
                "job_search_country",
                "job_search_location",
                "job_search_country_confirmed",
            )
        }

    def require_available_evidence(
        self, state: dict, *, include_extraction: bool = True
    ) -> None:
        with self._sessions() as db:
            run = MarketReviewRepository(db).get_run(
                UUID(state["run_id"]), state["course_id"], state["teacher_id"]
            )
            if run is None:
                raise LookupError("Analysis run not found")
            omissions = available_evidence_omissions(
                run, include_extraction=include_extraction
            )
            if (
                omissions
                and run.candidate_manifest.get("acknowledged_omissions") != omissions
            ):
                raise ValueError(
                    "Retry or use Continue with available evidence to acknowledge current omissions before advancing"
                )

    def extraction_is_complete(self, state: dict, jobs: list[dict]) -> bool:
        """Stop repeating the same assessed sample when only fixed bounds remain."""
        with self._sessions() as db:
            run = MarketReviewRepository(db).get_run(
                UUID(state["run_id"]), state["course_id"], state["teacher_id"]
            )
            if run is None:
                raise LookupError("Analysis run not found")
            coverage = deepcopy(run.extraction_coverage)
        assessments = coverage.get("assessments", [])
        selected_ids = {job.get("snapshot_id") for job in jobs}
        if (
            coverage.get("extraction_version") != _EXTRACTION_VERSION
            or coverage.get("status") not in {"full", "partial"}
            or not assessments
            or None in selected_ids
            or selected_ids != {item.get("snapshot_id") for item in assessments}
            or any(item.get("status") != "full" for item in assessments)
        ):
            return False
        if coverage["status"] == "full":
            return True
        association = coverage.get("association_coverage", {})
        if association.get("failed_calls") or association.get("rejected_mappings"):
            return False
        fixed_warnings = {
            f"O*NET association inference omitted {association[f'omitted_{kind}']} {kind} at its bounded limit; exact identity matching still covered all selected rows."
            for kind in ("observations", "catalog_rows")
            if association.get(f"omitted_{kind}")
        }
        fixed_warnings.add("O*NET association inference reached its call limit.")
        warnings = set(coverage.get("warnings", [])) - set(
            coverage.get("semantic_grouping", {}).get("warnings", [])
        )
        return bool(warnings) and warnings <= fixed_warnings

    def prepare_extraction_jobs(
        self, state: dict, cached_jobs: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """Resolve current owned content before dispatch; release SQL before LLM.

        Persistence revalidates references after the external work finishes.
        """
        jobs, skipped, seen = [], [], set()
        with self._sessions() as db:
            repo = MarketReviewRepository(db)
            repo.lock_vacancy_lifecycle()
            run = repo.get_run(
                UUID(state["run_id"]), state["course_id"], state["teacher_id"]
            )
            if run is None:
                raise LookupError("Analysis run not found")
            for cached in cached_jobs:
                snapshot_id = UUID(cached["snapshot_id"])
                if snapshot_id in seen:
                    continue
                seen.add(snapshot_id)
                snapshot = repo.get_vacancy_snapshot(
                    snapshot_id, run.course_id, run.teacher_id
                )
                if (
                    snapshot is not None
                    and snapshot.run_id == run.id
                    and "jobs" in run.config.get("evidence_sources", ["jobs"])
                    and snapshot.provider in run.config.get("sources", [])
                    and not snapshot.purged_at
                    and snapshot.status != "archived"
                    and len(snapshot.description_text or "") >= 50
                ):
                    jobs.append(self._snapshot_job(snapshot))
                    continue
                skipped.append(
                    {
                        "snapshot_id": str(snapshot_id),
                        "demand_identity": snapshot.demand_identity
                        if snapshot is not None and snapshot.run_id == run.id
                        else f"unavailable:{snapshot_id}",
                        "status": "failed",
                        "total_chunks": 0,
                        "assessed_chunks": 0,
                        "uncovered_chars": 0,
                        "warnings": [
                            f"Posting {snapshot_id}: current owned content unavailable; cached content was not sent for extraction."
                        ],
                    }
                )
            db.commit()
        return jobs, skipped

    @staticmethod
    def _snapshot_job(snapshot) -> dict:
        return {
            "snapshot_id": str(snapshot.id),
            "title": snapshot.title,
            "company": snapshot.company,
            "description": snapshot.description_text,
            "url": snapshot.original_url,
            "site": snapshot.provider,
            "skill_tags": deepcopy(snapshot.skill_tags),
            "demand_identity": snapshot.demand_identity,
            "retrieved_at": snapshot.retrieved_at.isoformat(),
            "status": snapshot.status,
        }

    def _onet(self, config: dict) -> tuple[list[dict], dict]:
        if not config.get("onet_selection_confirmed"):
            raise ValueError("Confirm one to five O*NET occupations before collection")
        codes = [o["soc_code"] for o in config.get("selected_onet_occupations", [])]
        try:
            with self._sessions() as db:
                service = OccupationReferenceService(OccupationReferenceRepository(db))
                rows = service.get_skill_evidence(
                    config["course_id"],
                    config["teacher_id"],
                    config["onet_release"],
                    codes,
                )
                items = [
                    row.model_dump(mode="json")
                    if hasattr(row, "model_dump")
                    else deepcopy(row)
                    for row in rows
                ]
            return items, SourceOutcome(
                status="success" if items else "empty",
                received_count=len(items),
                usable_count=len(items),
            ).model_dump()
        except Exception:
            return [], SourceOutcome(
                status="error",
                warnings=[
                    "O*NET lookup failed; retry or acknowledge the omitted reference source."
                ],
            ).model_dump()

    def collect_sources(
        self, run_config: dict, search_terms: list[str], *, results_per_source: int = 15
    ) -> dict:
        config = deepcopy(run_config)
        search_terms = list(
            dict.fromkeys(
                term.strip()
                for term in search_terms
                if isinstance(term, str) and term.strip()
            )
        )
        evidence_sources = config.get("evidence_sources", ["jobs"])
        if "onet" in evidence_sources and not config.get("onet_selection_confirmed"):
            raise ValueError("Confirm one to five O*NET occupations before collection")
        if (
            not isinstance(results_per_source, int)
            or isinstance(results_per_source, bool)
            or not 1 <= results_per_source <= 100
        ):
            raise ValueError("Result cap must be from 1 to 100")
        if "jobs" in evidence_sources and not any(
            term.strip() for term in search_terms
        ):
            raise ValueError("At least one nonblank search query is required")
        country = normalize_job_search_country(config.get("country"))
        sources = tuple(config.get("sources", SOURCES))
        self._jobs.validate_compatibility(
            country, sources, evidence_sources=evidence_sources
        )
        # Freeze authoritative config before any provider work (including empty/error).
        with self._sessions() as db:
            repo = MarketReviewRepository(db)
            run = repo.get_run(
                UUID(config["run_id"]),
                config["course_id"],
                config["teacher_id"],
                for_update=True,
            )
            if run is None:
                raise LookupError("Analysis run not found")
            if {k: config.get(k) for k in run.config} != run.config:
                raise ValueError(
                    "Source configuration differs from the durable analysis"
                )
            run.source_outcomes = {
                s: SourceOutcome(status="loading").model_dump()
                for s in ([*sources] if "jobs" in evidence_sources else [])
                + (["onet"] if "onet" in evidence_sources else [])
            }
            run.integration_review = None
            db.commit()
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs_future = (
                pool.submit(
                    self._jobs.fetch,
                    search_terms=search_terms,
                    country=country,
                    sources=sources,
                    results_per_source=results_per_source,
                    evidence_sources=evidence_sources,
                )
                if "jobs" in evidence_sources
                else None
            )
            onet_future = (
                pool.submit(self._onet, config) if "onet" in evidence_sources else None
            )
            jobs = jobs_future.result() if jobs_future else None
            onet, onet_outcome = onet_future.result() if onet_future else ([], None)
        outcomes = (
            {key: value.model_dump() for key, value in jobs.outcomes.items()}
            if jobs
            else {}
        )
        if onet_outcome is not None:
            outcomes["onet"] = onet_outcome
        usable_jobs = []
        purged_counts = {}
        with self._sessions() as db:
            repo = MarketReviewRepository(db)
            repo.lock_vacancy_lifecycle()  # BEFORE get_run(for_update) / snapshot locks.
            run = repo.get_run(
                UUID(config["run_id"]),
                config["course_id"],
                config["teacher_id"],
                for_update=True,
            )
            for record in jobs.records if jobs else []:
                snapshot = repo.upsert_vacancy_snapshot(run.id, record)
                # Full response stored above even when it cannot be extracted.
                if snapshot.purged_at:
                    purged_counts[snapshot.provider] = (
                        purged_counts.get(snapshot.provider, 0) + 1
                    )
                if (
                    not snapshot.purged_at
                    and snapshot.status != "archived"
                    and len(snapshot.description_text or "") >= 50
                ):
                    usable_jobs.append(self._snapshot_job(snapshot))
            for source in sources if jobs else []:
                outcomes[source]["usable_count"] = sum(
                    job["site"] == source for job in usable_jobs
                )
                if purged_counts.get(source):
                    outcomes[source]["status"] = "partial"
                    outcomes[source]["warnings"].append(
                        f"{purged_counts[source]} posting(s) have unavailable retained content and were excluded from extraction."
                    )
            previous = deepcopy(run.candidate_manifest)
            previous.update(
                selected_candidate_ids=run.selected_candidate_ids,
                excluded_candidate_ids=run.excluded_candidate_ids,
            )
            existing = [
                self._validated_observation(repo, run, self._observation(c))
                for c in previous.get("candidates", [])
            ]
            if existing or onet:
                manifest = reconcile_candidates(
                    existing + onet_candidates(onet), previous
                )
                for candidate in manifest["candidates"]:
                    candidate["job_metrics"] = calculate_job_metrics(
                        [], [], coverage_status="pending"
                    )
                self._save_manifest(repo, run, manifest)
            run.source_outcomes = outcomes
            run.extraction_coverage = {
                "status": "pending",
                "sample_limits": {
                    "results_per_query_provider": results_per_source,
                    "hours_old": 72,
                    "queries": list(dict.fromkeys(search_terms)),
                    "scope": "selected provider sample, not complete market coverage",
                },
                "selected_postings": 0,
                "assessed_postings": 0,
                "failed_postings": 0,
                "total_chunks": 0,
                "assessed_chunks": 0,
                "warnings": [],
                "acknowledged": False,
            }
            db.commit()
            return {
                "jobs": usable_jobs,
                "source_outcomes": outcomes,
                "candidates": deepcopy(run.candidate_manifest.get("candidates", [])),
                "candidate_revision": run.candidate_revision,
                "onet_evidence": onet,
            }

    @staticmethod
    def _validated_observation(
        repo, run, item: dict, *, trusted_extraction=False
    ) -> dict:
        refs, identities = [], []
        for ref in item.get("evidence_references", []):
            snapshot = repo.get_vacancy_snapshot(
                UUID(ref["snapshot_id"]), run.course_id, run.teacher_id
            )
            if (
                snapshot is None
                or snapshot.run_id != run.id
                or "jobs" not in run.config.get("evidence_sources", ["jobs"])
                or snapshot.purged_at
                or snapshot.status == "archived"
                or snapshot.provider not in run.config.get("sources", [])
                or ref.get("provider") != snapshot.provider
                or ref.get("original_url") != snapshot.original_url
            ):
                continue
            if ref.get("evidence_kind") == "provider_tag":
                valid = ref.get("original_phrase") in snapshot.skill_tags
            elif ref.get("evidence_kind") == "extracted_text":
                start, end = ref.get("excerpt_start"), ref.get("excerpt_end")
                valid = (
                    isinstance(start, int)
                    and not isinstance(start, bool)
                    and isinstance(end, int)
                    and not isinstance(end, bool)
                    and 0 <= start < end <= len(snapshot.description_text or "")
                    and snapshot.description_text[start:end] == ref.get("excerpt")
                    and isinstance(ref.get("original_phrase"), str)
                    and bool(ref["original_phrase"].strip())
                    and ref.get("original_phrase", "") in ref.get("excerpt", "")
                )
            else:
                valid = False
            if valid:
                refs.append(deepcopy(ref))
                identities.append(snapshot.demand_identity)
                if trusted_extraction and ref.get("evidence_kind") == "extracted_text":
                    observation = {
                        "reference_hash": reference_fingerprint(ref),
                        "competency": item["name"],
                        "identity_key": item.get("identity_key"),
                    }
                    manifest = deepcopy(run.candidate_manifest)
                    registry = manifest.setdefault("validated_observations", [])
                    if observation not in registry:
                        registry.append(observation)
                    run.candidate_manifest = manifest
        return {
            **deepcopy(item),
            "onet_associations": [],
            "evidence_references": refs,
            "supporting_identities": list(dict.fromkeys(identities)),
        }

    @staticmethod
    def _observation(candidate: dict) -> dict:
        return {
            **deepcopy(candidate),
            "name": candidate["display_name"],
            "category": candidate["category_id"],
        }

    @staticmethod
    def _save_manifest(repo, run, manifest):
        manifest["validated_observations"] = deepcopy(
            run.candidate_manifest.get("validated_observations", [])
        )
        repo.update_manifest(
            run.id,
            run.course_id,
            run.teacher_id,
            expected_candidate_revision=run.candidate_revision,
            candidates=manifest["candidates"],
            categories=manifest["categories"],
        )
        run.candidate_manifest = deepcopy(manifest)
        run.selected_candidate_ids = manifest["selected_candidate_ids"]
        run.excluded_candidate_ids = manifest["excluded_candidate_ids"]

    def save_extraction(
        self, config: dict, observations: list[dict], assessments: list[dict]
    ) -> dict:
        # Prepare detached, validated inputs; no SQL session spans external work.
        with self._sessions() as db:
            repo = MarketReviewRepository(db)
            run = repo.get_run(
                UUID(config["run_id"]), config["course_id"], config["teacher_id"]
            )
            if run is None:
                raise LookupError("Analysis run not found")
            authoritative = {
                **deepcopy(run.config),
                "run_id": str(run.id),
                "course_id": run.course_id,
                "teacher_id": run.teacher_id,
            }
            prepared_config = deepcopy(run.config)
            use_onet = "onet" in run.config.get("evidence_sources", ["jobs"])
            if use_onet:
                self._require_active_run(repo, run)
            revisions = (run.candidate_revision, run.selection_revision)
            previous = deepcopy(run.candidate_manifest)
            previous.update(
                selected_candidate_ids=deepcopy(run.selected_candidate_ids),
                excluded_candidate_ids=deepcopy(run.excluded_candidate_ids),
            )
            prepared = [
                self._validated_observation(repo, run, item) for item in observations
            ]
            prepared = [item for item in prepared if item["evidence_references"]]
        prepared, grouping_coverage = merge_evidenced_skills(prepared, previous)
        rows, outcome = self._onet(authoritative) if use_onet else ([], {})
        decisions, association_coverage = (
            map_associations(prepared, rows) if use_onet else ([], None)
        )
        if use_onet and outcome.get("status") == "error":
            association_coverage["status"] = "partial"
            association_coverage["warnings"].extend(outcome["warnings"])
        with self._sessions() as db:
            repo = MarketReviewRepository(db)
            repo.lock_vacancy_lifecycle()
            run = repo.get_run(
                UUID(config["run_id"]),
                config["course_id"],
                config["teacher_id"],
                for_update=True,
            )
            if run is None:
                raise LookupError("Analysis run not found")
            if (
                run.config != prepared_config
                or (run.candidate_revision, run.selection_revision) != revisions
            ):
                raise RevisionConflict(
                    "Analysis changed during source association; retry extraction"
                )
            if use_onet:
                self._require_active_run(repo, run)
            if use_onet and outcome.get("status") != "error":
                # Immutable catalog lookup is SQL-only and selected configuration
                # is still authoritative. Never trust model-returned source rows.
                current = OccupationReferenceService(
                    OccupationReferenceRepository(db)
                ).get_skill_evidence(
                    run.course_id,
                    run.teacher_id,
                    run.config["onet_release"],
                    [
                        item["soc_code"]
                        for item in run.config.get("selected_onet_occupations", [])
                    ],
                )
                current_rows = [
                    item.model_dump(mode="json")
                    if hasattr(item, "model_dump")
                    else deepcopy(item)
                    for item in current
                ]
                if sorted(rows, key=lambda row: row["id"]) != sorted(
                    current_rows, key=lambda row: row["id"]
                ):
                    raise RevisionConflict(
                        "Selected O*NET evidence changed; retry extraction"
                    )
            validated = [
                self._validated_observation(repo, run, item, trusted_extraction=True)
                for item in prepared
            ]
            # Keep the prepared indexes until the mapping has been applied.
            unchanged_indexes = {
                index
                for index, (current, original) in enumerate(
                    zip(validated, prepared, strict=True)
                )
                if current["evidence_references"] == original["evidence_references"]
            }
            if use_onet:
                validated = enrich_observations(
                    validated,
                    rows,
                    [
                        decision
                        for decision in decisions
                        if decision["observation_index"] in unchanged_indexes
                    ],
                )
            if use_onet and any(
                current["evidence_references"] != original["evidence_references"]
                for current, original in zip(validated, prepared, strict=True)
            ):
                association_coverage["status"] = "partial"
                association_coverage["warnings"].append(
                    "Posting content changed or was removed during O*NET association; invalidated references were discarded."
                )
            validated = [item for item in validated if item["evidence_references"]]
            selected = {a["demand_identity"] for a in assessments}
            assessed = {
                a["demand_identity"] for a in assessments if a["assessed_chunks"] > 0
            }
            status = (
                "full"
                if assessments and all(a["status"] == "full" for a in assessments)
                else "partial"
                if assessed
                else "failed"
            )
            coverage = {
                "extraction_version": _EXTRACTION_VERSION,
                "status": status,
                "sample_limits": deepcopy(
                    run.extraction_coverage.get("sample_limits", {})
                ),
                "selected_postings": len(selected),
                "assessed_postings": len(assessed),
                "failed_postings": len(selected - assessed),
                "total_chunks": sum(a["total_chunks"] for a in assessments),
                "assessed_chunks": sum(a["assessed_chunks"] for a in assessments),
                "warnings": sorted(
                    {w for a in assessments for w in a.get("warnings", [])}
                    | set(grouping_coverage["warnings"])
                ),
                "acknowledged": False,
                "assessments": deepcopy(assessments),
                "semantic_grouping": grouping_coverage,
            }
            if association_coverage is not None:
                coverage["association_coverage"] = association_coverage
                coverage["warnings"] = sorted(
                    set(coverage["warnings"] + association_coverage["warnings"])
                )
                if association_coverage["status"] != "full" and status == "full":
                    coverage["status"] = status = "partial"
            previous = deepcopy(run.candidate_manifest)
            previous.update(
                selected_candidate_ids=run.selected_candidate_ids,
                excluded_candidate_ids=run.excluded_candidate_ids,
            )
            references = onet_candidates(rows) if use_onet else []
            for reference in references:
                matching = []
                for item in validated:
                    matching.extend(
                        ref
                        for ref in item["evidence_references"]
                        if (
                            (
                                ref["evidence_kind"] == "extracted_text"
                                and normalized_competency(item["name"])
                                == normalized_competency(reference["name"])
                            )
                            or (
                                ref["evidence_kind"] == "provider_tag"
                                and normalized_competency(ref["original_phrase"])
                                == normalized_competency(reference["name"])
                            )
                        )
                    )
                if not matching:
                    continue
                checked = self._validated_observation(
                    repo,
                    run,
                    {**reference, "evidence_references": matching},
                    trusted_extraction=True,
                )
                reference["evidence_references"] = checked["evidence_references"]
                reference["supporting_identities"] = checked["supporting_identities"]
            manifest = reconcile_candidates(validated + references, previous)
            for c in manifest["candidates"]:
                c["job_metrics"] = calculate_job_metrics(
                    c.get("supporting_identities", []),
                    assessed,
                    selected_identities=selected,
                    coverage_status=status,
                )
            self._save_manifest(repo, run, manifest)
            run.extraction_coverage = coverage
            db.commit()
            return {
                "candidates": deepcopy(manifest["candidates"]),
                "candidate_revision": run.candidate_revision,
                "extraction_coverage": coverage,
            }

    @staticmethod
    def _require_active_run(repo, run) -> None:
        snapshot = repo.load_active_snapshot(
            f"mda-{run.teacher_id}-course-{run.course_id}"
        )
        if not snapshot or snapshot.get("run_id") != str(run.id):
            raise RevisionConflict("Review must belong to the active analysis")


def get_market_source_service() -> MarketSourceService:
    return MarketSourceService()


class MarketConfigurationService:
    def __init__(self, repository, jobs, occupations):
        self._repo = repository
        self._jobs = jobs
        self._occupations = occupations

    def save_snapshot(self, thread_id: str, snapshot: dict) -> None:
        self._repo.save_configuration_snapshot(thread_id, snapshot)

    def configure(self, course_id: int, teacher_id: int, state: dict, request: dict):
        run = (
            self._repo.get_run(
                UUID(state["run_id"]), course_id, teacher_id, for_update=True
            )
            if state.get("run_id")
            else None
        )
        if state.get("run_id") and run is None:
            raise LookupError("Analysis run not found")
        original = deepcopy(run.config if run else {})
        config = {
            "country": state.get("job_search_country") or "USA",
            "sources": list(SOURCES),
            "evidence_sources": ["jobs"],
            "onet_release": None,
            **original,
        }
        country_raw = request.get("country") or request.get("location")
        if country_raw:
            config["country"] = normalize_job_search_country(country_raw).key
        for key in ("sources", "evidence_sources", "onet_release"):
            if request.get(key) is not None:
                config[key] = deepcopy(request[key])
        config["evidence_sources"] = list(dict.fromkeys(config["evidence_sources"]))
        if not config["evidence_sources"]:
            raise ValueError("Select at least one evidence source")
        from .job_sources import normalize_job_sources

        config["sources"] = (
            list(normalize_job_sources(config["sources"]))
            if "jobs" in config["evidence_sources"]
            else list(dict.fromkeys(config["sources"]))
        )
        self._jobs.validate_compatibility(
            normalize_job_search_country(config["country"]),
            tuple(config["sources"]),
            evidence_sources=config["evidence_sources"],
        )
        started = bool(
            run
            and (
                run.lifecycle != "draft"
                or run.candidate_manifest.get("candidates")
                or any(
                    o.get("status", "idle") != "idle"
                    for o in run.source_outcomes.values()
                )
            )
        )
        if started and any(
            config.get(k) != original.get(k)
            for k in ("country", "sources", "evidence_sources", "onet_release")
        ):
            raise ValueError(
                "Configuration is locked; start a new analysis to change sources, market or release"
            )
        if "onet" in config["evidence_sources"]:
            config["onet_release"] = self._occupations.pin_release(
                course_id, teacher_id, config.get("onet_release")
            )
            codes = request.get("onet_occupation_codes")
            current_codes = [
                o["soc_code"] for o in config.get("selected_onet_occupations", [])
            ]
            if codes is not None and (
                codes != current_codes
                or config["onet_release"] != original.get("onet_release")
            ):
                if started:
                    raise ValueError(
                        "Occupation changes require a new analysis after collection starts"
                    )
                choices = (
                    self._occupations.get_occupation_choices(
                        course_id, teacher_id, config["onet_release"], codes
                    )
                    if codes
                    else []
                )
                config["selected_onet_occupations"] = [o.model_dump() for o in choices]
                config["onet_selection_confirmed"] = bool(choices)
            if original.get("onet_release") != config[
                "onet_release"
            ] and not request.get("onet_occupation_codes"):
                config["selected_onet_occupations"] = []
                config["onet_selection_confirmed"] = False
        else:
            config["onet_release"] = None
            config["selected_onet_occupations"] = []
            config["onet_selection_confirmed"] = False
        if run is None:
            run = self._repo.create_run(course_id, teacher_id, config)
        else:
            self._repo.update_configuration(run, config)
        state.update(
            {
                "run_id": str(run.id),
                "teacher_id": teacher_id,
                "sources": config["sources"],
                "evidence_sources": config["evidence_sources"],
                "onet_release": config["onet_release"],
                "selected_onet_occupations": [
                    o["soc_code"] for o in config.get("selected_onet_occupations", [])
                ],
                "onet_selection_confirmed": config.get(
                    "onet_selection_confirmed", False
                ),
                "job_search_country": config["country"],
                "job_search_location": normalize_job_search_country(
                    config["country"]
                ).location,
                "candidate_revision": run.candidate_revision,
                "source_outcomes": deepcopy(run.source_outcomes),
            }
        )
        if country_raw:
            state["job_search_country_confirmed"] = True
        return run


def available_evidence_omissions(run, *, include_extraction: bool = True) -> list[str]:
    omissions = [
        f"{provider}: {outcome['status']}"
        for provider, outcome in sorted(run.source_outcomes.items())
        if outcome.get("status") in {"partial", "error"}
    ]
    omissions.extend(
        f"{provider}: {warning}"
        for provider, outcome in sorted(run.source_outcomes.items())
        if outcome.get("status") in {"partial", "error"}
        for warning in outcome.get("warnings", [])
    )
    coverage = run.extraction_coverage
    if include_extraction and coverage.get("status") in {"partial", "failed"}:
        omissions.append(f"extraction: {coverage['status']}")
        advisory = set(coverage.get("semantic_grouping", {}).get("warnings", []))
        omissions.extend(w for w in coverage.get("warnings", []) if w not in advisory)
    return sorted(set(omissions))
