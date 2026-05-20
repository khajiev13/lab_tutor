"""Regression tests for the post-ICCSE2026 multi-relational GAT refactor.

The paper-side fix (Thesis_ARCD/wiki/log.md entry [2026-05-16T19:35]) replaced
BatchNorm-over-nodes with per-node LayerNorm + per-layer residuals to fix
over-smoothing on small graphs. These tests lock the new architecture in:

* `BipartiteGCNStack` exposes ``fwd_norms`` / ``bwd_norms`` (LayerNorm) and
  ``src_proj`` / ``tgt_proj`` / ``out_proj`` projections.
* `HomoGCNStack` exposes ``norms`` (LayerNorm) and ``in_proj`` / ``out_proj``.
* Forward pass preserves shape and produces non-zero output (residual path is
  alive even with random Gaussian skill embeddings).

If a regression reintroduces ``fwd_bns`` / ``bwd_bns`` / ``bns`` keys, the
saved state-dict will silently break ``model_registry.from_dir`` (it falls back
to ``is_available=False``) and agents will degrade to heuristic mastery.
"""

from __future__ import annotations

import torch

from app.modules.arcd_agent.model.gat.multi_relational import (
    BipartiteGCNStack,
    HomoGCNStack,
    MultiRelationalGAT,
)


def test_bipartite_gcn_stack_uses_layernorm_not_batchnorm() -> None:
    stack = BipartiteGCNStack(
        d_source=64, d_target_in=64, d_hidden=64, d_out=64, n_layers=3
    )

    assert hasattr(stack, "fwd_norms"), (
        "BipartiteGCNStack must expose fwd_norms (LayerNorm list)"
    )
    assert hasattr(stack, "bwd_norms"), (
        "BipartiteGCNStack must expose bwd_norms (LayerNorm list)"
    )
    assert not hasattr(stack, "fwd_bns"), (
        "BatchNorm path must be removed (over-smoothing fix)"
    )
    assert not hasattr(stack, "bwd_bns"), (
        "BatchNorm path must be removed (over-smoothing fix)"
    )

    for norm in list(stack.fwd_norms) + list(stack.bwd_norms):
        assert isinstance(norm, torch.nn.LayerNorm), (
            f"Expected nn.LayerNorm, got {type(norm).__name__}"
        )

    assert (
        hasattr(stack, "src_proj")
        and hasattr(stack, "tgt_proj")
        and hasattr(stack, "out_proj")
    )


def test_homo_gcn_stack_uses_layernorm_and_input_projection() -> None:
    stack = HomoGCNStack(d_in=128, d_hidden=64, d_out=64, n_layers=2, n_heads=4)

    assert hasattr(stack, "norms"), "HomoGCNStack must expose norms (LayerNorm list)"
    assert not hasattr(stack, "bns"), (
        "BatchNorm path must be removed (over-smoothing fix)"
    )
    assert hasattr(stack, "in_proj"), (
        "HomoGCNStack must project raw embeddings to model width"
    )
    assert hasattr(stack, "out_proj")

    for norm in stack.norms:
        assert isinstance(norm, torch.nn.LayerNorm)


def test_skill_stage_forward_preserves_shape_and_residual_alive() -> None:
    """Random init should still propagate through the residual path.

    Output must stay shape (n_skills, d_out) and be non-zero (variance > 0).
    A pre-refactor BatchNorm-over-nodes path collapsed the per-node variance to
    near-zero on small graphs (n_skills < 32), which is why the residual +
    LayerNorm rewrite was necessary.
    """
    torch.manual_seed(0)
    n_skills = 10
    d_in, d_out = 16, 8

    H = torch.randn(n_skills, d_in)
    A = torch.eye(n_skills)
    A[1, 0] = A[2, 1] = A[3, 2] = 1.0

    stack = HomoGCNStack(d_in=d_in, d_hidden=d_out, d_out=d_out, n_layers=2, n_heads=2)
    out = stack(H, A)

    assert out.shape == (n_skills, d_out)
    assert torch.isfinite(out).all(), "Output contains NaN / Inf"
    assert out.var().item() > 1e-6, "Variance collapsed — residual path is dead"


def test_multi_relational_gat_returns_all_five_stage_outputs() -> None:
    """All 5 stages (h_s, h_qa, h_v, h_r, h_u) must be present at d=2048-compatible size.

    This locks the paper's 5-stage shape contract in place. Anyone breaking the
    output dictionary keys will need to update both the writeback script and
    the inference paths in `cognitive_diagnosis/service.py`.
    """
    torch.manual_seed(0)
    n_skills, n_questions, n_videos, n_readings, n_students = 6, 8, 4, 3, 5
    d = 16

    gat = MultiRelationalGAT(
        d_skill_embed=d,
        d=d,
        n_layers=2,
        n_questions=n_questions,
        n_videos=n_videos,
        n_readings=n_readings,
        n_students=n_students,
        n_heads=2,
        dropout=0.0,
    )
    H = torch.randn(n_skills, d)
    A_pre = torch.eye(n_skills)
    A_qs = torch.zeros(n_questions, n_skills)
    A_qs[range(n_questions), [i % n_skills for i in range(n_questions)]] = 1
    A_vs = torch.zeros(n_videos, n_skills)
    A_vs[range(n_videos), [i % n_skills for i in range(n_videos)]] = 1
    A_rs = torch.zeros(n_readings, n_skills)
    A_rs[range(n_readings), [i % n_skills for i in range(n_readings)]] = 1
    A_uq = torch.zeros(n_students, n_questions)
    A_uq[range(n_students), [i % n_questions for i in range(n_students)]] = 1

    out = gat(H, A_pre, A_qs, A_vs, A_rs, A_uq)

    assert set(out.keys()) == {"h_s", "h_qa", "h_v", "h_r", "h_u"}
    assert out["h_s"].shape == (n_skills, d)
    assert out["h_qa"].shape == (n_questions, d)
    assert out["h_v"].shape == (n_videos, d)
    assert out["h_r"].shape == (n_readings, d)
    assert out["h_u"].shape == (n_students, d)
