"""decline-curve-lab: seeded synthetic wells, decline-curve analysis, surveillance.

Only what exists today is exported. Metrics, the exponential Arps curve and the
lift-candidate screening rules land here; the hyperbolic curve and model selection, and
forecasts and EUR, arrive in later tickets and will be added here as they land.
"""

from decline_curve_lab.arps import (
    MONTHS_PER_YEAR,
    ExponentialFit,
    FitError,
    effective_decline_from_nominal,
    elapsed_months,
    exponential_rate,
    fit_exponential,
    positive_rate_mask,
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
    "DEFAULT_HIGH_WATER_CUT",
    "DEFAULT_LIFT_RATE_BBL_D",
    "DEFAULT_PRESSURE_DECLINE_COUNT",
    "DEFAULT_SEED",
    "DEFAULT_WELLS",
    "ExponentialFit",
    "FitError",
    "LIFT_REASONS",
    "LIFT_REASON_LABELS",
    "LOW_RATE_HIGH_WATER_CUT",
    "METRIC_COLUMNS",
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
    "flag_lift_candidates",
    "generate_production",
    "load_production",
    "positive_rate_mask",
    "production_csv_bytes",
    "to_years",
    "write_sample_csv",
]