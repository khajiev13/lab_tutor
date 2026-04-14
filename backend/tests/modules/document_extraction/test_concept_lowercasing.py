from app.modules.document_extraction.neo4j_repository import MentionInput
from app.modules.document_extraction.schemas import ConceptExtraction
from app.modules.document_extraction.service import (
    _build_mentions,
    _canonicalize_concept_name,
)


def test_canonicalize_concept_name_lowercases_and_preserves_original() -> None:
    canonical, original = _canonicalize_concept_name("  SQL  ")
    assert canonical == "sql"
    assert original == "SQL"


def test_build_mentions_lowercases_concept_name_and_keeps_original_name() -> None:
    concepts = [
        ConceptExtraction(name="SQL", definition="d1", text_evidence="e1"),
        ConceptExtraction(
            name="  Data Warehousing  ", definition="d2", text_evidence="e2"
        ),
        # Should be skipped
        ConceptExtraction(name="   ", definition="d3", text_evidence="e3"),
    ]

    mentions = _build_mentions(concepts=concepts, source_document="file.txt")
    assert mentions == [
        MentionInput(
            name="sql",
            original_name="SQL",
            definition="d1",
            text_evidence="e1",
            source_document="file.txt",
        ),
        MentionInput(
            name="data warehousing",
            original_name="Data Warehousing",
            definition="d2",
            text_evidence="e2",
            source_document="file.txt",
        ),
    ]
