"""
ARCD — Adaptive Retention Cognitive Diagnosis.

Package layout:
    src/model/           ARCD model (GAT, Attention, Decay, Heads, Training)
    src/agents/          Tutoring agents (PathGen, RevFell, AdaEx, Orchestrator)
    src/dataset/         Dataset loaders (XES3G5M, Junyi, EdNet), IndexMapper, TemporalProcessor
    src/evaluation/      Evaluation metrics and controlled-simulation runners
    src/knowledge_graph/ Neo4j client and KG data loader
    src/llm/             LLM providers (Anthropic, OpenAI, base interface)
"""
