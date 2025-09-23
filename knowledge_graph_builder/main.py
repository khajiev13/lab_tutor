#!/usr/bin/env python3
"""
Simple Knowledge Graph Builder - Single Document Testing

A minimal script for testing the canonical relationship-centric knowledge graph
extraction on individual DOCX documents. This script:

1. Processes one specific DOCX file using the LangChain extraction service
2. Uses the canonical relationship-centric approach
3. Saves extraction results to JSON
4. Inserts data into Neo4j database
5. Provides simple success/failure feedback

No logging - uses only code comments for documentation.
Perfect for testing and debugging individual documents.
"""

import sys
from pathlib import Path
from services.ingestion import IngestionService


def process_single_document(docx_file_path: str, output_dir: str = "test_output",
                          clear_database: bool = True, generate_embeddings: bool = True) -> bool:
    """
    Process a single DOCX document through the complete extraction pipeline.

    Args:
        docx_file_path: Path to the DOCX file to process
        output_dir: Directory to save extraction results
        clear_database: Whether to clear Neo4j database before processing
        generate_embeddings: Whether to generate embeddings for concepts

    Returns:
        True if processing succeeded, False otherwise
    """

    # Validate input file exists
    docx_path = Path(docx_file_path)
    if not docx_path.exists():
        print(f"❌ File not found: {docx_file_path}")
        return False

    if not docx_path.suffix.lower() == '.docx':
        print(f"❌ Not a DOCX file: {docx_file_path}")
        return False

    # Initialize the ingestion service
    try:
        ingestion_service = IngestionService()
    except Exception as e:
        print(f"❌ Failed to initialize ingestion service: {e}")
        return False

    # Clear database if requested
    if clear_database:
        try:
            # Clear Neo4j database
            query = "MATCH (n) DETACH DELETE n"
            ingestion_service.neo4j_service.graph.query(query)
            print("🗑️  Database cleared")
        except Exception as e:
            print(f"⚠️  Database clearing failed: {e}")

    # Process the document
    print(f"🔄 Processing: {docx_path.name}")

    try:
        # Use the canonical relationship-centric approach with LangChain
        result = ingestion_service.process_single_document(
            str(docx_path),
            output_dir,
            insert_to_neo4j=True,
            generate_embeddings=generate_embeddings
        )

        # Check if processing succeeded
        if result.get('success', False):
            topic_name = result.get('topic_name', 'Unknown Topic')
            sanitized_topic = result.get('sanitized_topic', 'unknown_topic')

            print(f"✅ Successfully processed: {docx_path.name}")
            print(f"   📋 Topic: {topic_name}")
            print(f"   📁 Output folder: {sanitized_topic}/")

            # Show saved files
            saved_files = result.get('saved_files', {})
            for file_type, file_path in saved_files.items():
                file_size = Path(file_path).stat().st_size
                print(f"   📄 {file_type}: {Path(file_path).name} ({file_size:,} bytes)")

            # Show Neo4j insertion results
            neo4j_result = result.get('neo4j_insertion')
            if neo4j_result and neo4j_result.success:
                nodes_created = neo4j_result.nodes_created
                relationships_created = neo4j_result.relationships_created
                print(f"   🗄️  Neo4j: {nodes_created} nodes, {relationships_created} relationships created")
            elif neo4j_result:
                print(f"   ⚠️  Neo4j insertion failed: {neo4j_result.error or 'Unknown error'}")

            return True

        else:
            error_msg = result.get('error', 'Unknown error')
            print(f"❌ Processing failed: {error_msg}")
            return False

    except Exception as e:
        print(f"❌ Exception during processing: {e}")
        return False


def main():
    """
    Main entry point for single document testing.

    Modify the configuration below to test different documents.
    """

    # =============================================================================
    # CONFIGURATION - Modify these settings for your testing needs
    # =============================================================================

    # Path to the DOCX file you want to test (relative to the project root)
    DOCX_FILE = "unstructured_script/4 types of NoSQL.docx"

    # Output directory for extraction results
    OUTPUT_DIR = "test_output"

    # Whether to clear the Neo4j database before processing
    CLEAR_DATABASE = True

    # Whether to generate embeddings for concepts
    GENERATE_EMBEDDINGS = True

    # =============================================================================
    # PROCESSING
    # =============================================================================

    print("🚀 Single Document Knowledge Graph Extraction")
    print("=" * 60)
    print(f"📄 Document: {DOCX_FILE}")
    print(f"📁 Output: {OUTPUT_DIR}/")
    print(f"🗑️  Clear database: {CLEAR_DATABASE}")
    print(f"🧠 Generate embeddings: {GENERATE_EMBEDDINGS}")
    print("-" * 60)

    # Process the document
    success = process_single_document(
        docx_file_path=DOCX_FILE,
        output_dir=OUTPUT_DIR,
        clear_database=CLEAR_DATABASE,
        generate_embeddings=GENERATE_EMBEDDINGS
    )

    # Final status
    print("-" * 60)
    if success:
        print("🎉 Processing completed successfully!")
        print("🌐 Check Neo4j Browser: http://localhost:7474")
        print("   Username: neo4j, Password: password123")
    else:
        print("💥 Processing failed!")

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()