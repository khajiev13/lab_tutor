#!/usr/bin/env python3
"""
Bulk Re-processing Script for DOCX Files with Enhanced Relationship Structure

This script re-processes all DOCX files to generate new Neo4j-ready JSON files
with the simplified relationship-centric approach (local_definition + source_file).

Usage:
    python scripts/bulk_reprocess_docx_files.py [--dry-run] [--output-dir OUTPUT_DIR] [--ingest]
    
Options:
    --dry-run      : Show what would be processed without actually processing
    --output-dir   : Output directory for processed files (default: enhanced_output)
    --ingest       : Automatically ingest to Neo4j after processing (default: False)
    --clear-db     : Clear database before ingestion (only with --ingest)
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


def find_docx_files(base_dir: Path) -> List[Path]:
    """Find all DOCX files in the directory structure."""
    docx_files = []

    # Common locations for DOCX files
    search_patterns = [
        "**/*.docx",
        "unstructured_script/**/*.docx",
        "documents/**/*.docx",
        "input/**/*.docx"
    ]

    for pattern in search_patterns:
        docx_files.extend(base_dir.glob(pattern))

    # Filter out template files and system files
    filtered_files = []
    for file_path in docx_files:
        # Skip template files, system files, and files in .venv
        if (not str(file_path).endswith('default.docx') and
            '.venv' not in str(file_path) and
            'template' not in str(file_path).lower()):
            filtered_files.append(file_path)

    # Remove duplicates and sort
    unique_files = list(set(filtered_files))
    return sorted(unique_files)


def estimate_processing_time(num_files: int) -> str:
    """Estimate total processing time based on number of files."""
    # Rough estimate: 2-3 minutes per file (including LLM calls)
    avg_time_per_file = 150  # seconds
    total_seconds = num_files * avg_time_per_file
    
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    
    if hours > 0:
        return f"~{hours}h {minutes}m"
    else:
        return f"~{minutes}m"


def main():
    parser = argparse.ArgumentParser(description='Bulk re-process DOCX files with enhanced relationship structure')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be processed without actually processing')
    parser.add_argument('--output-dir', type=str, default='enhanced_output',
                       help='Output directory for processed files (default: enhanced_output)')
    parser.add_argument('--ingest', action='store_true',
                       help='Automatically ingest to Neo4j after processing')
    parser.add_argument('--clear-db', action='store_true',
                       help='Clear database before ingestion (only with --ingest)')
    parser.add_argument('--base-dir', type=str, default='.',
                       help='Base directory to search for DOCX files (default: current directory)')
    
    args = parser.parse_args()
    
    # Find all DOCX files
    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        print(f"❌ Error: Directory {base_dir} does not exist")
        return 1
    
    docx_files = find_docx_files(base_dir)
    
    if not docx_files:
        print(f"❌ No DOCX files found in {base_dir}")
        return 1
    
    print(f"📁 Found {len(docx_files)} DOCX files")
    print(f"⏱️  Estimated processing time: {estimate_processing_time(len(docx_files))}")
    print()
    
    if args.dry_run:
        print("🔍 DRY RUN - Files that would be processed:")
        for i, file_path in enumerate(docx_files, 1):
            rel_path = file_path.relative_to(base_dir)
            print(f"   {i:2d}. {rel_path}")
        print()
        print(f"💡 Output directory: {args.output_dir}")
        print("💡 Remove --dry-run to perform actual processing")
        if args.ingest:
            print("💡 Files would be automatically ingested to Neo4j after processing")
        return 0
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    print(f"📁 Output directory: {output_dir.absolute()}")
    print()
    
    # Initialize services
    try:
        ingestion_service = IngestionService()
        print("✅ Ingestion service initialized")
        
        if args.ingest:
            neo4j_service = Neo4jService()
            print("✅ Neo4j service initialized")
            
            if args.clear_db:
                print("🗑️  Clearing database...")
                neo4j_service.clear_database()
                print("🔧 Setting up constraints and indexes...")
                neo4j_service.create_constraints_and_indexes()
                print("✅ Database prepared for fresh ingestion")
        
    except Exception as e:
        print(f"❌ Failed to initialize services: {e}")
        return 1
    
    print()
    
    # Process files
    print("🔄 Starting bulk re-processing...")
    successful = 0
    failed = 0
    neo4j_files = []
    start_time = time.time()
    
    for i, file_path in enumerate(docx_files, 1):
        rel_path = file_path.relative_to(base_dir)
        print(f"📄 Processing {i}/{len(docx_files)}: {rel_path}")
        
        try:
            # Process the DOCX file
            result = ingestion_service.process_document_with_langextract(
                str(file_path),
                str(output_dir),
                insert_to_neo4j=False  # We'll handle ingestion separately
            )
            
            if result['success']:
                successful += 1
                neo4j_file = result['saved_files']['neo4j_json']
                neo4j_files.append(neo4j_file)
                print(f"   ✅ Success - Neo4j file: {Path(neo4j_file).name}")
                
                # Ingest to Neo4j if requested
                if args.ingest:
                    try:
                        ingest_result = neo4j_service.process_topic_json_file(neo4j_file)
                        if ingest_result:
                            print(f"   ✅ Ingested to Neo4j")
                        else:
                            print(f"   ⚠️  Processing succeeded but ingestion failed")
                    except Exception as e:
                        print(f"   ⚠️  Processing succeeded but ingestion error: {e}")
            else:
                failed += 1
                error_msg = result.get('error', 'Unknown error')
                print(f"   ❌ Failed: {error_msg}")
                
        except Exception as e:
            failed += 1
            print(f"   ❌ Error: {e}")
        
        # Show progress
        elapsed = time.time() - start_time
        avg_time = elapsed / i
        remaining = (len(docx_files) - i) * avg_time
        print(f"   ⏱️  Progress: {i}/{len(docx_files)} | "
              f"Elapsed: {elapsed/60:.1f}m | "
              f"ETA: {remaining/60:.1f}m")
        print()
    
    total_time = time.time() - start_time
    
    print("📊 Bulk re-processing completed:")
    print(f"   ✅ Successful: {successful}")
    print(f"   ❌ Failed: {failed}")
    print(f"   📁 Total processed: {len(docx_files)}")
    print(f"   ⏱️  Total time: {total_time/60:.1f} minutes")
    print(f"   📄 Neo4j files generated: {len(neo4j_files)}")
    
    if neo4j_files:
        print()
        print("📁 Generated Neo4j-ready files:")
        for neo4j_file in neo4j_files[:5]:  # Show first 5
            print(f"   • {Path(neo4j_file).name}")
        if len(neo4j_files) > 5:
            print(f"   • ... and {len(neo4j_files) - 5} more")
    
    # Show final database stats if ingestion was performed
    if args.ingest:
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
