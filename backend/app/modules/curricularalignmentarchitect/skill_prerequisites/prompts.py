from __future__ import annotations

DUPE_JUDGE_PROMPT = """\
You are a curriculum ontology specialist. You will be given a group of skills that are candidates for being duplicates of each other.

Your task: Decide whether ALL skills in the group represent the same underlying skill.

For each skill you are given:
- name: the skill name
- description: what the skill covers
- chapter: the chapter where this skill appears
- concepts: related concepts for the skill

Guidelines:
- Skills are duplicates only if they require mastering the same knowledge and ability.
- Minor wording differences do not matter — focus on semantics.
- A more general skill and a specific sub-skill are NOT duplicates.
- If they ARE duplicates, choose the canonical_name that is clearest and most general.
- skill_names_to_merge must list all names in the group EXCEPT the canonical_name.
- If they are NOT duplicates, set are_duplicates=false, canonical_name=null, skill_names_to_merge=[].

Skills to evaluate:
{skills_json}

Return ONLY valid JSON matching the DupeGroupVerdict schema:
{{
  "are_duplicates": true|false,
  "canonical_name": "<best name or null>",
  "skill_names_to_merge": ["<name1>", ...],
  "reasoning": "<brief explanation>"
}}"""


CLUSTER_PREREQ_PROMPT = """\
You are a curriculum sequencing specialist. You will be given a cluster of semantically related skills from a course.

Your task: Identify PREREQUISITE relationships between these skills.

A prerequisite means: a student MUST master skill A before they can meaningfully learn skill B.
- Only output A -> B if B directly uses knowledge, procedure, or vocabulary from A and the learner would be blocked without A.
- Use chapter ordering as a strong hint: lower chapter_index = taught earlier = likely prerequisite, but override when needed.
- Skills from the same chapter are often parallel, not prerequisites.
- Do NOT emit edges for paraphrases or near-duplicate descriptions of the same activity.
- Do NOT emit edges for compare-vs-compare, classify-vs-classify, or other same-level analytical skills unless one explicitly depends on the other.
- Do NOT emit edges for broad tool-list vs specific-tool variants when neither skill is required to perform the other.
- Do NOT emit edges between taxonomy/classification and operational skills unless the operational task explicitly depends on first identifying or using that taxonomy.
- Only output edges where the dependency is concrete and required, not merely helpful.
- Do NOT create transitive edges — if A→B and B→C already exist, do NOT add A→C.
- Confidence levels:
  - "high": Unambiguous dependency (e.g. must understand recursion before dynamic programming)
  - "medium": Strong pedagogical suggestion but not strictly required
  - "low": Helpful to know first but learnable independently

Skills in this cluster (sorted by chapter order):
{skills_json}

Return ONLY valid JSON matching the ClusterPrerequisiteResult schema:
{{
  "edges": [
    {{
      "prerequisite_skill": "<skill name>",
      "dependent_skill": "<skill name>",
      "confidence": "high|medium|low",
      "reasoning": "<brief explanation>"
    }}
  ]
}}

If no clear prerequisite relationships exist, return {{"edges": []}}."""
