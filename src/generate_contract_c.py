
"""Generate Contract C from the real Contract A and B artifacts."""

import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
CONTRACTS = ROOT / "contracts"
DOCS = ROOT / "docs"

REQUIRED_B = {
    "segment_id", "test_year", "method", "risk_percentile",
    "confidence_label", "is_ood", "actual_break", "length_m",
}

CONTRACT_C_COLUMNS = [
    "test_year", "method", "ranking_mode", "segment_id",
    "priority_rank", "cumulative_length_m", "risk_percentile",
    "risk_pattern", "confidence_label", "consequence_index",
    "recommended_action", "reason_short", "actual_break",
]


def risk_pattern(row):
    """Assign a descriptive pattern, not a physical cause."""
    confidence = str(row["confidence_label"]).upper()

    if (
        confidence == "LOW"
        or bool(row["is_ood"])
        or bool(row.get("is_ambiguous_history", False))
    ):
        return "Data-poor"

    flags = str(row.get("data_quality_flags", "[]")).lower()
    if flags not in ("", "[]", "nan", "none") and flags != "null":
        return "Data-poor"

    nearby = row.get("nearby_prior_breaks")
    if pd.notna(nearby) and pd.to_numeric(nearby, errors="coerce") > 0:
        return "Spatial-cluster"

    prior = pd.to_numeric(
        row.get("prior_break_count"), errors="coerce"
    )
    if pd.notna(prior) and prior > 0:
        return "Repeat-break"

    age = pd.to_numeric(row.get("age_years"), errors="coerce")
    if pd.notna(age) and age >= 50:
        return "Age-led"

    material = str(row.get("material", "UNKNOWN")).strip().upper()
    if material not in ("", "UNKNOWN", "NAN", "NONE"):
        return "Material/cohort"

    return "General risk profile"



def action_and_reason(row):
    """Route actions using confidence, OOD status, and prior-break history."""
    confidence = str(row["confidence_label"]).strip().upper()
    is_ood = bool(row["is_ood"])
    prior_break_count = int(row["prior_break_count"])

    if (
        confidence == "HIGH"
        and not is_ood
        and prior_break_count >= 3
    ):
        return (
            "RENEWAL_REVIEW",
            "High confidence and at least three prior recorded breaks; "
            "refer for human-reviewed renewal assessment.",
        )

    if confidence in {"LOW", "MEDIUM"} or is_ood:
        return (
            "INSPECT",
            "Evidence is limited or unfamiliar; inspect and verify "
            "the asset record before capital decisions.",
        )

    if prior_break_count in {1, 2}:
        return (
            "INSPECT",
            "One or two prior recorded breaks; inspect and verify "
            "before deciding on further action.",
        )

    return (
        "MONITOR",
        "No repeated-break threshold met; continue routine monitoring "
        "and reassess as new evidence becomes available.",
    )


def recommend_action(row):
    confidence = str(row["confidence_label"]).strip().upper()
    is_ood = bool(row["is_ood"])
    prior_break_count = int(row["prior_break_count"])

    # 1. Renewal review requires strong confidence and repeated history.
    if (
        confidence == "HIGH"
        and not is_ood
        and prior_break_count >= 3
    ):
        return "RENEWAL_REVIEW"

    # 2. Uncertain or out-of-distribution pipes need inspection first.
    if confidence in {"LOW", "MEDIUM"} or is_ood:
        return "INSPECT"

    # 3. Some prior-break evidence warrants inspection.
    if prior_break_count in {1, 2}:
        return "INSPECT"

    # 4. Everything else is monitored.
    return "MONITOR"



