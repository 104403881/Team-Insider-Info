"""Shared column names, score bands, and file contracts.

Team artifacts can replace the demo tables without changing the UI.
Drop files into the data folder using the names below.
"""

from __future__ import annotations

PIPE_YEAR_FILE = "pipe_year.parquet"
PREDICTIONS_FILE = "fold_predictions.parquet"
METRICS_FILE = "metrics.json"
WORKLIST_FILE = "ranked_worklists.parquet"
FEATURES_FILE = "features.parquet"
OUTCOMES_FILE = "outcomes.parquet"
BREAKS_CLEAN_FILE = "breaks_clean.parquet"
PIPES_CLEAN_FILE = "pipes_clean.parquet"
MANIFEST_FILE = "manifest.json"

# Facts known at a decision year. Predictions and outcomes are added elsewhere.
FEATURE_COLUMNS = [
    "pipe_id",
    "zone",
    "material",
    "install_year",
    "length_m",
    "diameter_mm",
    "decision_year",
    "age_years",
    "historical_breaks",
]

# Columns that must never influence rank or budget selection.
FORBIDDEN_FIELDS = frozenset(
    {
        "future_breaks",
        "future_break_count",
        "outcome_breaks",
        "actual_breaks",
        "actual_outcome",
        "breaks_after",
        "y_true",
        "label",
        "target",
        "failure_after",
        "target_next_year_break",
        "target_break_count",
        "target_end_date",
        "outcome_coverage",
    }
)

PIPE_COLUMN_ALIASES = {
    "pipe_id": ["pipe_id", "segment_id", "asset_id", "pipeid", "facilityid", "watmainid", "id"],
    "year": ["year", "snapshot_year", "obs_year", "observation_year"],
    "material": ["material", "pipe_material", "mat", "material_type"],
    "install_year": ["install_year", "installation_year", "year_installed", "insyear", "year_inst"],
    "length_m": ["length_m", "length", "pipe_length", "shape_length", "length_metres"],
    "diameter_mm": ["diameter_mm", "pipe_size_mm", "diameter", "diam", "nominal_diameter", "diameter_nominal"],
    "break_count": ["break_count", "breaks", "n_breaks", "num_breaks", "failure_count", "n_failures"],
    "prior_break_count": ["prior_break_count", "historical_breaks"],
    "zone": ["zone", "district", "area", "pressure_zone", "neighbourhood"],
    "cost": ["cost", "replacement_cost", "cost_myr", "capital_cost", "renewal_cost"],
}

PREDICTION_COLUMN_ALIASES = {
    "pipe_id": ["pipe_id", "segment_id", "asset_id", "pipeid", "facilityid", "id"],
    "year": ["year", "decision_year", "eval_year", "as_of_year", "snapshot_year"],
    "predicted_risk": [
        "predicted_risk",
        "risk_score",
        "score",
        "pred",
        "y_pred",
        "prediction",
        "probability",
        "pred_prob",
    ],
    "fold": ["fold", "cv_fold", "split"],
}

# Screening heuristic weights. These are not a trained model.
MATERIAL_WEIGHTS = {
    "Cast Iron": 0.30,
    "Asbestos Cement": 0.24,
    "Ductile Iron": 0.14,
    "PVC": 0.06,
    "HDPE": 0.04,
    "Unknown": 0.12,
}

# Utility codes seen in the Kitchener inventory. Unlisted codes use Unknown.
MATERIAL_CODE_MAP = {
    "CI": "Cast Iron",
    "CAST IRON": "Cast Iron",
    "AC": "Asbestos Cement",
    "ASBESTOS CEMENT": "Asbestos Cement",
    "DI": "Ductile Iron",
    "DUCTILE IRON": "Ductile Iron",
    "PVC": "PVC",
    "PVCO": "PVC",
    "PVCB": "PVC",
    "PVCF": "PVC",
    "HDPE": "HDPE",
    "HDPE IN CI": "HDPE",
    "PE": "HDPE",
    "UNKNOWN": "Unknown",
    "XXX": "Unknown",
}

AGE_WEIGHT = 0.45
AGE_CAP_YEARS = 80
BREAK_WEIGHT = 0.25
BREAK_CAP = 5

# Action bands applied to whatever score is in use.
RENEWAL_THRESHOLD = 0.70
INSPECT_THRESHOLD = 0.45

ACTION_RENEWAL = "Renewal Review"
ACTION_INSPECT = "Inspect"
ACTION_MONITOR = "Monitor"

BAND_HIGH = "High"
BAND_MODERATE = "Moderate"
BAND_LOW = "Low"

PROOF_HORIZON_YEARS = 3
DEMO_DECISION_YEAR = 2024

STRATEGY_JAGAPAIP = "jagapaip"
STRATEGY_OLDEST = "oldest_first"
