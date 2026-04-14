Implementation plan for Teacher Content Recommendations via Book Gap Analysis.

Read the full plan: .github/prompts/plan-teacherContentRecommendations.prompt.md

## Summary
Add a recommendations/ sub-module inside curricularalignmentarchitect/ that uses the already-computed ChapterAnalysisSummary data (book concepts with sim_max scores) to generate LLM-driven recommendations for what teachers should add/improve in their documents.

## Key Insight
ChapterAnalysisSummary already stores book_unique_concepts_json (with sim_max), course_coverage_json, chapter_details_json, and topic_scores_json. Concepts with low sim_max (< 0.35) are novel — things the teacher should add.

## Architecture
- recommendations/schemas.py — RecommendationItem, RecommendationReport
- recommendations/repository.py — data from SQL + Neo4j
- recommendations/service.py — orchestration
- recommendations/agents/book_gap_analysis.py — LLM agent
- api_routes/recommendations.py — POST endpoint

## Data Flow
```
ChapterAnalysisSummary (SQL) + Neo4j TEACHER_UPLOADED_DOCUMENT
  → Repository → Service → Book Gap Analysis Agent (LLM)
  → RecommendationReport → API Response
```

$ARGUMENTS
