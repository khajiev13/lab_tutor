#!/usr/bin/env python3
"""
Main Script for Knowledge Graph Builder
Demonstrates both main services:
1. Data Extraction from unstructured_script folder
2. Linking CONCEPT nodes with relationships
"""

import sys
import argparse
from pathlib import Path
from typing import Optional


def run_extraction(
    input_dir: str = "unstructured_script",
    output_dir: str = "batch_output",
    clear_db: bool = False,
    single_file: Optional[str] = None,
    insert_to_neo4j: bool = True,
):
    """
    SERVICE 1: Extract concepts from DOCX files.
    
    Args:
        input_dir: Directory containing DOCX files
        output_dir: Directory to save extraction results
        clear_db: Whether to clear Neo4j database before processing
        single_file: Optional path to process only a single file
    """
    print("\n" + "="*80)
    print("📚 SERVICE 1: EXTRACTING CONCEPTS FROM DOCUMENTS")
    print("="*80)
    
    from services.ingestion import IngestionService

    if clear_db and not insert_to_neo4j:
        print("\n⚠️  --clear requested but --no-ingestion is set; skipping DB clear.")

    ingestion = IngestionService()
    
    if single_file:
        print(f"\n🔍 Processing single file: {single_file}")
        result = ingestion.process_single_document(
            docx_path=single_file,
            output_dir=output_dir,
            insert_to_neo4j=insert_to_neo4j,
        )
        
        if result['success']:
            print(f"✅ Successfully extracted concepts from {single_file}")
            print(f"   Topic: {result.get('topic_name', 'Unknown')}")
            print(f"   Output: {result.get('topic_folder', 'Unknown')}")
        else:
            print(f"❌ Failed: {result.get('error', 'Unknown error')}")
            return False
    else:
        print(f"\n🔍 Processing all DOCX files in: {input_dir}")
        result = ingestion.process_batch_documents(
            input_directory=input_dir,
            output_directory=output_dir,
            clear_database=clear_db
        )
        
        print(f"\n📊 Batch Processing Results:")
        print(f"   Total files: {result['total_files']}")
        print(f"   Successful: {result['successful']}")
        print(f"   Failed: {result['failed']}")
        print(f"   Time: {result['processing_time']:.2f}s")
        
        if result['failed_files']:
            print(f"\n❌ Failed files: {', '.join(result['failed_files'])}")
    
    return True


def run_json_ingestion(
    batch_output_dir: str = "batch_output",
    clear_db: bool = False
):
    """
    SERVICE 1B: Load already-extracted JSON files into Neo4j.
    
    Args:
        batch_output_dir: Directory containing topic folders with extraction JSONs
        clear_db: Whether to clear Neo4j database before loading
    """
    import json
    from models.extraction_models import CompleteExtractionResult, CanonicalExtractionResult, ConceptExtraction, ExtractionMetadata
    
    print("\n" + "="*80)
    print("📦 SERVICE 1B: LOADING EXISTING JSON FILES INTO NEO4J")
    print("="*80)
    
    from neo4j_database import Neo4jService

    neo4j = Neo4jService()
    
    if clear_db:
        print("\n🗑️  Clearing database...")
        neo4j.clear_database()
        print("✅ Database cleared")
    
    print(f"\n🔍 Looking for topic folders in: {batch_output_dir}")
    
    # Check if directory exists
    batch_path = Path(batch_output_dir)
    if not batch_path.exists():
        print(f"❌ Error: Directory not found: {batch_output_dir}")
        return False
    
    # Find topic folders (folders with _extraction.json files)
    topic_folders = []
    for item in batch_path.iterdir():
        if item.is_dir():
            json_files = list(item.glob("*_extraction.json"))
            if json_files:
                topic_folders.append(item)
    
    if not topic_folders:
        print(f"❌ No topic folders with extraction JSONs found in {batch_output_dir}")
        return False
    
    print(f"   Found {len(topic_folders)} topic folders")
    
    # Process each topic folder
    total_success = 0
    total_failed = 0
    
    for i, topic_folder in enumerate(topic_folders, 1):
        topic_name = topic_folder.name
        json_files = list(topic_folder.glob("*_extraction.json"))
        
        print(f"\n[{i}/{len(topic_folders)}] Processing topic: {topic_name}")
        print(f"   JSON files: {len(json_files)}")
        
        for json_file in json_files:
            try:
                # Load JSON data
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Convert concepts list to ConceptExtraction objects
                concepts = [
                    ConceptExtraction(
                        name=c.get('name', ''),
                        definition=c.get('definition', ''),
                        text_evidence=c.get('text_evidence', '')
                    )
                    for c in data.get('concepts', [])
                ]
                
                # Create extraction result from JSON
                extraction = CanonicalExtractionResult(
                    topic=data.get('topic', topic_name),
                    summary=data.get('summary', ''),
                    keywords=data.get('keywords', []),
                    concepts=concepts
                )
                
                complete_result = CompleteExtractionResult(
                    extraction=extraction,
                    metadata=ExtractionMetadata(
                        source_file=str(json_file),
                        original_text_length=0,
                        processed_text_length=0,
                        model_used='pre-extracted'
                    ),
                    success=True
                )
                
                # Create graph data
                graph_data = neo4j.create_graph_data_from_extraction(
                    extraction_result=complete_result,
                    source_file=str(json_file)
                )
                
                # Insert into Neo4j
                result = neo4j.insert_graph_data(
                    graph_data=graph_data,
                    source_file=str(json_file)
                )
                
                if result.success:
                    total_success += 1
                    print(f"   ✅ {json_file.name}: {result.nodes_created} nodes, {result.relationships_created} relationships")
                else:
                    total_failed += 1
                    print(f"   ❌ {json_file.name}: {result.error}")
                    
            except Exception as e:
                total_failed += 1
                print(f"   ❌ {json_file.name}: {e}")
                import traceback
                traceback.print_exc()
    
    print(f"\n📊 JSON Ingestion Results:")
    print(f"   Total files processed: {total_success}")
    print(f"   Total files failed: {total_failed}")
    
    # Print database stats
    db_stats = neo4j.get_database_stats()
    print(f"\n📊 Database Statistics:")
    for key, value in db_stats.items():
        print(f"   {key}: {value}")
    
    return total_failed == 0


