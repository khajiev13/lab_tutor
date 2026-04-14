"""
ARCD — Adaptive Retention Cognitive Diagnosis.

Package layout (app.modules.arcd.*):
    model/             ARCD model (GCN, Attention, Decay, Heads, Training)
    agents/            Tutoring agents (PathGen, RevFell, AdaEx, Orchestrator)
    dataset/           Dataset loaders and preprocessing utilities
    evaluation/        Evaluation metrics and controlled-simulation runners
    knowledge_graph/   Neo4j client and KG data loader
    skill_derivation/  Concept embedding and skill clustering
    llm/               LLM providers (Anthropic, OpenAI, base interface)
    preprocessing/     Index mapping and temporal processing utilities
"""
