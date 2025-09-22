#!/usr/bin/env python3
"""
Bulk Ingestion Script for Existing Neo4j-ready JSON Files

This script ingests all existing Neo4j-ready JSON files from the production_output directory
using the simplified relationship-centric approach.

Usage:
    python scripts/bulk_ingest_existing_files.py [--dry-run] [--clear-db]
    
Options:
    --dry-run    : Show what would be processed without actually ingesting
    --clear-db   : Clear the database before ingestion (default: False)
"""

import sys
import argparse
from pathlib import Path
import json
from typing import List, Dict, Any

# Add the parent directory to the path so we can import our services
sys.path.append(str(Path(__file__).parent.parent))

from services.neo4j_service import Neo4jService


def find_neo4j_files(base_dir: Path) -> List[Path]:
    """Find all Neo4j-ready JSON files in the directory structure."""
    neo4j_files = list(base_dir.glob("**/neo4j_ready/*_neo4j.json"))
    return sorted(neo4j_files)


def analyze_file_structure(file_path: Path) -> Dict[str, Any]:
    """Analyze the structure of a Neo4j-ready JSON file."""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # Count relationship types
        rel_types = {}
        mentions_with_props = 0
        mentions_total = 0
        
        for rel in data.get('relationships', []):
            rel_type = rel.get('relationship_type', 'UNKNOWN')
            rel_types[rel_type] = rel_types.get(rel_type, 0) + 1
            
            if rel_type == 'MENTIONS':
                mentions_total += 1
                props = rel.get('properties', {})
                if 'local_definition' in props and 'source_file' in props:
                    mentions_with_props += 1
        
        return {
            'file': file_path.name,
            'nodes': len(data.get('nodes', [])),
            'relationships': len(data.get('relationships', [])),
            'relationship_types': rel_types,
            'mentions_with_enhanced_props': mentions_with_props,
            'mentions_total': mentions_total,
            'has_enhanced_structure': mentions_with_props > 0
        }
    except Exception as e:
        return {
            'file': file_path.name,
            'error': str(e)
        }


def main():
    parser = argparse.ArgumentParser(description='Bulk ingest existing Neo4j-ready JSON files')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be processed without actually ingesting')
    parser.add_argument('--clear-db', action='store_true',
                       help='Clear the database before ingestion')
    parser.add_argument('--base-dir', type=str, default='production_output',
                       help='Base directory to search for Neo4j files (default: production_output)')
    
    args = parser.parse_args()
    
    # Find all Neo4j-ready JSON files
    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        print(f"❌ Error: Directory {base_dir} does not exist")
        return 1
    
    neo4j_files = find_neo4j_files(base_dir)
    
    if not neo4j_files:
        print(f"❌ No Neo4j-ready JSON files found in {base_dir}")
        return 1
    
    print(f"📁 Found {len(neo4j_files)} Neo4j-ready JSON files")
    print()
    
    # Analyze file structures
    print("🔍 Analyzing file structures...")
    analyses = []
    enhanced_files = []
    legacy_files = []
    
    for file_path in neo4j_files:
        analysis = analyze_file_structure(file_path)
        analyses.append(analysis)
        
        if 'error' not in analysis:
            if analysis['has_enhanced_structure']:
                enhanced_files.append(file_path)
            else:
                legacy_files.append(file_path)
    
    print(f"   ✅ Enhanced files (with relationship properties): {len(enhanced_files)}")
    print(f"   📄 Legacy files (without relationship properties): {len(legacy_files)}")
    print()
    
    if args.dry_run:
        print("🔍 DRY RUN - Files that would be processed:")
        for analysis in analyses:
            if 'error' not in analysis:
                status = "✅ Enhanced" if analysis['has_enhanced_structure'] else "📄 Legacy"
                print(f"   {status}: {analysis['file']} "
                      f"({analysis['nodes']} nodes, {analysis['relationships']} rels)")
        print()
        print("💡 Use --clear-db to clear database before ingestion")
        print("💡 Remove --dry-run to perform actual ingestion")
        return 0
    
    # Initialize Neo4j service
    try:
        neo4j_service = Neo4jService()
        print("✅ Connected to Neo4j")
    except Exception as e:
        print(f"❌ Failed to connect to Neo4j: {e}")
        return 1
    
    # Clear database if requested
    if args.clear_db:
        print("🗑️  Clearing database...")
        neo4j_service.clear_database()
        print("🔧 Setting up constraints and indexes...")
        neo4j_service.create_constraints_and_indexes()
        print("✅ Database prepared for fresh ingestion")
        print()
    
    # Process files
    print("🔄 Starting bulk ingestion...")
    successful = 0
    failed = 0
    
    for i, file_path in enumerate(neo4j_files, 1):
        print(f"📄 Processing {i}/{len(neo4j_files)}: {file_path.name}")
        
        try:
            result = neo4j_service.process_topic_json_file(str(file_path))
            if result:
                successful += 1
                print(f"   ✅ Success")
            else:
                failed += 1
                print(f"   ❌ Failed")
        except Exception as e:
            failed += 1
            print(f"   ❌ Error: {e}")
    
    print()
    print("📊 Bulk ingestion completed:")
    print(f"   ✅ Successful: {successful}")
    print(f"   ❌ Failed: {failed}")
    print(f"   📁 Total processed: {len(neo4j_files)}")
    
    # Show final database stats
    try:
        stats = neo4j_service.get_database_stats()
        print()
        print("📈 Final database statistics:")
        for key, value in stats.items():
            print(f"   • {key}: {value}")
    except Exception as e:
        print(f"❌ Could not retrieve database stats: {e}")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
