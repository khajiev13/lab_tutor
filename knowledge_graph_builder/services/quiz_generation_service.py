"""
Quiz Generation Service using LangChain and LLM.

This service generates unique ABCD quiz questions for concepts based on
their definitions and text evidence, storing them in Neo4j.
"""

import os
import logging
from typing import List, Dict, Any, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from models.quiz_models import QuizQuestion
from prompts.quiz_generation_prompts import (
    QUIZ_GENERATION_SYSTEM_PROMPT,
    QUIZ_GENERATION_PROMPT,
    format_existing_questions
)
from services.neo4j_service import Neo4jService

logger = logging.getLogger(__name__)


class QuizGenerationService:
    """
    Service for generating quiz questions using LLM and storing them in Neo4j.
    
    Uses LangChain's structured output to generate unique ABCD questions
    based on concept definitions and text evidence.
    """
    
    def __init__(
        self, 
        neo4j_service: Optional[Neo4jService] = None,
        model_id: str = "gpt-4o-2024-08-06",
        verbose: bool = False
    ):
        """
        Initialize the quiz generation service.
        
        Args:
            neo4j_service: Neo4jService instance (will create new if not provided)
            model_id: LLM model identifier (e.g., GPT-4o variants via XiaoCase proxy)
            verbose: Enable verbose logging
        """
        self.neo4j_service = neo4j_service or Neo4jService()
        self.model_id = model_id
        self.api_key = os.getenv("XIAO_CASE_API_KEY")
        self.api_base = os.getenv("XIAO_CASE_API_BASE", "https://api.xiaocaseai.com/v1")
        self.verbose = verbose
        
        if not self.api_key:
            raise ValueError("XIAO_CASE_API_KEY environment variable is required")
        
        # Initialize LangChain LLM via XiaoCase (OpenAI-compatible) API
        base_llm = ChatOpenAI(
            model=model_id,
            api_key=SecretStr(self.api_key),
            base_url=self.api_base,
            temperature=0.3,  # Allow some creativity for question generation
            timeout=120,
            max_completion_tokens=2048
        )
        
        # Use structured output with method selection based on model
        # For GPT-4o through proxy API, use json_mode (same as enhanced_langgraph_service)
        # This ensures compatibility with XiaoCase API and avoids parsing issues
        # 
        # NOTE: If you want to try strict JSON schema mode (response_format: {type: "json_schema", strict: true}),
        # you could experiment with not specifying a method, or check if LangChain supports passing
        # response_format directly. However, json_mode has been proven to work reliably with proxy APIs.
        if "gpt-4o" in model_id:
            # Use json_mode for GPT-4o (more compatible with proxy APIs)
            # This matches the approach in enhanced_langgraph_service.py which works in batch processing
            self.llm = base_llm.with_structured_output(QuizQuestion, method="json_mode")
            if self.verbose:
                logger.info(f"Using json_mode for GPT-4o model: {model_id}")
        else:
            # Use default function_calling for other models
            self.llm = base_llm.with_structured_output(QuizQuestion, method="function_calling")
            if self.verbose:
                logger.info(f"Using function_calling for model: {model_id}")
        
        # Create chat prompt template with system and human messages
        # No need for format instructions when using with_structured_output
        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", QUIZ_GENERATION_SYSTEM_PROMPT),
            ("human", QUIZ_GENERATION_PROMPT)
        ])
        
        # Complete chain: prompt -> LLM (with structured output)
        self.chain = self.prompt_template | self.llm
    
    def generate_single_question(
        self,
        concept_name: str,
        definition: str,
        text_evidence: str,
        existing_questions: List[str]
    ) -> QuizQuestion:
        """
        Generate a single quiz question using one LLM call.
        
        Args:
            concept_name: Name of the concept
            definition: Concept definition
            text_evidence: Source text evidence
            existing_questions: List of existing question texts for uniqueness
            
        Returns:
            QuizQuestion object with question and options
        """
        # Format existing questions section
        existing_questions_section = format_existing_questions(existing_questions)
        
        # Format prompt with concept information
        prompt_input = {
            "concept_name": concept_name,
            "definition": definition,
            "text_evidence": text_evidence,
            "further_instructions": "",
            "existing_questions_section": existing_questions_section
        }
        
        try:
            # Generate question using LangChain chain
            result = self.chain.invoke(prompt_input)
            
            # Log response type for debugging (especially important for XiaoCase API)
            result_type = type(result).__name__
            if self.verbose:
                logger.info(f"Response type: {result_type}")
                logger.info(f"Response isinstance checks - QuizQuestion: {isinstance(result, QuizQuestion)}, dict: {isinstance(result, dict)}")
                if isinstance(result, dict):
                    logger.info(f"Response dict keys: {list(result.keys())}")
                    logger.info(f"Response dict preview: {str(result)[:200]}...")
            
            # Ensure result is a QuizQuestion (with_structured_output should return Pydantic model)
            if isinstance(result, QuizQuestion):
                question = result
                if self.verbose:
                    logger.debug(f"Result is already QuizQuestion object")
            elif isinstance(result, dict):
                # Fallback: convert dict to QuizQuestion if needed
                if self.verbose:
                    logger.info(f"Converting dict to QuizQuestion: {result}")
                question = QuizQuestion(**result)
            else:
                # Unexpected type - log it
                logger.warning(f"Unexpected result type: {result_type}, value: {result}")
                question = result
            
            if self.verbose:
                logger.info(f"Final question object type: {type(question).__name__}")
                logger.info(f"Generated question for concept '{concept_name}': {question.question_text[:50]}...")
            else:
                logger.debug(f"Generated question for concept '{concept_name}': {question.question_text[:50]}...")
            
            return question
            
        except Exception as e:
            logger.error(f"Error generating question for concept '{concept_name}': {e}")
            # Enhanced error logging for debugging XiaoCase API issues
            if self.verbose:
                logger.error(f"Exception type: {type(e).__name__}")
                logger.error(f"Exception message: {str(e)}")
                if hasattr(e, 'args') and len(e.args) > 0:
                    logger.error(f"Exception args: {e.args}")
                # Try to get raw response from chain if available
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
            # Log the raw response if available for debugging
            if hasattr(e, 'args') and len(e.args) > 0:
                logger.debug(f"Parsing error details: {e.args[0]}")
            raise
    
    def generate_questions_for_concept(
        self,
        concept_name: str,
        definition: str,
        text_evidence: str,
        theory_id: str,
        existing_questions: Optional[List[str]] = None
    ) -> List[QuizQuestion]:
        """
        Generate 3 unique questions for a concept-theory pair using 3 separate LLM calls.
        
        Each call appends previously generated questions to ensure uniqueness.
        
        Args:
            concept_name: Name of the concept
            definition: Concept definition
            text_evidence: Source text evidence
            theory_id: ID of the theory this question is based on
            existing_questions: List of existing question texts (from database)
            
        Returns:
            List of 3 QuizQuestion objects
        """
        if existing_questions is None:
            existing_questions = []
        
        questions = []
        current_existing = existing_questions.copy()
        
        # Generate 3 questions sequentially, appending each to the context
        for i in range(3):
            logger.debug(f"Generating question {i+1}/3 for concept '{concept_name}' (theory: {theory_id})...")
            
            try:
                question = self.generate_single_question(
                    concept_name=concept_name,
                    definition=definition,
                    text_evidence=text_evidence,
                    existing_questions=current_existing
                )
                
                
                questions.append(question)
                # Append the new question to existing questions for next iteration
                current_existing.append(question.question_text)
                
                evidence_preview = (text_evidence or "").strip().replace("\n", " ")
                if len(evidence_preview) > 160:
                    evidence_preview = f"{evidence_preview[:160]}..."
                
                logger.debug(
                    "  -> Generated question: '%s' | correct: %s | evidence snippet: %s",
                    question.question_text,
                    question.correct_answer,
                    evidence_preview
                )
                
            except Exception as e:
                logger.error(f"Failed to generate question {i+1}/3 for '{concept_name}' (theory: {theory_id}): {e}")
                # Continue with remaining questions even if one fails
                continue
        
        if len(questions) < 3:
            logger.warning(
                f"Only generated {len(questions)}/3 questions for concept '{concept_name}' (theory: {theory_id})"
            )
        
        return questions
    
    def generate_questions_for_all_concepts(
        self,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate questions for all theory-concept pairs in the database.
        Each theory-concept pair gets its own set of questions based on its specific text_evidence.
        
        Args:
            limit: Optional limit on number of theory-concept pairs to process
            
        Returns:
            Dictionary with summary statistics
        """
        # Fetch all theory-concept pairs with evidence (not DISTINCT, so we get all pairs)
        theory_concept_pairs = self.neo4j_service.get_concepts_with_evidence(limit=limit)
        
        if not theory_concept_pairs:
            logger.warning("No theory-concept pairs found in database")
            return {
                "total_pairs": 0,
                "pairs_processed": 0,
                "questions_generated": 0,
                "questions_stored": 0,
                "errors": []
            }
        
        logger.info(f"Processing {len(theory_concept_pairs)} theory-concept pairs...")
        
        stats = {
            "total_pairs": len(theory_concept_pairs),
            "pairs_processed": 0,
            "questions_generated": 0,
            "questions_stored": 0,
            "errors": [],
            "pair_details": []
        }
        
        for i, pair_data in enumerate(theory_concept_pairs, 1):
            concept_name = pair_data["concept_name"]
            definition = pair_data["definition"]
            text_evidence = pair_data["text_evidence"]
            theory_name = pair_data["theory_name"]
            theory_id = pair_data["theory_id"]
            
            logger.info(f"[{i}/{len(theory_concept_pairs)}] Processing: '{concept_name}' from '{theory_name}'")
            
            pair_record: Optional[Dict[str, Any]] = None
            try:
                # Get existing questions for this specific concept-theory pair
                existing_questions = self.neo4j_service.get_existing_questions_for_concept_and_theory(
                    concept_name=concept_name,
                    theory_id=theory_id
                )
                
                if existing_questions:
                    logger.debug(f"  Found {len(existing_questions)} existing questions for this theory")
                
                evidence_text = (text_evidence or "").strip().replace("\n", " ")
                pair_record = {
                    "concept_name": concept_name,
                    "theory_name": theory_name,
                    "theory_id": theory_id,
                    "text_evidence_excerpt": evidence_text[:200],
                    "existing_questions_count": len(existing_questions),
                    "generated_questions": [],
                    "generated_count": 0,
                    "stored_count": 0
                }
                
                # Generate 3 new questions for this theory-concept pair
                questions = self.generate_questions_for_concept(
                    concept_name=concept_name,
                    definition=definition,
                    text_evidence=text_evidence,
                    theory_id=theory_id,
                    existing_questions=existing_questions
                )
                
                stats["questions_generated"] += len(questions)
                pair_record["generated_count"] = len(questions)
                
                # Store each question in Neo4j
                for question in questions:
                    question_entry = {
                        "question_text": question.question_text,
                        "option_a": question.option_a,
                        "option_b": question.option_b,
                        "option_c": question.option_c,
                        "option_d": question.option_d,
                        "correct_answer": question.correct_answer,
                        "stored": False
                    }

                    question_data = {
                        "question_text": question.question_text,
                        "option_a": question.option_a,
                        "option_b": question.option_b,
                        "option_c": question.option_c,
                        "option_d": question.option_d,
                        "correct_answer": question.correct_answer,
                        "theory_name": theory_name,
                        "text_evidence": text_evidence
                    }
                    
                    success = self.neo4j_service.create_quiz_question_node(
                        concept_name=concept_name,
                        theory_id=theory_id,
                        question_data=question_data
                    )
                    
                    if success:
                        stats["questions_stored"] += 1
                        pair_record["stored_count"] += 1
                        question_entry["stored"] = True
                    else:
                        stats["errors"].append(
                            f"Failed to store question for '{concept_name}' (theory: {theory_name})"
                        )
                    
                    pair_record["generated_questions"].append(question_entry)
                
                stats["pairs_processed"] += 1
                stats["pair_details"].append(pair_record)
                
            except Exception as e:
                error_msg = f"Error processing '{concept_name}' from theory '{theory_name}': {e}"
                logger.error(error_msg)
                stats["errors"].append(error_msg)
                if pair_record:
                    pair_record["error"] = str(e)
                    stats["pair_details"].append(pair_record)
                continue
        
        logger.info("\n" + "="*80)
        logger.info("Quiz Generation Summary:")
        logger.info(f"  Total theory-concept pairs: {stats['total_pairs']}")
        logger.info(f"  Pairs processed: {stats['pairs_processed']}")
        logger.info(f"  Questions generated: {stats['questions_generated']}")
        logger.info(f"  Questions stored: {stats['questions_stored']}")
        logger.info(f"  Errors: {len(stats['errors'])}")
        logger.info("="*80)
        
        return stats
    
    def generate_questions_for_single_concept(
        self,
        concept_name: str
    ) -> Dict[str, Any]:
        """
        Generate questions for a single specific concept.
        If the concept appears in multiple theories, generates questions for each theory separately.
        
        Args:
            concept_name: Name of the concept to generate questions for
            
        Returns:
            Dictionary with results
        """
        # Fetch all theory-concept pairs
        all_pairs = self.neo4j_service.get_concepts_with_evidence()
        
        # Find all pairs for this specific concept
        concept_pairs = [
            c for c in all_pairs 
            if c["concept_name"].lower() == concept_name.lower()
        ]
        
        if not concept_pairs:
            logger.error(f"Concept '{concept_name}' not found in database")
            return {
                "success": False,
                "error": f"Concept '{concept_name}' not found",
                "questions_generated": 0,
                "questions_stored": 0,
                "theories_processed": 0
            }
        
        logger.info(f"Found concept '{concept_name}' in {len(concept_pairs)} theory/theories")
        
        total_questions_generated = 0
        total_questions_stored = 0
        pair_details: List[Dict[str, Any]] = []
        
        # Generate questions for each theory-concept pair
        for pair_data in concept_pairs:
            theory_name = pair_data["theory_name"]
            theory_id = pair_data["theory_id"]
            
            logger.info(f"Processing theory: '{theory_name}'")
            
            # Get existing questions for this specific concept-theory pair
            existing_questions = self.neo4j_service.get_existing_questions_for_concept_and_theory(
                concept_name=concept_name,
                theory_id=theory_id
            )
            
            evidence_text = (pair_data["text_evidence"] or "").strip().replace("\n", " ")
            pair_record = {
                "concept_name": pair_data["concept_name"],
                "theory_name": theory_name,
                "theory_id": theory_id,
                "text_evidence_excerpt": evidence_text[:200],
                "existing_questions_count": len(existing_questions),
                "generated_questions": [],
                "generated_count": 0,
                "stored_count": 0
            }

            # Generate questions
            questions = self.generate_questions_for_concept(
                concept_name=pair_data["concept_name"],
                definition=pair_data["definition"],
                text_evidence=pair_data["text_evidence"],
                theory_id=theory_id,
                existing_questions=existing_questions
            )
            
            total_questions_generated += len(questions)
            pair_record["generated_count"] = len(questions)
            
            # Store questions
            for question in questions:
                question_entry = {
                    "question_text": question.question_text,
                    "option_a": question.option_a,
                    "option_b": question.option_b,
                    "option_c": question.option_c,
                    "option_d": question.option_d,
                    "correct_answer": question.correct_answer,
                    "stored": False
                }

                question_data = {
                    "question_text": question.question_text,
                    "option_a": question.option_a,
                    "option_b": question.option_b,
                    "option_c": question.option_c,
                    "option_d": question.option_d,
                    "correct_answer": question.correct_answer,
                    "theory_name": theory_name,
                    "text_evidence": pair_data["text_evidence"]
                }
                
                success = self.neo4j_service.create_quiz_question_node(
                    concept_name=pair_data["concept_name"],
                    theory_id=theory_id,
                    question_data=question_data
                )
                
                if success:
                    total_questions_stored += 1
                    pair_record["stored_count"] += 1
                    question_entry["stored"] = True
                
                pair_record["generated_questions"].append(question_entry)
            
            pair_details.append(pair_record)
        
        return {
            "success": True,
            "concept_name": concept_name,
            "theories_processed": len(concept_pairs),
            "questions_generated": total_questions_generated,
            "questions_stored": total_questions_stored,
            "pair_details": pair_details
        }

