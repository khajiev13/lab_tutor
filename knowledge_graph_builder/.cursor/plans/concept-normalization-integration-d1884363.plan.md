<!-- d1884363-9e40-4d98-bec7-bb79cc8aaefb c07f9738-8086-4437-8a82-1808531d78c7 -->
# Concept Normalization Integration Plan

## Overview

Integrate concept normalization into the existing relationship detection workflow. The generation node will make two LLM calls (find similar concepts + generate relationships), validation will check both, and convergence requires both tasks to complete. At the end, apply concept merges before inserting relationships.

---

## 1. Update State Models

**File: `models/langgraph_state_models.py`**

Add new fields to `EnhancedRelationshipState`:

```python
class ConceptMerge(BaseModel):
    """Proposed merge between two similar concepts."""
    concept_a: str = Field(description="First concept name")
    concept_b: str = Field(description="Second concept name")
    canonical: str = Field(description="Canonical name to use after merge")
    variants: List[str] = Field(description="All variant names")
    r: str = Field(description="Reasoning for merge (max 80 chars)")

class MergeValidationFeedback(BaseModel):
    """Validation feedback for concept merges."""
    weak_merges: List[WeakMerge] = Field(
        default_factory=list,
        description="Merges that should NOT happen"
    )
    validation_notes: str = Field(default="")
    total_validated: int = Field(default=0)
    weak_count: int = Field(default=0)

class WeakMerge(BaseModel):
    """A weak/incorrect merge proposal."""
    concept_a: str
    concept_b: str
    canonical: str
    r: str  # Original reasoning
    w: str  # Why it's weak

# Add to EnhancedRelationshipState TypedDict:
all_merges: Dict[Tuple[str, str], ConceptMerge]
weak_merges: Dict[Tuple[str, str], str]
new_merge_batch: List[ConceptMerge]
```

---

## 2. Create Concept Normalization Prompts

**File: `prompts/concept_normalization_prompts.py`** (new file)

```python
CONCEPT_NORMALIZATION_SYSTEM_TEMPLATE = """You are a concept normalization expert.

Find concepts with THE SAME meaning based on NAME similarity:
- Case variations: "ETL" vs "etl"
- Punctuation: "Extract, Transform, and Load" vs "Extract, Transform, load"
- Minor wording: "Machine Learning" vs "machine learning"
- Acronyms: "ML" vs "Machine Learning" (likely same)

Generate approximately 30-50 merge proposals per iteration.

## Output JSON
{{
  "merges": [
    {{"concept_a": "name1", "concept_b": "name2", "canonical": "best name", "variants": ["name1", "name2"], "r": "reason"}}
  ]
}}

**Note**: You only see names. Validator will check definitions.
Use shortened keys: concept_a, concept_b, canonical, variants, r=reasoning"""

CONCEPT_NORMALIZATION_USER_TEMPLATE = """# Concepts ({num_concepts})

{concept_list}

# AVOID These Weak Merges ({num_weak})

{weak_merges_list}

---

**Task**: Find concepts that LOOK similar by name.
Focus on obvious name variations. Validator will verify with definitions.

Return ~30-50 merge proposals."""

CONCEPT_VALIDATION_SYSTEM_TEMPLATE = """You are a merge validator with access to concept definitions.

Check if proposed merges are truly the SAME concept:
- Compare definitions semantically
- Approve if definitions mean the same thing
- Reject if definitions are different (even if names similar)

**VALID**: Same meaning in definitions
**WEAK**: Different meanings, should stay separate

## Output JSON
{{
  "weak_merges": [
    {{"concept_a": "X", "concept_b": "Y", "canonical": "Z", "r": "original", "w": "why weak"}}
  ],
  "validation_notes": "assessment",
  "total_validated": 50,
  "weak_count": 5
}}

Return ONLY weak merges. Valid ones inferred programmatically."""

CONCEPT_VALIDATION_USER_TEMPLATE = """# Merge Proposals ({num_merges})

{merges_summary}

# Concept Definitions

{definitions_text}

---

**Task**: Validate merges using definitions.
Return ONLY merges that should NOT happen (weak merges)."""
```

