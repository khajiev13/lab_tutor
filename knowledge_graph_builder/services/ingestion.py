from pathlib import Path
from typing import Dict, Any

from utils.doc_utils import load_single_docx_document
from utils.output_utils import organize_extraction_output
from services.extraction_langchain import LangChainCanonicalExtractionService
from services.embedding import EmbeddingService
from services.neo4j_service import Neo4jService
from models.neo4j_models import Neo4jInsertionResult


class IngestionService:
    """
    Simplified knowledge graph ingestion service using LangChain extraction.
    Handles document processing, concept extraction, and Neo4j insertion.
    """

    def __init__(self, neo4j_service=None, embedding_service=None, canonical_extraction_service=None):
        """
        Initialize with optional services. Services will be auto-initialized if not provided.

        Args:
            neo4j_service: Optional Neo4j service instance
            embedding_service: Optional embedding service instance
            canonical_extraction_service: Optional LangChain canonical extraction service
        """
        self._neo4j_service = neo4j_service or Neo4jService()
        self._embedding_service = embedding_service or EmbeddingService()
        self._canonical_extraction_service = canonical_extraction_service or LangChainCanonicalExtractionService()

    @property
    def neo4j_service(self):
        """Get the Neo4j service instance."""
        return self._neo4j_service

    @property
    def embedding_service(self):
        """Get the embedding service instance."""
        return self._embedding_service

    @property
    def canonical_extraction_service(self):
        """Get the canonical extraction service instance."""
        return self._canonical_extraction_service



    def process_single_document(self, docx_path: str, output_dir: str = "output",
                              insert_to_neo4j: bool = True, generate_embeddings: bool = True) -> Dict[str, Any]:
        """
        Process a single DOCX document using LangChain extraction and optional Neo4j insertion.

        This method handles the complete pipeline for processing a single document:
        - Loads and preprocesses the DOCX document
        - Extracts concepts using LangChain canonical extraction
        - Creates topic-based folder structure for output
        - Optionally inserts extracted data into Neo4j database

        Args:
            docx_path: Path to the DOCX file to process
            output_dir: Base directory to create structured folders
            insert_to_neo4j: Whether to immediately insert into Neo4j database
            generate_embeddings: Whether to generate embeddings (unused but kept for compatibility)

        Returns:
            Dictionary with processing results and file paths
        """
        # Unused parameter kept for API compatibility
        _ = generate_embeddings
        
        try:
            # Load document
            documents = load_single_docx_document(docx_path)
            if not documents:
                return {
                    'success': False,
                    'error': 'No content found in document',
                    'source_file': docx_path
                }

            # Perform LangChain canonical extraction first to get the topic
            base_filename = Path(docx_path).stem

            # Set up temporary output path for initial extraction
            temp_output_path = Path(output_dir) / "temp_extraction"
            self.canonical_extraction_service.current_output_path = str(temp_output_path)
            self.canonical_extraction_service.current_filename = base_filename

            extraction_result = self.canonical_extraction_service.compress_and_extract_concepts(
                documents=documents,
                source_file_path=docx_path
            )

            # Organize extraction output into topic-based folder structure
            saved_files, topic_folder = organize_extraction_output(
                extraction_result=extraction_result,
                document_path=docx_path,
                output_dir=output_dir,
                temp_output_path=temp_output_path,
                base_filename=base_filename
            )

            # Neo4j insertion if requested (delegated to Neo4j service)
            neo4j_insertion_result = None
            if insert_to_neo4j and extraction_result.success:
                try:
                    # Delegate graph data creation and insertion to Neo4j service
                    graph_data = self.neo4j_service.create_graph_data_from_extraction(
                        extraction_result=extraction_result,
                        source_file=docx_path
                    )

                    # Insert using Neo4j service
                    neo4j_insertion_result = self.neo4j_service.insert_graph_data(
                        graph_data=graph_data,
                        source_file=docx_path
                    )

                    if neo4j_insertion_result.success:
                        print(f"✅ Successfully inserted into Neo4j: {neo4j_insertion_result.nodes_created} nodes, {neo4j_insertion_result.relationships_created} relationships")
                    else:
                        print(f"⚠️  Neo4j insertion failed: {neo4j_insertion_result.error or 'Unknown error'}")

                except Exception as insert_error:
                    neo4j_insertion_result = Neo4jInsertionResult(
                        success=False,
                        source_file=docx_path,
                        error=str(insert_error)
                    )

            # Extract topic information for return value
            topic_name = extraction_result.extraction.topic if extraction_result.success else Path(docx_path).stem
            sanitized_topic = topic_folder.name

            return {
                'success': True,
                'source_file': docx_path,
                'base_filename': base_filename,
                'topic_name': topic_name,
                'sanitized_topic': sanitized_topic,
                'topic_folder': str(topic_folder),
                'saved_files': saved_files,
                'extraction_result': extraction_result,
                'neo4j_insertion': neo4j_insertion_result
            }

        except Exception as e:
            print(f"❌ Error processing document: {e}")
            return {
                'success': False,
                'source_file': docx_path,
                'error': str(e)
            }




