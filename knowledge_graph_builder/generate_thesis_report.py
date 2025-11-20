#!/usr/bin/env python3
"""
Thesis Report Generation Script for Quiz Question Dataset

This script generates a comprehensive markdown report documenting:
1. Graph-anchored question dataset properties
2. Generation statistics and coverage
3. Qualitative properties of generated questions
4. System capabilities for pre-assessment and personalization
"""

import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

from neo4j_database import Neo4jService
from services.quiz_generation_service import QuizGenerationService

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def format_question_for_report(question: Dict[str, Any], include_evidence: bool = True) -> str:
    """Format a question dictionary for markdown report."""
    lines = [
        f"**Question:** {question['question_text']}",
        f"- **A:** {question['option_a']}",
        f"- **B:** {question['option_b']}",
        f"- **C:** {question['option_c']}",
        f"- **D:** {question['option_d']}",
        f"- **Correct Answer:** {question['correct_answer']}",
        f"- **Concept:** {question['concept_name']}",
        f"- **Theory:** {question['theory_name']}"
    ]
    
    if include_evidence and question.get('text_evidence_excerpt'):
        lines.append(f"- **Text Evidence Excerpt:** {question['text_evidence_excerpt']}")
    
    return "\n".join(lines)


def generate_report(
    generation_stats: Dict[str, Any],
    neo4j_stats: Dict[str, Any],
    sample_questions: List[Dict[str, Any]]
) -> str:
    """
    Generate comprehensive markdown report.
    
    Args:
        generation_stats: Statistics from quiz generation process
        neo4j_stats: Statistics queried from Neo4j
        sample_questions: Sample questions with full context
        
    Returns:
        Markdown report as string
    """
    report_lines = []
    
    # Header
    report_lines.extend([
        "# Quiz Generation Dataset Report",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        ""
    ])
    
    # Executive Summary
    report_lines.extend([
        "## Executive Summary",
        "",
        f"This report documents the generation of a graph-anchored quiz question dataset "
        f"for pre-assessment purposes. The system generated **{generation_stats.get('questions_generated', 0)} questions** "
        f"from **{generation_stats.get('total_pairs', 0)} theory-concept pairs**, covering "
        f"**{generation_stats.get('unique_concepts', 0)} unique concepts** across "
        f"**{neo4j_stats.get('unique_theories_with_questions', 0)} theories**.",
        "",
        "### Key Metrics",
        "",
        f"- **Total Questions Generated:** {generation_stats.get('questions_generated', 0)}",
        f"- **Total Questions Stored:** {generation_stats.get('questions_stored', 0)}",
        f"- **Storage Success Rate:** {(generation_stats.get('questions_stored', 0) / max(generation_stats.get('questions_generated', 1), 1) * 100):.1f}%",
        f"- **Unique Concepts Covered:** {generation_stats.get('unique_concepts', 0)}",
        f"- **Theory-Concept Pairs Processed:** {generation_stats.get('pairs_processed', 0)}",
        f"- **Concepts with Multiple Theories:** {len(generation_stats.get('multi_theory_concepts', []))}",
        f"- **Average Questions per Concept:** {(generation_stats.get('questions_generated', 0) / max(generation_stats.get('unique_concepts', 1), 1)):.2f}",
        "",
        "---",
        ""
    ])
    
    # Graph-Anchored Question Dataset Properties
    report_lines.extend([
        "## 1. Graph-Anchored Question Dataset Properties",
        "",
        "### Dataset Structure",
        "",
        "The quiz questions are stored as `QUIZ_QUESTION` nodes in Neo4j, with explicit "
        "relationships to both `CONCEPT` and `THEORY` nodes. This dual-anchoring enables "
        "traceability and supports personalized question selection based on learning context.",
        "",
        "### Graph Connectivity",
        "",
        f"- **Total Questions in Database:** {neo4j_stats.get('total_questions', 0)}",
        f"- **Questions Linked to CONCEPT Nodes:** {neo4j_stats.get('questions_linked_to_concepts', 0)}",
        f"- **Questions Linked to THEORY Nodes:** {neo4j_stats.get('questions_linked_to_theories', 0)}",
        f"- **Fully Linked Questions (CONCEPT ↔ QUIZ_QUESTION ↔ THEORY):** {neo4j_stats.get('fully_linked_questions', 0)}",
        f"- **Questions with Text Evidence:** {neo4j_stats.get('questions_with_text_evidence', 0)}",
        f"- **Unique Concepts with Questions:** {neo4j_stats.get('unique_concepts_with_questions', 0)}",
        f"- **Unique Theories with Questions:** {neo4j_stats.get('unique_theories_with_questions', 0)}",
        "",
        "### Graph Structure Description",
        "",
        "The knowledge graph structure follows this pattern:",
        "",
        "```",
        "CONCEPT --[HAS_QUESTION]--> QUIZ_QUESTION <--[HAS_QUESTION]-- THEORY",
        "```",
        "",
        "Each `QUIZ_QUESTION` node contains:",
        "- `question_text`: The question prompt",
        "- `option_a`, `option_b`, `option_c`, `option_d`: Multiple choice options",
        "- `correct_answer`: The correct option (A, B, C, or D)",
        "- `concept_name`: Name of the associated concept",
        "- `theory_name`: Name of the associated theory",
        "- `theory_id`: Unique identifier of the theory",
        "- `text_evidence`: Source text excerpt used for question generation",
        "",
        "This structure enables:",
        "1. **Traceability:** Questions can be traced back to their source theory and concept",
        "2. **Personalization:** Questions can be filtered by concept or theory for adaptive learning",
        "3. **Explainability:** Text evidence provides context for why questions were generated",
        "",
        "---",
        ""
    ])
    
    # Generation Statistics
    report_lines.extend([
        "## 2. Generation Statistics",
        "",
        "### Coverage Metrics",
        "",
        f"- **Total Theory-Concept Pairs:** {generation_stats.get('total_pairs', 0)}",
        f"- **Pairs Successfully Processed:** {generation_stats.get('pairs_processed', 0)}",
        f"- **Processing Success Rate:** {(generation_stats.get('pairs_processed', 0) / max(generation_stats.get('total_pairs', 1), 1) * 100):.1f}%",
        f"- **Questions Generated:** {generation_stats.get('questions_generated', 0)}",
        f"- **Questions Stored:** {generation_stats.get('questions_stored', 0)}",
        f"- **Storage Success Rate:** {(generation_stats.get('questions_stored', 0) / max(generation_stats.get('questions_generated', 1), 1) * 100):.1f}%",
        "",
        "### Concept Coverage",
        "",
        f"- **Unique Concepts:** {generation_stats.get('unique_concepts', 0)}",
        f"- **Concepts with Multiple Theories:** {len(generation_stats.get('multi_theory_concepts', []))}",
        "",
    ])
    
    # Multi-theory concepts
    multi_theory = generation_stats.get('multi_theory_concepts', [])
    if multi_theory:
        report_lines.extend([
            "#### Concepts with Multiple Theories",
            "",
            "The following concepts appear in multiple theories, demonstrating the system's "
            "ability to generate context-specific questions for the same concept across different "
            "theoretical frameworks:",
            "",
        ])
        
        for mtc in multi_theory[:10]:  # Show top 10
            theories_list = ", ".join([t["theory_name"] for t in mtc["theories"]])
            report_lines.append(
                f"- **{mtc['concept_name']}** ({mtc['theory_count']} theories): {theories_list}"
            )
        
        if len(multi_theory) > 10:
            report_lines.append(f"\n*... and {len(multi_theory) - 10} more concepts with multiple theories*")
        
        report_lines.append("")
    
    # Questions per concept distribution
    questions_dist = generation_stats.get('questions_per_concept_distribution', {})
    if questions_dist:
        report_lines.extend([
            "### Questions per Concept Distribution",
            "",
            "The system generates 3 questions per theory-concept pair. Concepts that appear "
            "in multiple theories will have more questions:",
            "",
        ])
        
        # Sort by question count
        sorted_concepts = sorted(questions_dist.items(), key=lambda x: x[1], reverse=True)
        report_lines.append("| Concept | Question Count |")
        report_lines.append("|---------|----------------|")
        for concept, count in sorted_concepts[:20]:  # Top 20
            report_lines.append(f"| {concept} | {count} |")
        
        if len(sorted_concepts) > 20:
            report_lines.append(f"\n*... and {len(sorted_concepts) - 20} more concepts*")
        
        report_lines.append("")
    
    # Text evidence statistics
    text_evidence_stats = generation_stats.get('text_evidence_length_stats', {})
    if text_evidence_stats:
        report_lines.extend([
            "### Text Evidence Statistics",
            "",
            "All questions are generated from text evidence extracted from source documents:",
            "",
            f"- **Average Text Evidence Length:** {text_evidence_stats.get('avg', 0):.0f} characters",
            f"- **Minimum Length:** {text_evidence_stats.get('min', 0)} characters",
            f"- **Maximum Length:** {text_evidence_stats.get('max', 0)} characters",
            "",
        ])
    
    # Timing statistics
    timing_stats = generation_stats.get('pair_timings', {})
    if timing_stats:
        report_lines.extend([
            "### Processing Performance",
            "",
            f"- **Average Time per Pair:** {timing_stats.get('avg', 0):.2f} seconds",
            f"- **Total Processing Time:** {timing_stats.get('total', 0):.1f} seconds",
            "",
        ])
    
    # Errors
    errors = generation_stats.get('errors', [])
    if errors:
        report_lines.extend([
            "### Errors Encountered",
            "",
            f"**Total Errors:** {len(errors)}",
            "",
            "Sample errors:",
            "",
        ])
        for error in errors[:5]:
            report_lines.append(f"- {error}")
        if len(errors) > 5:
            report_lines.append(f"\n*... and {len(errors) - 5} more errors*")
        report_lines.append("")
    
    report_lines.extend([
        "---",
        ""
    ])
    
    # Qualitative Properties
    report_lines.extend([
        "## 3. Qualitative Properties",
        "",
        "### Question Quality and Diversity",
        "",
        "The generated questions demonstrate several qualitative properties:",
        "",
        "1. **Text Evidence Alignment:** Questions are directly generated from source text evidence, "
        "ensuring relevance and accuracy",
        "2. **Distractor Quality:** Incorrect options are designed to be plausible but clearly "
        "distinguishable from the correct answer",
        "3. **Question Diversity:** Each theory-concept pair generates 3 unique questions, "
        "covering different facets of the concept",
        "4. **Context Preservation:** Questions maintain links to their source theory and concept, "
        "enabling explainability",
        "",
        "### Sample Questions",
        "",
        "The following sample questions demonstrate the quality and structure of the generated dataset:",
        "",
    ])
    
    # Show sample questions
    for idx, question in enumerate(sample_questions[:10], 1):  # Show first 10
        report_lines.extend([
            f"#### Sample Question {idx}",
            "",
            format_question_for_report(question, include_evidence=True),
            "",
        ])
    
    if len(sample_questions) > 10:
        report_lines.append(f"*... and {len(sample_questions) - 10} more sample questions*")
        report_lines.append("")
    
    report_lines.extend([
        "---",
        ""
    ])
    
    # System Capabilities
    report_lines.extend([
        "## 4. System Capabilities & Insights",
        "",
        "### Pre-Assessment Question Bank",
        "",
        "The generated dataset serves as a comprehensive pre-assessment question bank with the following properties:",
        "",
        "1. **Comprehensive Coverage:** Questions cover all concepts across all theories in the knowledge base",
        "2. **Scalable Generation:** The system can generate questions for new concepts as they are added to the knowledge graph",
        "3. **Quality Assurance:** Each question is validated for uniqueness and stored with full traceability",
        "",
        "### Traceability and Explainability",
        "",
        "Every question in the dataset maintains explicit links to:",
        "",
        "- **Source Concept:** The concept being assessed",
        "- **Source Theory:** The theoretical context from which the question was generated",
        "- **Text Evidence:** The specific text excerpt used for question generation",
        "",
        "This traceability enables:",
        "",
        "- **Explainability:** Students can see why a question was asked and what it assesses",
        "- **Debugging:** Incorrect questions can be traced back to their source",
        "- **Quality Control:** Questions can be reviewed in context of their source material",
        "",
        "### Personalization Potential",
        "",
        "The graph-anchored structure enables several personalization strategies:",
        "",
        "1. **Concept-Based Selection:** Questions can be filtered by specific concepts a student needs to practice",
        "2. **Theory-Based Selection:** Questions can be selected from specific theories based on learning path",
        "3. **Multi-Theory Concepts:** For concepts appearing in multiple theories, questions can be selected "
        "to show different perspectives",
        "4. **Adaptive Difficulty:** Questions can be weighted based on concept complexity or theory depth",
        "",
        "### Multi-Theory Concept Handling",
        "",
        f"The system identified **{len(multi_theory)} concepts** that appear in multiple theories. "
        "For these concepts, the system generates separate question sets for each theory-concept pair, "
        "allowing for context-specific assessment. This demonstrates the system's ability to handle "
        "concepts that have different interpretations or applications across different theoretical frameworks.",
        "",
    ])
    
    if multi_theory:
        report_lines.extend([
            "#### Example Multi-Theory Concept",
            "",
            f"**Concept:** {multi_theory[0]['concept_name']}",
            f"**Appears in {multi_theory[0]['theory_count']} theories:**",
            "",
        ])
        for theory in multi_theory[0]['theories']:
            report_lines.append(f"- {theory['theory_name']}")
        report_lines.append("")
        report_lines.append(
            "This concept receives separate question sets for each theory, ensuring that questions "
            "are contextually appropriate to the specific theoretical framework."
        )
        report_lines.append("")
    
    report_lines.extend([
        "---",
        ""
    ])
    
    # Appendix
    report_lines.extend([
        "## Appendix: Detailed Statistics",
        "",
        "### Questions per Theory Distribution",
        "",
        "| Theory | Question Count |",
        "|--------|----------------|",
    ])
    
    questions_per_theory = neo4j_stats.get('questions_per_theory', [])
    for theory_data in questions_per_theory[:30]:  # Top 30
        report_lines.append(
            f"| {theory_data['theory_name']} | {theory_data['question_count']} |"
        )
    
    if len(questions_per_theory) > 30:
        report_lines.append(f"\n*... and {len(questions_per_theory) - 30} more theories*")
    
    report_lines.extend([
        "",
        "### Neo4j Query Examples",
        "",
        "To explore the dataset in Neo4j Browser:",
        "",
        "```cypher",
        "// Get all questions for a concept",
        "MATCH (c:CONCEPT {name: 'YourConcept'})-[:HAS_QUESTION]->(q:QUIZ_QUESTION)",
        "RETURN q",
        "",
        "// Get questions from a specific theory",
        "MATCH (t:THEORY {id: 'theory_id'})-[:HAS_QUESTION]->(q:QUIZ_QUESTION)",
        "RETURN q",
        "",
        "// Get questions with full context",
        "MATCH (c:CONCEPT)-[:HAS_QUESTION]->(q:QUIZ_QUESTION)<-[:HAS_QUESTION]-(t:THEORY)",
        "RETURN c.name, q.question_text, t.name",
        "LIMIT 25",
        "```",
        "",
        "---",
        "",
        f"*Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        ""
    ])
    
    return "\n".join(report_lines)


