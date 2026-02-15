"""
Script to categorize all concepts into skills using LLM and store in Neo4j.

Usage:
    cd backend
    uv run python scripts/categorize_concepts_to_skills.py
"""

import json
import logging
import sys
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

# Add parent directory to path for app imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.settings import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SkillCategorization(BaseModel):
    """A single skill with its associated concepts."""
    skill_name: str = Field(description="The name of the skill (e.g., 'Data Science', 'Distributed Systems')")
    concept_names: List[str] = Field(description="List of concept names that belong to this skill")


class SkillCategorizationResult(BaseModel):
    """Complete categorization result."""
    skills: List[SkillCategorization] = Field(description="List of skills with their associated concepts")


SKILL_CATEGORIZATION_SYSTEM_PROMPT = """You are an expert at categorizing technical concepts into meaningful skills for educational purposes.

**Task**: Group the provided technical concepts into skills that represent meaningful learning objectives or competencies.

**Guidelines**:
1. Skills should represent broad, meaningful learning objectives (e.g., "Data Science", "Distributed Systems", "Machine Learning", "Database Design")
2. Each concept should be assigned to exactly one skill
3. Concepts should be grouped logically - concepts that are typically learned together or used together should be in the same skill
4. Skill names should be clear and educational (avoid overly technical or niche names)
5. Aim for 8-20 skills total (depending on concept diversity)
6. Each skill should have at least 3-5 concepts, but can have many more

**Examples**:
- Concepts: ["pandas", "numpy", "matplotlib", "data visualization"] → Skill: "Data Science"
- Concepts: ["HDFS", "MapReduce", "Spark", "distributed computing"] → Skill: "Distributed Systems"
- Concepts: ["supervised learning", "unsupervised learning", "neural networks", "deep learning"] → Skill: "Machine Learning"

**Output Format**:
Return a JSON object with a "skills" array, where each skill has:
- skill_name: The name of the skill
- concept_names: Array of concept names assigned to this skill"""

SKILL_CATEGORIZATION_PROMPT = """Categorize the following technical concepts into meaningful skills.

**Concepts ({num_concepts} total)**:
{concept_list}

**Instructions**:
- Group concepts into skills that represent meaningful learning objectives
- Each concept should appear in exactly one skill
- Use clear, educational skill names (e.g., "Data Science", "Distributed Systems")
- Ensure logical grouping of related concepts

Return your response as a JSON object matching the required schema."""


def categorize_concepts_to_skills(concept_names: List[str]) -> SkillCategorizationResult:
    """Use LLM to categorize concepts into skills."""
    if not settings.llm_api_key:
        raise ValueError("LLM API key is required. Set LAB_TUTOR_LLM_API_KEY or XIAO_CASE_API_KEY")
    
    logger.info(f"Categorizing {len(concept_names)} concepts into skills...")
    
    # Format concept list
    concept_list = "\n".join([f"- {name}" for name in sorted(concept_names)])
    
    # Create LLM
    base_llm = ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=SecretStr(settings.llm_api_key),
        temperature=0.3,  # Low temperature for more consistent categorization
        timeout=600,
        max_completion_tokens=8192,
    )
    
    # Use structured output
    method = "json_mode" if "gpt-4o" in settings.llm_model else "function_calling"
    llm = base_llm.with_structured_output(SkillCategorizationResult, method=method)
    
    # Create prompt
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", SKILL_CATEGORIZATION_SYSTEM_PROMPT),
        ("human", SKILL_CATEGORIZATION_PROMPT)
    ])
    
    chain = prompt_template | llm
    
    # Invoke
    result = chain.invoke({
        "num_concepts": len(concept_names),
        "concept_list": concept_list
    })
    
    logger.info(f"Generated {len(result.skills)} skills")
    return result


def save_categorization_to_file(result: SkillCategorizationResult, filename: str = "skill_categorization.json"):
    """Save categorization result to a JSON file."""
    data = {
        "skills": [
            {
                "skill_name": skill.skill_name,
                "concept_names": skill.concept_names,
                "concept_count": len(skill.concept_names)
            }
            for skill in result.skills
        ],
        "total_skills": len(result.skills),
        "total_concepts": sum(len(skill.concept_names) for skill in result.skills)
    }
    
    output_path = Path(__file__).parent.parent.parent / filename
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved categorization to {output_path}")


if __name__ == "__main__":
    # Load concepts from file
    concepts_file = Path(__file__).parent.parent.parent / "concepts_list.json"
    if not concepts_file.exists():
        logger.error(f"Concepts file not found at {concepts_file}")
        logger.info("Please create concepts_list.json with: {\"concepts\": [\"concept1\", \"concept2\", ...]}")
        sys.exit(1)
    
    with open(concepts_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        concepts = data.get("concepts", [])
    
    if not concepts:
        logger.error("No concepts found in concepts_list.json")
        sys.exit(1)
    
    logger.info(f"Loaded {len(concepts)} concepts from {concepts_file}")
    
    try:
        # Categorize concepts
        result = categorize_concepts_to_skills(concepts)
        
        # Save to file
        save_categorization_to_file(result)
        
        print(f"\n✅ Categorization complete!")
        print(f"   - Generated {len(result.skills)} skills")
        print(f"   - Categorized {sum(len(skill.concept_names) for skill in result.skills)} concepts")
        print(f"\nNext step: Use MCP tools to store skills in Neo4j")
        
        # Print summary
        print("\nSkills generated:")
        for skill in result.skills:
            print(f"  - {skill.skill_name}: {len(skill.concept_names)} concepts")
        
    except Exception as e:
        logger.exception(f"Error during categorization: {e}")
        sys.exit(1)