def main():
    b_path = ARTIFACTS / "fold_predictions.parquet"
    a_path = ARTIFACTS / "pipe_year.parquet"

    b = pd.read_parquet(b_path)
    a = pd.read_parquet(a_path)

    missing = REQUIRED_B - set(b.columns)
    if missing:
        raise ValueError(f"Contract B missing columns: {sorted(missing)}")

    # Join point-in-time descriptive fields from Contract A.
    a_fields = [
        "segment_id", "score_year", "install_year", "age_years",
        "material", "prior_break_count", "years_since_last_break",
        "is_ambiguous_history", "data_quality_flags",
    ]
    if "nearby_prior_breaks" in a.columns:
        a_fields.append("nearby_prior_breaks")

    a_join = a[a_fields].copy()

    a_join = a_join.rename(columns={"score_year": "test_year"})

    if a_join.duplicated(["segment_id", "test_year"]).any():
        raise ValueError("Contract A has duplicate segment_id/test_year rows")
    
    joined = b.merge(
        a_join,
        on=["segment_id", "test_year"],
        how="left",
        validate="many_to_one",
        indicator=True,
    )

    unmatched = int((joined["_merge"] != "both").sum())
    if unmatched:
        raise ValueError(
            f"{unmatched} Contract B rows could not join to Contract A."
        )
    joined = joined.drop(columns="_merge")

    output = []

    # Each method retains Contract B's exact ranking order.
    for (year, method), group in joined.groupby(
        ["test_year", "method"], sort=True
    ):
        group = group.copy()
        group["segment_id"] = group["segment_id"].astype(str)
        group["confidence_label"] = (
            group["confidence_label"].astype(str).str.upper()
        )

        group = group.sort_values(
            ["risk_percentile", "segment_id"],
            ascending=[False, True],
            kind="stable",
        ).reset_index(drop=True)

        group["priority_rank"] = range(1, len(group) + 1)
        group["cumulative_length_m"] = group["length_m"].astype(float).cumsum()

        for _, row in group.iterrows():
            action, reason = action_and_reason(row)
            pattern = risk_pattern(row)
            action, reason = action_and_reason(row)

            output.append({
                "test_year": int(year),
                "method": str(method),
                "ranking_mode": "VALIDATED_RISK",
                "segment_id": str(row["segment_id"]),
                "priority_rank": int(row["priority_rank"]),
                "cumulative_length_m": float(row["cumulative_length_m"]),
                "risk_percentile": float(row["risk_percentile"]),
                "risk_pattern": pattern,
                "confidence_label": str(row["confidence_label"]),
                # Scenario scoring is disabled; this neutral value is not
                # used in ranking or action routing.
                "consequence_index": 0.0,
                "recommended_action": action,
                "reason_short": reason,
                "actual_break": int(row["actual_break"]),
            })

    result = pd.DataFrame(output, columns=CONTRACT_C_COLUMNS)

    if result.empty:
        raise ValueError("Generated Contract C is empty.")

    if result.duplicated(
        ["test_year", "method", "ranking_mode", "segment_id"]
    ).any():
        raise ValueError("Generated Contract C has duplicate keys.")

    if not result["recommended_action"].isin(
        {"MONITOR", "INSPECT", "RENEWAL_REVIEW"}
    ).all():
        raise ValueError("Generated Contract C has an invalid action.")

    # Safety assertion: no low-confidence or OOD renewal recommendations.
    check = result.merge(
        b[["segment_id", "test_year", "method", "is_ood"]],
        on=["segment_id", "test_year", "method"],
        how="left",
        validate="one_to_one",
    )
    unsafe = check["recommended_action"].eq("RENEWAL_REVIEW") & (
        check["confidence_label"].eq("LOW")
        | check["is_ood"].fillna(False).astype(bool)
    )
    if unsafe.any():
        raise ValueError("Unsafe RENEWAL_REVIEW recommendation detected.")

    # Reject causal language in explanations.
    forbidden = (
        "caused", "causes", "cause of", "root cause", "because of",
        "due to", "will fail", "will break", "leads to",
    )
    text = (
        result["risk_pattern"].astype(str)
        + " "
        + result["reason_short"].astype(str)
    ).str.lower()
    if any(text.str.contains(term, regex=False).any() for term in forbidden):
        raise ValueError("Causal language found in a risk explanation.")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    CONTRACTS.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)

    result.to_parquet(
        ARTIFACTS / "ranked_worklists.parquet", index=False
    )

    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "JagaPaip Contract C - Ranked Worklists",
        "version": "1.0",
        "type": "object",
        "description": "One row per segment, test year, method and ranking mode.",
        "properties": {
            "test_year": {"type": "integer"},
            "method": {"type": "string"},
            "ranking_mode": {
                "type": "string",
                "enum": ["VALIDATED_RISK", "SCENARIO_CONSEQUENCE"],
            },
            "segment_id": {"type": "string"},
            "priority_rank": {"type": "integer", "minimum": 1},
            "cumulative_length_m": {"type": "number"},
            "risk_percentile": {"type": "number", "minimum": 0, "maximum": 1},
            "risk_pattern": {"type": "string"},
            "confidence_label": {
                "type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]
            },
            "consequence_index": {
                "type": "number",
                "description": "Assumption-only field; 0.0 means no scenario applied.",
            },
            "recommended_action": {
                "type": "string",
                "enum": ["MONITOR", "INSPECT", "RENEWAL_REVIEW"],
            },
            "reason_short": {"type": "string"},
            "actual_break": {"type": "integer", "enum": [0, 1]},
            "geometry_wkt": {"type": ["string", "null"]},
        },
        "required": CONTRACT_C_COLUMNS,
        "additionalProperties": True,
    }
    (CONTRACTS / "ranked_worklists.schema.json").write_text(
        json.dumps(schema, indent=2) + "\n", encoding="utf-8"
    )

    policy = """# JagaPaip Decision Policy

## Validated risk worklists
Contract C preserves Contract B's ordering by risk_percentile descending,
then segment_id ascending. priority_rank and cumulative_length_m are
deterministic. Equal-budget selection uses the cumulative network length.

## Action routing
- HIGH confidence, not OOD, and at least 3 prior recorded breaks: RENEWAL_REVIEW.
- LOW or MEDIUM confidence, or OOD: INSPECT.
- 1–2 prior recorded breaks: INSPECT.
- Otherwise: MONITOR.

Action routing uses historical information available before the score date.
Risk percentile is a relative ranking, not a calibrated failure probability.
RENEWAL_REVIEW is for human assessment, not an automatic replacement decision.

## Descriptive patterns
Patterns summarize available records; they are not physical root causes.
Spatial-cluster is assigned only when nearby_prior_breaks is present and
positive. If the required evidence is absent, the pattern is not inferred.

## Scenario separation
SCENARIO_CONSEQUENCE is not generated by this script. consequence_index is
set to 0.0 for VALIDATED_RISK rows and does not affect ranking, actions, or
measured metrics. Any future consequence scenario must be visibly labelled
as assumption-based and kept separate from validated results.

## Limitations and display safety
actual_break is retained for internal evaluation and Proof Mode. The normal
worklist UI must hide it until the presenter reveals outcomes. Risk percentiles
are relative rankings, not probabilities. All actions require appropriate
human judgement and local asset knowledge.
"""
    (DOCS / "decision-policy.md").write_text(policy, encoding="utf-8")

    print(f"Created {len(result):,} Contract C rows.")
    print("Methods:", ", ".join(sorted(result["method"].unique())))
    print("Years:", ", ".join(map(str, sorted(result["test_year"].unique()))))
    print("Ranking modes:", ", ".join(sorted(result["ranking_mode"].unique())))
    print("Action counts:")
    print(result["recommended_action"].value_counts().to_string())
    print("Wrote artifacts/ranked_worklists.parquet")
    print("Wrote contracts/ranked_worklists.schema.json")
    print("Wrote docs/decision-policy.md")


if __name__ == "__main__":
    main()