---

## 3. Update Generation Node

**File: `services/enhanced_langgraph_service.py`**

Modify `_generation_node` to handle both tasks:

```python
def _generation_node(self, state: EnhancedRelationshipState) -> EnhancedRelationshipState:
    iteration = state["iteration_count"]
    
    # Check what needs to be done
    merges_converged = self._check_merges_converged(state)
    relationships_converged = self._check_relationships_converged(state)
    
    if merges_converged and relationships_converged:
        # Both converged, nothing to generate
        return {**state, "new_merge_batch": [], "new_batch": []}
    
    # === LLM CALL 1: Find Similar Concepts (if not converged) ===
    new_merges = []
    if not merges_converged:
        new_merges = self._find_similar_concepts(
            concepts=state["concepts"],
            weak_merges=state["weak_merges"]
        )
        if self.config.verbose_logging:
            print(f"   🔀 Found {len(new_merges)} merge proposals")
    
    # === LLM CALL 2: Generate Relationships (if not converged) ===
    new_relationships = []
    if not relationships_converged:
        new_relationships = self._generate_relationships(
            concepts=state["concepts"],
            weak_patterns=state["weak_relationships"]
        )
        if self.config.verbose_logging:
            print(f"   🔗 Generated {len(new_relationships)} relationships")
    
    updated_state = {
        **state,
        "new_merge_batch": new_merges,
        "new_batch": new_relationships
    }
    
    self._save_iteration_state(updated_state, iteration, "generation")
    return updated_state  # type: ignore

def _find_similar_concepts(
    self,
    concepts: List[Dict],
    weak_merges: Dict
) -> List[ConceptMerge]:
    """Call LLM to find similar concepts that should be merged."""
    
    # Get all definitions from Neo4j
    concept_names = [c["name"] for c in concepts]
    definitions = self.neo4j_service.get_concept_definitions(concept_names)
    
    # Format prompt
    messages = CONCEPT_NORMALIZATION_PROMPT.format_messages(
        num_concepts=len(concepts),
        concept_list=format_concepts(concepts),
        definitions_text=format_definitions(definitions),
        num_weak=len(weak_merges),
        weak_merges_list=format_weak_merges(weak_merges)
    )
    
    # Call LLM with structured output
    batch = self.merge_chain.invoke(messages)  # type: ignore
    return batch.merges  # type: ignore

def _check_merges_converged(self, state):
    """Check if merge generation has converged."""
    # Converged if generation returned 0 merge proposals (can't find more)
    # NOT based on weak count (50 proposals with 0 weak = 50 new valid = NOT converged)
    
    if len(state["convergence_metrics"].merge_count_trend) >= 3:
        last_three = state["convergence_metrics"].merge_count_trend[-3:]
        # If generation returned 0 proposals for 3 iterations → converged
        if all(count == 0 for count in last_three):
            return True
    return False
    
def _check_relationships_converged(self, state):
    """Check if relationship generation has converged."""
    # Same logic as merge convergence
    # Based on how many NEW valid relationships added, not weak count
    
    if len(state["convergence_metrics"].valid_count_trend) >= 3:
        last_three = state["convergence_metrics"].valid_count_trend[-3:]
        if all(count == 0 for count in last_three):
            return True
    return False
```

---

## 4. Update Validation Node

**File: `services/enhanced_langgraph_service.py`**

Extend `_validation_node` to validate both merges and relationships:

