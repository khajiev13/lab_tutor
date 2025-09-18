#!/usr/bin/env python3
"""
Docker-Friendly Neo4j Data Ingestion Script

A simplified version of the ingestion script designed to be run automatically
when the Docker container starts. This script will:

1. Wait for Neo4j to be ready
2. Check if data already exists in the database
3. Ingest data from production_output if the database is empty
4. Provide clear logging for Docker container monitoring

Usage:
    python docker_ingest.py
"""

import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

# Add the current directory to Python path to import services
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.neo4j_service import Neo4jService


def wait_for_neo4j(max_attempts: int = 30, delay: int = 2) -> bool:
    """
    Wait for Neo4j to be ready by attempting to connect.
    
    Args:
        max_attempts: Maximum number of connection attempts
        delay: Delay between attempts in seconds
        
    Returns:
        True if Neo4j is ready, False if timeout
    """
    print("⏳ Waiting for Neo4j to be ready...")
    
    for attempt in range(1, max_attempts + 1):
        try:
            # Try to create a Neo4j service instance
            neo4j_service = Neo4jService()
            # Try a simple query to test connection
            neo4j_service.graph.query("RETURN 1 as test")
            print(f"✅ Neo4j is ready! (attempt {attempt}/{max_attempts})")
            return True
        except Exception as e:
            print(f"⏳ Attempt {attempt}/{max_attempts}: Neo4j not ready yet ({e})")
            if attempt < max_attempts:
                time.sleep(delay)
    
    print(f"❌ Neo4j failed to become ready after {max_attempts} attempts")
    return False


def check_database_has_data(neo4j_service: Neo4jService) -> bool:
    """
    Check if the database already contains knowledge graph data.
    
    Args:
        neo4j_service: Neo4j service instance
        
    Returns:
        True if database has data, False if empty
    """
    try:
        stats = neo4j_service.get_database_stats()
        total_nodes = stats.get("Total nodes", 0)
        total_relationships = stats.get("Total relationships", 0)
        
        if total_nodes > 0 or total_relationships > 0:
            print(f"📊 Database already contains data:")
            print(f"   • Nodes: {total_nodes}")
            print(f"   • Relationships: {total_relationships}")
            return True
        else:
            print("📊 Database is empty - ready for data ingestion")
            return False
            
    except Exception as e:
        print(f"⚠️  Error checking database status: {e}")
        return False


def find_production_output_dir() -> Optional[Path]:
    """
    Find the production_output directory in the current working directory.
    
    Returns:
        Path to production_output directory or None if not found
    """
    current_dir = Path.cwd()
    production_output = current_dir / "production_output"
    
    if production_output.exists() and production_output.is_dir():
        # Check if it contains topic folders with neo4j_ready data
        topic_folders = []
        for item in production_output.iterdir():
            if item.is_dir() and (item / "neo4j_ready").exists():
                topic_folders.append(item)
        
        if topic_folders:
            print(f"📁 Found production_output directory with {len(topic_folders)} topics")
            return production_output
        else:
            print("📁 Found production_output directory but no topic folders with neo4j_ready data")
            return None
    else:
        print("📁 No production_output directory found in current working directory")
        return None


def main():
    """Main function for Docker-friendly ingestion."""
    print("🐳 Docker Neo4j Data Ingestion")
    print("=" * 40)
    print(f"📍 Working directory: {Path.cwd()}")
    print(f"🐍 Python path: {sys.executable}")
    print()
    
    # Step 1: Wait for Neo4j to be ready
    if not wait_for_neo4j():
        print("❌ Cannot proceed without Neo4j connection")
        sys.exit(1)
    
    try:
        # Step 2: Initialize Neo4j service
        print("\n🔌 Initializing Neo4j service...")
        neo4j_service = Neo4jService()
        
        # Step 3: Check if database already has data
        print("\n📊 Checking database status...")
        if check_database_has_data(neo4j_service):
            print("✅ Database already contains data - skipping ingestion")
            print("   To force re-ingestion, clear the database first")
            return
        
        # Step 4: Find production output directory
        print("\n📁 Looking for production_output directory...")
        production_output = find_production_output_dir()
        
        if not production_output:
            print("⚠️  No production_output directory found - skipping ingestion")
            print("   This is normal if no data has been extracted yet")
            return
        
        # Step 5: Run ingestion
        print(f"\n🚀 Starting data ingestion from: {production_output}")
        results = neo4j_service.ingest_all_topics(str(production_output))
        
        # Step 6: Display results
        if 'error' in results:
            print(f"❌ Ingestion failed: {results['error']}")
            sys.exit(1)
        else:
            print_simple_summary(results)
            print("\n🎉 Data ingestion completed successfully!")
            
    except KeyboardInterrupt:
        print("\n⚠️  Ingestion interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during ingestion: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def print_simple_summary(results: Dict[str, Any]):
    """
    Print a simple summary suitable for Docker logs.
    
    Args:
        results: Results dictionary from Neo4j service ingestion
    """
    print("\n" + "=" * 40)
    print("📊 INGESTION COMPLETE")
    print("=" * 40)
    
    topics_processed = len(results.get('topics_processed', []))
    topics_failed = len(results.get('topics_failed', []))
    total_files = results.get('total_files_processed', 0)
    total_nodes = results.get('total_nodes', 0)
    total_relationships = results.get('total_relationships', 0)
    
    print(f"✅ Topics processed: {topics_processed}")
    print(f"❌ Topics failed: {topics_failed}")
    print(f"📄 Files processed: {total_files}")
    print(f"🔗 Nodes created: {total_nodes}")
    print(f"↔️  Relationships created: {total_relationships}")
    
    # Show database stats
    if 'database_stats' in results:
        db_stats = results['database_stats']
        print(f"\n📈 Final database state:")
        for stat_name, count in db_stats.items():
            if stat_name != 'error' and 'Total' in stat_name:
                print(f"   • {stat_name}: {count}")


if __name__ == "__main__":
    main()
