"""decline-curve-lab: seeded synthetic wells, decline-curve analysis, surveillance.

Only what exists today is exported. Curve fits, forecasts, EUR and lift screening
arrive in later tickets and will be added here as they land.
"""

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
    "DEFAULT_SEED",
    "DEFAULT_WELLS",
    "METRIC_COLUMNS",
    "PRODUCTION_COLUMNS",
    "SAMPLE_CSV_NAME",
    "SAMPLE_CSV_PATH",
    "SAMPLE_DATA_DIR",
    "SchemaError",
    "WellSpec",
    "compute_metrics",
    "generate_production",
    "load_production",
    "production_csv_bytes",
    "write_sample_csv",
]