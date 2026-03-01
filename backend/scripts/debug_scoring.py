"""Debug script to check why chapter analysis scoring returns zeros."""

from sqlalchemy.orm import joinedload

from app.core.database import SessionLocal
from app.modules.curricularalignmentarchitect.models import (
    BookChapter,
    BookConcept,
    BookSection,
    ConceptRelevance,
    CourseConceptCache,
)

db = SessionLocal()

RUN_ID = 9

# 1. Check course concept cache
cache = db.query(CourseConceptCache).filter(CourseConceptCache.run_id == RUN_ID).all()
cache_with_emb = [c for c in cache if c.name_embedding is not None]
print(f"\n=== Course Concept Cache (run {RUN_ID}) ===")
print(f"Total cached: {len(cache)}")
print(f"With name_embedding: {len(cache_with_emb)}")
if cache:
    c = cache[0]
    emb_len = len(list(c.name_embedding)) if c.name_embedding is not None else 0
    print(f"Sample: name={c.concept_name!r}, topic={c.doc_topic!r}, emb_len={emb_len}")

# 2. Check chapters
chapters = db.query(BookChapter).filter(BookChapter.run_id == RUN_ID).all()
print(f"\n=== Chapters (run {RUN_ID}) ===")
print(f"Total chapters: {len(chapters)}")
book_ids = set()
for ch in chapters:
    book_ids.add(ch.selected_book_id)
    print(f"  Book {ch.selected_book_id}: Ch {ch.chapter_index} - {ch.chapter_title!r}")

# 3. Check sections and concepts per book
for book_id in sorted(book_ids):
    print(f"\n=== Book {book_id} concepts ===")
    chs = (
        db.query(BookChapter)
        .filter(BookChapter.run_id == RUN_ID, BookChapter.selected_book_id == book_id)
        .options(joinedload(BookChapter.sections).joinedload(BookSection.concepts))
        .all()
    )
    total = 0
    core_supp = 0
    with_emb = 0
    core_supp_with_emb = 0
    relevance_counts = {}
    for ch in chs:
        for sec in ch.sections:
            for c in sec.concepts:
                total += 1
                rel = c.relevance.value if c.relevance else "None"
                relevance_counts[rel] = relevance_counts.get(rel, 0) + 1
                has_emb = c.name_embedding is not None
                if has_emb:
                    with_emb += 1
                if c.relevance in (
                    ConceptRelevance.CORE,
                    ConceptRelevance.SUPPLEMENTARY,
                ):
                    core_supp += 1
                    if has_emb:
                        core_supp_with_emb += 1
    print(f"  Total concepts: {total}")
    print(f"  Relevance breakdown: {relevance_counts}")
    print(f"  Core/Supplementary: {core_supp}")
    print(f"  With name_embedding: {with_emb}")
    print(f"  Core/Supp WITH embedding: {core_supp_with_emb}")
    if total > 0 and core_supp_with_emb == 0:
        # Sample a few concepts to see their state
        for ch in chs[:1]:
            for sec in ch.sections[:1]:
                for c in sec.concepts[:3]:
                    print(
                        f"  Sample: name={c.name!r}, relevance={c.relevance}, emb={'YES' if c.name_embedding else 'NO'}, run_id={c.run_id}"
                    )

# 4. Check BookConcept directly (not through joins)
print(f"\n=== Direct BookConcept query (run {RUN_ID}) ===")
direct_count = db.query(BookConcept).filter(BookConcept.run_id == RUN_ID).count()
direct_with_emb = (
    db.query(BookConcept)
    .filter(
        BookConcept.run_id == RUN_ID,
        BookConcept.name_embedding.isnot(None),
    )
    .count()
)
print(f"Total BookConcept: {direct_count}")
print(f"With name_embedding: {direct_with_emb}")

# 5. Check if concepts are linked via section → chapter → run correctly
print("\n=== Relationship chain check ===")
sample_concepts = (
    db.query(BookConcept).filter(BookConcept.run_id == RUN_ID).limit(5).all()
)
for c in sample_concepts:
    sec = db.query(BookSection).filter(BookSection.id == c.section_id).first()
    if sec:
        ch = db.query(BookChapter).filter(BookChapter.id == sec.chapter_id).first()
        print(
            f"  Concept {c.id}: section_id={c.section_id}, sec.chapter_id={sec.chapter_id}, ch.run_id={ch.run_id if ch else 'N/A'}, ch.selected_book_id={ch.selected_book_id if ch else 'N/A'}"
        )
    else:
        print(f"  Concept {c.id}: section_id={c.section_id}, NO SECTION FOUND")

db.close()
