"""
Services package for the knowledge graph builder.

This package contains all the service classes for handling different
aspects of the knowledge graph building process:

- EmbeddingService: Handles text embeddings using OpenAI API
- ExtractionService: LLM-based text processing and concept extraction  
- IngestionService: Complete pipeline for knowledge graph ingestion
- Neo4jService: Neo4j database operations using LangChain
"""

from .embedding import EmbeddingService
from .extraction import ExtractionService
from .ingestion import IngestionService
from .neo4j_service import Neo4jService

__all__ = [
    'EmbeddingService',
    'ExtractionService', 
    'IngestionService',
    'Neo4jService'
]

__version__ = '1.0.0'
