"""The reviewed JSON corpus is the independent cross-language oracle."""

import json
from pathlib import Path

import pytest

from app.modules.marketdemandanalyst import schemas

CORPUS = json.loads(
    (Path(__file__).parents[1] / "fixtures/teacher-workspace-patterns.json").read_text()
)


@pytest.mark.parametrize("case", CORPUS["cases"], ids=lambda case: case["name"])
def test_golden_workspace_pattern_rules(case):
    from app.modules.marketdemandanalyst.workspace_patterns import (
        derive_pattern_observations,
    )

    review = schemas.SkillReview.model_validate(case["review"])
    request = schemas.RunReviewContext.model_validate(case["context"])
    before = review.model_dump(mode="json")
    assert [
        row.model_dump(mode="json")
        for row in derive_pattern_observations(review, request)
    ] == case["expected"]
    assert review.model_dump(mode="json") == before
