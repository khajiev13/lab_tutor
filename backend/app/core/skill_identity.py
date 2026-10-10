"""Trusted graph target predicates shared by student/resource consumers."""

TARGET_IDENTITY = "CASE WHEN sk:CAREER_SKILL THEN 'career:' + toString(sk.id) WHEN sk:BOOK_SKILL THEN 'book:' + toString(sk.id) WHEN sk:MARKET_SKILL THEN 'market:' + sk.evidence_target_id END"
COURSE_MEMBERSHIP = """(
    EXISTS { MATCH (course)-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)<-[:MAPPED_TO|RELEVANT_TO_CHAPTER]-(sk) }
    OR (sk:BOOK_SKILL AND EXISTS { MATCH (course)-[:CANDIDATE_BOOK]->(:BOOK)-[:HAS_CHAPTER]->(:BOOK_CHAPTER)-[:HAS_SKILL]->(sk) })
)"""


def target_match() -> str:
    return (
        "MATCH (course:CLASS {id:$course_id}), (sk:SKILL) "
        f"WHERE {COURSE_MEMBERSHIP} AND ({TARGET_IDENTITY})=$target_identity "
    )