```python
def _validation_node(self, state: EnhancedRelationshipState) -> EnhancedRelationshipState:
    new_merge_batch = state["new_merge_batch"]
    new_relationship_batch = state["new_batch"]
    
    # === VALIDATE MERGES ===
    if new_merge_batch:
        merge_feedback = self._validate_merges(new_merge_batch)
        
        # Process merge validation
        weak_merge_keys = set()
        for weak_merge in merge_feedback.weak_merges:
            key = (weak_merge.concept_a, weak_merge.concept_b)
            weak_merge_keys.add(key)
            state["weak_merges"][key] = weak_merge.w
        
        # Calculate valid merges
        valid_merges = [
            m for m in new_merge_batch
            if (m.concept_a, m.concept_b) not in weak_merge_keys
        ]
        
        # Add to accumulated merges (auto-deduplicate)
        for merge in valid_merges:
            key = (merge.concept_a, merge.concept_b)
            state["all_merges"][key] = merge
    
    # === VALIDATE RELATIONSHIPS (existing logic) ===
    if new_relationship_batch:
        rel_feedback = self._validate_relationships(new_relationship_batch, ...)
        # ... existing relationship validation ...
    
    # Update convergence metrics
    state["convergence_metrics"].update_merge_trends(...)
    
    self._save_iteration_state(state, state["iteration_count"], "validation")
    return updated_state  # type: ignore

def _validate_merges(
    self,
    batch: List[ConceptMerge]
) -> MergeValidationFeedback:
    """Call LLM to validate merge proposals."""
    
    # Get definitions for all concepts in batch
    concept_names = set()
    for merge in batch:
        concept_names.update([merge.concept_a, merge.concept_b])
    definitions = self.neo4j_service.get_concept_definitions(list(concept_names))
    
    # Format prompt
    messages = CONCEPT_VALIDATION_PROMPT.format_messages(
        num_merges=len(batch),
        merges_summary=format_merges(batch),
        definitions_text=format_definitions(definitions)
    )
    
    # Call LLM
    feedback = self.merge_validation_chain.invoke(messages)  # type: ignore
    return feedback  # type: ignore
```

---

## 5. Update Convergence Checker

**File: `services/enhanced_langgraph_service.py`**

Check both merge and relationship convergence:

```python
def _convergence_checker(self, state: EnhancedRelationshipState) -> str:
    iteration = state["iteration_count"]
    max_iterations = state["max_iterations"]
    
    # Check merge convergence
    merges_converged = self._check_merges_converged(state)
    
    # Check relationship convergence (existing)
    relationships_converged = self._check_relationships_converged(state)
    
    # Both must converge
    if merges_converged and relationships_converged:
        return "complete"
    
    # Max iterations reached
    if iteration >= max_iterations:
        return "complete"
    
    return "continue"
```

---

## 6. Update Database Save Logic

**File: `services/neo4j_service.py`**

Add merge functionality:

```python
def merge_concepts(
    self,
    canonical: str,
    variants: List[str]
) -> bool:
    """
    Merge multiple concept nodes into one canonical node.
    
    1. Update canonical node with all aliases
    2. Redirect all relationships to canonical node
    3. Delete variant nodes
    """
    query = """
    // Find all variant nodes
    MATCH (variant:CONCEPT)
    WHERE variant.name IN $variants AND variant.name <> $canonical
    
    // Find canonical node
    MATCH (canonical_node:CONCEPT {name: $canonical})
    
    // Copy relationships from variants to canonical
    WITH variant, canonical_node
    OPTIONAL MATCH (variant)-[r:MENTIONS]-(other)
    MERGE (canonical_node)-[new_r:MENTIONS]-(other)
    SET new_r = properties(r)
    
    // Update canonical node with aliases
    WITH canonical_node, collect(DISTINCT variant.name) AS variant_names
    SET canonical_node.aliases = COALESCE(canonical_node.aliases, []) + variant_names
    SET canonical_node.merge_count = size(canonical_node.aliases)
    
    // Delete variant nodes
    WITH variant_names
    MATCH (v:CONCEPT)
    WHERE v.name IN variant_names
    DETACH DELETE v
    
    RETURN canonical_node.name, canonical_node.aliases
    """
    
    result = self.graph.query(query, {
        "canonical": canonical,
        "variants": variants
    })
    return len(result) > 0

def apply_all_merges(self, merge_state: Dict) -> int:
    """Apply all concept merges from state."""
    merge_count = 0
    
    for merge_key, merge_info in merge_state.items():
        success = self.merge_concepts(
            canonical=merge_info.canonical,
            variants=merge_info.variants
        )
        if success:
            merge_count += 1
    
    return merge_count
```

---

