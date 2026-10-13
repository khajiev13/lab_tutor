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


@pytest.mark.parametrize(
    "value,expected",
    [
        ("\u0009Python\u0009", "python"),
        ("\u000aPython\u000a", "python"),
        ("\u000bPython\u000b", "python"),
        ("\u000cPython\u000c", "python"),
        ("\u000dPython\u000d", "python"),
        ("\u0020Python\u0020", "python"),
        ("\u00a0Python\u00a0", "python"),
        ("\u1680Python\u1680", "python"),
        ("\u2000Python\u2000", "python"),
        ("\u2001Python\u2001", "python"),
        ("\u2002Python\u2002", "python"),
        ("\u2003Python\u2003", "python"),
        ("\u2004Python\u2004", "python"),
        ("\u2005Python\u2005", "python"),
        ("\u2006Python\u2006", "python"),
        ("\u2007Python\u2007", "python"),
        ("\u2008Python\u2008", "python"),
        ("\u2009Python\u2009", "python"),
        ("\u200aPython\u200a", "python"),
        ("\u2028Python\u2028", "python"),
        ("\u2029Python\u2029", "python"),
        ("\u202fPython\u202f", "python"),
        ("\u205fPython\u205f", "python"),
        ("\u3000Python\u3000", "python"),
        ("\ufeffPython\ufeff", "python"),
        ("\u0085Python\u0085", "\u0085python\u0085"),
        ("\u001cPython\u001c", "\u001cpython\u001c"),
        ("\u001dPython\u001d", "\u001dpython\u001d"),
        ("\u001ePython\u001e", "\u001epython\u001e"),
        ("\u001fPython\u001f", "\u001fpython\u001f"),
        ("Py\ufeffthon", "py\ufeffthon"),
        ("Py\u0085thon", "py\u0085thon"),
        ("Py\u001cthon", "py\u001cthon"),
        ("Py\u001dthon", "py\u001dthon"),
        ("Py\u001ethon", "py\u001ethon"),
        ("Py\u001fthon", "py\u001fthon"),
        ("Py  thon", "py  thon"),
        ("Py\tthon", "py\tthon"),
    ],
)
def test_workspace_normalization_uses_ecmascript_edge_trim(value, expected):
    from app.modules.marketdemandanalyst.workspace_patterns import _normalized_text

    assert _normalized_text(value) == expected


@pytest.mark.parametrize("metric,bounds,value", [("IM", (1, 5), 4), ("LV", (0, 7), 4)])
@pytest.mark.parametrize("identity", ["matching", "wrong", "missing"])
def test_reported_value_requires_matching_scale_identity(
    metric, bounds, value, identity
):
    from app.modules.marketdemandanalyst.workspace_patterns import reported_value

    rating = {
        "status": "reported",
        "value": value,
        "minimum": bounds[0],
        "maximum": bounds[1],
    }
    if identity != "missing":
        rating["scale_id"] = (
            metric if identity == "matching" else ("LV" if metric == "IM" else "IM")
        )
    evidence = {"ratings": {metric: rating}}
    before = json.loads(json.dumps(evidence))
    assert reported_value(evidence, metric) == (4.0 if identity == "matching" else None)
    assert evidence == before
