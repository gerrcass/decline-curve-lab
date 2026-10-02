"""decline-curve-lab: seeded synthetic wells, decline-curve analysis, surveillance.

Only what exists today is exported. Metrics, both Arps curves — the exponential and the
hyperbolic, with the decline-curve selection between them — the lift-candidate screening
rules land here, along with the EUR, the fleet EUR table and the terminal-decline switch
they depend on.

The oil-rate forecast itself is **not** re-exported here, because ``forecast`` is already
the name of this package's forecast module and a package attribute cannot be both the
module and the function inside it. Call it as ``decline_curve_lab.forecast.forecast(...)``;
everything else in that module — the terminal-decline switch, the documented defaults,
``eur`` and ``eur_table`` — is available here.
"""

import inspect

from decline_curve_lab.arps import (
    CURVATURE_CEILING_BOUND,
    CURVATURE_FLOOR_BOUND,
    CURVE_BY_OVERRIDE,
    CURVE_BY_RMSE,
    CURVE_ONLY_AVAILABLE,
    EXPONENTIAL_CURVE,
    HYPERBOLIC_CURVE,
    MAX_NOMINAL_DECLINE,
    MIN_CURVATURE,
    MIN_NOMINAL_DECLINE,
    MIN_RELATIVE_RMSE_IMPROVEMENT,
    NOMINAL_DECLINE_CEILING_BOUND,
    NOMINAL_DECLINE_FLOOR_BOUND,
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
from decline_curve_lab.forecast import (
    DEFAULT_ECONOMIC_LIMIT_RATE_BBL_D,
    DEFAULT_FORECAST_MONTHS,
    DEFAULT_MAX_HORIZON_MONTHS,
    DEFAULT_TERMINAL_DECLINE_ANNUAL,
    EUR_COLUMN,
    EUR_STOP_LABELS,
    EUR_TABLE_COLUMNS,
    EUR_TABLE_INPUT_COLUMNS,
    FORECAST_COLUMNS,
    EurEstimate,
    Forecast,
    STOP_AT_ECONOMIC_LIMIT,
    STOP_AT_HORIZON_CAP,
    TerminalSwitch,
    decline_curvature,
    eur,
    eur_table,
    terminal_switch,
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
    "CURVATURE_CEILING_BOUND",
    "CURVATURE_FLOOR_BOUND",
    "CURVE_BY_OVERRIDE",
    "CURVE_BY_RMSE",
    "CURVE_ONLY_AVAILABLE",
    "DEFAULT_ECONOMIC_LIMIT_RATE_BBL_D",
    "DEFAULT_FORECAST_MONTHS",
    "DEFAULT_HIGH_WATER_CUT",
    "DEFAULT_LIFT_RATE_BBL_D",
    "DEFAULT_MAX_HORIZON_MONTHS",
    "DEFAULT_PRESSURE_DECLINE_COUNT",
    "DEFAULT_SEED",
    "DEFAULT_TERMINAL_DECLINE_ANNUAL",
    "DEFAULT_WELLS",
    "DeclineCurveSelection",
    "EUR_COLUMN",
    "EUR_STOP_LABELS",
    "EUR_TABLE_COLUMNS",
    "EUR_TABLE_INPUT_COLUMNS",
    "EXPONENTIAL_CURVE",
    "EurEstimate",
    "ExponentialFit",
    "FORECAST_COLUMNS",
    "FitError",
    "Forecast",
    "HYPERBOLIC_CURVE",
    "HyperbolicFit",
    "LIFT_REASONS",
    "LIFT_REASON_LABELS",
    "LOW_RATE_HIGH_WATER_CUT",
    "MAX_NOMINAL_DECLINE",
    "METRIC_COLUMNS",
    "MIN_CURVATURE",
    "MIN_NOMINAL_DECLINE",
    "MIN_RELATIVE_RMSE_IMPROVEMENT",
    "MONTHS_PER_YEAR",
    "NOMINAL_DECLINE_CEILING_BOUND",
    "NOMINAL_DECLINE_FLOOR_BOUND",
    "PRODUCTION_COLUMNS",
    "SAMPLE_CSV_NAME",
    "SAMPLE_CSV_PATH",
    "SAMPLE_DATA_DIR",
    "STOP_AT_ECONOMIC_LIMIT",
    "STOP_AT_HORIZON_CAP",
    "SUSTAINED_PRESSURE_DECLINE",
    "SchemaError",
    "TerminalSwitch",
    "WellSpec",
    "compute_metrics",
    "decline_curvature",
    "effective_decline_from_nominal",
    "elapsed_months",
    "eur",
    "eur_table",
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
    "terminal_switch",
    "to_years",
    "write_sample_csv",
]

assert __all__ == sorted(__all__), "__all__ must stay sorted with plain sorted()"

# The ordering assert above cannot catch the bug that actually happened here: a public name
# imported into the package and left out of `__all__` is still sorted *correctly* by
# omission, and is reachable as an attribute while being invisible to `import *` and to any
# documentation tool. So the second half of the invariant is stated too — every public name
# the package binds is exported. Submodules are the one deliberate exception, reached as
# `decline_curve_lab.arps` rather than imported by name.
_UNEXPORTED = sorted(
    name
    for name, value in vars().items()
    if not name.startswith("_") and not inspect.ismodule(value) and name not in __all__
)
assert not _UNEXPORTED, (
    "every public name the package binds must be in __all__; missing: " f"{_UNEXPORTED}"
)
