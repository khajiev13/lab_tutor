#!/usr/bin/env python3
"""
Demonstration Script for Simplified Relationship-Centric Approach

This script demonstrates the key benefits of the simplified relationship-centric approach
by ingesting a few files and showing powerful queries enabled by the enhanced structure.

Usage:
    python scripts/demo_simplified_approach.py
"""

import sys
from pathlib import Path

# Add the parent directory to the path so we can import our services
sys.path.append(str(Path(__file__).parent.parent))

from services.neo4j_service import Neo4jService
from services.ingestion import IngestionService


def clear_and_setup_database(neo4j_service):
    """Clear database and set up fresh environment."""
    print("🗑️  Clearing database...")
    neo4j_service.clear_database()
    print("🔧 Setting up constraints and indexes...")
    neo4j_service.create_constraints_and_indexes()
    print("✅ Database ready for demonstration")


def ingest_sample_files(neo4j_service, ingestion_service):
    """Ingest a few sample files to demonstrate the approach."""
    
    # Sample files to demonstrate with
    sample_files = [
        "test_simplified/External_Data_Acquisition_Using_Web_Crawlers/neo4j_ready/transcript BD 2-3 external data acquisition_neo4j.json"
    ]
    
    # Check if we have any existing enhanced files, otherwise create one
    enhanced_file = Path(sample_files[0])
    if not enhanced_file.exists():
        print("📄 Creating sample enhanced file...")
        docx_file = "unstructured_script/transcript BD 2-3 external data acquisition.docx"
        result = ingestion_service.process_document_with_langextract(
            docx_file,
            "demo_output",
            insert_to_neo4j=False
        )
        if result['success']:
            sample_files = [result['saved_files']['neo4j_json']]
            print(f"✅ Created: {Path(sample_files[0]).name}")
        else:
            print("❌ Failed to create sample file")
            return False
    
    # Ingest the files
    print(f"📄 Ingesting {len(sample_files)} sample file(s)...")
    for file_path in sample_files:
        if Path(file_path).exists():
            result = neo4j_service.process_topic_json_file(file_path)
            if result:
                print(f"   ✅ Ingested: {Path(file_path).name}")
            else:
                print(f"   ❌ Failed: {Path(file_path).name}")
        else:
            print(f"   ⚠️  File not found: {file_path}")
    
    return True


def demonstrate_queries(neo4j_service):
    """Demonstrate powerful queries enabled by the relationship-centric approach."""
    
    print("\n🔍 Demonstrating Relationship-Centric Queries")
    print("=" * 60)
    
    # Query 1: Show enhanced MENTIONS relationships
    print("\n1️⃣  Enhanced MENTIONS Relationships:")
    print("   Query: Show relationship properties for concept definitions")
    
    mentions = neo4j_service.query("""
        MATCH (t:THEORY)-[r:MENTIONS]->(c:CONCEPT)
        RETURN c.name, r.local_definition, r.source_file
        ORDER BY c.name
        LIMIT 3
    """)
    
    for mention in mentions:
        print(f"   📋 Concept: {mention['c.name']}")
        print(f"      Definition: {mention['r.local_definition'][:80]}...")
        print(f"      Source: {mention['r.source_file']}")
        print()
    
    # Query 2: Provenance tracking
    print("2️⃣  Provenance Tracking:")
    print("   Query: Find all concepts from a specific document")
    
    provenance = neo4j_service.query("""
        MATCH (t:THEORY)-[r:MENTIONS]->(c:CONCEPT)
        WHERE r.source_file CONTAINS "external data acquisition"
        RETURN c.name, r.local_definition
        ORDER BY c.name
        LIMIT 5
    """)
    
    if provenance:
        source_file = "external data acquisition document"
        print(f"   📄 Concepts from {source_file}:")
        for item in provenance:
            print(f"      • {item['c.name']}: {item['r.local_definition'][:60]}...")
    else:
        print("   📄 No provenance data found (using legacy files)")
    
    # Query 3: Concept definition comparison
    print("\n3️⃣  Concept Definition Variations:")
    print("   Query: Compare definitions of the same concept across sources")
    
    variations = neo4j_service.query("""
        MATCH (t:THEORY)-[r:MENTIONS]->(c:CONCEPT)
        WITH c.name as concept_name, collect({
            definition: r.local_definition,
            source: r.source_file
        }) as definitions
        WHERE size(definitions) > 1
        RETURN concept_name, definitions
        LIMIT 2
    """)
    
    if variations:
        for variation in variations:
            print(f"   🔄 Concept: {variation['concept_name']}")
            for i, def_info in enumerate(variation['definitions'][:2], 1):
                print(f"      Definition {i}: {def_info['definition'][:50]}...")
                print(f"      Source {i}: {def_info['source']}")
            print()
    else:
        print("   🔄 No concept variations found (need multiple sources)")
    
    # Query 4: Database statistics
    print("4️⃣  Database Statistics:")
    stats = neo4j_service.get_database_stats()
    for key, value in stats.items():
        print(f"   📊 {key}: {value}")


