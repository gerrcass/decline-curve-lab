"""decline-curve-lab: seeded synthetic wells, decline-curve analysis, surveillance.

Only what exists today is exported. Metrics, the hyperbolic curve and model selection,
forecasts, EUR and lift screening arrive in later tickets and will be added here as
they land.
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
from decline_curve_lab.synthetic import (
    DEFAULT_SEED,
    DEFAULT_WELLS,
    WellSpec,
    generate_production,
    production_csv_bytes,
    write_sample_csv,
)

__all__ = [
    "DEFAULT_SEED",
    "DEFAULT_WELLS",
    "MONTHS_PER_YEAR",
    "PRODUCTION_COLUMNS",
    "SAMPLE_CSV_NAME",
    "SAMPLE_CSV_PATH",
    "SAMPLE_DATA_DIR",
    "ExponentialFit",
    "FitError",
    "SchemaError",
    "WellSpec",
    "effective_decline_from_nominal",
    "elapsed_months",
    "exponential_rate",
    "fit_exponential",
    "generate_production",
    "load_production",
    "positive_rate_mask",
    "production_csv_bytes",
    "to_years",
    "write_sample_csv",
]