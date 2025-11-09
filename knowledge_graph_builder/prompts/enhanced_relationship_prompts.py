"""
Enhanced Prompt Templates for Iterative Relationship Detection with Quality Scoring

This module contains advanced ChatPromptTemplate-based prompts that incorporate
quality metrics, detailed validation criteria, and structured feedback for the
enhanced LangGraph workflow.
"""

from langchain_core.prompts import ChatPromptTemplate


# =============================================================================
# BINARY VALIDATION PROMPT (No Scoring - Only Valid/Weak Classification)
# =============================================================================

BINARY_VALIDATION_SYSTEM_TEMPLATE = """You are a relationship validator.

Classify each relationship as VALID or WEAK based on concept definitions.

## Classification Criteria

**VALID**: 
- Correct relation type for the connection
- Proper direction (source → target makes sense)
- Supported by concept definitions
- Specific and accurate

**WEAK**:
- Wrong relation type (should use USED_FOR instead of RELATED_TO, etc.)
- Wrong direction (reversed source/target)
- Too generic or vague
- Not supported by definitions
- Factually incorrect

## Allowed Relationship Types
{relationship_types}

## Output Format

Return JSON with ONLY the WEAK relationships. Valid relationships will be inferred programmatically.

{{
  "weak_relationships": [
    {{
      "s": "cnn",
      "t": "deep learning",
      "rel": "SAME_AS",
      "r": "Type of DL",
      "w": "CNN is USED_FOR DL, not SAME_AS. Not synonyms."
    }}
  ],
  "validation_notes": "Brief overall assessment",
  "total_validated": 300,
  "weak_count": 30
}}

**CRITICAL**:
- Return ONLY valid JSON (no markdown code fences)
- Include ONLY weak relationships in the array
- Keep w (weakness reason) under 80 characters
- Base w on concept definitions
- Use shortened keys: s=source, t=target, rel=relation, r=reasoning, w=weakness"""


BINARY_VALIDATION_USER_TEMPLATE = """# Relationships to Validate ({num_relationships})

{relationships_summary}

# Concept Definitions

{definitions_text}

---

**Task**: Validate each relationship against definitions.

Return ONLY the WEAK relationships with brief reasons why they're weak.

Valid relationships will be calculated programmatically as:
valid_relationships = all_relationships - weak_relationships"""


BINARY_VALIDATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", BINARY_VALIDATION_SYSTEM_TEMPLATE),
    ("human", BINARY_VALIDATION_USER_TEMPLATE)
])


# =============================================================================
# LEGACY VALIDATION PROMPT (Deprecated - kept for reference)
# =============================================================================

ENHANCED_VALIDATION_SYSTEM_TEMPLATE = """You are a relationship validator. Assess quality and provide operations.

## Quality Scoring (0.0-1.0)
- **Accuracy**: Factual correctness (1.0=perfect, 0.8-0.9=1-2 errors, 0.6-0.7=3-5 errors, <0.6=many errors)
- **Relevance**: Use specific types (prefer USED_FOR/SAME_AS over RELATED_TO when applicable)
- **Completeness**: Coverage of important relationships (1.0=complete, 0.8-0.9=1-2 missing, <0.8=gaps)
- **Overall**: Weighted average (accuracy×0.5 + relevance×0.3 + completeness×0.2)

## Operations
- **modify**: Fix wrong relation type/direction
- **delete**: Remove duplicates/factually wrong relationships
- **add**: Add critical missing relationships (only obvious ones)

## Allowed Types
{relationship_types}

## Output JSON
{{
  "quality_metrics": {{"accuracy_score": 0.85, "relevance_score": 0.80, "completeness_score": 0.75, "overall_score": 0.81}},
  "modify_operations": [{{"source": "A", "relation": "OLD", "target": "B", "action": "modify", "new_relation": "NEW", "reason": "brief reason"}}],
  "delete_operations": [{{"source": "A", "relation": "REL", "target": "B", "action": "delete", "reason": "brief reason"}}],
  "add_operations": [{{"source": "A", "target": "B", "relation": "REL", "reasoning": "brief reason"}}],
  "validation_notes": "Brief assessment",
  "issues_found": 5
}}

Return ONLY valid JSON. No markdown. Keep reasoning under 80 chars."""


ENHANCED_VALIDATION_USER_TEMPLATE = """# Relationships ({num_relationships})

{rel_summary}

{definitions_text}

---

Validate and return JSON with:
1. Quality scores (accuracy, relevance, completeness, overall)
2. Operations (modify/delete/add) with brief reasons (<80 chars)
3. Validation notes (concise assessment)
4. Issue count

**Guidelines**:
- modify: Wrong type/direction
- delete: Duplicates/factually wrong
- add: Only obvious missing relationships
- Empty operations = ready to converge"""


ENHANCED_VALIDATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", ENHANCED_VALIDATION_SYSTEM_TEMPLATE),
    ("human", ENHANCED_VALIDATION_USER_TEMPLATE)
])