def show_comparison_with_legacy(neo4j_service):
    """Show the difference between enhanced and legacy approaches."""
    
    print("\n📊 Enhanced vs Legacy Approach Comparison")
    print("=" * 60)
    
    # Check for enhanced relationships
    enhanced_count = neo4j_service.query("""
        MATCH (t:THEORY)-[r:MENTIONS]->(c:CONCEPT)
        WHERE exists(r.local_definition) AND exists(r.source_file)
        RETURN count(*) as count
    """)[0]['count']
    
    # Check for legacy relationships
    legacy_count = neo4j_service.query("""
        MATCH (t:THEORY)-[r:MENTIONS]->(c:CONCEPT)
        WHERE NOT exists(r.local_definition)
        RETURN count(*) as count
    """)[0]['count']
    
    total_mentions = enhanced_count + legacy_count
    
    print(f"📈 Enhanced MENTIONS relationships: {enhanced_count}")
    print(f"📄 Legacy MENTIONS relationships: {legacy_count}")
    print(f"📊 Total MENTIONS relationships: {total_mentions}")
    
    if enhanced_count > 0:
        print(f"✅ {enhanced_count/total_mentions*100:.1f}% of relationships have enhanced properties")
        print("\n🎯 Benefits of Enhanced Relationships:")
        print("   • Complete provenance tracking")
        print("   • Context-aware queries")
        print("   • Definition comparison across sources")
        print("   • Source-specific concept retrieval")
    else:
        print("📄 All relationships are legacy format")
        print("\n💡 To see enhanced benefits, run:")
        print("   python scripts/bulk_reprocess_docx_files.py --ingest --clear-db")


def main():
    """Main demonstration function."""
    
    print("🎯 Simplified Relationship-Centric Approach Demonstration")
    print("=" * 70)
    
    try:
        # Initialize services
        neo4j_service = Neo4jService()
        ingestion_service = IngestionService()
        print("✅ Services initialized")
        
        # Set up clean environment
        clear_and_setup_database(neo4j_service)
        
        # Ingest sample files
        if ingest_sample_files(neo4j_service, ingestion_service):
            # Demonstrate queries
            demonstrate_queries(neo4j_service)
            
            # Show comparison
            show_comparison_with_legacy(neo4j_service)
        else:
            print("❌ Failed to ingest sample files")
            return 1
        
        print("\n🎉 Demonstration completed!")
        print("\n📚 Next Steps:")
        print("   • Run bulk ingestion: python scripts/bulk_ingest_existing_files.py --clear-db")
        print("   • Re-process with enhanced structure: python scripts/bulk_reprocess_docx_files.py --ingest")
        print("   • Explore with custom Cypher queries")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error during demonstration: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
