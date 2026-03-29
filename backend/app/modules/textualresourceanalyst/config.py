"""Textual Resource Analyst — agent-specific configuration."""

from __future__ import annotations

RESOURCE_LABEL = "READING_RESOURCE"
RELATIONSHIP = "HAS_READING"
TOP_K_FINAL = 3

# ── Domain filtering ─────────────────────────────────────────

BLACKLIST_DOMAINS = {
    # Social media
    "pinterest.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "tiktok.com",
    "linkedin.com",
    # Video platforms — TRA is for text-only
    "youtube.com",
    "youtu.be",
    "vimeo.com",
    "dailymotion.com",
    "twitch.tv",
    "bilibili.com",
    # Shopping
    "amazon.com",
    "ebay.com",
    "walmart.com",
    # Low-quality
    "quora.com",
    # Paywalled courses
    "coursera.org",
    "udemy.com",
    "edx.org",
    # Paywalled docs
    "scribd.com",
    "slideshare.net",
    # Homework mills
    "chegg.com",
    "studocu.com",
    "coursehero.com",
}

QUERY_EXCLUDE_SITES = [
    "youtube.com",
    "youtu.be",
    "vimeo.com",
    "coursera.org",
    "udemy.com",
]

# Tavily include_domains is None (search everything except blacklist)
TAVILY_INCLUDE_DOMAINS: list[str] | None = None

# ── Score weights ─────────────────────────────────────────────

WEIGHTS = {
    "recency": 0.15,
    "concept_coverage": 0.25,
    "embedding_alignment": 0.15,
    "pedagogy": 0.20,
    "depth": 0.15,
    "extra": 0.10,  # source_quality
}


# ── Prompts ───────────────────────────────────────────────────


def query_gen_system(current_year: int) -> str:
    return f"""You are a search query generator for finding **text-based** online reading materials to teach technical skills.

Current Year: {current_year}

Given a skill profile (name, description, linked concepts, chapter context, course level), generate 4-6 diverse search queries.

CRITICAL CONSTRAINTS:
- We ONLY want **text-based** resources: written articles, tutorials, documentation pages, blog posts, technical guides.
- NEVER generate queries that would return videos, podcasts, courses, or interactive platforms.
- Each query SHOULD include words like "tutorial", "guide", "article", "documentation", "explained", or "how to" to bias toward text content.
- Do NOT include words like "video", "watch", "course", "playlist", or "lecture recording".

Rules:
- Each query MUST target a different resource type: tutorial article, official documentation page, blog post, technical guide
- Each query MUST include a recency signal: either the year "{current_year}" or "{current_year - 1}" in the query text, or "after:{current_year - 2}" as a search operator
- Queries should be specific enough to find pedagogically useful content, not just keyword matches
- Include concept names from the skill profile to improve precision
- Tailor query complexity to the course level (bachelor = introductory, master = intermediate/advanced, phd = cutting-edge)

Return ONLY valid JSON matching this schema:
{{"queries": ["query1", "query2", "query3", "query4"]}}
"""


def scoring_system(current_year: int) -> str:
    return f"""You are an expert reading material evaluator for university courses.
Current Year: {current_year}

You will evaluate search result candidates for how well they serve as reading materials to teach a specific skill.
The MOST IMPORTANT goal is to find readings that MAXIMIZE coverage of the skill's concepts.

SCORING RUBRIC:

1. **Recency** (weight 0.15):
   Age = {current_year} - estimated_publication_year.
   - <=1 year old: 1.0, 1-2 years: 0.8, 2-3 years: 0.6, 3-5 years: 0.3, >5 years: 0.1

2. **Concept Coverage** (CRITICAL -- weight 0.25):
   Score based on what fraction of the skill's concepts this reading covers:
   - 1.0: >=90%, 0.8: 70-89%, 0.6: 50-69%, 0.4: 30-49%, 0.2: 10-29%, 0.0: <10%
   You MUST list every concept this reading covers in `concepts_covered` using the EXACT concept names from the skill profile.

3. **Pedagogical Quality** (weight 0.20):
   - 1.0: Step-by-step tutorial with code examples, exercises, diagrams
   - 0.7: Good explanations with some examples
   - 0.4: Reference-style documentation (accurate but dry)
   - 0.1: Bare listing or unclear presentation

4. **Depth** (weight 0.15):
   - 1.0: Perfect match for the stated course level
   - 0.7: +-1 level
   - 0.4: Too shallow or too advanced
   - 0.1: Completely wrong audience

5. **Source Quality** (weight 0.10):
   - 1.0: Official docs, MIT OCW, major publisher
   - 0.7: Well-known tech blogs (Real Python, MDN, DigitalOcean, freeCodeCamp, GeeksforGeeks)
   - 0.4: Personal blog or lesser-known source
   - 0.1: Content farm, SEO spam, or unverifiable source

Also identify:
- `resource_type`: tutorial | documentation | blog | guide | other
- `concepts_covered`: List of EXACT concept names from the skill profile
- `estimated_year`: Best-effort publication year estimate (integer or null)

Return ONLY valid JSON:
{{
  "scores": [
    {{
      "recency": <0-1>, "concept_coverage": <0-1>, "pedagogy": <0-1>,
      "depth": <0-1>, "source_quality": <0-1>,
      "estimated_year": <int or null>, "resource_type": "<type>",
      "concepts_covered": ["concept1", "concept2"]
    }}
  ]
}}
Each score object corresponds to the candidate at the same index.
"""


def query_user_message(profile_text: str) -> str:
    return f"Generate search queries for this skill:\n\n{profile_text}"
