from __future__ import annotations

from neo4j import Driver

from app.core.settings import settings


def load_skills_without_embeddings(driver: Driver, course_id: int) -> list[dict]:
    with driver.session(database=settings.neo4j_database) as session:
        result = session.run(
            """
            MATCH (cl:CLASS {id: $course_id})
            MATCH (cl)-[:HAS_COURSE_CHAPTER]->(cc:COURSE_CHAPTER)<-[:MAPPED_TO]-(s:SKILL)
            WHERE s.name_embedding IS NULL
            RETURN s.name AS name, labels(s) AS labels
            UNION
            MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(b:BOOK)-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)-[:HAS_SKILL]->(s:SKILL)
            WHERE s.name_embedding IS NULL
            RETURN s.name AS name, labels(s) AS labels
            """,
            course_id=course_id,
        )
        return [record.data() for record in result]


def write_skill_embeddings(driver: Driver, rows: list[dict]) -> None:
    with driver.session(database=settings.neo4j_database) as session:
        session.run(
            """
            UNWIND $rows AS row
            MATCH (s:SKILL {name: row.name})
            SET s.name_embedding = row.embedding
            """,
            rows=rows,
        ).consume()


def load_all_skills_for_course(driver: Driver, course_id: int) -> list[dict]:
    with driver.session(database=settings.neo4j_database) as session:
        result = session.run(
            """
            MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(b:BOOK)
                  -[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)-[:HAS_SKILL]->(s:BOOK_SKILL)
            WITH cl, s, ch,
                 [(s)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | c.name] AS concepts,
                 COLLECT {
                     MATCH (cl)-[:HAS_COURSE_CHAPTER]->(cc:COURSE_CHAPTER)<-[:MAPPED_TO]-(s)
                     RETURN cc { .title, .chapter_index }
                     LIMIT 1
                 } AS mapped_cc
            RETURN
                s.name AS name,
                coalesce(s.description, '') AS description,
                concepts,
                coalesce(mapped_cc[0].title, ch.title, '') AS chapter_title,
                coalesce(mapped_cc[0].chapter_index, ch.chapter_index, 0) AS chapter_index,
                'book' AS skill_type,
                s.name_embedding AS name_embedding
            UNION
            MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(cc:COURSE_CHAPTER)
                  <-[:MAPPED_TO]-(s:MARKET_SKILL)
            RETURN
                s.name AS name,
                coalesce(s.description, '') AS description,
                [(s)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | c.name] AS concepts,
                coalesce(cc.title, '') AS chapter_title,
                coalesce(cc.chapter_index, 0) AS chapter_index,
                'market' AS skill_type,
                s.name_embedding AS name_embedding
            """,
            course_id=course_id,
        )
        return [record.data() for record in result]


def merge_skill_into_canonical(
    driver: Driver, canonical_name: str, dupe_names: list[str]
) -> None:
    with driver.session(database=settings.neo4j_database) as session:
        session.run(
            """
            UNWIND $dupe_names AS dupe_name
            MATCH (canonical:SKILL {name: $canonical_name})
            MATCH (dup:SKILL {name: dupe_name})
            WHERE canonical <> dup
            CALL apoc.refactor.mergeNodes([canonical, dup], {properties: 'discard', mergeRels: true})
            YIELD node
            RETURN count(node) AS merged
            """,
            canonical_name=canonical_name,
            dupe_names=dupe_names,
        ).consume()


def replace_skill_prerequisites(
    driver: Driver, course_id: int, edges: list[dict]
) -> int:
    with driver.session(database=settings.neo4j_database) as session:
        return session.execute_write(
            _replace_skill_prerequisites_tx,
            course_id,
            edges,
        )


def _replace_skill_prerequisites_tx(tx, course_id: int, edges: list[dict]) -> int:
    result = tx.run(
        """
        MATCH (cl:CLASS {id: $course_id})
        CALL {
            WITH cl
            MATCH (cl)-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)<-[:MAPPED_TO]-(s:SKILL)
            RETURN collect(DISTINCT s) AS mapped_skills
        }
        CALL {
            WITH cl
            MATCH (cl)-[:CANDIDATE_BOOK]->(:BOOK)-[:HAS_CHAPTER]->(:BOOK_CHAPTER)
                  -[:HAS_SKILL]->(s:SKILL)
            RETURN collect(DISTINCT s) AS book_skills
        }
        WITH mapped_skills + book_skills AS raw_skills
        UNWIND raw_skills AS course_skill
        WITH collect(DISTINCT course_skill) AS course_skills
        CALL {
            WITH course_skills
            UNWIND course_skills AS a
            MATCH (a)-[r:PREREQUISITE]->(b)
            WHERE b IN course_skills
            DELETE r
            RETURN count(r) AS deleted
        }
        WITH course_skills
        CALL {
            WITH course_skills
            UNWIND $edges AS e
            MATCH (a:SKILL {name: e.prereq_name})
            WHERE a IN course_skills
            MATCH (b:SKILL {name: e.dependent_name})
            WHERE b IN course_skills
            MERGE (a)-[r:PREREQUISITE]->(b)
            SET r.confidence = e.confidence,
                r.reasoning = e.reasoning,
                r.created_at = datetime()
            RETURN count(r) AS written
        }
        RETURN written
        """,
        course_id=course_id,
        edges=edges,
    ).single()
    return result["written"] if result else 0


def load_review_skills_for_course(driver: Driver, course_id: int) -> list[dict]:
    skills_by_name: dict[str, dict] = {}
    for row in load_all_skills_for_course(driver, course_id):
        name = str(row.get("name") or "").strip()
        if not name or name in skills_by_name:
            continue
        skills_by_name[name] = {
            "name": name,
            "source": row.get("skill_type") or "unknown",
            "chapter_title": row.get("chapter_title"),
        }
    return sorted(skills_by_name.values(), key=lambda skill: skill["name"])


def get_skill_prerequisites(driver: Driver, course_id: int) -> list[dict]:
    with driver.session(database=settings.neo4j_database) as session:
        result = session.run(
            """
            MATCH (cl:CLASS {id: $course_id})
            MATCH (cl)-[:HAS_COURSE_CHAPTER]->(cc:COURSE_CHAPTER)<-[:MAPPED_TO]-(a:SKILL)-[r:PREREQUISITE]->(b:SKILL)
            RETURN a.name AS from_skill, b.name AS to_skill, r.confidence AS confidence, r.reasoning AS reasoning
            UNION
            MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(bk:BOOK)-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)-[:HAS_SKILL]->(a:SKILL)-[r:PREREQUISITE]->(b:SKILL)
            RETURN a.name AS from_skill, b.name AS to_skill, r.confidence AS confidence, r.reasoning AS reasoning
            """,
            course_id=course_id,
        )
        return [record.data() for record in result]