## 7. Save Results to JSON (NO Database Updates Yet)

**File: `services/enhanced_langgraph_service.py`**

Save complete results for review before applying to database:

```python
def _save_results(
    self,
    relationships: List[ConceptRelationship],
    output_file: str,
    workflow_stats: Dict,
    final_state: Dict[str, Any]
) -> str:
    """Save results to JSON for review. Does NOT update database."""
    
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_file)
    
    # Convert merges to readable format
    merges_dict = [
        {
            "concept_a": merge.concept_a,
            "concept_b": merge.concept_b,
            "canonical": merge.canonical,
            "variants": merge.variants,
            "reasoning": merge.r
        }
        for merge in final_state["all_merges"].values()
    ]
    
    # Convert relationships to dicts (with original names)
    relationships_dict = [
        {"s": rel.s, "t": rel.t, "rel": rel.rel, "r": rel.r}
        for rel in relationships
    ]
    
    # Also show what relationships WOULD look like with canonical names
    canonical_preview = []
    for rel in relationships:
        canonical_s = self._map_to_canonical(rel.s, final_state["all_merges"])
        canonical_t = self._map_to_canonical(rel.t, final_state["all_merges"])
        
        canonical_preview.append({
            "original": {"s": rel.s, "t": rel.t},
            "canonical": {"s": canonical_s, "t": canonical_t},
            "rel": rel.rel,
            "r": rel.r,
            "was_mapped": (canonical_s != rel.s or canonical_t != rel.t)
        })
    
    # Prepare output data
    output_data = {
        "metadata": workflow_stats,
        "concept_merges": {
            "total": len(merges_dict),
            "merges": merges_dict,
            "weak_merges": [
                {
                    "concept_a": key[0],
                    "concept_b": key[1],
                    "reason": reason
                }
                for key, reason in final_state["weak_merges"].items()
            ]
        },
        "relationships": {
            "total": len(relationships_dict),
            "original": relationships_dict,
            "canonical_preview": canonical_preview
        }
    }
    
    # Save to file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*80}")
    print(f"📁 Results saved to: {output_path}")
    print(f"👀 REVIEW THE FILE BEFORE APPLYING TO DATABASE")
    print(f"{'='*80}")
    
    return output_path

def _map_to_canonical(
    self,
    concept_name: str,
    merge_state: Dict
) -> str:
    """Map original concept name to canonical name if merged."""
    for merge_info in merge_state.values():
        if concept_name in merge_info.variants:
            return merge_info.canonical
    return concept_name  # Not merged
```

---

## 7b. Add Database Update Script (Separate Tool)

**File: `apply_normalization.py`** (new file)

Separate script to apply changes after review:

```python
#!/usr/bin/env python3
"""
Apply concept merges and relationships to Neo4j after manual review.

Usage:
  python apply_normalization.py output/results.json
"""

import json
import sys
from services.neo4j_service import Neo4jService

def apply_results(results_file: str):
    """Apply merges and relationships from JSON to Neo4j."""
    
    # Load results
    with open(results_file, 'r') as f:
        data = json.load(f)
    
    neo4j = Neo4jService()
    
    # === STEP 1: Apply concept merges ===
    merges = data["concept_merges"]["merges"]
    print(f"🔀 Applying {len(merges)} concept merges...")
    
    for merge in merges:
        success = neo4j.merge_concepts(
            canonical=merge["canonical"],
            variants=merge["variants"]
        )
        if success:
            print(f"   ✅ Merged {merge['variants']} → {merge['canonical']}")
    
    # === STEP 2: Insert relationships (with canonical names) ===
    relationships = data["relationships"]["canonical_preview"]
    print(f"\n🔗 Inserting {len(relationships)} relationships...")
    
    for rel in relationships:
        if rel["was_mapped"]:
            print(f"   📍 Mapped: {rel['original']['s']} → {rel['canonical']['s']}")
        
        # Insert relationship
        neo4j.create_concept_relationship(
            source=rel["canonical"]["s"],
            target=rel["canonical"]["t"],
            relation=rel["rel"],
            reasoning=rel["r"]
        )
    
    print(f"\n✅ Applied all changes to Neo4j!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python apply_normalization.py output/results.json")
        sys.exit(1)
    
    apply_results(sys.argv[1])
```

