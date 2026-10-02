"""decline-curve-lab: seeded synthetic wells, decline-curve analysis, surveillance.

Only what exists today is exported. Metrics, both Arps curves — the exponential and the
hyperbolic, with the decline-curve selection between them — and the lift-candidate
screening rules land here; forecasts and EUR arrive in later tickets and will be added
here as they land.
"""

from decline_curve_lab.arps import (
    CURVE_BY_OVERRIDE,
    CURVE_BY_RMSE,
    CURVE_ONLY_AVAILABLE,
    EXPONENTIAL_CURVE,
    HYPERBOLIC_CURVE,
    MAX_NOMINAL_DECLINE,
    MIN_CURVATURE,
    MIN_RELATIVE_RMSE_IMPROVEMENT,
    MONTHS_PER_YEAR,
    DeclineCurveSelection,
    ExponentialFit,
    FitError,
    HyperbolicFit,
    effective_decline_from_nominal,
    elapsed_months,
    exponential_rate,
    fit_exponential,
    fit_hyperbolic,
    hyperbolic_rate,
    positive_rate_mask,
    select_decline_curve,
    to_years,
)
from decline_curve_lab.io import (
    PRODUCTION_COLUMNS,
    SAMPLE_CSV_NAME,
    SAMPLE_CSV_PATH,
    SAMPLE_DATA_DIR,
    SchemaError,
    load_production,
)
from decline_curve_lab.metrics import METRIC_COLUMNS, compute_metrics
from decline_curve_lab.surveillance import (
    DEFAULT_HIGH_WATER_CUT,
    DEFAULT_LIFT_RATE_BBL_D,
    DEFAULT_PRESSURE_DECLINE_COUNT,
    LIFT_REASONS,
    LIFT_REASON_LABELS,
    LOW_RATE_HIGH_WATER_CUT,
    SUSTAINED_PRESSURE_DECLINE,
    flag_lift_candidates,
)
from decline_curve_lab.synthetic import (
    DEFAULT_SEED,
    DEFAULT_WELLS,
    WellSpec,
    generate_production,
    production_csv_bytes,
    write_sample_csv,
)

__all__ = [
    "CURVE_BY_OVERRIDE",
    "CURVE_BY_RMSE",
    "CURVE_ONLY_AVAILABLE",
    "DEFAULT_HIGH_WATER_CUT",
    "DEFAULT_LIFT_RATE_BBL_D",
    "DEFAULT_PRESSURE_DECLINE_COUNT",
    "DEFAULT_SEED",
    "DEFAULT_WELLS",
    "EXPONENTIAL_CURVE",
    "ExponentialFit",
    "FitError",
    "HYPERBOLIC_CURVE",
    "HyperbolicFit",
    "LIFT_REASONS",
    "LIFT_REASON_LABELS",
    "LOW_RATE_HIGH_WATER_CUT",
    "MAX_NOMINAL_DECLINE",
    "METRIC_COLUMNS",
    "MIN_CURVATURE",
    "MIN_RELATIVE_RMSE_IMPROVEMENT",
    "MONTHS_PER_YEAR",
    "PRODUCTION_COLUMNS",
    "SAMPLE_CSV_NAME",
    "SAMPLE_CSV_PATH",
    "SAMPLE_DATA_DIR",
    "SUSTAINED_PRESSURE_DECLINE",
    "SchemaError",
    "WellSpec",
    "compute_metrics",
    "effective_decline_from_nominal",
    "elapsed_months",
    "exponential_rate",
    "fit_exponential",
    "fit_hyperbolic",
    "flag_lift_candidates",
    "generate_production",
    "hyperbolic_rate",
    "load_production",
    "positive_rate_mask",
    "production_csv_bytes",
    "select_decline_curve",
    "to_years",
    "write_sample_csv",
]

assert __all__ == sorted(__all__), "__all__ must stay sorted with plain sorted()"