# =============================================================================
# GENERATION PROMPT (Binary Approach - Avoid Weak Patterns)
# =============================================================================

BINARY_GENERATION_SYSTEM_TEMPLATE = """You are a semantic relationship detector for technical concepts.

Generate HIGH-CONFIDENCE relationships:
- **Accurate**: Factually correct, proper types and direction
- **Specific**: Prefer USED_FOR over RELATED_TO when applicable
- **Clear**: Keep reasoning SHORT (max 80 chars)
- **Honest**: Return empty list if no confident relationships found

**CRITICAL CONSTRAINT**:
- Both source AND target MUST be exact concept names from the provided list
- DO NOT create relationships to concepts not in the list
- If no valid target exists in the list, skip that relationship

**Quality > Quantity**:
- Generate ONLY relationships you are highly confident about
- Generate as many quality connections as you can reasonably find
- Focus on important and obvious connections
- Empty list is perfectly valid if no strong relationships found
- Never invent relationships - honesty over completeness

## Relationship Types
{relationship_types_desc}

**Note**: SAME_AS removed - concept normalization handles duplicates/synonyms.

## Output JSON
{{
  "relationships": [
    {{"s": "concept", "t": "concept", "rel": "TYPE", "r": "brief reason"}}
  ]
}}

Return ONLY valid JSON. No markdown. Keep r (reasoning) under 80 chars.
Use shortened keys: s=source, t=target, rel=relation, r=reasoning"""


BINARY_GENERATION_USER_TEMPLATE = """# Concepts ({num_concepts})

{concept_list}

# AVOID These Weak Patterns ({num_weak})

{weak_patterns_list}

---

**Task**: Generate NEW relationships, avoiding the weak patterns above.

**IMPORTANT**: 
- Both source AND target must be from the concept list above
- Use exact concept names as they appear in the list (all lowercase)
- DO NOT use concepts not in the list

**Types**:
- **USED_FOR**: Tool/method for purpose (e.g., tensorflow → deep learning)
- **RELATED_TO**: General association (use when USED_FOR doesn't fit)

**Standards**:
- High confidence only
- Focus on important and obvious connections
- Generate as many quality connections as you can reasonably find
- Return empty list if no strong relationships found
- Never force relationships"""


BINARY_GENERATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", BINARY_GENERATION_SYSTEM_TEMPLATE),
    ("human", BINARY_GENERATION_USER_TEMPLATE)
])


# =============================================================================
# LEGACY GENERATION PROMPT (Deprecated - kept for reference)
# =============================================================================

ENHANCED_GENERATOR_FIRST_SYSTEM_TEMPLATE = """You are a semantic relationship detector for technical concepts.

Generate HIGH-QUALITY relationships (focus on quality over quantity):
- **Accurate**: Factually correct, proper types and direction
- **Specific**: Prefer USED_FOR/SAME_AS over RELATED_TO when applicable
- **Selective**: Only STRONG, OBVIOUS relationships (avg 2-3 per concept)

## Types
{relationship_types_desc}

## Output JSON
{{
  "relationships": [
    {{"source": "concept", "target": "concept", "relation": "TYPE", "reasoning": "brief reason"}}
  ]
}}

Return ONLY valid JSON. No markdown. Keep reasoning under 80 chars."""


ENHANCED_GENERATOR_FIRST_USER_TEMPLATE = """# Concepts ({num_concepts})

{concept_list}

---

Generate IMPORTANT relationships only (quality > quantity):
- SAME_AS: Synonyms, acronyms (e.g., ml ↔ machine learning)
- USED_FOR: Tool/method for purpose (e.g., tensorflow → deep learning)
- RELATED_TO: General association (use only when above don't fit)

Target: ~{target_count} strong relationships. Focus on obvious, high-confidence connections."""


ENHANCED_GENERATOR_FIRST_PROMPT = ChatPromptTemplate.from_messages([
    ("system", ENHANCED_GENERATOR_FIRST_SYSTEM_TEMPLATE),
    ("human", ENHANCED_GENERATOR_FIRST_USER_TEMPLATE)
])


# =============================================================================
# REFINEMENT PROMPT (DEPRECATED - NO LONGER USED)
# =============================================================================
#
# NOTE: This prompt is NO LONGER USED after refactoring to programmatic operation application.
#
# Previously, this prompt was used to ask the LLM to apply MODIFY/DELETE/ADD operations
# to the full relationship set. This approach had critical issues:
# 1. LLM would regenerate relationships instead of preserving them (relationship loss)
# 2. Quality degradation due to incomplete relationship sets
# 3. Operations not applied correctly
#
# NEW APPROACH (implemented in enhanced_langgraph_service.py):
# - MODIFY/DELETE operations: Applied programmatically in Python (_apply_operations_programmatically)
# - ADD operations: LLM generates only NEW relationships (_generate_new_relationships)
# - Result: Zero relationship loss, exact operation application, predictable behavior
#
# This prompt is kept for historical reference and documentation purposes.
# If you need to modify how operations are applied, edit the Python code, not this prompt.
# =============================================================================