def run_relationship_detection(
    max_iterations: int = 5,
    verbose: bool = True,
    output_file: str = "final.json"
):
    """
    SERVICE 2: Detect relationships between CONCEPT nodes.
    
    Args:
        max_iterations: Maximum iterations for relationship detection
        verbose: Enable verbose logging
        output_file: Output filename for results
    """
    print("\n" + "="*80)
    print("🔗 SERVICE 2: LINKING CONCEPT NODES (RELATIONSHIP DETECTION)")
    print("="*80)
    
    # Initialize services
    from neo4j_database import Neo4jService
    from services.enhanced_langgraph_service import EnhancedRelationshipService
    from models.langgraph_state_models import WorkflowConfiguration

    neo4j = Neo4jService()
    
    # Get all concepts from database
    print("\n📊 Fetching concepts from Neo4j...")
    concepts = neo4j.get_all_concepts()
    print(f"   Found {len(concepts)} concepts in database")
    
    if len(concepts) == 0:
        print("\n⚠️  No concepts found in database!")
        print("   Please run extraction first (--extract flag)")
        return False
    
    # Configure workflow
    config = WorkflowConfiguration(
        max_iterations=max_iterations,
        verbose_logging=verbose,
        relationship_types={
            "USED_FOR": "Indicates practical application or purpose",
            "RELATED_TO": "General semantic or contextual connection",
            "IS_A": "Taxonomic relationship (subtype/supertype)",
            "PART_OF": "Component or compositional relationship"
        }
    )
    
    # Run relationship detection
    print(f"\n🚀 Starting relationship detection workflow...")
    print(f"   Max iterations: {max_iterations}")
    
    service = EnhancedRelationshipService(neo4j, config)
    relationships, output_path, workflow_stats = service.detect_relationships(
        output_file=output_file
    )
    
    # Print results
    print(f"\n✅ Workflow completed!")
    print(f"\n📊 Results Summary:")
    print(f"   Valid Relationships: {workflow_stats.get('total_valid_relationships', 0)}")
    print(f"   Concept Merges: {workflow_stats.get('total_concept_merges', 0)}")
    print(f"   Iterations Run: {workflow_stats.get('total_iterations', 0)}")
    print(f"   Processing Time: {workflow_stats.get('processing_time_seconds', 0):.2f}s")
    
    convergence = workflow_stats.get('convergence', {})
    if convergence:
        print(f"   Convergence: {convergence.get('achieved', False)}")
        print(f"   Reason: {convergence.get('reason', 'Unknown')}")
    
    # Show sample relationships
    if relationships:
        print(f"\n🔍 Sample Relationships:")
        for i, rel in enumerate(relationships[:5], 1):
            print(f"   {i}. {rel.s} --[{rel.rel}]--> {rel.t}")
            print(f"      Reasoning: {rel.r[:80]}...")
    
    print(f"\n💾 Results saved to: {output_path}")
    
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Knowledge Graph Builder - Extract concepts and build relationships",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run both services (extract + link)
  python run_extraction_and_linking.py --all
  
  # Load from existing JSON files and run relationship detection
  python run_extraction_and_linking.py --all --from-json --clear
  
  # Only extract concepts from documents
  python run_extraction_and_linking.py --extract
  
  # Only load from JSON files
  python run_extraction_and_linking.py --extract --from-json
  
  # Only detect relationships (requires concepts already in DB)
  python run_extraction_and_linking.py --link
  
  # Extract single file
  python run_extraction_and_linking.py --extract --file unstructured_script/document.docx
  
  # Clear database and re-extract everything from DOCX
  python run_extraction_and_linking.py --extract --clear
        """
    )
    
    # Service selection
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run both extraction and relationship detection"
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="Run SERVICE 1: Extract concepts from DOCX files"
    )
    parser.add_argument(
        "--link",
        action="store_true",
        help="Run SERVICE 2: Detect relationships between concepts"
    )
    
    # Extraction options
    parser.add_argument(
        "--from-json",
        action="store_true",
        help="Load from existing JSON files instead of extracting from DOCX"
    )
    parser.add_argument(
        "--input-dir",
        default="unstructured_script",
        help="Input directory with DOCX files (default: unstructured_script)"
    )
    parser.add_argument(
        "--output-dir",
        default="batch_output",
        help="Output directory for extractions (default: batch_output)"
    )
    parser.add_argument(
        "--batch-dir",
        default="batch_output",
        help="Directory containing topic folders with extraction JSONs (default: batch_output)"
    )
    parser.add_argument(
        "--file",
        help="Process single file instead of entire directory"
    )
    parser.add_argument(
        "--no-ingestion",
        "--no-neo4j",
        action="store_true",
        help="Extraction only: do NOT insert results into Neo4j"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear Neo4j database before extraction"
    )
    
    # Relationship detection options
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=5,
        help="Maximum iterations for relationship detection (default: 5)"
    )
    parser.add_argument(
        "--output-file",
        default="final.json",
        help="Output filename for relationship detection results (default: final.json)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Disable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Determine what to run
    run_extract = args.extract or args.all
    run_link = args.link or args.all
    
    if not (run_extract or run_link):
        print("❌ Error: You must specify at least one service to run")
        print("   Use --extract, --link, or --all")
        print("   Run with --help for more information")
        sys.exit(1)
    
    # Display banner
    print("\n" + "="*80)
    print("🚀 KNOWLEDGE GRAPH BUILDER")
    print("="*80)
    print("\nServices to run:")
    if run_extract:
        print("  ✓ SERVICE 1: Concept Extraction")
    if run_link:
        print("  ✓ SERVICE 2: Relationship Detection")
    
    # Run extraction or JSON loading service
    if run_extract:
        if args.from_json:
            if args.no_ingestion:
                print("❌ Error: --from-json requires Neo4j ingestion; remove --no-ingestion")
                sys.exit(1)
            # Load from existing JSONs
            success = run_json_ingestion(
                batch_output_dir=args.batch_dir,
                clear_db=args.clear
            )
        else:
            # Extract from DOCX files
            success = run_extraction(
                input_dir=args.input_dir,
                output_dir=args.output_dir,
                clear_db=args.clear,
                single_file=args.file,
                insert_to_neo4j=not args.no_ingestion,
            )
        
        if not success:
            print("\n❌ Extraction/loading failed!")
            sys.exit(1)
    
    # Run relationship detection service
    if run_link:
        success = run_relationship_detection(
            max_iterations=args.max_iterations,
            verbose=not args.quiet,
            output_file=args.output_file
        )
        if not success:
            print("\n❌ Relationship detection failed!")
            sys.exit(1)
    
    # Final summary
    print("\n" + "="*80)
    print("✅ ALL SERVICES COMPLETED SUCCESSFULLY")
    print("="*80)

    neo4j_used = run_link or (run_extract and (args.from_json or (not args.no_ingestion)))
    if neo4j_used:
        print("\n💡 Access Neo4j Browser at: http://localhost:7474")
        print("   Username: neo4j")
        print("   Password: password123")


if __name__ == "__main__":
    main()

