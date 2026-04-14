import unittest

from neo4j_database.neo4j_service import normalize_concept_name


class TestNormalizeConceptName(unittest.TestCase):
    def test_lowercases_and_trims(self) -> None:
        self.assertEqual(normalize_concept_name("  SQL  "), "sql")

    def test_collapses_whitespace(self) -> None:
        self.assertEqual(normalize_concept_name("Data   Warehousing"), "data warehousing")

    def test_suffix_stripping_and_lowercasing(self) -> None:
        self.assertEqual(normalize_concept_name("Indexing Strategies"), "indexing")












