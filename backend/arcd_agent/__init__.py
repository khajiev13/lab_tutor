"""
ARCD — Adaptive Retention Cognitive Diagnosis.

Package layout:
    src/model/          ARCD model (GCN, Attention, Decay, Heads, Training)
    src/agents/         Tutoring agents (PathGen, RevFell, AdaEx, Orchestrator)
    src/dataset/        Dataset loaders and preprocessing utilities
    src/evaluation/     Evaluation metrics and controlled-simulation runners
    src/knowledge_graph/ Neo4j client and KG data loader
    src/skill_derivation/ Concept embedding and skill clustering
    src/llm/            LLM utilities (prompt helpers, chain factories)
    src/preprocessing/  Legacy preprocessing (re-exported via src/dataset/)
"""
