#!/usr/bin/env python3
"""
Neo4j Data Ingestion Script

This script ingests all extracted Neo4j-ready data from the production_output directory
into the Neo4j database. It's designed to be run when setting up the Docker container
on a new machine to restore previously extracted knowledge graph data.

Usage:
    python ingest_extracted_data.py [--output-dir production_output] [--clear-db]

Arguments:
    --output-dir: Directory containing topic folders with neo4j_ready data (default: production_output)
    --clear-db: Clear the database before ingestion (default: False)
    --help: Show this help message
"""

import argparse
import sys
import os
from pathlib import Path
from typing import Dict, Any

# Add the current directory to Python path to import services
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.neo4j_service import Neo4jService


def validate_output_directory(output_dir: Path) -> bool:
    """
    Validate that the output directory exists and contains topic folders with neo4j_ready data.
    
    Args:
        output_dir: Path to the output directory
        
    Returns:
        True if valid, False otherwise
    """
    if not output_dir.exists():
        print(f"❌ Output directory does not exist: {output_dir}")
        return False
    
    if not output_dir.is_dir():
        print(f"❌ Output path is not a directory: {output_dir}")
        return False
    
    # Check for topic folders with neo4j_ready subdirectories
    topic_folders = []
    for item in output_dir.iterdir():
        if item.is_dir() and (item / "neo4j_ready").exists():
            topic_folders.append(item)
    
    if not topic_folders:
        print(f"❌ No topic folders with neo4j_ready data found in: {output_dir}")
        print("   Expected structure: {output_dir}/{topic_name}/neo4j_ready/*.json")
        return False
    
    print(f"✅ Found {len(topic_folders)} topic folders with neo4j_ready data:")
    for folder in topic_folders:
        json_files = list((folder / "neo4j_ready").glob("*.json"))
        print(f"   • {folder.name}: {len(json_files)} JSON files")
    
    return True


def main():
    """Main function to handle command line arguments and run the ingestion."""
    parser = argparse.ArgumentParser(
        description="Ingest extracted Neo4j-ready data into Neo4j database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Ingest data from default production_output directory
    python ingest_extracted_data.py
    
    # Ingest data from custom directory and clear database first
    python ingest_extracted_data.py --output-dir my_output --clear-db
    
    # Show help
    python ingest_extracted_data.py --help
        """
    )
    
    parser.add_argument(
        "--output-dir",
        type=str,
        default="production_output",
        help="Directory containing topic folders with neo4j_ready data (default: production_output)"
    )
    
    parser.add_argument(
        "--clear-db",
        action="store_true",
        help="Clear the database before ingestion (default: False)"
    )
    
    args = parser.parse_args()
    
    # Convert output directory to Path object
    output_dir = Path(args.output_dir)
    
    print("🚀 Neo4j Data Ingestion Script")
    print("=" * 50)
    print(f"📁 Output directory: {output_dir.absolute()}")
    print(f"🗑️  Clear database: {args.clear_db}")
    print()
    
    # Validate output directory
    if not validate_output_directory(output_dir):
        sys.exit(1)
    
    try:
        # Initialize Neo4j service
        print("🔌 Connecting to Neo4j database...")
        neo4j_service = Neo4jService()
        
        # Clear database if requested
        if args.clear_db:
            print("🗑️  Clearing database...")
            neo4j_service.clear_database()
        
        # Run the ingestion
        print("\n🚀 Starting data ingestion...")
        results = neo4j_service.ingest_all_topics(str(output_dir))
        
        # Display results
        if 'error' in results:
            print(f"❌ Ingestion failed: {results['error']}")
            sys.exit(1)
        else:
            print_ingestion_summary(results)
            print("\n🎉 Data ingestion completed successfully!")
            
    except KeyboardInterrupt:
        print("\n⚠️  Ingestion interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error during ingestion: {e}")
        sys.exit(1)


def print_ingestion_summary(results: Dict[str, Any]):
    """
    Print a detailed summary of the ingestion results.
    
    Args:
        results: Results dictionary from Neo4j service ingestion
    """
    print("\n" + "=" * 60)
    print("📊 INGESTION SUMMARY")
    print("=" * 60)
    
    # Overall statistics
    print(f"📁 Base directory: {results.get('base_directory', 'N/A')}")
    print(f"📋 Topics processed: {len(results.get('topics_processed', []))}")
    print(f"❌ Topics failed: {len(results.get('topics_failed', []))}")
    print(f"📄 Total files processed: {results.get('total_files_processed', 0)}")
    print(f"❌ Total files failed: {results.get('total_files_failed', 0)}")
    print(f"🔗 Total nodes created: {results.get('total_nodes', 0)}")
    print(f"↔️  Total relationships created: {results.get('total_relationships', 0)}")
    
    # Database statistics
    if 'database_stats' in results:
        print(f"\n📈 DATABASE STATISTICS:")
        db_stats = results['database_stats']
        for stat_name, count in db_stats.items():
            if stat_name != 'error':
                print(f"   • {stat_name}: {count}")
    
    # Successfully processed topics
    if results.get('topics_processed'):
        print(f"\n✅ SUCCESSFULLY PROCESSED TOPICS:")
        for topic_result in results['topics_processed']:
            topic_name = topic_result['topic_folder']
            file_count = len(topic_result['processed_files'])
            node_count = topic_result['total_nodes']
            rel_count = topic_result['total_relationships']
            print(f"   • {topic_name}")
            print(f"     - Files: {file_count}")
            print(f"     - Nodes: {node_count}")
            print(f"     - Relationships: {rel_count}")
    
    # Failed topics (if any)
    if results.get('topics_failed'):
        print(f"\n❌ FAILED TOPICS:")
        for topic_result in results['topics_failed']:
            topic_name = topic_result['topic_folder']
            failed_files = topic_result.get('failed_files', [])
            print(f"   • {topic_name}: {len(failed_files)} failed files")
            for failed_file in failed_files:
                print(f"     - {failed_file}")


if __name__ == "__main__":
    main()
