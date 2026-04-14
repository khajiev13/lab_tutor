# Autoresearch Demo: The RL Algorithm Brain Scan

**Paper:** [rl_algorithm_brain_scan.pdf](rl_algorithm_brain_scan.pdf)

**Skills Used:** [Autoresearch](../../0-autoresearch-skill/), [ML Paper Writing](../../20-ml-paper-writing/), [GRPO RL Training](../../06-post-training/grpo-rl-training/), [TRL](../../06-post-training/trl-fine-tuning/), [SAELens](../../04-mechanistic-interpretability/saelens/), [TransformerLens](../../04-mechanistic-interpretability/transformer-lens/)

## What Happened

An AI agent autonomously investigated what RL alignment algorithms actually do to model internals — a question no prior work had systematically addressed. The agent:

1. **Surveyed literature** on RLOO, GRPO, and DPO, identifying the gap: nobody had compared what these algorithms do at the weight and feature level on the same base model
2. **Ran inner loop experiments** training GPT-2 Small with RLOO, GRPO, and DPO on sentiment and toxicity tasks, then analyzing weight deltas via SVD and feature changes via SAELens
3. **Discovered three key findings** through outer loop synthesis:
   - DPO is a rank-1 perturbation (top-1 SVD direction recovers 95.6% of behavioral effect)
   - Online RL (RLOO/GRPO) produces distributed, structure-preserving modifications (effective rank 200 vs 119)
   - DPO creates a "concentrated perturbation cascade" disrupting 2x more SAE features in later layers
4. **Validated causally** with SVD ablation experiments — not just correlation but causal evidence
5. **Wrote the paper** in ICML format using the ml-paper-writing skill

## Key Findings

- **DPO is rank-1 alignment**: A single SVD direction per weight matrix recovers 95.6% of DPO's behavioral effect. GRPO needs 50+ directions for equivalent recovery.
- **Online RL preserves structure**: RLOO and GRPO maintain higher effective rank (200 vs 119) and better preserve the base model's SAE feature structure (Jaccard 0.83 vs 0.69)
- **DPO's concentrated perturbation cascade**: Despite lower-rank changes, DPO disrupts 2x more SAE features in later layers (1619 vs 527-870), amplifying perturbations through the network
- Results hold across sentiment and toxicity tasks with statistical significance (n=3 seeds, non-overlapping CIs)

## Why This Demo Matters

This demonstrates autoresearch orchestrating multiple domain skills together:
- **Post-training skills** (TRL, GRPO) for training the RL models
- **Interpretability skills** (SAELens, TransformerLens) for analyzing what changed
- **Paper writing skill** for producing the ICML submission
- The two-loop architecture enabled the agent to both run experiments AND synthesize them into mechanistic understanding — "DPO is a rank-1 perturbation" is a conceptual insight, not just a metric
