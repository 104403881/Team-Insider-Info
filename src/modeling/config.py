"""Frozen evaluation settings.

These mirror the kickoff decisions in TEAM_EXECUTION_PLAN.md sections 3-4.
Changing any of them changes measured results, so treat an edit as a
contract change and announce it in the team channel.
"""

SCHEMA_VERSION = "1.0"
SEED = 2026

TARGET = "target_next_year_break"

BUDGETS = (0.01, 0.02, 0.05, 0.10)
PRIMARY_BUDGET = 0.05
SELECTION_UNIT = "network_length_fraction"

BASELINE_METHODS = ("random", "oldest", "prior_breaks")
# Champion candidates, simplest first: this order breaks ties.
CANDIDATE_METHODS = ("oldest", "prior_breaks", "lookup", "logistic")
CONTRACT_METHODS = ("random", "oldest", "prior_breaks", "champion")

CHAMPION_SELECTION_RULE = (
    "highest mean capture_at_05 across test years among non-random methods; "
    "ties (equal to 4 d.p.) go to the simpler method"
)
SELECTION_RULE = (
    "within each test_year and method, sort by risk_percentile descending then "
    "segment_id ascending; select the longest prefix whose cumulative length_m "
    "does not exceed budget x total length_m of that year's eligible segments"
)

MIN_TRAIN_YEARS = 3
N_TEST_YEARS = 3

# Confidence: number of training pipe-years sharing the segment's
# material x installation decade.
HIGH_SUPPORT = 200
MEDIUM_SUPPORT = 30
AGE_RANGE_TOLERANCE_YEARS = 5


def budget_key(budget: float) -> str:
    """0.05 -> '05', as used in metric names such as capture_at_05."""
    return f"{round(budget * 100):02d}"


def budget_label(budget: float) -> str:
    """0.05 -> 'budget_0.05', as used for by_year keys in metrics.json."""
    return f"budget_{budget:.2f}"
