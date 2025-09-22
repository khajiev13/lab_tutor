#!/usr/bin/env python3
"""
Canonical Relationship-Centric Processing Script

This script processes documents using the true canonical relationship-centric approach:
- CONCEPT nodes contain only canonical names (no definitions or embeddings)
- All contextual definitions are stored in MENTIONS relationship properties
- Concept names are normalized to canonical forms

Usage:
    python scripts/process_canonical_approach.py [--sample] [--output-dir OUTPUT_DIR] [--ingest]
"""

import sys
import argparse
from pathlib import Path
import json
from typing import List, Dict, Any
import time

# Add the parent directory to the path so we can import our services
sys.path.append(str(Path(__file__).parent.parent))

from services.ingestion import IngestionService
from services.neo4j_service import Neo4jService


def find_sample_docx_files(base_dir: Path, limit: int = 3) -> List[Path]:
    """Find a few sample DOCX files for testing."""
    docx_files = []
    
    # Look for DOCX files
    search_patterns = [
        "unstructured_script/**/*.docx"
    ]
    
    for pattern in search_patterns:
        docx_files.extend(base_dir.glob(pattern))
    
    # Filter out template files
    filtered_files = []
    for file_path in docx_files:
        if (not str(file_path).endswith('default.docx') and 
            '.venv' not in str(file_path) and
            'template' not in str(file_path).lower()):
            filtered_files.append(file_path)
    
    # Return first few files for sample processing
    return sorted(filtered_files)[:limit]


def find_all_docx_files(base_dir: Path) -> List[Path]:
    """Find all DOCX files for full processing."""
    docx_files = []
    
    search_patterns = [
        "unstructured_script/**/*.docx"
    ]
    
    for pattern in search_patterns:
        docx_files.extend(base_dir.glob(pattern))
    
    # Filter out template files
    filtered_files = []
    for file_path in docx_files:
        if (not str(file_path).endswith('default.docx') and 
            '.venv' not in str(file_path) and
            'template' not in str(file_path).lower()):
            filtered_files.append(file_path)
    
    return sorted(filtered_files)


def process_files_canonical(files: List[Path], output_dir: Path, ingestion_service: IngestionService) -> Dict[str, Any]:
    """Process files using the canonical relationship-centric approach."""
    
    results = {
        'successful': 0,
        'failed': 0,
        'neo4j_files': [],
        'errors': []
    }
    
    print(f"🔄 Processing {len(files)} files with canonical approach...")
    start_time = time.time()
    
    for i, file_path in enumerate(files, 1):
        rel_path = file_path.relative_to(Path('.'))
        print(f"\n📄 Processing {i}/{len(files)}: {rel_path}")
        
        try:
            # Process the DOCX file
            result = ingestion_service.process_document_with_langextract(
                str(file_path),
                str(output_dir),
                insert_to_neo4j=False  # We'll handle ingestion separately
            )
            
            if result['success']:
                results['successful'] += 1
                neo4j_file = result['saved_files']['neo4j_json']
                results['neo4j_files'].append(neo4j_file)
                print(f"   ✅ Success - Neo4j file: {Path(neo4j_file).name}")
                
                # Show canonical concepts created
                with open(neo4j_file, 'r') as f:
                    data = json.load(f)
                
                concept_nodes = [n for n in data.get('nodes', []) if n.get('label') == 'CONCEPT']
                mentions_rels = [r for r in data.get('relationships', []) if r.get('relationship_type') == 'MENTIONS']
                
                print(f"   📊 Created {len(concept_nodes)} canonical concepts, {len(mentions_rels)} contextual definitions")
                
                # Show sample canonical concepts
                if concept_nodes:
                    print(f"   🎯 Sample canonical concepts:")
                    for concept in concept_nodes[:3]:
                        name = concept.get('properties', {}).get('name', 'Unknown')
                        print(f"      • {name}")
                
            else:
                results['failed'] += 1
                error_msg = result.get('error', 'Unknown error')
                results['errors'].append(f"{rel_path}: {error_msg}")
                print(f"   ❌ Failed: {error_msg}")
                
        except Exception as e:
            results['failed'] += 1
            results['errors'].append(f"{rel_path}: {str(e)}")
            print(f"   ❌ Error: {e}")
        
        # Show progress
        elapsed = time.time() - start_time
        if i > 0:
            avg_time = elapsed / i
            remaining = (len(files) - i) * avg_time
            print(f"   ⏱️  Progress: {i}/{len(files)} | "
                  f"Elapsed: {elapsed/60:.1f}m | "
                  f"ETA: {remaining/60:.1f}m")
    
    total_time = time.time() - start_time
    results['total_time'] = total_time
    
    return results


def ingest_to_neo4j(neo4j_files: List[str], neo4j_service: Neo4jService, clear_db: bool = False) -> Dict[str, Any]:
    """Ingest processed files to Neo4j."""
    
    if clear_db:
        print("🗑️  Clearing database...")
        neo4j_service.clear_database()
        print("🔧 Setting up constraints and indexes...")
        neo4j_service.create_constraints_and_indexes()
    
    print(f"🔄 Ingesting {len(neo4j_files)} files to Neo4j...")
    
    successful = 0
    failed = 0
    
    for i, neo4j_file in enumerate(neo4j_files, 1):
        file_name = Path(neo4j_file).name
        print(f"📄 Ingesting {i}/{len(neo4j_files)}: {file_name}")
        
        try:
            result = neo4j_service.process_topic_json_file(neo4j_file)
            if result:
                successful += 1
                print(f"   ✅ Success")
            else:
                failed += 1
                print(f"   ❌ Failed")
        except Exception as e:
            failed += 1
            print(f"   ❌ Error: {e}")
    
    return {
        'successful': successful,
        'failed': failed,
        'total': len(neo4j_files)
    }


