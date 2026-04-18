"""
ARCD — Adaptive Retention Cognitive Diagnosis.

Package layout (app.modules.arcd.*):
    model/             ARCD model (GAT, Attention, Decay, Heads, Training)
    agents/            Tutoring agents (PathGen, RevFell, AdaEx, Orchestrator)
    dataset/           Loaders (XES3G5M, Junyi, EdNet), IndexMapper, TemporalProcessor
    evaluation/        Evaluation metrics and controlled-simulation runners
    knowledge_graph/   Neo4j client and KG data loader
    llm/               LLM providers (Anthropic, OpenAI, base interface)
"""
