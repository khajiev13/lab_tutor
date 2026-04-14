# Autoresearch Demo: Embedding Norm Heterogeneity Drives LoRA Fine-Tuning Brittleness

**Paper:** [norm-heterogeneity-lora-brittleness.pdf](norm-heterogeneity-lora-brittleness.pdf)

**Skills Used:** [Autoresearch](../../0-autoresearch-skill/), [ML Paper Writing](../../20-ml-paper-writing/), [Research Ideation](../../21-research-ideation/)

## What Happened

An AI agent ran the full autoresearch workflow autonomously — from literature survey through experiments to paper writing. Starting from the hypothesis that ETF crystallization drives LoRA fine-tuning brittleness in overtrained models, the agent:

1. **Surveyed literature** connecting two recent papers: NeurIPS 2025 Best Paper Runner-Up on superposition/ETF structure and ICML 2025 on catastrophic overtraining
2. **Ran inner loop experiments** across Pythia-410M and Pythia-1.4B checkpoints, computing ETF overlap metrics and norm statistics at each checkpoint, then applying LoRA fine-tuning
3. **Discovered a null result** — ETF overlap geometry does NOT predict fine-tuning difficulty (r=0.14), refuting the starting hypothesis
4. **Pivoted** — identified embedding norm heterogeneity (coefficient of variation) as the actual causal predictor (r=-0.84 at 410M, r=-0.99 at 1.4B)
5. **Deepened** with causal experiments — equalizing norms before LoRA increases fine-tunability by up to 79%
6. **Wrote the paper** using the ml-paper-writing skill

## Key Findings

- ETF overlap metrics show no correlation with LoRA fine-tuning difficulty — a clear negative result
- Norm CV of LM head rows strongly predicts deconfounded fine-tunability (r=-0.99 at 1.4B)
- Equalizing norms before LoRA increases relative fine-tunability by up to 79%
- The effect is rank-independent — increasing LoRA rank does not mitigate it
- Norms encode semantic specificity, creating an impedance mismatch with LoRA's uniform low-rank updates

## Why This Demo Matters

This demonstrates the autoresearch two-loop architecture working as designed:
- **Inner loop** ran constrained experiments (checkpoint analysis, LoRA fine-tuning, metric computation)
- **Outer loop** synthesized a null result into a pivot, leading to a stronger finding than the original hypothesis
- The agent autonomously went from "ETF predicts brittleness" to "actually no, norm heterogeneity does" — a genuine research pivot that produced a more interesting paper
