#!/usr/bin/env python3
"""
Standalone script for generating quiz questions from concepts in Neo4j.

This script generates 3 unique ABCD questions per concept based on their
definitions and text evidence, storing them as QUIZ_QUESTION nodes in Neo4j.
"""

import sys
import argparse
import json
import logging
from pathlib import Path

from neo4j_database import Neo4jService
from services.quiz_generation_service import QuizGenerationService

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def export_to_json(stats: dict, questions_data: list, output_path: str):
    """
    Export quiz generation results to JSON file.
    
    Args:
        stats: Summary statistics dictionary
        questions_data: List of question dictionaries
        output_path: Path to output JSON file
    """
    output = {
        "summary": stats,
        "questions": questions_data
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Exported results to {output_path}")


def main():
    """Main entry point for quiz generation script."""
    parser = argparse.ArgumentParser(
        description="Generate quiz questions for concepts in Neo4j database"
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of concepts to process"
    )
    
    parser.add_argument(
        "--concept",
        type=str,
        default=None,
        help="Generate questions for specific concept only"
    )
    
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Optional JSON output file path"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print("\n" + "="*80)
    print("📝 QUIZ GENERATION SERVICE")
    print("="*80)
    
    try:
        # Initialize services
        logger.info("Initializing Neo4j service...")
        neo4j_service = Neo4jService()
        
        # Ensure constraints and indexes are created
        logger.info("Setting up database constraints and indexes...")
        neo4j_service.create_constraints_and_indexes()
        
        logger.info("Initializing Quiz Generation service...")
        quiz_service = QuizGenerationService(
            neo4j_service=neo4j_service,
            verbose=args.verbose
        )
        
        questions_data = []

        # Generate questions based on arguments
        if args.concept:
            # Generate for single concept
            logger.info(f"Generating questions for concept: {args.concept}")
            result = quiz_service.generate_questions_for_single_concept(
                concept_name=args.concept
            )
            
            if result["success"]:
                print(f"\n✅ Successfully generated questions for '{args.concept}'")
                print(f"   Theories processed: {result['theories_processed']}")
                print(f"   Questions generated: {result['questions_generated']}")
                print(f"   Questions stored: {result['questions_stored']}")
            else:
                print(f"\n❌ Failed: {result.get('error', 'Unknown error')}")
                sys.exit(1)
            
            stats = result.copy()
            stats["errors"] = [] if result["success"] else [result.get("error", "Unknown error")]
            for detail in stats.get("pair_details", []):
                for question in detail.get("generated_questions", []):
                    questions_data.append({
                        "concept_name": detail["concept_name"],
                        "theory_name": detail["theory_name"],
                        "theory_id": detail["theory_id"],
                        "text_evidence_excerpt": detail["text_evidence_excerpt"],
                        **question
                    })
            
        else:
            # Generate for all concepts (with optional limit)
            logger.info(f"Generating questions for all concepts (limit: {args.limit})")
            stats = quiz_service.generate_questions_for_all_concepts(limit=args.limit)
            for detail in stats.get("pair_details", []):
                for question in detail.get("generated_questions", []):
                    questions_data.append({
                        "concept_name": detail["concept_name"],
                        "theory_name": detail["theory_name"],
                        "theory_id": detail["theory_id"],
                        "text_evidence_excerpt": detail["text_evidence_excerpt"],
                        **question
                    })
        
        # Export to JSON if requested
        if args.output_json:
            export_to_json(stats, questions_data, args.output_json)
        
        # Print summary
        print("\n" + "="*80)
        print("📊 GENERATION SUMMARY")
        print("="*80)
        if 'theories_processed' in stats:
            # Single concept mode
            print(f"Concept: {stats.get('concept_name', 'N/A')}")
            print(f"Theories processed: {stats['theories_processed']}")
        elif 'total_pairs' in stats:
            # All concepts mode
            print(f"Total theory-concept pairs: {stats['total_pairs']}")
            print(f"Pairs processed: {stats['pairs_processed']}")
        else:
            # Fallback for old format
            print(f"Total concepts: {stats.get('total_concepts', 0)}")
            print(f"Concepts processed: {stats.get('concepts_processed', 0)}")
        print(f"Questions generated: {stats['questions_generated']}")
        print(f"Questions stored: {stats['questions_stored']}")
        
        pair_details = stats.get("pair_details", [])
        if pair_details:
            print("\n🔎 Detailed per theory-concept results (showing up to 5 pairs):")
            for detail in pair_details[:5]:
                print(f" - Concept: {detail['concept_name']} | Theory: {detail['theory_name']}")
                print(f"   Existing questions: {detail['existing_questions_count']} | Generated: {detail['generated_count']} | Stored: {detail['stored_count']}")
                print(f"   Evidence excerpt: {detail['text_evidence_excerpt']}")
                for idx, question in enumerate(detail.get("generated_questions", []), 1):
                    status = "stored" if question.get("stored") else "not stored"
                    print(f"     {idx}. {question['question_text']} (Answer: {question['correct_answer']}, {status})")

            if len(pair_details) > 5:
                print(f"   ... {len(pair_details) - 5} additional theory-concept pairs omitted from console output")
        
        if stats['errors']:
            print(f"\n⚠️  Errors encountered: {len(stats['errors'])}")
            for error in stats['errors'][:5]:  # Show first 5 errors
                print(f"   - {error}")
            if len(stats['errors']) > 5:
                print(f"   ... and {len(stats['errors']) - 5} more errors")
        
        print("\n💡 Access Neo4j Browser at: http://localhost:7474")
        print("   Query concepts: MATCH (c:CONCEPT)-[:HAS_QUESTION]->(q:QUIZ_QUESTION) RETURN c, q LIMIT 25")
        print("   Query documents: MATCH (t:TEACHER_UPLOADED_DOCUMENT)-[:HAS_QUESTION]->(q:QUIZ_QUESTION) RETURN t, q LIMIT 25")
        print("   Query both: MATCH (c:CONCEPT)-[:HAS_QUESTION]->(q:QUIZ_QUESTION)<-[:HAS_QUESTION]-(t:TEACHER_UPLOADED_DOCUMENT) RETURN c, q, t LIMIT 25")
        print("="*80)
        
    except Exception as e:
        logger.error(f"Quiz generation failed: {e}", exc_info=True)
        print(f"\n❌ Quiz generation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

