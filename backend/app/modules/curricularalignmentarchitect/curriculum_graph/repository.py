"""Neo4j data-access layer for curriculum graph construction."""

from __future__ import annotations

import logging

from neo4j import ManagedTransaction

logger = logging.getLogger(__name__)


class CurriculumGraphRepository:
    """All Neo4j write operations for curriculum graph construction."""

    # ── Book node ────────────────────────────────────────────────

    @staticmethod
    def create_book_node(
        tx: ManagedTransaction,
        book_id: str,
        title: str,
        authors: str | None,
        publisher: str | None,
        year: str | None,
    ) -> None:
        tx.run(
            """
            MERGE (b:BOOK {id: $id})
            SET b.title     = $title,
                b.authors   = $authors,
                b.publisher = $publisher,
                b.year      = $year
            """,
            id=book_id,
            title=title,
            authors=authors or "",
            publisher=publisher or "",
            year=year or "",
        ).consume()

    @staticmethod
    def link_class_to_book(
        tx: ManagedTransaction,
        course_id: int,
        book_id: str,
        rank: int = 0,
        s_final: float = 0.0,
    ) -> None:
        tx.run(
            """
            MATCH (c:CLASS {id: $course_id})
            MATCH (b:BOOK {id: $book_id})
            MERGE (c)-[r:CANDIDATE_BOOK]->(b)
            SET r.rank    = $rank,
                r.s_final = $s_final
            """,
            course_id=course_id,
            book_id=book_id,
            rank=rank,
            s_final=s_final,
        ).consume()

    # ── Chapter nodes ───────────────────────────────────────────

    @staticmethod
    def create_chapter_nodes(
        tx: ManagedTransaction,
        book_id: str,
        chapters: list[dict],
    ) -> None:
        """Create BOOK_CHAPTER nodes and link them to the BOOK.

        Each dict in *chapters* must contain:
        ``id``, ``title``, ``chapter_index``, ``content``, ``summary``, ``summary_embedding``.
        """
        tx.run(
            """
            UNWIND $chapters AS ch
            MERGE (n:BOOK_CHAPTER {id: ch.id})
            SET n.title             = ch.title,
                n.chapter_index     = ch.chapter_index,
                n.content           = ch.content,
                n.summary           = ch.summary,
                n.summary_embedding = ch.summary_embedding
            WITH n, ch
            MATCH (b:BOOK {id: $book_id})
            MERGE (b)-[:HAS_CHAPTER]->(n)
            """,
            book_id=book_id,
            chapters=chapters,
        ).consume()

    @staticmethod
    def link_chapters_linked_list(
        tx: ManagedTransaction,
        book_id: str,
    ) -> None:
        """Create NEXT_CHAPTER linked-list edges in chapter_index order."""
        tx.run(
            """
            MATCH (b:BOOK {id: $book_id})-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)
            WITH ch ORDER BY ch.chapter_index
            WITH collect(ch) AS chapters
            UNWIND range(0, size(chapters) - 2) AS i
            WITH chapters[i] AS a, chapters[i + 1] AS b
            MERGE (a)-[:NEXT_CHAPTER]->(b)
            """,
            book_id=book_id,
        ).consume()

    # ── Section nodes ───────────────────────────────────────────

    @staticmethod
    def create_section_nodes(
        tx: ManagedTransaction,
        chapter_id: str,
        sections: list[dict],
    ) -> None:
        """Create BOOK_SECTION nodes and link them to a BOOK_CHAPTER.

        Each dict: ``id``, ``title``, ``section_index``, ``theory``.
        """
        tx.run(
            """
            UNWIND $sections AS sec
            MERGE (s:BOOK_SECTION {id: sec.id})
            SET s.title         = sec.title,
                s.section_index = sec.section_index,
                s.theory        = sec.theory
            WITH s, sec
            MATCH (ch:BOOK_CHAPTER {id: $chapter_id})
            MERGE (ch)-[:HAS_SECTION]->(s)
            """,
            chapter_id=chapter_id,
            sections=sections,
        ).consume()

    @staticmethod
    def link_sections_linked_list(
        tx: ManagedTransaction,
        chapter_id: str,
    ) -> None:
        tx.run(
            """
            MATCH (ch:BOOK_CHAPTER {id: $chapter_id})-[:HAS_SECTION]->(s:BOOK_SECTION)
            WITH s ORDER BY s.section_index
            WITH collect(s) AS sections
            UNWIND range(0, size(sections) - 2) AS i
            WITH sections[i] AS a, sections[i + 1] AS b
            MERGE (a)-[:NEXT_SECTION]->(b)
            """,
            chapter_id=chapter_id,
        ).consume()

    # ── Concept nodes ───────────────────────────────────────────

    @staticmethod
    def merge_concept_node(
        tx: ManagedTransaction,
        name: str,
        embedding: list[float] | None,
        description: str | None,
    ) -> None:
        tx.run(
            """
            MERGE (c:CONCEPT {name: toLower($name)})
            ON CREATE SET c.description = $description,
                          c.embedding   = $embedding,
                          c.merge_count = 0,
                          c.aliases     = []
            ON MATCH SET  c.embedding   = CASE WHEN c.embedding IS NULL
                                               THEN $embedding
                                               ELSE c.embedding END,
                          c.description = CASE WHEN c.description IS NULL
                                               THEN $description
                                               ELSE c.description END
            """,
            name=name,
            embedding=embedding,
            description=description,
        ).consume()

    @staticmethod
    def create_mentions_rel(
        tx: ManagedTransaction,
        section_id: str,
        concept_name: str,
        relevance: str,
        text_evidence: str | None,
    ) -> None:
        tx.run(
            """
            MATCH (s:BOOK_SECTION {id: $section_id})
            MATCH (c:CONCEPT {name: toLower($concept_name)})
            MERGE (s)-[r:MENTIONS]->(c)
            SET r.relevance     = $relevance,
                r.text_evidence = $text_evidence
            """,
            section_id=section_id,
            concept_name=concept_name,
            relevance=relevance,
            text_evidence=text_evidence,
        ).consume()

    # ── Skill nodes ─────────────────────────────────────────────

    @staticmethod
    def create_skill_node(
        tx: ManagedTransaction,
        skill_id: str,
        name: str,
        description: str,
        name_embedding: list[float] | None = None,
        description_embedding: list[float] | None = None,
    ) -> None:
        tx.run(
            """
            MERGE (sk:BOOK_SKILL {id: $skill_id})
            SET sk:SKILL,
                sk.name                  = $name,
                sk.description           = $description,
                sk.name_embedding        = $name_embedding,
                sk.description_embedding = $description_embedding
            """,
            skill_id=skill_id,
            name=name,
            description=description,
            name_embedding=name_embedding,
            description_embedding=description_embedding,
        ).consume()

    @staticmethod
    def link_skill_to_chapter(
        tx: ManagedTransaction,
        chapter_id: str,
        skill_id: str,
    ) -> None:
        tx.run(
            """
            MATCH (ch:BOOK_CHAPTER {id: $chapter_id})
            MATCH (sk:BOOK_SKILL {id: $skill_id})
            MERGE (ch)-[:HAS_SKILL]->(sk)
            """,
            chapter_id=chapter_id,
            skill_id=skill_id,
        ).consume()

    @staticmethod
    def link_skill_requires_concept(
        tx: ManagedTransaction,
        skill_id: str,
        concept_name: str,
    ) -> None:
        tx.run(
            """
            MATCH (sk:BOOK_SKILL {id: $skill_id})
            MATCH (c:CONCEPT {name: toLower($concept_name)})
            MERGE (sk)-[:REQUIRES_CONCEPT]->(c)
            """,
            skill_id=skill_id,
            concept_name=concept_name,
        ).consume()

    @staticmethod
    def merge_skill_concept(
        tx: ManagedTransaction,
        skill_id: str,
        concept_name: str,
    ) -> None:
        """MERGE concept node and link it to a skill (safe to call without prior concept creation)."""
        tx.run(
            """
            MATCH (sk:BOOK_SKILL {id: $skill_id})
            MERGE (c:CONCEPT {name: toLower($concept_name)})
            MERGE (sk)-[:REQUIRES_CONCEPT]->(c)
            """,
            skill_id=skill_id,
            concept_name=concept_name,
        ).consume()

    @staticmethod
    def create_skill_nodes_batch(
        tx: ManagedTransaction,
        chapter_id: str,
        skills: list[dict],
    ) -> None:
        """Batch-create BOOK_SKILL nodes, link to chapter, and link to concepts.

        Each dict in *skills* must contain:
        ``id``, ``name``, ``description``, ``name_embedding``, ``description_embedding``,
        ``concepts`` (list of concept name strings).
        """
        # Create skill nodes + link to chapter in one UNWIND
        tx.run(
            """
            UNWIND $skills AS sk
            MERGE (n:BOOK_SKILL {id: sk.id})
            SET n:SKILL,
                n.name                  = sk.name,
                n.description           = sk.description,
                n.name_embedding        = sk.name_embedding,
                n.description_embedding = sk.description_embedding
            WITH n, sk
            MATCH (ch:BOOK_CHAPTER {id: $chapter_id})
            MERGE (ch)-[:HAS_SKILL]->(n)
            WITH n, sk
            UNWIND sk.concepts AS concept_name
            MERGE (c:CONCEPT {name: toLower(concept_name)})
            MERGE (n)-[:REQUIRES_CONCEPT]->(c)
            """,
            chapter_id=chapter_id,
            skills=skills,
        ).consume()

    # ── Skill similarity search ─────────────────────────────────

    @staticmethod
    def find_similar_skills(
        tx: ManagedTransaction,
        skill_id: str,
        embedding: list[float],
        threshold: float = 0.85,
        top_k: int = 5,
    ) -> list[dict]:
        """Query the vector index for similar SKILL nodes."""
        result = tx.run(
            """
            CALL db.index.vector.queryNodes('skill_name_embedding_idx', $top_k, $embedding)
            YIELD node, score
            WHERE score >= $threshold AND node.id <> $skill_id
            RETURN node { .id, .name, .description } AS skill, score
            """,
            embedding=embedding,
            threshold=threshold,
            top_k=top_k,
            skill_id=skill_id,
        )
        return [record.data() for record in result]

    # ── Concept similarity merging ──────────────────────────────

    @staticmethod
    def vector_index_exists(
        tx: ManagedTransaction,
        index_name: str = "concept_embedding_idx",
    ) -> bool:
        """Check whether the vector index exists and is ONLINE."""
        result = tx.run(
            "SHOW INDEXES YIELD name, state "
            "WHERE name = $name AND state = 'ONLINE' "
            "RETURN count(*) AS cnt",
            name=index_name,
        ).single()
        return result is not None and result["cnt"] > 0

    @staticmethod
    def find_similar_concepts(
        tx: ManagedTransaction,
        concept_name: str,
        embedding: list[float],
        threshold: float | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """Query the vector index for similar CONCEPT nodes."""
        from app.core.settings import settings

        if threshold is None:
            threshold = settings.concept_similarity_threshold

        result = tx.run(
            """
            CALL db.index.vector.queryNodes('concept_embedding_idx', $top_k, $embedding)
            YIELD node, score
            WHERE score >= $threshold AND node.name <> toLower($concept_name)
            RETURN node.name AS name, score
            """,
            embedding=embedding,
            threshold=threshold,
            top_k=top_k,
            concept_name=concept_name,
        )
        return [record.data() for record in result]

    @staticmethod
    def merge_similar_concepts(
        tx: ManagedTransaction,
        keep_name: str,
        merge_name: str,
    ) -> None:
        """Merge *merge_name* into *keep_name* using apoc.refactor.mergeNodes."""
        tx.run(
            """
            MATCH (a:CONCEPT {name: toLower($keep_name)})
            MATCH (b:CONCEPT {name: toLower($merge_name)})
            WITH a, b
            WHERE a <> b
            CALL apoc.refactor.mergeNodes([a, b], {properties: 'combine', mergeRels: true})
            YIELD node
            SET node.merge_count = coalesce(node.merge_count, 0) + 1,
                node.aliases     = CASE
                    WHEN $merge_name IN coalesce(node.aliases, [])
                    THEN node.aliases
                    ELSE coalesce(node.aliases, []) + $merge_name
                END
            """,
            keep_name=keep_name,
            merge_name=merge_name,
        ).consume()
