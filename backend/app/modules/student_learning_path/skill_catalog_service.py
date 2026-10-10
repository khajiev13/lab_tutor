"""One SQL-authoritative availability/identity resolver for all student consumers."""

from collections import defaultdict
from uuid import UUID

from fastapi import HTTPException

from app.modules.courses.curriculum_schemas import (
    MarketSkillBankJobPosting,
    MarketSkillBankSkill,
)
from app.modules.marketdemandanalyst.review_service import qualifying_vacancy_bindings

from . import neo4j_repository as graph
from .repository import SkillCatalogRepository
from .schemas import (
    CareerSkillBankSkill,
    SkillReferenceDisplay,
    StudentSkillBankJobPosting,
    StudentSkillBankSkill,
)

_VACANCY_FIELDS = (
    "snapshot_id",
    "provider",
    "original_url",
    "original_phrase",
    "evidence_kind",
    "excerpt",
    "excerpt_start",
    "excerpt_end",
    "retrieved_at",
    "status",
)
_ONET_FIELDS = (
    "id",
    "release",
    "soc_code",
    "occupation_title",
    "family",
    "element_id",
    "label",
    "definition",
    "workplace_example",
    "ratings",
    "flags",
    "source_url",
    "attribution",
)


class SkillCatalogService:
    def __init__(self, db, session):
        self._repo = SkillCatalogRepository(db)
        self._session = session

    def catalog(self, course_id: int) -> list[dict]:
        targets = graph.get_course_targets(self._session, course_id)
        references = self._repo.references(course_id)
        known = {row.target_identity for row in references}
        for target in targets:
            if target["legacy"] and target["target_identity"] not in known:
                self._repo.legacy_reference(course_id, target)
        if any(t["legacy"] and t["target_identity"] not in known for t in targets):
            self._repo.commit()
            references = self._repo.references(course_id)
        active, historical = self._repo.approved_items(course_id)
        _, _, bindings = self._repo.review.active_projection_items(
            course_id, [str(r.id) for r in references]
        )
        binding_map = {
            (
                b.approval_id,
                str(b.skill_reference_id),
                str(b.candidate_id),
                str(b.vacancy_snapshot_id or b.onet_evidence_id),
            ): b
            for b in bindings
        }
        target_map = {row["target_identity"]: row for row in targets}
        supported = defaultdict(list)
        for approval, item in active:
            ref_id = item["skill_reference_id"]
            run = self._repo.run(approval.run_id)
            if run is None or run.course_id != course_id:
                continue
            snapshots = self._repo.review.vacancy_snapshots_by_ids(
                [row["snapshot_id"] for row in item.get("vacancy_bindings", [])]
            )
            current = qualifying_vacancy_bindings(
                run,
                {**item["candidate"], "identity_key": item.get("identity_key")},
                item["target"],
                snapshots,
                trusted_observations=item.get("validated_observations", []),
            )
            current = [
                row
                for row in current
                if (
                    b := binding_map.get(
                        (approval.id, ref_id, item["candidate_id"], row["snapshot_id"])
                    )
                )
                is not None
                and b.provenance == row
                and b.run_id == approval.run_id
                and b.course_id == course_id
            ]
            if current:
                supported[ref_id].append((approval, item, current, snapshots))
        rows = []
        for ref in references:
            target = target_map.get(ref.target_identity)
            legacy = bool(target and target["legacy"])
            contexts = supported[str(ref.id)]
            contexts = [
                c
                for c in contexts
                if c[1]["target"]
                == {
                    "identity": ref.target_identity,
                    "label": ref.label,
                    "source": ref.source,
                    "origin": ref.origin,
                }
            ]
            ready = bool(
                target
                and target.get("projected_reference_id") == str(ref.id)
                and target.get("projection_revision") == ref.approved_revision
                and ref.projection_revision == ref.approved_revision
                and ref.projection_status == "projected"
            )
            available = legacy or bool(
                contexts and ready and ref.available_for_new_selection
            )
            evidence = {
                row["snapshot_id"]: {key: row.get(key) for key in _VACANCY_FIELDS}
                for _, _, current, _ in contexts
                for row in current
            }
            associations = {}
            for approval, item, _, _ in contexts:
                for association in item.get("onet_bindings", []):
                    ev = association["evidence"]
                    binding = binding_map.get(
                        (approval.id, str(ref.id), item["candidate_id"], ev["id"])
                    )
                    if binding is not None and binding.provenance == association:
                        associations[(ev["id"], association["relation"])] = {
                            "evidence": {key: ev.get(key) for key in _ONET_FIELDS},
                            **{
                                key: association.get(key)
                                for key in ("relation", "mapping_method", "rationale")
                            },
                        }
            chapters = {
                ch["chapter_id"]: ch
                for _, item, _, _ in contexts
                for ch in item.get("chapters", [])
            }
            if not chapters:
                chapters = {
                    ch["chapter_id"]: {
                        "chapter_id": ch["chapter_id"],
                        "title": ch["title"],
                    }
                    for ch in (target or {}).get("chapters", [])
                }
            candidate = (
                contexts[0][1]["candidate"]
                if contexts
                else (historical.get(str(ref.id), [{}])[-1].get("candidate", {}))
            )
            if not contexts:
                for item in historical.get(str(ref.id), []):
                    snapshots = self._repo.review.vacancy_snapshots_by_ids(
                        [e["snapshot_id"] for e in item.get("vacancy_bindings", [])]
                    )
                    for e in item.get("vacancy_bindings", []):
                        snapshot = snapshots.get(e["snapshot_id"])
                        if snapshot is None:
                            continue
                        safe = {key: e.get(key) for key in _VACANCY_FIELDS}
                        if snapshot.purged_at:
                            safe.update(
                                original_phrase="",
                                excerpt=None,
                                excerpt_start=None,
                                excerpt_end=None,
                                status="purged",
                            )
                        evidence[e["snapshot_id"]] = safe
            rows.append(
                {
                    **(target or {}),
                    "target_identity": ref.target_identity,
                    "name": ref.label,
                    "label": ref.label,
                    "skill_reference_id": str(ref.id),
                    "source": ref.source,
                    "skill_type": ref.source,
                    "origin": ref.origin,
                    "description": (target or {}).get("description")
                    or candidate.get("description"),
                    "category": candidate.get("category_id")
                    if candidate.get("category_id") is not None
                    else (target or {}).get("category"),
                    "chapters": list(chapters.values()),
                    "qualifying_posting_links": sorted(
                        {e["original_url"] for e in evidence.values()}
                    ),
                    "evidence_references": list(evidence.values()),
                    "onet_associations": list(associations.values()),
                    "job_metrics": self._metrics(contexts),
                    "projection_status": "projected"
                    if legacy
                    else ref.projection_status,
                    "available_for_new_selection": available,
                    "availability_reason": None
                    if available
                    else "Projection is not ready"
                    if contexts
                    else "No active qualifying job-backed approval",
                    "career": str(ref.id) in historical,
                    "is_selected": False,
                    "peer_count": 0,
                }
            )
        return rows

    @staticmethod
    def _metrics(contexts):
        if len({str(a.run_id) for a, _, _, _ in contexts}) != 1:
            return None
        metrics = [item["candidate"].get("job_metrics") for _, item, _, _ in contexts]
        if any(not m for m in metrics):
            return None
        denominators = {
            (
                m.get("assessed_posting_count"),
                m.get("selected_posting_count"),
                m.get("coverage_status"),
            )
            for m in metrics
        }
        if len(denominators) != 1:
            return None
        assessed, selected, coverage = denominators.pop()
        count = len(
            {
                snapshots[e["snapshot_id"]].demand_identity
                for _, _, current, snapshots in contexts
                for e in current
            }
        )
        if (
            not isinstance(assessed, int)
            or not isinstance(selected, int)
            or assessed < count
            or selected < assessed
            or coverage not in {"full", "partial", "failed", "pending"}
        ):
            return None
        return {
            "supporting_posting_count": count,
            "assessed_posting_count": assessed,
            "selected_posting_count": selected,
            "percentage": 100 * count / assessed if assessed else None,
            "coverage_status": coverage,
        }

    def resolve(self, course_id, *, ids=None, choices=None, require_available=True):
        catalog = self.catalog(course_id)
        by_id = {row["skill_reference_id"]: row for row in catalog}
        rows = []
        invalid = []
        for value in ids or []:
            try:
                normalized = str(UUID(str(value)))
            except ValueError:
                normalized = str(value)
            if normalized not in by_id:
                invalid.append(str(value))
            else:
                rows.append(by_id[normalized])
        if invalid:
            self._error(
                422,
                "invalid_skill_reference",
                "Unknown or inaccessible skill reference",
                ids=invalid,
            )
        for choice in choices or []:
            matches = [
                row
                for row in catalog
                if row["name"] == choice["name"]
                and (not choice.get("source") or row["source"] == choice["source"])
            ]
            if len(matches) > 1:
                self._error(
                    409,
                    "ambiguous_skill_name",
                    "Use a skill reference for this ambiguous name",
                    names=[choice["name"]],
                )
            if not matches:
                self._error(
                    409,
                    "skill_unavailable",
                    "Skill is not offered in this course",
                    names=[choice["name"]],
                )
            rows.extend(matches)
        rows = list({row["target_identity"]: row for row in rows}.values())
        unavailable = [r for r in rows if not r["available_for_new_selection"]]
        if require_available and unavailable:
            self._error(
                409,
                "skill_unavailable",
                "Skill is unavailable for new selection",
                ids=[r["skill_reference_id"] for r in unavailable],
                names=[r["name"] for r in unavailable],
            )
        return rows

    @staticmethod
    def _error(status, code, message, *, ids=None, names=None):
        raise HTTPException(
            status,
            {
                "code": code,
                "message": message,
                "skill_reference_ids": ids or [],
                "skill_names": names or [],
            },
        )

    def enrich_banks(self, course_id, bank, *, student_id=None):
        catalog = self.catalog(course_id)
        if not catalog:
            return bank
        selected = graph.get_selection_target_counts(
            self._session, course_id, student_id
        )
        selected_ids = []
        peers = {}
        for row in catalog:
            overlay = selected.get(row["target_identity"], {})
            row["is_selected"] = bool(
                student_id is not None and overlay.get("selected")
            )
            row["peer_count"] = (
                int(overlay.get("peer_count", 0)) if student_id is not None else 0
            )
            peers[row["skill_reference_id"]] = row["peer_count"]
            if row["is_selected"]:
                selected_ids.append(row["skill_reference_id"])
        by_identity = {row["target_identity"]: row for row in catalog}
        # Graph banks carry target identity internally. No label equivalence guess.
        books = getattr(bank, "book_skill_banks", getattr(bank, "book_skill_bank", []))
        book_targets = graph.get_book_bank_target_identities(self._session, course_id)
        for book in books:
            for chapter in book.chapters:
                replacements = []
                for row in book_targets.get(str(chapter.chapter_id), []):
                    data = by_identity.get(row["target_identity"])
                    if data:
                        cls = (
                            type(chapter.skills[0])
                            if chapter.skills
                            else StudentSkillBankSkill
                        )
                        replacements.append(cls.model_validate(data))
                if replacements:
                    chapter.skills = replacements
        postings = {p.url: p for p in bank.market_skill_bank}
        student_bank = hasattr(bank, "book_skill_banks")
        posting_class = (
            StudentSkillBankJobPosting if student_bank else MarketSkillBankJobPosting
        )
        skill_class = StudentSkillBankSkill if student_bank else MarketSkillBankSkill
        for posting in bank.market_skill_bank:
            posting.skills = []
        metadata = graph.get_job_posting_metadata_by_urls(
            self._session,
            [
                url
                for row in catalog
                for url in row.get("posting_urls", []) + row["qualifying_posting_links"]
            ],
        )
        for row in catalog:
            urls = set(row["qualifying_posting_links"])
            if row.get("legacy"):
                urls.update(row.get("posting_urls", []))
            for url in urls:
                if url not in postings:
                    info = metadata.get(url, {})
                    postings[url] = posting_class(
                        url=url,
                        title=info.get("title") or "Job posting",
                        company=info.get("company") or "",
                    )
                posting = postings[url]
                posting.skills.append(skill_class.model_validate(row))
        bank.market_skill_bank = list(postings.values())
        bank.career_skill_bank = [
            CareerSkillBankSkill.model_validate(row) for row in catalog if row["career"]
        ]
        if hasattr(bank, "selected_skill_reference_ids"):
            bank.selected_skill_reference_ids = selected_ids
            bank.peer_selection_counts_by_reference = peers
            bank.selected_skill_names = list(
                dict.fromkeys(row["name"] for row in catalog if row["is_selected"])
            )
            for edge in bank.prerequisite_edges:
                for prefix in ("prerequisite", "dependent"):
                    matches = [
                        r
                        for r in catalog
                        if r["name"] == getattr(edge, prefix + "_name")
                    ]
                    if len(matches) == 1:
                        setattr(
                            edge,
                            prefix + "_skill_reference_id",
                            matches[0]["skill_reference_id"],
                        )
        return bank

    def enrich_path(self, course_id, path):
        rows = {row["target_identity"]: row for row in self.catalog(course_id)}
        for chapter in path["chapters"]:
            for skill in chapter["selected_skills"]:
                row = rows.get(skill.get("target_identity"))
                if row:
                    skill.update(SkillReferenceDisplay.model_validate(row).model_dump())
                    skill["source"] = row["source"]
        return path
