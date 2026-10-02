"""Screening rules that flag wells as lift candidates.

A **lift candidate** is a well that a simple screening rule flags as warranting
engineering review for artificial lift. The flag is a screening result for a human to
act on or dismiss: it is never a recommendation, never a decision to intervene in a
well, and never a substitute for the review it asks for.

The rule
========

One well is flagged when **either** of these holds on the well's **most recent
production period**:

1. **Low oil rate with high water cut** — ``qo`` below
   :data:`DEFAULT_LIFT_RATE_BBL_D` (100 bbl/d) **and** water cut ``fw`` above
   :data:`DEFAULT_HIGH_WATER_CUT` (0.7). Both halves must hold: a low rate on its own
   is a small well rather than a waterlogged one, and high water cut on its own is a
   well still making plenty of oil.
2. **A sustained wellhead-pressure decline** — wellhead pressure falling across
   :data:`DEFAULT_PRESSURE_DECLINE_COUNT` (3) consecutive production periods.

Why 100 bbl/d
=============

100 bbl/d is the conventional ~100 bbl/d screen for whether a well is a candidate for
artificial lift at all, and it is a **daily average** oil rate because every rate in
the production schema is a daily average over the production period (ADR-0002). That
makes ``qo < 100`` a comparison between two daily averages in the same unit. A monthly
volume read into the same comparison would be about thirty times too large and would
flag the whole fleet, so the threshold is stated in bbl/d and this module never divides
a rate by the length of a production period.

The pressure rule, exactly
==========================

"Falling across 3 consecutive production periods" means **three consecutive
period-over-period declines ending at the well's most recent production period**. With
``t`` the most recent production period of a well:

    whp[t-3] > whp[t-2] > whp[t-1] > whp[t]

Three declines are three comparisons, so the rule needs **four** observations to see
them. Two edges follow from "consecutive declines", and both are load-bearing:

- **Two declines do not flag.** A well that stepped down once or twice is being operated;
  flagging it would fill a reviewer's list with wells whose wellhead pressure recovered.
- **Equal pressures are not falling.** The comparison is strict, so a flat wellhead
  pressure can never accumulate declines no matter how many production periods show it.

The rule is read at the well's most recent production period, and a well with fewer
observations than the rule needs is **not** flagged. A well with three production
periods holds only two periods of change, so it cannot show three declines; there is
no shortened read of the rule and no exception for a young well. Silently treating a
short history as a decline would flag exactly the wells that have the least evidence
behind them.

Both edges are why the test suite pins two declines and four production periods as
opposite answers rather than treating "3 consecutive" as a phrase.

What is reported
================

:func:`flag_lift_candidates` returns **one row per well**, not one row per production
period, because the screen answers "which wells are lift candidates right now". Each
row carries the production period the rules were read from — ``latest_date`` — the three
measurements the rules read (``qo``, ``water_cut``, ``wellhead_pressure``), the
``candidate_lift`` boolean, and ``lift_reasons``: every reason that fired, not just the
first, so a reviewer sees the whole case at once. A well no rule reaches is still in the
frame, unflagged, with an empty tuple of reasons, so the screen reports on the fleet it
looked at rather than only on the wells that tripped something.

Wells are independent, so the screen reports one well's own production periods and
never another's. Production periods are sorted by well then date before the rules are
read, so which production period a well is screened on is its latest *date* and not
whichever period the production CSV happened to list last.
"""

from __future__ import annotations

import pandas as pd

from decline_curve_lab import io

__all__ = [
    "DEFAULT_HIGH_WATER_CUT",
    "DEFAULT_LIFT_RATE_BBL_D",
    "DEFAULT_PRESSURE_DECLINE_COUNT",
    "LIFT_REASON_LABELS",
    "LIFT_REASONS",
    "LOW_RATE_HIGH_WATER_CUT",
    "SCREENING_COLUMNS",
    "SCREENING_INPUT_COLUMNS",
    "SUSTAINED_PRESSURE_DECLINE",
    "flag_lift_candidates",
]

