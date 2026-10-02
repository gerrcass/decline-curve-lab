"""Derived metrics for each production period: water cut, GOR and cumulative oil.

One call adds three columns to the production periods of every well:

``water_cut``
    The glossary's ``fw``: the fraction of total **liquid** that is water,
    ``qw / (qo + qw)``, as a decimal in ``[0, 1]`` and never a percentage.
``GOR``
    The glossary's gas-oil ratio, ``qg / qo``, in scf/bbl.
``Np``
    The glossary's cumulative oil: the running total of oil the well has produced,
    in bbl.

Units come straight from ADR-0002: ``qo`` and ``qw`` are bbl/d and ``qg`` is scf/d, so
water cut and GOR are ratios of rates and need no conversion, while cumulative oil has
to integrate a rate over time.

Cumulative oil and the days-per-production-period rule
======================================================

Cumulative oil is a volume, and the production schema stores rates, so each
production period's volume is ``rate * the length of that production period``. A
production period is a calendar month and the ``date`` column gives its first day, so
the length comes from the date itself: 28, 29, 30 or 31 days, never a constant.

    volume over a production period [bbl] = qo [bbl/d] * days in that month [d]
    Np at a production period              = running sum of those volumes

This is the one rule this project uses for every monthly series, so a well's
cumulative oil, its forecast and its EUR all sit on one basis that a hand
calculation can check. EIA normalises every month to 30.4 days; we do not, because
our ``date`` column is exact.

Rows are sorted by well then date before the running total is taken, so
cumulative oil does not depend on the order a production CSV happens to list its
production periods in, and each well accumulates over **its own** production periods
only — wells are independent, so one well's production never appears in another's
``Np``.

Undefined edges
===============

A shut-in or water-only production period has real rates but no oil, and its ratios
are undefined rather than infinite. Two cases matter, and both are handled without
dividing by zero:

- ``qo + qw == 0`` — the production period produced no liquid at all, so there is no
  fraction of anything: ``water_cut`` is ``NaN``. (The all-liquid edge, ``qw == 0``,
  is ``0.0`` and the all-water edge, ``qo == 0``, is ``1.0``; both are exact.)
- ``qo == 0`` — there are no barrels of oil for the gas to be measured against, so
  ``GOR`` is ``NaN``.

``NaN`` is used rather than ``inf`` because an infinite gas-oil ratio would read as
"very gassy" and pull up any average it took part in, and because a missing value
compares false against every threshold a later screening rule might apply. A
production period with no oil contributes nothing to ``Np``, since its volume is zero.

``compute_metrics`` does not mutate its input, and returns its production periods in
canonical order — by well, then by date — so a caller that wants one well's history
in time order gets it without sorting again.
"""

from __future__ import annotations

import pandas as pd

from decline_curve_lab import io

__all__ = [
    "METRIC_COLUMNS",
    "compute_metrics",
]

#: The derived columns :func:`compute_metrics` adds to every production period, in the
#: order they are added.
METRIC_COLUMNS: tuple[str, ...] = ("water_cut", "GOR", "Np")

#: The columns the metrics are derived from: which well and which production period a
#: row is, and the daily-average rates behind each ratio.
DERIVED_FROM_COLUMNS: tuple[str, ...] = ("well_id", "date", "qo", "qw", "qg")


def compute_metrics(production: pd.DataFrame) -> pd.DataFrame:
    """Add water cut, gas-oil ratio and cumulative oil to every production period.

    Args:
        production: Production periods as returned by
            :func:`decline_curve_lab.io.load_production`, for one well or for many.
            ``date`` must be ``datetime64`` and the rates ``float64``, which is what
            the reader guarantees; the metrics are meaningless on any other basis.

    Returns:
        A new frame holding the input's production periods plus :data:`METRIC_COLUMNS`,
        with its production periods sorted by well then by date. ``water_cut`` is a
        decimal in ``[0, 1]``, ``GOR`` is scf/bbl and ``Np`` is bbl of oil produced
        cumulatively over **that well's own** production periods.

    Raises:
        SchemaError: A column the metrics are derived from is missing. The message
            names the offending columns.
    """
    _require_columns(production)
    ordered = production.sort_values(["well_id", "date"], kind="mergesort").reset_index(
        drop=True
    )
    liquid = ordered["qo"] + ordered["qw"]
    return ordered.assign(
        water_cut=_share(ordered["qw"], liquid),
        GOR=_share(ordered["qg"], ordered["qo"]),
        Np=_cumulative_oil(ordered),
    )


def _require_columns(production: pd.DataFrame) -> None:
    """Reject a frame the metrics cannot be derived from, naming what is missing."""
    missing = [
        column for column in DERIVED_FROM_COLUMNS if column not in production.columns
    ]
    if missing:
        raise io.SchemaError(
            f"production schema error: missing required column(s) {missing}; "
            f"the metrics are derived from {list(DERIVED_FROM_COLUMNS)}"
        )


def _share(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide two rate series, leaving a zero denominator undefined, not infinite.

    Both sides of every ratio here are daily-average rates, so the ratio is a pure
    dimensionless quantity. A zero denominator means the ratio has no value — a
    production period with no liquid to share, or no oil to measure gas against — and
    is reported as ``NaN`` instead of ``inf``.
    """
    return numerator.div(denominator.where(denominator.ne(0.0)))


def _cumulative_oil(ordered: pd.DataFrame) -> pd.Series:
    """Cumulative oil in bbl, accumulated over each well's own production periods.

    The production periods are already sorted by well then date, so one grouped
    running sum per well is all the accumulation needed: the group boundary restarts
    the total, which is what keeps one well's production out of another's ``Np``.
    """
    period_days = ordered["date"].dt.days_in_month
    volume = ordered["qo"] * period_days
    return volume.groupby(ordered["well_id"], sort=False).cumsum()
