"""LLM prompt templates for recommendation agents."""

from __future__ import annotations

BOOK_GAP_ANALYSIS_SYSTEM = """\
You are an expert curriculum consultant helping university teachers improve their course materials.

You will be given:
1. **Novel book concepts** — concepts the textbook covers that the teacher's course materials do NOT mention at all (similarity < 0.35). These are the highest-priority gaps.
2. **Overlap concepts** — concepts with weak coverage (0.35 ≤ similarity < 0.55). The teacher mentions something related but coverage is insufficient.
3. **Teacher documents** — a list of the teacher's current uploaded documents with their topics, summaries, and the concepts they mention.
4. **Book skills** — skills the textbook teaches, linked to specific concepts and chapters.

Your job is to produce a structured recommendation report that advises the teacher on:
- Which **missing concepts** they should add to their materials (with specific chapter/section references from the book).
- Which **existing documents** have **insufficient coverage** and need strengthening.
- Which **skills** from the book are not being developed in the current materials.
- Any **structural** improvements (e.g., topics that should be split, reorganized, or merged).

Guidelines:
- Be specific and actionable. Reference exact concept names, document topics, and book chapters.
- Prioritize: high = concept is core and completely missing; medium = weak overlap; low = nice-to-have.
- Group related concepts into single recommendations when they belong to the same chapter/topic.
- Suggest which existing teacher document would be the best place to add missing content.
- Keep the summary concise (2-3 sentences max).
- Produce between 3 and 15 recommendations total. Focus on the most impactful gaps.

You MUST respond with ONLY a raw JSON object (no markdown, no code fences, no extra text).
Use EXACTLY this schema:

{
  "summary": "2-3 sentence executive summary of findings",
  "recommendations": [
    {
      "category": "missing_concept | insufficient_coverage | suggested_skill | structural",
      "priority": "high | medium | low",
      "title": "Short headline",
      "description": "Detailed explanation of the gap",
      "rationale": "Why this matters for the course",
      "book_evidence": {
        "chapter_title": "Chapter name or null",
        "section_title": "Section name or null",
        "text_evidence": "Quote or null"
      },
      "affected_teacher_document": "Filename or topic of teacher doc most affected, or null",
      "suggested_action": "Concrete next step the teacher should take"
    }
  ]
}

Field rules:
- "category" must be one of: "missing_concept", "insufficient_coverage", "suggested_skill", "structural"
- "priority" must be one of: "high", "medium", "low" (lowercase!)
- Every recommendation MUST include all fields: category, priority, title, description, rationale, suggested_action
- "book_evidence" and "affected_teacher_document" may be null
"""

BOOK_GAP_ANALYSIS_USER = """\
## Book: {book_title}

### Novel Concepts (NOT covered in teacher materials)
{novel_concepts_text}

### Overlap Concepts (weakly covered)
{overlap_concepts_text}

### Teacher's Current Documents
{teacher_documents_text}

### Book Skills
{skills_text}

Produce the recommendation report as a raw JSON object. Do NOT wrap in markdown code fences.
"""


def format_novel_concepts(concepts: list[dict]) -> str:
    """Format novel concepts for the LLM prompt."""
    if not concepts:
        return "None — all book concepts are covered."

    lines: list[str] = []
    for c in concepts:
        parts = [f"- **{c['name']}**"]
        if c.get("chapter_title"):
            parts.append(f"(Ch: {c['chapter_title']}")
            if c.get("section_title"):
                parts.append(f"/ {c['section_title']}")
            parts.append(")")
        parts.append(f"[sim={c['sim_max']:.2f}]")
        if c.get("description"):
            parts.append(f"— {c['description'][:200]}")
        lines.append(" ".join(parts))

    return "\n".join(lines)


def format_overlap_concepts(concepts: list[dict]) -> str:
    """Format overlap concepts for the LLM prompt."""
    if not concepts:
        return "None — all partially-covered concepts have good similarity."

    lines: list[str] = []
    for c in concepts:
        best = c.get("best_course_match", "?")
        lines.append(
            f'- **{c["name"]}** [sim={c["sim_max"]:.2f}] best course match: "{best}"'
        )

    return "\n".join(lines)


def format_teacher_documents(documents: list[dict]) -> str:
    """Format teacher documents for the LLM prompt."""
    if not documents:
        return "No teacher documents found."

    lines: list[str] = []
    for doc in documents:
        topic = doc.get("topic", "Unknown")
        filename = doc.get("source_filename", "")
        summary = (doc.get("summary") or "")[:300]
        concepts = doc.get("concept_names", [])
        concepts_str = ", ".join(concepts[:10])
        if len(concepts) > 10:
            concepts_str += f" (+{len(concepts) - 10} more)"

        line = f"- **{topic}**"
        if filename:
            line += f" ({filename})"
        if summary:
            line += f"\n  Summary: {summary}"
        if concepts_str:
            line += f"\n  Concepts: {concepts_str}"
        lines.append(line)

    return "\n".join(lines)


def format_skills(skills: list[dict]) -> str:
    """Format book skills for the LLM prompt."""
    if not skills:
        return "No skills extracted."

    lines: list[str] = []
    for sk in skills:
        line = f"- **{sk['name']}**"
        if sk.get("chapter_title"):
            line += f" (Ch: {sk['chapter_title']})"
        if sk.get("description"):
            line += f" — {sk['description'][:150]}"
        concepts = sk.get("concept_names", [])
        if concepts:
            line += f"\n  Related concepts: {', '.join(concepts[:5])}"
        lines.append(line)

    return "\n".join(lines)
