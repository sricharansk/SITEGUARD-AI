"""Runs the offline evaluation and red-team suite (app/evaluation.py) as a CI gate."""

import pytest

from app import evaluation


@pytest.fixture(scope="module")
def result():
    return evaluation.run()


def test_safety_critical_gates(result):
    test = result["summary"]["test"]
    assert test["critical_underrated"] == 0, "a CRITICAL incident was rated LOW or MEDIUM"
    assert test["pipeline_invariants"] == 1.0
    assert result["redteam_contained"] == 1.0, [r for r in result["redteam"] if not r["contained"]]


def test_accuracy_regression_floor(result):
    test = result["summary"]["test"]
    # Floors sit just under the measured held-out numbers; raise them when the agents improve.
    assert test["class_accuracy"] >= 0.87
    assert test["domain_accuracy"] >= 0.91
    assert test["severity_within_one"] >= 0.95
    assert test["retrieval_hit_at_3"] >= 0.91


def test_every_class_is_in_the_gold_set(result):
    from app.agents import rules

    labelled = set(result["by_class"])
    assert set(rules.SAFETY_HAZARDS) | set(rules.QUALITY_DEFECTS) <= labelled


def test_report_renders(result):
    md = evaluation.to_markdown(result)
    assert "Pilot targets" in md and "Red-team suite" in md and "RT10" in md