ENHANCED_GENERATOR_REFINEMENT_SYSTEM_TEMPLATE = """# Role
You are a **precise relationship editor** applying validated operations to improve relationship quality.

# Mission
**PRESERVE ALL RELATIONSHIPS** unless explicitly told to delete them.

Apply operations with surgical precision - no regeneration, only targeted edits.

## Operation Types

### 1. MODIFY [CHANGE]
Find exact match → Change specified fields → Keep everything else

**Example**:
- Operation: {{source: "A", relation: "RELATED_TO", target: "B", new_relation: "USED_FOR"}}
- Action: Find "A --[RELATED_TO]--> B" → Change to "A --[USED_FOR]--> B"

### 2. DELETE [REMOVE]
Find exact match → Remove completely

**Example**:
- Operation: {{source: "A", relation: "X", target: "B"}}
- Action: Find "A --[X]--> B" → Remove it

### 3. ADD [NEW]
Create new relationship → Add to list

**Example**:
- Operation: {{source: "C", relation: "Z", target: "D", reasoning: "..."}}
- Action: Add "C --[Z]--> D" with reasoning

## Matching Rules (EXACT MATCH REQUIRED)

### String Comparison
**Case-sensitive and whitespace-sensitive**:
- "Machine Learning" ≠ "machine learning"
- "Data Science" ≠ "Data Science "

**Exact match required**:
```
operation.source == relationship.source AND
operation.relation == relationship.relation AND
operation.target == relationship.target
```

### If No Exact Match
- **DO NOT** guess or find similar relationships
- **SKIP** that operation
- **PRESERVE** original relationships unchanged

## The Golden Rule: PRESERVATION

**DEFAULT ACTION**: Copy relationship unchanged

Only modify/delete if **EXACT MATCH** found.

**Example**:
- Current: 100 relationships
- Operations: MODIFY 3, DELETE 2, ADD 5
- Output: 103 relationships (100 - 2 deleted - 3 modified + 3 modified + 5 added)

## Output Format

{{
  "relationships": [
    {{
      "source": "exact concept name",
      "target": "exact concept name",
      "relation": "RELATION_TYPE",
      "reasoning": "brief explanation"
    }}
  ]
}}

**CRITICAL**:
- Return ONLY valid JSON (no markdown, no code fences)
- Include ALL relationships (modified + unchanged + added)
- Do NOT regenerate - only edit the provided list"""


ENHANCED_GENERATOR_REFINEMENT_USER_TEMPLATE = """# Current Relationships ({num_current} total)
**IMPORTANT**: Account for ALL {num_current} relationships in your output!

{relationships_summary}

---

# Operations to Apply ({total_ops} total)

## Quality Context
**Previous Quality Score**: {previous_quality_score:.2f}
**Target Quality Score**: 0.85+

## MODIFY Operations ({num_modify})
{modify_summary}

## DELETE Operations ({num_delete})
{delete_summary}

## ADD Operations ({num_add})
{add_summary}

---

# Allowed Relationship Types
{relationship_types_desc}

---

# Application Algorithm

## Step-by-Step Process

1. **CREATE** empty output list

2. **FOR EACH** of the {num_current} current relationships:

   a. Check if it matches ANY DELETE operation (exact source/relation/target)
      - IF YES: Skip it (don't add to output)
      - IF NO: Continue to step b

   b. Check if it matches ANY MODIFY operation (exact source/relation/target)
      - IF YES: Apply modification (change specified fields)
                Add MODIFIED version to output
      - IF NO: Add UNCHANGED to output

3. **FOR EACH** ADD operation:
   - Add new relationship to output

4. **RETURN** output list

## Expected Output Count

- Starting: {num_current} relationships
- After DELETE: {num_current} - {num_delete} = {expected_after_delete}
- After MODIFY: Same count (just changed fields)
- After ADD: {expected_after_delete} + {num_add} = {expected_final}

**Expected final count**: Approximately {expected_final} relationships

## Quality Checks

Before returning, verify:
1. ✅ Did I include ALL {num_current} relationships (unless deleted)?
2. ✅ Did I apply all {num_modify} MODIFY operations?
3. ✅ Did I remove all {num_delete} DELETE targets?
4. ✅ Did I add all {num_add} ADD operations?
5. ✅ Is my output count close to expected ({expected_final})?

**If output count differs significantly from input, YOU MADE A MISTAKE!**

---

# Output

Return JSON with ALL relationships after applying operations.

**CRITICAL**:
- No markdown code fences
- Include modified + unchanged + added relationships
- Do NOT regenerate from scratch
- Preserve all relationships not explicitly modified/deleted"""


ENHANCED_GENERATOR_REFINEMENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", ENHANCED_GENERATOR_REFINEMENT_SYSTEM_TEMPLATE),
    ("human", ENHANCED_GENERATOR_REFINEMENT_USER_TEMPLATE)
])

