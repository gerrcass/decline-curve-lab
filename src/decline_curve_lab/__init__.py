"""decline-curve-lab: seeded synthetic wells, decline-curve analysis, surveillance.

Only what exists today is exported. Metrics and both Arps curves — the exponential and
the hyperbolic, with model selection between them — land here; forecasts, EUR and lift
screening arrive in later tickets and will be added here as they land.
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
    "DEFAULT_SEED",
    "DEFAULT_WELLS",
    "EXPONENTIAL_CURVE",
    "ExponentialFit",
    "FitError",
    "HYPERBOLIC_CURVE",
    "HyperbolicFit",
    "MAX_NOMINAL_DECLINE",
    "METRIC_COLUMNS",
    "MIN_CURVATURE",
    "MIN_RELATIVE_RMSE_IMPROVEMENT",
    "MONTHS_PER_YEAR",
    "PRODUCTION_COLUMNS",
    "SAMPLE_CSV_NAME",
    "SAMPLE_CSV_PATH",
    "SAMPLE_DATA_DIR",
    "SchemaError",
    "WellSpec",
    "compute_metrics",
    "effective_decline_from_nominal",
    "elapsed_months",
    "exponential_rate",
    "fit_exponential",
    "fit_hyperbolic",
    "generate_production",
    "hyperbolic_rate",
    "load_production",
    "positive_rate_mask",
    "production_csv_bytes",
    "select_decline_curve",
    "to_years",
    "write_sample_csv",
]