---

## 8. Update LLM Chains

**File: `services/enhanced_langgraph_service.py`** (`__init__` method)

Add chains for merge operations:

```python
# Existing chains
self.relationship_chain = self.llm.with_structured_output(RelationshipBatch)
self.validation_chain = self.llm.with_structured_output(ValidationFeedback)

# NEW: Merge chains
self.merge_chain = self.llm.with_structured_output(MergeBatch)
self.merge_validation_chain = self.llm.with_structured_output(MergeValidationFeedback)
```

---

## 9. Update Iteration Logging

**File: `services/enhanced_langgraph_service.py`**

Log both merges and relationships in iteration files:

```python
def _save_iteration_state(self, state: Dict[str, Any], iteration: int, phase: str):
    serializable_state = {
        # ... existing fields ...
        
        # NEW: Merge tracking
        "all_merges": [
            {
                "concept_a": merge.concept_a,
                "concept_b": merge.concept_b,
                "canonical": merge.canonical,
                "variants": merge.variants,
                "r": merge.r
            }
            for merge in state["all_merges"].values()
        ],
        "weak_merges": [
            {
                "concept_a": key[0],
                "concept_b": key[1],
                "reason": reason
            }
            for key, reason in state["weak_merges"].items()
        ],
        "new_merge_batch": [
            # ... format new merges ...
        ],
        "metrics": {
            # ... existing metrics ...
            "total_merges": len(state["all_merges"]),
            "total_weak_merges": len(state["weak_merges"])
        }
    }
    # ... save to file ...
```

---

## 10. Remove SAME_AS from Relationship Generation

**File: `prompts/enhanced_relationship_prompts.py`**

Update generation prompt to remove SAME_AS:

```python
# Remove SAME_AS from relationship types
# Only keep USED_FOR and RELATED_TO

BINARY_GENERATION_SYSTEM_TEMPLATE = """...

## Relationship Types
- **USED_FOR**: Tool/method for purpose (e.g., TensorFlow → Deep Learning)
- **RELATED_TO**: General association (use sparingly)

Note: SAME_AS removed - concept normalization handles duplicates.
"""
```

Update config to remove SAME_AS:

```python
# In run scripts and tests
relationship_types={
    "USED_FOR": "Tool/method used for a specific purpose",
    "RELATED_TO": "General semantic connection"
    # SAME_AS removed
}
```

---

## Testing Strategy

1. Test with 10 concepts first
2. Verify merge proposals make sense
3. Check validation catches incorrect merges
4. Confirm database merges work correctly
5. Verify relationships use canonical names
6. Test with 100 concepts
7. Test with all 250 concepts

---

## Expected Behavior

- Iteration 1: Find ~30-50 merge proposals, generate ~60 relationships
- Validation: Reject weak merges/relationships
- Iteration 2-3: Refine until convergence
- At end: Apply merges, insert relationships to merged concepts
- Result: Cleaner graph with canonical concept names

### To-dos

- [ ] Add ConceptMerge, MergeValidationFeedback, WeakMerge models and new state fields to langgraph_state_models.py
- [ ] Create concept_normalization_prompts.py with system/user templates for finding and validating merges
- [ ] Modify _generation_node to make two smart LLM calls (merges + relationships) and add _find_similar_concepts method
- [ ] Extend _validation_node to validate both merges and relationships with separate feedback processing
- [ ] Update _convergence_checker to require both merge and relationship convergence
- [ ] Add merge_concepts and apply_all_merges methods to neo4j_service.py
- [ ] Modify _save_results to apply merges first, map relationships to canonical names, then insert
- [ ] Initialize merge_chain and merge_validation_chain with structured output in __init__
- [ ] Extend _save_iteration_state to log merge proposals, weak merges, and merge metrics
- [ ] Remove SAME_AS from relationship types in prompts and configuration files
- [ ] Test with 10, 100, and 250 concepts to verify merge detection and database updates work correctly