def analyze_canonical_structure(neo4j_service: Neo4jService):
    """Analyze the canonical structure in the database."""
    
    print("\n🔍 Analyzing Canonical Structure")
    print("=" * 50)
    
    # Get database stats
    stats = neo4j_service.get_database_stats()
    print("📊 Database Statistics:")
    for key, value in stats.items():
        print(f"   • {key}: {value}")
    
    # Check canonical concepts (should have no definition property)
    canonical_concepts = neo4j_service.query("""
        MATCH (c:CONCEPT)
        WHERE NOT exists(c.definition)
        RETURN c.name, c.total_mentions, c.created_at
        ORDER BY c.total_mentions DESC
        LIMIT 5
    """)
    
    print(f"\n🎯 Top Canonical Concepts (no definitions stored):")
    for concept in canonical_concepts:
        print(f"   • {concept['c.name']} (mentioned {concept['c.total_mentions']} times)")
    
    # Check contextual definitions in relationships
    contextual_defs = neo4j_service.query("""
        MATCH (t:THEORY)-[r:MENTIONS]->(c:CONCEPT)
        WHERE exists(r.local_definition)
        RETURN c.name, r.local_definition, r.source_file
        ORDER BY c.name
        LIMIT 5
    """)
    
    print(f"\n📋 Sample Contextual Definitions (stored in relationships):")
    for def_info in contextual_defs:
        print(f"   • {def_info['c.name']}:")
        print(f"     Definition: {def_info['r.local_definition'][:80]}...")
        print(f"     Source: {def_info['r.source_file']}")
        print()
    
    # Check for concept normalization effectiveness
    concept_variations = neo4j_service.query("""
        MATCH (c:CONCEPT)
        RETURN c.name
        ORDER BY c.name
    """)
    
    print(f"📝 All Canonical Concept Names:")
    for concept in concept_variations[:10]:
        print(f"   • {concept['c.name']}")
    if len(concept_variations) > 10:
        print(f"   • ... and {len(concept_variations) - 10} more")


def main():
    """Main processing function."""
    
    parser = argparse.ArgumentParser(description='Process documents with canonical relationship-centric approach')
    parser.add_argument('--sample', action='store_true', 
                       help='Process only 3 sample files for testing')
    parser.add_argument('--output-dir', type=str, default='production_output_canonical',
                       help='Output directory for processed files (default: production_output_canonical)')
    parser.add_argument('--ingest', action='store_true',
                       help='Automatically ingest to Neo4j after processing')
    parser.add_argument('--clear-db', action='store_true',
                       help='Clear database before ingestion (only with --ingest)')
    
    args = parser.parse_args()
    
    print("🎯 Canonical Relationship-Centric Processing")
    print("=" * 60)
    
    try:
        # Initialize services
        ingestion_service = IngestionService()
        print("✅ Ingestion service initialized")
        
        if args.ingest:
            neo4j_service = Neo4jService()
            print("✅ Neo4j service initialized")
        
        # Find files to process
        if args.sample:
            files = find_sample_docx_files(Path('.'), limit=3)
            print(f"📁 Found {len(files)} sample files for testing")
        else:
            files = find_all_docx_files(Path('.'))
            print(f"📁 Found {len(files)} files for processing")
        
        if not files:
            print("❌ No DOCX files found")
            return 1
        
        # Create output directory
        output_dir = Path(args.output_dir)
        output_dir.mkdir(exist_ok=True)
        print(f"📁 Output directory: {output_dir.absolute()}")
        
        # Process files
        results = process_files_canonical(files, output_dir, ingestion_service)
        
        print(f"\n📊 Processing Results:")
        print(f"   ✅ Successful: {results['successful']}")
        print(f"   ❌ Failed: {results['failed']}")
        print(f"   ⏱️  Total time: {results['total_time']/60:.1f} minutes")
        
        if results['errors']:
            print(f"\n❌ Errors:")
            for error in results['errors'][:5]:
                print(f"   • {error}")
        
        # Ingest to Neo4j if requested
        if args.ingest and results['neo4j_files']:
            print(f"\n🔄 Ingesting to Neo4j...")
            ingest_results = ingest_to_neo4j(results['neo4j_files'], neo4j_service, args.clear_db)
            
            print(f"📊 Ingestion Results:")
            print(f"   ✅ Successful: {ingest_results['successful']}")
            print(f"   ❌ Failed: {ingest_results['failed']}")
            
            # Analyze the canonical structure
            if ingest_results['successful'] > 0:
                analyze_canonical_structure(neo4j_service)
        
        print(f"\n🎉 Canonical processing completed!")
        print(f"📁 Results saved in: {output_dir}")
        
        return 0 if results['failed'] == 0 else 1
        
    except Exception as e:
        print(f"❌ Error during processing: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
