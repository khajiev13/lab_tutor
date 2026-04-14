"""
Knowledge Graph Data Loader
============================

Loads knowledge graph structure (mappings and prerequisites) from JSON artifacts.
"""

import json
from pathlib import Path

import pandas as pd


def load_knowledge_graph(
    dataset_dir: Path,
) -> tuple[dict, dict, dict, pd.DataFrame]:
    """
    Load knowledge graph structure from JSON files on disk.

    Args:
        dataset_dir: Path to dataset directory containing a kg/ subdirectory.

    Returns:
        Tuple of (skill_concept_map, question_concept_map, question_skill_map, prerequisites_df)
    """
    kg_dir = dataset_dir / "kg"

    skill_concept = {}
    question_concept = {}
    question_skill = {}

    if (kg_dir / "skill_concept_mapping.json").exists():
        with open(kg_dir / "skill_concept_mapping.json") as f:
            skill_concept = json.load(f)

    if (kg_dir / "question_concept_mapping.json").exists():
        with open(kg_dir / "question_concept_mapping.json") as f:
            question_concept = json.load(f)

    if (kg_dir / "question_skill_mapping.json").exists():
        with open(kg_dir / "question_skill_mapping.json") as f:
            question_skill = json.load(f)

    prereq_path = dataset_dir / "prerequisites.csv"
    if prereq_path.exists() and prereq_path.stat().st_size > 1:
        prerequisites_df = pd.read_csv(prereq_path)
    else:
        prerequisites_df = pd.DataFrame(columns=["prerequisite", "dependent"])

    return skill_concept, question_concept, question_skill, prerequisites_df
