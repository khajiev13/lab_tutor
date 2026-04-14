"""Visual Content Evaluator — agent-specific configuration."""

from __future__ import annotations

RESOURCE_LABEL = "VIDEO_RESOURCE"
RELATIONSHIP = "HAS_VIDEO"
TOP_K_FINAL = 3

# ── Domain filtering ─────────────────────────────────────────

BLACKLIST_DOMAINS: set[str] = set()  # We want YouTube, so no blacklist

# For YouTube-only: restrict searches to youtube.com
QUERY_EXCLUDE_SITES: list[str] = []  # No exclusions — we WANT youtube results

# Tavily include_domains restricts to YouTube
TAVILY_INCLUDE_DOMAINS: list[str] | None = ["youtube.com"]

# ── Score weights ─────────────────────────────────────────────

WEIGHTS = {
    "recency": 0.15,
    "concept_coverage": 0.25,
    "embedding_alignment": 0.15,
    "pedagogy": 0.20,
    "depth": 0.15,
    "extra": 0.10,  # production_quality
}


# ── Prompts ───────────────────────────────────────────────────


def query_gen_system(current_year: int) -> str:
    return f"""You are a search query generator for finding **YouTube video** materials to teach technical skills.

Current Year: {current_year}

Given a skill profile (name, description, linked concepts, chapter context, course level), generate 4-6 diverse YouTube search queries.

CRITICAL CONSTRAINTS:
- We ONLY want **video-based** resources on YouTube.
- NEVER generate queries that would return standard text articles.
- Each query SHOULD include words like "tutorial", "lecture", "explained", "course", "walkthrough", or "crash course" to bias toward video content.
- Queries should be optimized for YouTube's search engine.
- Include concept names from the skill profile to improve precision.

Rules:
- Each query MUST target a different resource type: lecture format, concise tutorial, practical walkthrough, deep dive
- Each query MUST include a recency signal: either the year "{current_year}" or "{current_year - 1}" in the query text
- Tailor query complexity to the course level (bachelor = introductory, master = intermediate/advanced, phd = cutting-edge)

Return ONLY valid JSON matching this schema:
{{"queries": ["query1", "query2", "query3", "query4"]}}
"""


def scoring_system(current_year: int) -> str:
    return f"""You are an expert video evaluator for university courses.
Current Year: {current_year}

You will evaluate YouTube video candidates for how well they serve to teach a specific skill visually.
The MOST IMPORTANT goal is to find videos that MAXIMIZE coverage of the skill's concepts.

SCORING RUBRIC:

1. **Recency** (weight 0.15):
   Age = {current_year} - estimated_publication_year.
   - <=1 year old: 1.0, 1-2 years: 0.8, 2-3: 0.6, 3-5: 0.3, >5: 0.1.

2. **Concept Coverage** (CRITICAL -- weight 0.25):
   Score based on what fraction of the skill's concepts this video covers:
   - 1.0: >=90%, 0.8: 70-89%, 0.6: 50-69%, 0.4: 30-49%, 0.2: 10-29%, 0.0: <10%.
   You MUST list every concept this covers in `concepts_covered` using EXACT names from the skill profile.

3. **Pedagogical/Visual Quality** (weight 0.20):
   - 1.0: High likelihood of strong visual explanations, animations, or clear step-by-step guidance
   - 0.7: Standard tutorial format
   - 0.4: Likely just a talking head or dry lecture recording
   - 0.1: Non-educational or confusing

4. **Depth** (weight 0.15):
   - 1.0: Perfect match for the course level
   - 0.7: Slightly too simple or advanced
   - 0.4: Shallow overview
   - 0.1: Completely wrong audience

5. **Production Quality** (weight 0.10):
   - 1.0: Professional channel, known educator (e.g., freeCodeCamp, MIT OCW, 3Blue1Brown)
   - 0.7: Good quality indie creator
   - 0.4: Unclear quality, generic snippet
   - 0.1: Likely low quality or spammy

Resource Types: lecture | tutorial | code_walkthrough | animation | other

Return ONLY valid JSON:
{{
  "scores": [
    {{
      "recency": <0-1>, "concept_coverage": <0-1>,
      "pedagogy": <0-1>, "depth": <0-1>, "production_quality": <0-1>,
      "estimated_year": <int or null>, "resource_type": "<type>",
      "concepts_covered": ["concept1"]
    }}
  ]
}}
"""


def query_user_message(profile_text: str) -> str:
    return f"Generate video search queries for this skill:\n\n{profile_text}"
