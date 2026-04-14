"""
Services package for the knowledge graph builder.

This package contains all the service classes for handling different
aspects of the knowledge graph building process:

- EmbeddingService: Handles text embeddings using OpenAI API
- LangChainCanonicalExtractionService: LangChain-based concept extraction
- IngestionService: Complete pipeline for knowledge graph ingestion
- Neo4jService: Neo4j database operations using LangChain
"""

from .embedding import EmbeddingService
from .extraction_langchain import LangChainCanonicalExtractionService

# Optional imports:
# - IngestionService may depend on Neo4j integration depending on configuration.
# - Neo4jService lives at the repo root (not installed in this package by default).
try:
    from .ingestion import IngestionService
except Exception:  # pragma: no cover
    IngestionService = None  # type: ignore[assignment]

try:
    from neo4j_database import Neo4jService
except Exception:  # pragma: no cover
    Neo4jService = None  # type: ignore[assignment]

__all__ = [
    "EmbeddingService",
    "LangChainCanonicalExtractionService",
    "IngestionService",
    "Neo4jService",
]

__version__ = '1.0.0'
