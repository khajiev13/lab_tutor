#!/usr/bin/env python3
"""
Batch processing script for knowledge graph extraction from multiple DOCX files.

This script processes all DOCX files in a directory using the LangChain-based
canonical extraction service and inserts the results into Neo4j.
"""

from services.ingestion import IngestionService
from services.neo4j_service import Neo4jService


def main():
    """Main batch processing function."""
    
    # Configuration
    INPUT_DIRECTORY = "unstructured_script/"
    OUTPUT_DIRECTORY = "batch_output/"
    CLEAR_DATABASE = True
    GENERATE_EMBEDDINGS = True
    
    print("🚀 Batch Knowledge Graph Extraction")
    print("=" * 60)
    print(f"📁 Input directory: {INPUT_DIRECTORY}")
    print(f"📁 Output directory: {OUTPUT_DIRECTORY}")
    print(f"🗑️  Clear database: {CLEAR_DATABASE}")
    print(f"🧠 Generate embeddings: {GENERATE_EMBEDDINGS}")
    print("-" * 60)
    
    # Initialize services
    neo4j_service = Neo4jService()
    
    # Test Neo4j connection
    try:
        # Simple connection test by trying to access the graph
        _ = neo4j_service.graph.query("RETURN 1 as test")
        print("✅ Connected to Neo4j at bolt://localhost:7687")
    except Exception as e:
        print(f"❌ Failed to connect to Neo4j: {e}")
        print("Please ensure Neo4j is running and accessible.")
        return
    
    # Initialize ingestion service
    ingestion_service = IngestionService(neo4j_service=neo4j_service)
    
    # Process all documents in batch
    try:
        results = ingestion_service.process_batch_documents(
            input_directory=INPUT_DIRECTORY,
            output_directory=OUTPUT_DIRECTORY,
            clear_database=CLEAR_DATABASE,
            generate_embeddings=GENERATE_EMBEDDINGS
        )
        
        # Final summary
        print(f"\n🎉 Batch processing completed!")
        print(f"📊 Results: {results['successful']}/{results['total_files']} files processed successfully")
        
        if results['failed'] > 0:
            print(f"⚠️  {results['failed']} files failed to process")
            
        print(f"⏱️  Total time: {results['processing_time']:.2f} seconds")
        print(f"🌐 Check Neo4j Browser: http://localhost:7474")
        print(f"   Username: neo4j, Password: password123")
        
    except Exception as e:
        print(f"❌ Batch processing failed: {e}")


if __name__ == "__main__":
    main()
