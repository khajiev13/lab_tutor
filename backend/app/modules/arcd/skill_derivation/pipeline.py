"""Orchestrates the full Phase 0 skill derivation pipeline."""

from __future__ import annotations

import logging

from app.modules.arcd.llm.base import BaseLLMProvider
from app.modules.arcd.skill_derivation.clustering import find_optimal_k
from app.modules.arcd.skill_derivation.embedder import embed_concepts, extract_concepts
from app.modules.arcd.skill_derivation.llm_validator import (
    should_recluster,
    validate_clusters,
)
from app.modules.arcd.skill_derivation.models import CourseSkillMap, SkillCluster
from app.modules.arcd.skill_derivation.prerequisite import (
    derive_skill_prerequisites,
    fetch_concept_prereqs,
)

logger = logging.getLogger(__name__)

MAX_RECLUSTER_ITERATIONS = 3


class SkillDerivationPipeline:
    def __init__(
        self,
        driver,
        llm_provider: BaseLLMProvider | None = None,
        st_model: str = "all-MiniLM-L6-v2",
        tau_prereq: float = 0.1,
    ):
        self.driver = driver
        self.llm_provider = llm_provider
        self.st_model = st_model
        self.tau_prereq = tau_prereq

    def run(self, course_id: str | None = None) -> CourseSkillMap:
        concepts = extract_concepts(self.driver, course_id)
        if not concepts:
            logger.warning("No concepts found for course_id=%s", course_id)
            return CourseSkillMap(course_id=course_id)

        concept_ids, embeddings = embed_concepts(concepts, self.st_model)

        result = find_optimal_k(embeddings)
        labels = result.labels

        # LLM validation loop
        for _ in range(MAX_RECLUSTER_ITERATIONS):
            clusters_by_concepts = self._group_concepts(concept_ids, labels, result.k_optimal)
            if self.llm_provider is None:
                break
            validations = validate_clusters(
                [[concepts[concept_ids.index(cid)]["name"] for cid in cids]
                 for cids in clusters_by_concepts],
                self.llm_provider,
            )
            if not should_recluster(validations):
                for _i, _v in enumerate(validations):
                    pass  # names applied below
                break
            k_adjust = sum(1 for v in validations if v.action == "split") - \
                       sum(1 for v in validations if v.action == "merge")
            new_k = max(2, result.k_optimal + k_adjust)
            result = find_optimal_k(embeddings, k_min=new_k, k_max=new_k)
            labels = result.labels
        else:
            clusters_by_concepts = self._group_concepts(concept_ids, labels, result.k_optimal)

        # Build skill clusters
        skills = []
        validations_map = {}
        if self.llm_provider is not None:
            clusters_text = [[concepts[concept_ids.index(cid)]["name"] for cid in cids]
                             for cids in clusters_by_concepts]
            validations = validate_clusters(clusters_text, self.llm_provider)
            validations_map = {v.cluster_idx: v for v in validations}

        for k_idx in range(result.k_optimal):
            mask = labels == k_idx
            v = validations_map.get(k_idx)
            name = v.skill_name if v else f"skill_{k_idx + 1:02d}"
            desc = v.description if v else ""
            skills.append(SkillCluster(
                skill_id=f"skill_{k_idx + 1:02d}",
                skill_name=name,
                description=desc,
                concept_ids=[concept_ids[i] for i in range(len(concept_ids)) if mask[i]],
                centroid=result.centroids[k_idx],
            ))

        concept_prereqs = fetch_concept_prereqs(self.driver, course_id)
        prereqs = derive_skill_prerequisites(skills, concept_prereqs, self.tau_prereq)

        skill_map = CourseSkillMap(
            course_id=course_id,
            skills=skills,
            prerequisites=prereqs,
            K=result.k_optimal,
            silhouette_score=result.silhouette,
        )

        self._write_to_neo4j(skill_map)
        return skill_map

    def _group_concepts(self, concept_ids, labels, k):
        groups = [[] for _ in range(k)]
        for i, cid in enumerate(concept_ids):
            groups[labels[i]].append(cid)
        return groups

    def _write_to_neo4j(self, skill_map: CourseSkillMap):
        with self.driver.session() as session:
            for sk in skill_map.skills:
                session.run(
                    "MERGE (s:SKILL {skill_id: $sid}) "
                    "SET s.name = $name, s.description = $desc, s.course_id = $cid",
                    sid=sk.skill_id, name=sk.skill_name,
                    desc=sk.description, cid=skill_map.course_id,
                )
                for cid in sk.concept_ids:
                    session.run(
                        "MATCH (s:SKILL {skill_id: $sid}) "
                        "MATCH (c:CONCEPT) WHERE c.concept_id = $cid OR c.name = $cid "
                        "MERGE (s)-[:INCLUDES]->(c)",
                        sid=sk.skill_id, cid=cid,
                    )
            for p in skill_map.prerequisites:
                session.run(
                    "MATCH (a:SKILL {skill_id: $a}) "
                    "MATCH (b:SKILL {skill_id: $b}) "
                    "MERGE (a)-[r:PREREQUISITE]->(b) SET r.strength = $s",
                    a=p.from_skill, b=p.to_skill, s=p.strength,
                )
