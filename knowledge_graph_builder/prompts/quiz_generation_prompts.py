"""
Prompt templates for quiz question generation.

This module contains prompt templates for generating unique ABCD quiz questions
based on concept definitions and text evidence.
"""

QUIZ_GENERATION_SYSTEM_PROMPT = """You are an expert at creating educational quiz questions that test deep understanding of technical concepts.

**Task**: Generate a single, high-quality multiple-choice question (ABCD format) based on the provided concept information.

**Requirements**:
1. The question must test understanding of the concept, not just recall
2. The correct answer must be directly supported by the text_evidence provided
3. Distractor options (incorrect answers) should be plausible but clearly wrong
4. The question should be clear, concise, and unambiguous
5. All options should be roughly the same length
6. Avoid trivial questions that can be answered without understanding

**Uniqueness Requirement**:
- If existing questions are provided, ensure your question is completely different
- Use different wording, different question angles, and different multiple choice options
- Do not repeat similar question structures or answer patterns

**Output Format**:
You must return a valid JSON object with the following structure:
- question_text: A clear, well-formulated question (string)
- option_a: The text for option A (string)
- option_b: The text for option B (string)
- option_c: The text for option C (string)
- option_d: The text for option D (string)
- correct_answer: One of "A", "B", "C", or "D" that matches the text_evidence (literal string)

**CRITICAL**: Return ONLY valid JSON. No markdown code fences, no additional text, just the JSON object.
"""

QUIZ_GENERATION_PROMPT = """Generate a unique multiple-choice question based on the following concept information.

**Concept Name**: {concept_name}

**Definition**: {definition}

**Text Evidence**: {text_evidence}

{further_instructions}

Generate ONE question that tests understanding of this concept. The correct answer must be directly supported by the text evidence provided above.

{existing_questions_section}

**IMPORTANT**: Return your response as a valid JSON object matching the required schema. Do not wrap it in markdown code blocks or add any explanatory text. Return ONLY the JSON object.
"""

def format_existing_questions(existing_questions: list) -> str:
    """
    Format existing questions for inclusion in the prompt.
    
    Args:
        existing_questions: List of question text strings
        
    Returns:
        Formatted string to append to prompt
    """
    if not existing_questions:
        return ""
    
    questions_text = "\n".join([
        f"{i+1}. {q}" for i, q in enumerate(existing_questions)
    ])
    
    return f"""
**IMPORTANT - Existing Questions for This Concept**:
The following questions have already been generated for this concept. Your new question MUST be completely different in:
- Question wording and structure
- Question angle/perspective
- Multiple choice options
- Answer patterns

Existing questions:
{questions_text}

Ensure your new question is unique and does not overlap with any of the above questions.
"""

