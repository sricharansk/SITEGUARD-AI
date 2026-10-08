"""Deterministic risk engine (docs/AGENTS.md#risk-engine).

AI agents may *suggest* likelihood and consequence, but the score and band always come from this
versioned matrix, so identical inputs always give identical, explainable results.
"""

from dataclasses import dataclass

MATRIX_VERSION = "5x5-v1"

LIKELIHOOD = {1: "Rare", 2: "Unlikely", 3: "Possible", 4: "Likely", 5: "Almost certain"}
CONSEQUENCE = {1: "Insignificant", 2: "Minor", 3: "Moderate", 4: "Major", 5: "Catastrophic"}

# Inclusive upper bound of each band's score.
BANDS: list[tuple[int, str]] = [(4, "LOW"), (9, "MEDIUM"), (16, "HIGH"), (25, "CRITICAL")]


@dataclass(frozen=True)
class RiskResult:
    matrix_version: str
    likelihood: int
    consequence: int
    score: int
    band: str
    rationale: str


def assess(likelihood: int, consequence: int) -> RiskResult:
    if not isinstance(likelihood, int) or isinstance(likelihood, bool) or likelihood not in LIKELIHOOD:
        raise ValueError("likelihood must be an integer 1-5")
    if not isinstance(consequence, int) or isinstance(consequence, bool) or consequence not in CONSEQUENCE:
        raise ValueError("consequence must be an integer 1-5")
    score = likelihood * consequence
    band = next(name for upper, name in BANDS if score <= upper)
    rationale = (
        f"Likelihood {likelihood} ({LIKELIHOOD[likelihood]}) x consequence {consequence} "
        f"({CONSEQUENCE[consequence]}) = {score}, which is {band} on matrix {MATRIX_VERSION} "
        f"(LOW <=4, MEDIUM <=9, HIGH <=16, CRITICAL >=17)."
    )
    return RiskResult(MATRIX_VERSION, likelihood, consequence, score, band, rationale)


def matrix() -> list[list[str]]:
    """Full matrix (rows = likelihood 1..5, cols = consequence 1..5) for display and tests."""
    return [[assess(lk, c).band for c in range(1, 6)] for lk in range(1, 6)]
