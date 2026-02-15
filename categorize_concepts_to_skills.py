"""
Script to categorize all concepts into skills using LLM and store in Neo4j.

This script:
1. Fetches all concepts from Neo4j (using MCP or direct connection)
2. Uses LLM to categorize concepts into skills
3. Creates skill nodes and CONCEPT->SKILL relationships in Neo4j
"""

import os
import json
import logging
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

# Try to use backend settings if available
try:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
    from app.core.settings import settings
    LLM_API_KEY = settings.llm_api_key
    LLM_BASE_URL = settings.llm_base_url
    LLM_MODEL = settings.llm_model
except ImportError:
    # Fallback to environment variables
    LLM_API_KEY = os.getenv("LAB_TUTOR_LLM_API_KEY") or os.getenv("XIAO_CASE_API_KEY")
    LLM_BASE_URL = os.getenv("LAB_TUTOR_LLM_BASE_URL") or os.getenv("XIAO_CASE_API_BASE", "https://api.xiaocaseai.com/v1")
    LLM_MODEL = os.getenv("LAB_TUTOR_LLM_MODEL") or os.getenv("XIAO_CASE_MODEL", "deepseek-v3.2")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


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
5. Aim for 5-15 skills total (depending on concept diversity)
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


def fetch_concepts_via_mcp() -> List[str]:
    """
    Fetch all concepts from Neo4j using MCP.
    Since we can't directly call MCP from a script, this function
    will be called by the MCP tools in the conversation.
    """
    # This will be populated by the actual MCP query
    raise NotImplementedError("This should be called via MCP tools")


def categorize_concepts_to_skills(concept_names: List[str]) -> SkillCategorizationResult:
    """Use LLM to categorize concepts into skills."""
    if not LLM_API_KEY:
        raise ValueError("LLM API key is required. Set LAB_TUTOR_LLM_API_KEY or XIAO_CASE_API_KEY")
    
    logger.info(f"Categorizing {len(concept_names)} concepts into skills...")
    
    # Format concept list
    concept_list = "\n".join([f"- {name}" for name in sorted(concept_names)])
    
    # Create LLM
    base_llm = ChatOpenAI(
        model=LLM_MODEL,
        base_url=LLM_BASE_URL,
        api_key=SecretStr(LLM_API_KEY),
        temperature=0.3,  # Low temperature for more consistent categorization
        timeout=300,
        max_completion_tokens=4096,
    )
    
    # Use structured output
    method = "json_mode" if "gpt-4o" in LLM_MODEL else "function_calling"
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
                "concept_names": skill.concept_names
            }
            for skill in result.skills
        ]
    }
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved categorization to {filename}")


def create_skills_in_neo4j(result: SkillCategorizationResult):
    """
    Create skill nodes and CONCEPT->SKILL relationships in Neo4j.
    This function returns the Cypher queries that should be executed via MCP.
    """
    queries = []
    
    # Helper function to escape single quotes for Cypher
    def escape_cypher_string(s: str) -> str:
        return s.replace("'", "\\'")
    
    # First, create all skill nodes
    for idx, skill in enumerate(result.skills, start=1):
        skill_name_escaped = escape_cypher_string(skill.skill_name)
        query = f"""
MERGE (s:SKILL {{id: {idx}, name: '{skill_name_escaped}'}})
SET s.name = '{skill_name_escaped}'
RETURN s
"""
        queries.append(("create_skill", query, {"skill_id": idx, "skill_name": skill.skill_name}))
    
    # Then, create CONCEPT->SKILL relationships
    for idx, skill in enumerate(result.skills, start=1):
        for concept_name in skill.concept_names:
            concept_name_escaped = escape_cypher_string(concept_name.lower())
            query = f"""
MATCH (c:CONCEPT {{name: '{concept_name_escaped}'}})
MATCH (s:SKILL {{id: {idx}}})
MERGE (c)-[:BELONGS_TO_SKILL]->(s)
RETURN c, s
"""
            queries.append(("link_concept_to_skill", query, {"concept_name": concept_name, "skill_name": skill.skill_name}))
    
    return queries


if __name__ == "__main__":
    # This script will be called after we fetch concepts via MCP
    print("This script will categorize concepts into skills.")
    print("Concepts should be fetched via MCP tools and passed to categorize_concepts_to_skills()")
    
    # Example usage (commented out - will be called from main execution):
    # concepts = ["pandas", "numpy", "matplotlib", "HDFS", "MapReduce"]
    # result = categorize_concepts_to_skills(concepts)
    # save_categorization_to_file(result)
    # queries = create_skills_in_neo4j(result)