def main():
    """Main entry point for thesis report generation."""
    print("\n" + "="*80)
    print("📊 THESIS REPORT GENERATION")
    print("="*80)
    print()
    
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
            verbose=False
        )
        
        # Step 1: Generate questions for all concepts
        print("Step 1: Generating questions for all concepts...")
        print("="*80)
        generation_stats = quiz_service.generate_questions_for_all_concepts(limit=None)
        
        if generation_stats.get('questions_generated', 0) == 0:
            print("\n⚠️  No questions were generated. Please check your database and try again.")
            sys.exit(1)
        
        print("\n✅ Question generation completed!")
        print(f"   Generated: {generation_stats.get('questions_generated', 0)} questions")
        print(f"   Stored: {generation_stats.get('questions_stored', 0)} questions")
        
        # Step 2: Query Neo4j for comprehensive statistics
        print("\nStep 2: Querying Neo4j for comprehensive statistics...")
        print("="*80)
        neo4j_stats = neo4j_service.get_quiz_statistics()
        sample_questions = neo4j_service.get_sample_questions_with_context(limit=20)
        
        print(f"✅ Retrieved statistics: {neo4j_stats.get('total_questions', 0)} total questions in database")
        print(f"   Sample questions retrieved: {len(sample_questions)}")
        
        # Step 3: Generate report
        print("\nStep 3: Generating markdown report...")
        print("="*80)
        report_content = generate_report(generation_stats, neo4j_stats, sample_questions)
        
        # Step 4: Write report to file
        output_dir = Path(__file__).parent / "output"
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / "quiz_generation_thesis_report.md"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        print(f"✅ Report generated successfully!")
        print(f"   Output: {output_path}")
        print(f"   Report length: {len(report_content)} characters")
        
        print("\n" + "="*80)
        print("📊 REPORT GENERATION COMPLETE")
        print("="*80)
        print(f"\n📄 Report saved to: {output_path}")
        print("\n💡 You can now review the report for your thesis documentation.")
        print("="*80)
        
    except Exception as e:
        logger.error(f"Report generation failed: {e}", exc_info=True)
        print(f"\n❌ Report generation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