#: Oil rate, in bbl/d as a **daily average** (ADR-0002), below which a well combined
#: with high water cut is screened as a lift candidate. 100 bbl/d is the conventional
#: ~100 bbl/d artificial-lift screen, not a measured constant: it is the point at which
#: a well is producing too little for natural flow to lift the fluid column unaided, and
#: it is exposed as a parameter so a field can argue with it in one place.
DEFAULT_LIFT_RATE_BBL_D: float = 100.0

#: Water cut as a decimal in ``[0, 1]`` (never a percentage), above which a low oil rate
#: is read as waterlogged. 0.7 is the conventional "are we producing mostly water"
#: screen. Like the rate threshold it is a default and a parameter, not a law.
DEFAULT_HIGH_WATER_CUT: float = 0.7

#: Number of consecutive period-over-period wellhead-pressure declines that flag a well.
#: Three declines is four observations; two is a well being operated rather than a well
#: losing its pressure. See the module docstring for why the count is exact.
DEFAULT_PRESSURE_DECLINE_COUNT: int = 3

#: Reason recorded when the oil rate is below the rate threshold *and* the water cut is
#: above the water-cut threshold on the well's most recent production period.
LOW_RATE_HIGH_WATER_CUT: str = "low_rate_high_water_cut"

#: Reason recorded when wellhead pressure fell across
#: :data:`DEFAULT_PRESSURE_DECLINE_COUNT` consecutive production periods ending at the
#: well's most recent production period.
SUSTAINED_PRESSURE_DECLINE: str = "sustained_wellhead_pressure_decline"

#: Every reason the screen can record, in the order a row reports them. The order is the
#: rule's own order — rate and water cut first, pressure second — so a row reads the
#: same way every time.
LIFT_REASONS: tuple[str, ...] = (LOW_RATE_HIGH_WATER_CUT, SUSTAINED_PRESSURE_DECLINE)

#: Plain-English wording for each reason, so the words shown beside a flag live here
#: with the rule that fired rather than being retyped in whatever renders the screen.
LIFT_REASON_LABELS: dict[str, str] = {
    LOW_RATE_HIGH_WATER_CUT: "low oil rate with high water cut",
    SUSTAINED_PRESSURE_DECLINE: "sustained wellhead-pressure decline",
}

#: The columns the rules read: which well and which production period a production
#: period is, the oil rate and water cut the rate rule compares, and the wellhead
#: pressure the decline rule follows. ``water_cut`` is a derived column, so the input is
#: the frame :func:`decline_curve_lab.metrics.compute_metrics` produces.
SCREENING_INPUT_COLUMNS: tuple[str, ...] = (
    "well_id",
    "date",
    "qo",
    "water_cut",
    "wellhead_pressure",
)

#: The columns of the returned frame, in order: which well, the production period both
#: rules were read from, the three measurements they read, the flag, and its reasons.
SCREENING_COLUMNS: tuple[str, ...] = (
    "well_id",
    "latest_date",
    "qo",
    "water_cut",
    "wellhead_pressure",
    "candidate_lift",
    "lift_reasons",
)


