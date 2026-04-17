from .attention_gcn import AttentionGCNLayer
from .basic_gcn import BasicGCNLayer
from .bipartite_gcn import BipartiteGCNLayer, BipartiteGCNStack
from .multi_relational import (
    HomoGCNStack,
    MultiRelationalGAT,
    # back-compat aliases
    MultiRelationalGCN,
    QuestionGATStage,
    QuestionGCNStage,
    ReadingGATStage,
    ReadingGCNStage,
    SkillGATStage,
    SkillGCNStage,
    StudentGATStage,
    StudentGCNStage,
    VideoGATStage,
    VideoGCNStage,
)
from .skill_gcn import SkillGCN

__all__ = [
    "BasicGCNLayer",
    "AttentionGCNLayer",
    "SkillGCN",
    "BipartiteGCNLayer",
    "BipartiteGCNStack",
    "HomoGCNStack",
    "SkillGATStage",
    "QuestionGATStage",
    "VideoGATStage",
    "ReadingGATStage",
    "StudentGATStage",
    "MultiRelationalGAT",
    # back-compat aliases
    "SkillGCNStage",
    "QuestionGCNStage",
    "VideoGCNStage",
    "ReadingGCNStage",
    "StudentGCNStage",
    "MultiRelationalGCN",
]
