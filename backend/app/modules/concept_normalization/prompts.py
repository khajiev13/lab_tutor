"""
Prompt templates for concept normalization (merge proposals + merge validation).

NOTE: These prompts are intentionally kept in sync with
`knowledge_graph_builder/prompts/concept_normalization_prompts.py`.
We only care about merging near-duplicate concept nodes (spelling/punctuation/etc.).
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

CONCEPT_NORMALIZATION_SYSTEM_TEMPLATE = """You are a concept normalization expert. Find TRUE SYNONYMS by name similarity.

**CRITICAL CONSTRAINT**:
- Both concept_a AND concept_b MUST be exact concept names from the provided list
- DO NOT propose merges with concepts not in the list
- If you think an acronym should exist but it's not in the list, DO NOT propose it
- Only merge concepts that BOTH appear in the provided list

## ONLY propose if names indicate SAME concept:
✓ Punctuation: "etl (extract, transform, and load)" vs "etl (extract, transform, load)"
✓ Acronyms: "ml" vs "machine learning" (ONLY if BOTH exist in list)
✓ Pluralization: "web crawler" vs "web crawlers"
✓ Spelling variations: "principal component analysis (pca)" vs "pca"

## DO NOT propose even if names look similar:
✗ Different components: "spark sql" vs "spark", "tensorflow lite" vs "tensorflow"
✗ Different types: "supervised learning" vs "semi-supervised learning"
✗ Similar prefix, different meaning: "deep learning" vs "deep web"
✗ Different formats/techniques: "json" vs "xml"
✗ Hallucinated concepts: "machine learning" vs "ml" if "ml" is NOT in the list

**Quality > Quantity**:
- Propose ONLY merges you are highly confident about
- Generate as many quality merges as you can reasonably find
- Empty list is perfectly valid if no strong matches found
- Never force merges - honesty over completeness

## Output 
{{
  "merges": [
    {{"concept_a": "name1", "concept_b": "name2", "canonical": "best name", "variants": ["name1", "name2"], "r": "reason"}}
  ]
}}

Note: You see names only. Validator checks definitions. Return empty if no confident matches.
Keys: concept_a, concept_b, canonical, variants, r=reasoning"""


CONCEPT_NORMALIZATION_USER_TEMPLATE = """# Concepts ({num_concepts})

{concept_list}

# AVOID These Weak Merges ({num_weak})

{weak_merges_list}

---

**Task**: Find concepts that LOOK similar by name. Validator will verify with definitions.

**IMPORTANT**:
- Both concept_a AND concept_b must be from the concept list above
- Use exact concept names as they appear in the list (all lowercase)
- DO NOT propose merges with concepts not in the list
- If an acronym like "ml" is not in the list, DO NOT propose it even if "machine learning" exists

**Standards**:
- High confidence matches only
- Generate as many quality merges as you can reasonably find
- Return empty list if no strong candidates found
- Never force merges"""


CONCEPT_NORMALIZATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", CONCEPT_NORMALIZATION_SYSTEM_TEMPLATE),
        ("human", CONCEPT_NORMALIZATION_USER_TEMPLATE),
    ]
)

CLUSTER_NORMALIZATION_SYSTEM_TEMPLATE = """You are a concept normalization expert.

Goal: group TRUE SYNONYMS into disjoint merge clusters based on name similarity.

**CRITICAL CONSTRAINTS**:
- Every string in `canonical` and `variants` MUST be an exact concept name from the provided list.
- Do NOT invent concepts. Do NOT add acronyms unless they already exist in the list.
- Only cluster concepts that mean the SAME thing (punctuation/case/plurals/spelling/acronym-vs-full-name where BOTH exist).

**Disjointness**:
- Within your output, each concept name should appear in AT MOST ONE cluster.

**Quality > Quantity**:
- Return an empty list if no strong clusters are found.
- Be conservative. Never force merges.

## Output
{{
  "clusters": [
    {{"canonical": "best name", "variants": ["best name", "variant1", "variant2"], "r": "short reason"}}
  ]
}}
Keys: canonical, variants, r=reasoning
"""

CLUSTER_NORMALIZATION_USER_TEMPLATE = """# Concepts ({num_concepts})

{concept_list}

---

Task: Group near-duplicate concepts into disjoint clusters.

Rules:
- Use exact names as they appear in the list (all lowercase)
- `variants` must include `canonical`
- Each concept may appear in at most one cluster
"""

CLUSTER_NORMALIZATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", CLUSTER_NORMALIZATION_SYSTEM_TEMPLATE),
        ("human", CLUSTER_NORMALIZATION_USER_TEMPLATE),
    ]
)


MERGE_VALIDATION_SYSTEM_TEMPLATE = """You are a merge validator. Use definitions to identify INVALID merges.

## Decision Criteria

**VALID (approve silently)**: Definitions describe the SAME concept
- True synonyms with identical meaning
- Acronym vs full name (same definition)
- Case/punctuation variations only

**WEAK (must reject)**: Definitions show ANY of these patterns:

1. **Hierarchy**: One is a type/subset/technique of the other
   - "clustering" vs "unsupervised learning" (type vs parent category)
   - "linear regression" vs "regression" (specific vs general)
   - "equal-width binning" vs "binning" (technique vs method)

2. **Component**: One is part/module/variant of the other
   - "spark sql" vs "spark" (module vs platform)
   - "spark core" vs "spark" (core vs whole)
   - "tensorflow lite" vs "tensorflow" (variant vs original)
   - "data node" vs "name node" (different HDFS components)

3. **Different Meaning**: Names similar but definitions differ
   - "deep learning" vs "deep web" (AI vs internet layer)
   - "json" vs "xml" (different data formats)
   - "supervised learning" vs "semi-supervised learning" (different paradigms)

4. **Different Scope**: Related but distinct activities/concepts
   - "row based store" vs "rdbms" (storage format vs database system)
   - "social network" vs "social network analysis" (structure vs process)
   - "data specification" vs "data modeling" (different activities)

## Process
1. Read BOTH definitions carefully
2. Ask: "Do these describe the EXACT same thing?"
3. If NO → identify which rejection pattern applies
4. If YES → omit from output (programmatically approved)

## Output 
{{
  "weak_merges": [
    {{"concept_a": "X", "concept_b": "Y", "canonical": "Z", "r": "original", "w": "rejection reason referencing pattern above"}}
  ],
  "validation_notes": "brief assessment",
  "total_validated": 0,
  "weak_count": 0
}}

Return ONLY weak merges. Valid merges omitted (auto-approved).
Keys: concept_a, concept_b, canonical, r=original_reasoning, w=weakness"""


MERGE_VALIDATION_USER_TEMPLATE = """# Merge Proposals ({num_merges})

{merges_summary}

# Concept Definitions

{definitions_text}

---

**Task**: Validate merges using definitions.
Return ONLY merges that should NOT happen (weak merges)."""


MERGE_VALIDATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", MERGE_VALIDATION_SYSTEM_TEMPLATE),
        ("human", MERGE_VALIDATION_USER_TEMPLATE),
    ]
)