def flag_lift_candidates(
    measured: pd.DataFrame,
    *,
    lift_rate_bbl_d: float = DEFAULT_LIFT_RATE_BBL_D,
    high_water_cut: float = DEFAULT_HIGH_WATER_CUT,
    pressure_declines: int = DEFAULT_PRESSURE_DECLINE_COUNT,
) -> pd.DataFrame:
    """Screen wells for lift candidacy, one row per well, with every reason recorded.

    A **lift candidate** is a screening flag for a human: this reports what a simple
    rule found, and a reviewer decides what it means for the well.

    Args:
        measured: Production periods carrying the derived metrics, as returned by
            :func:`decline_curve_lab.metrics.compute_metrics`, for one well or for
            many. ``water_cut`` is derived, so a bare production frame cannot be
            screened without it.
        lift_rate_bbl_d: Oil rate threshold in bbl/d, a **daily average** per
            ADR-0002. Defaults to :data:`DEFAULT_LIFT_RATE_BBL_D`.
        high_water_cut: Water-cut threshold as a decimal in ``[0, 1]`. Defaults to
            :data:`DEFAULT_HIGH_WATER_CUT`.
        pressure_declines: Consecutive wellhead-pressure declines that flag a well.
            ``n`` declines need ``n + 1`` production periods. Defaults to
            :data:`DEFAULT_PRESSURE_DECLINE_COUNT`.

    Returns:
        A new frame with one row per well, sorted by well id, holding
        :data:`SCREENING_COLUMNS`: the well id, the ``latest_date`` both rules were
        read from, the ``qo``, ``water_cut`` and ``wellhead_pressure`` at that
        production period, the ``candidate_lift`` boolean, and ``lift_reasons`` — a
        tuple of every reason that fired, empty when none did. The input is not
        mutated.

    Raises:
        SchemaError: A column the rules read is missing. The message names them.
        ValueError: ``pressure_declines`` is less than 1. A rule that cannot require a
            single decline would flag every well, including a constant pressure.
    """
    _require_columns(measured)
    if pressure_declines < 1:
        raise ValueError(
            f"pressure_declines must be at least 1, got {pressure_declines}; a rule "
            f"requiring no decline would flag every well"
        )

    # Sorted by well then date, so each well's most recent production period is the last
    # of its own production periods however the production CSV ordered them.
    ordered = measured.sort_values(["well_id", "date"], kind="mergesort").reset_index(
        drop=True
    )
    falling_pressure = _sustained_pressure_decline(ordered, pressure_declines)
    screened = (
        ordered.assign(falling_pressure=falling_pressure)
        .groupby("well_id", sort=True)
        .tail(1)
        .reset_index(drop=True)
        .rename(columns={"date": "latest_date"})
    )

    low_rate_high_water_cut = (screened["qo"] < lift_rate_bbl_d) & (
        screened["water_cut"] > high_water_cut
    )
    reasons = [
        tuple(reason for reason, reached in zip(LIFT_REASONS, flags) if reached)
        for flags in zip(low_rate_high_water_cut, screened["falling_pressure"])
    ]

    screened["candidate_lift"] = pd.Series(
        [bool(reached) for reached in reasons], index=screened.index, dtype="bool"
    )
    screened["lift_reasons"] = pd.Series(reasons, index=screened.index, dtype="object")

    return screened.loc[:, list(SCREENING_COLUMNS)]


def _require_columns(measured: pd.DataFrame) -> None:
    """Reject a frame the rules cannot be read from, naming what is missing."""
    missing = [
        column for column in SCREENING_INPUT_COLUMNS if column not in measured.columns
    ]
    if missing:
        raise io.SchemaError(
            f"production schema error: missing required column(s) {missing}; the "
            f"screening rules read {list(SCREENING_INPUT_COLUMNS)} from the frame "
            f"decline_curve_lab.metrics.compute_metrics returns"
        )


def _sustained_pressure_decline(ordered: pd.DataFrame, declines: int) -> pd.Series:
    """True on the production period ending ``declines`` consecutive pressure declines.

    For ``declines = 3`` this is ``whp[t-3] > whp[t-2] > whp[t-1] > whp[t]`` at the
    well's most recent production period ``t``: each step of the loop compares one
    production period against the one before it, within the well's own production
    periods.

    The comparisons are strict, so equal pressures are not a decline. A well with fewer
    production periods than the rule needs has no value for one of the lags, and a
    missing value compares false against every threshold — the same choice
    ``decline_curve_lab.metrics`` makes for an undefined ratio — so a well without the
    history to show the declines is left unflagged instead of being flagged by a
    shortened read of the rule.
    """
    wellhead_pressure = ordered["wellhead_pressure"]
    per_well = wellhead_pressure.groupby(ordered["well_id"], sort=False)
    falling = pd.Series(True, index=ordered.index)
    for step in range(1, declines + 1):
        falling &= per_well.shift(step) > per_well.shift(step - 1)
    return falling