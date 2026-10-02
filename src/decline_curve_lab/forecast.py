"""Oil-rate forecast and EUR for one well, on the well's own calendar.

The forecast window
===================

:func:`forecast` projects the well's decline curve onto **the production periods after
the well's most recent one**. For a well whose production periods end at ``t = n - 1``,
the twelve-month forecast is ``t = n .. n + 11``. The projection therefore starts where
the data stops, not where the fitted window started: ``qi`` is defined at ``t = 0``, so
a forecast placed at ``t = 0`` would be a statement about the past.

One production period is a calendar month, so every forecast row carries the ``date`` of
the month it stands for, built from the well's **own** first production period. And
because a rate in this project is a **daily average** (ADR-0002) while a volume is not,
each row's volume is the production period's calendar length times its rate:

    volume over a production period [bbl] = qo [bbl/d] * days in that month [d]

which is the same rule ``decline_curve_lab.metrics`` applies to cumulative oil ``Np``, so
a well's observed ``Np`` and its forecast volumes sit on one basis that a hand
calculation can check either of them against. EIA normalises every month to 30.4 days;
this project does not, because the ``date`` column is exact.

The terminal decline
====================

A hyperbolic decline curve has no end: it keeps a well producing at a decreasing rate
forever, so a forecast that simply ran it would overstate the long tail of recovery. The
EIA convention therefore ends the hyperbolic phase and continues on an **exponential
tail** once the decline has fallen to a **terminal decline** of 10 % nominal per year
(ADR-0001; ``docs/research/eia-terminal-decline-convention.md``, which confirms the
threshold is nominal and not effective, and records EIA's own printed "0.8 %/month" as
``0.10/12``).

The instantaneous decline of the hyperbolic is ``D(t) = D_eff / (1 + b * D_eff * t)``,
so the switch is where that reaches the terminal decline, and everything else follows
from that one moment:

    D_tail_eff = ln(1 + terminal_decline_annual)     # ln(1.10) = 0.0953102 /yr
    t_switch   = (D_eff / D_tail_eff - 1) / (b * D_eff)          # years, from t = 0
    q_switch   = qi * (D_eff / D_tail_eff) ** (-1 / b)           # exact: 1 + b*D_eff*t_sw
    q(t) = hyperbolic(t)                                        t <= t_switch
    q(t) = q_switch * exp(-D_tail_eff * (t - t_switch))         t >  t_switch

Three properties of that construction are load-bearing and each is pinned by a test:

* **The tail is ``exp``, not a second harmonic.** Both phases then have the *same*
  decline rate at the switch, so ``ln q`` is C1 across it — only curvature changes. A
  ``(1 + D_tail_eff * (t - t_switch)) ** -1`` tail would put a kink in the slope.
* **The tail is never re-anchored to ``qi``.** It continues from the rate the hyperbolic
  had actually reached by then, which for a well that has been declining for years is a
  small fraction of ``qi``; re-anchoring would multiply the forecast by two or three.
* **There is no switch at all** when the curve has no hyperbolic phase: ``b == 0`` is
  already the exponential, and a ``Di`` at or below the terminal decline means the well
  is at the threshold at ``t = 0``.

The threshold is a **parameter with a documented default**, not a constant buried in the
forecaster, so a project that believes EIA's convention is wrong can change it in one
place without touching the arithmetic.

The EUR ends at the economic limit rate
======================================

:func:`eur` integrates the fitted decline curve from ``t = 0`` until the curve reaches
the **economic limit rate**, and never toward zero (ADR-0003). Below that rate the well
is not producing, it is costing money, and crediting that production to it overstates its
recovery; "dead" here means *below the economic limit rate*, which is a rate and not a
decision to abandon the well.

    EUR = sum over the integrated production periods of  qo [bbl/d] * days in that month

— the same days-per-period rule the forecast uses and ``metrics`` applies to ``Np``, so a
hand calculation can check any of the three off one rule.

The economic limit rate and a horizon cap both apply, and the EUR stops at whichever
binds first:

* ``economic_limit_rate_bbl_d``, default **1.0 bbl/d**. About 1 % of the 100 bbl/d
  lift-screening threshold, so a plausible rate for a mature well that has already lost
  interest to artificial lift, and it keeps EUR numbers in the same order of magnitude as
  the rest of the project. A parameter rather than a constant because the honest value
  depends on oil price, operating cost and lift method — all of which are out of scope
  here, so this project can parameterise the limit but cannot derive it.
* ``max_horizon_months``, default **360** (30 years, matching EIA), which bounds the
  hyperbolic and harmonic tails. A hyperbolic curve integrated to the economic limit rate
  is finite, but without the terminal switch an unswitched hyperbolic or harmonic is not,
  and the cap is what makes the result a number rather than a divergence.

The terminal switch applies to the EUR as well, and it is what keeps a long tail from
dominating it: a well whose hyperbolic would run for centuries is handed to the
exponential tail first. Note where the switch lands — **no Arps curve can reach its
terminal decline sooner than ``1 / D_tail_eff = 10.5`` years**, at ``b = 1`` with a very
steep ``Di``, so a well with three to six years of history cannot have reached it however
fast it declines. That is inside a 30-year horizon, which means the switch usually shapes
the EUR, while the economic limit rate at 1 bbl/d is often not reached inside 30 years at
all and the **horizon cap** is then what ends the integration.
:attr:`EurEstimate.stop_reason` says which, and
:attr:`EurEstimate.terminal_switch_bounds_eur` whether the tail was inside the integrated
span.

Time is in production periods everywhere in this module's interface. It reaches ``arps``
that way and is converted to years there, once, so ``Di * t`` stays dimensionless
(ADR-0001) and nothing here converts a time axis twice.

The fleet table
===============

:func:`eur_table` is the fleet-wide comparison: one row per well with its decline curve,
its parameters, its EUR and what stopped it, **ordered in the library**. Sorting lives here
rather than in the dashboard on purpose — an app that re-sorted the returned rows would
have two places where "largest EUR first" is written down, and they would eventually
disagree. ``sort_by`` and ``descending`` are therefore arguments, so a sort control in the
app is a pair of values passed in and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from decline_curve_lab import arps, io

__all__ = [
    "DEFAULT_ECONOMIC_LIMIT_RATE_BBL_D",
    "DEFAULT_FORECAST_MONTHS",
    "DEFAULT_MAX_HORIZON_MONTHS",
    "DEFAULT_TERMINAL_DECLINE_ANNUAL",
    "EUR_COLUMN",
    "EUR_STOP_LABELS",
    "EUR_TABLE_COLUMNS",
    "EUR_TABLE_INPUT_COLUMNS",
    "FORECAST_COLUMNS",
    "Forecast",
    "EurEstimate",
    "STOP_AT_ECONOMIC_LIMIT",
    "STOP_AT_HORIZON_CAP",
    "TerminalSwitch",
    "decline_curvature",
    "eur",
    "eur_table",
    "forecast",
    "terminal_switch",
]

#: How many production periods a forecast covers by default: twelve, i.e. one year.
DEFAULT_FORECAST_MONTHS: int = 12

#: The terminal decline a forecast switches to an exponential tail at, as a **nominal
#: fraction per year**: 0.10 is EIA's 10 %/yr ("0.8 %/month", which is ``0.10/12``).
#: Nominal, not effective, per ADR-0001 and the research note that confirms it. The
#: effective equivalent ``ln(1.10) = 0.0953102`` is derived inside this module only and
#: never stored or reported. Exposed as a parameter because a project that disagrees with
#: the convention can then change it without touching the forecaster.
DEFAULT_TERMINAL_DECLINE_ANNUAL: float = 0.10

#: The columns a forecast carries, in order: the calendar month the production period
#: stands for, its elapsed time from the well's own ``t = 0``, the forecast oil rate in
#: bbl/d (a daily average, ADR-0002), and the volume that rate makes over that month's
#: length.
FORECAST_COLUMNS: tuple[str, ...] = ("date", "elapsed_months", "qo", "volume_bbl")

#: The oil rate, bbl/d, below which producing the well stops being worthwhile and the EUR
#: is cut off (ADR-0003). 1.0 bbl/d is the project's reconciled default: about 1 % of the
#: 100 bbl/d lift-screening threshold, so a plausible rate for a mature well that has
#: already lost interest to artificial lift, and it keeps EUR numbers in the same order of
#: magnitude as the rest of the project. A parameter and not a constant, because the
#: honest value depends on oil price, operating cost and lift method — all out of scope
#: here, so this project can parameterise the economic limit but cannot derive it.
DEFAULT_ECONOMIC_LIMIT_RATE_BBL_D: float = 1.0

#: The longest EUR, in production periods: 360, i.e. 30 years, which is EIA's own horizon
#: cap. It bounds the hyperbolic and harmonic tails, which would otherwise keep
#: accumulating. The EUR stops at whichever of this and the economic limit rate comes
#: first, and reports which.
DEFAULT_MAX_HORIZON_MONTHS: int = 360

#: Why an EUR stopped where it did. Both are real outcomes and a caller has to tell them
#: apart: an economic-limit stop means the well was dead, a cap stop means the model ran
#: out of horizon first and the well was still producing.
STOP_AT_ECONOMIC_LIMIT: str = "economic_limit_rate"
STOP_AT_HORIZON_CAP: str = "horizon_cap"

#: Wording for each stop reason, so the sentences shown beside an EUR live here with the
#: rule that produced them rather than being retyped in whatever renders the estimate.
EUR_STOP_LABELS: dict[str, str] = {
    STOP_AT_ECONOMIC_LIMIT: "the curve reached the economic limit rate",
    STOP_AT_HORIZON_CAP: "the horizon cap was reached first",
}

#: The EUR column of the fleet table, in bbl, and the column it is ordered by by default:
#: the comparison an analyst opens the table to make.
EUR_COLUMN: str = "eur_bbl"

#: The columns :func:`eur_table` reads: which well and which production period a production
#: period is, and the daily-average oil rate the decline curve is fitted to. It is the
#: production schema itself, so the frame :func:`decline_curve_lab.io.load_production`
#: returns can be handed over as it stands.
EUR_TABLE_INPUT_COLUMNS: tuple[str, ...] = ("well_id", "date", "qo")

#: The columns of the fleet table, in order: which well, which Arps curve its decline
#: curve is and how that was chosen, its three fitted parameters, the RMSE of the selected
#: curve in bbl/d, its EUR in bbl, the economic limit rate that EUR was cut at, and what
#: stopped it.
EUR_TABLE_COLUMNS: tuple[str, ...] = (
    "well_id",
    "curve",
    "chosen_by",
    "qi",
    "Di",
    "b",
    "rmse_bbl_d",
    EUR_COLUMN,
    "economic_limit_rate_bbl_d",
    "stop_reason",
)

#: A decline curve as ``arps`` hands it over: a selection (which curve was chosen and
#: why), or one fitted curve on its own. Both expose ``qi``, ``Di`` and ``rate_at``, and
#: the exponential exposes no ``b`` — which is exactly what "exponential" means, since
#: its decline curvature is ``b = 0``. Accepting both is what lets a forecast read the
#: parameters off the curve without branching on which curve it is.
DeclineCurve = arps.DeclineCurveSelection | arps.ExponentialFit | arps.HyperbolicFit


def decline_curvature(curve: DeclineCurve) -> float:
    """The decline curvature ``b`` of a decline curve, with the exponential's ``0.0``.

    A ``DeclineCurveSelection`` already reports ``b = 0.0`` for the exponential, and an
    ``ExponentialFit`` has no ``b`` at all because ``b = 0`` is what makes it the
    exponential. Both routes land on the same number, so nothing downstream has to ask
    which kind of curve it is holding.

    Args:
        curve: A decline curve, or a selection of one.

    Returns:
        The decline curvature: ``0.0`` for the exponential, else the fitted ``b``.
    """
    return float(getattr(curve, "b", 0.0))


def terminal_switch(
    curve: DeclineCurve, terminal_decline_annual: float = DEFAULT_TERMINAL_DECLINE_ANNUAL
) -> TerminalSwitch | None:
    """Where this decline curve hands over to an exponential tail, and at what rate.

    The EIA convention's switch, exactly as the module docstring states it: the
    hyperbolic runs until its own instantaneous decline ``D(t) = D_eff / (1 + b * D_eff *
    t)`` reaches the terminal decline, and the tail continues from the rate reached
    there. Both phases are derived from the nominal declines, with the effective rates
    derived here *after* the time unit is fixed in years — ``ln(1 + x)`` does not commute
    with a change of time unit, which is the one dimensional trap in this domain.

    Args:
        curve: The decline curve whose switch time is wanted.
        terminal_decline_annual: The terminal decline as a nominal fraction per year.
            Defaults to :data:`DEFAULT_TERMINAL_DECLINE_ANNUAL`.

    Returns:
        A :class:`TerminalSwitch` with the elapsed time and the rate at the switch, or
        ``None`` when there is no hyperbolic phase to switch out of. Two different
        reasons produce that ``None`` and a caller has to tell them apart, so
        ``decline_curvature(curve)`` answers it: the exponential Arps curve (``b == 0``)
        already is the tail, while a decline at or below the terminal decline has reached
        the threshold at ``t = 0`` and is forecast as the exponential from the start.
        ``None`` rather than a switch at ``t = 0``, because "the switch is at the start"
        is not the same claim as "there is no switch", and only one of them is right.

    Raises:
        ValueError: ``terminal_decline_annual`` is negative, so the "tail" would be a
            rising rate.
    """
    _require_terminal_decline(terminal_decline_annual)
    b = decline_curvature(curve)
    di_nominal = float(curve.Di)
    # One comparison of the nominal declines: `ln(1 + x)` is strictly increasing, so
    # `Di <= terminal` and `D_eff <= D_tail_eff` are the same statement, and the nominal
    # one is the one the convention is written in.
    if b == 0.0 or di_nominal <= terminal_decline_annual:
        return None

    d_eff = arps.effective_decline_from_nominal(di_nominal)
    tail_eff = arps.effective_decline_from_nominal(terminal_decline_annual)
    t_switch_years = (d_eff / tail_eff - 1.0) / (b * d_eff)
    return TerminalSwitch(
        t_switch_years=t_switch_years,
        q_switch_bbl_d=float(
            curve.rate_at(t_switch_years * arps.MONTHS_PER_YEAR)
        ),
        terminal_decline_annual=float(terminal_decline_annual),
    )


def forecast(
    curve: DeclineCurve,
    production_periods: pd.DataFrame | pd.Timestamp | str,
    *,
    months: int = DEFAULT_FORECAST_MONTHS,
    terminal_decline_annual: float = DEFAULT_TERMINAL_DECLINE_ANNUAL,
) -> Forecast:
    """Project a well's decline curve onto the production periods after its last one.

    The hyperbolic case hands over to an exponential tail at the **terminal decline**
    (the module docstring has the formulas and the three guards); every other case — the
    exponential Arps curve, or a decline already at or below the terminal decline — is
    projected unchanged, and nothing here branches on which curve it is holding.

    Args:
        curve: The well's decline curve: a ``DeclineCurveSelection`` from
            ``arps.select_decline_curve``, or one fitted curve on its own. Whatever is
            passed in is what the forecast follows, so an analyst's override is
            honoured by passing the overridden selection.
        production_periods: The well's production periods as
            ``decline_curve_lab.io.load_production`` returns them, from which the
            forecast's calendar is taken: the earliest ``date`` is the well's ``t = 0``
            and the largest elapsed time is where the data stops. A ``Timestamp`` or an
            ISO ``YYYY-MM-DD`` string naming that first production period is accepted
            too, for a caller that has only the date.
        months: How many production periods to forecast. Defaults to
            :data:`DEFAULT_FORECAST_MONTHS`.
        terminal_decline_annual: The terminal decline, as a nominal fraction per year.
            Defaults to :data:`DEFAULT_TERMINAL_DECLINE_ANNUAL`.

    Returns:
        A :class:`Forecast` whose :attr:`~Forecast.periods` carry
        :data:`FORECAST_COLUMNS`, and whose :attr:`~Forecast.switch` says where the
        curve changes shape.

    Raises:
        ValueError: ``months`` is less than one, ``terminal_decline_annual`` is
            negative, or ``production_periods`` carries no production period to measure
            the forecast window from.
    """
    if months < 1:
        raise ValueError(f"a forecast needs at least 1 production period, got {months}")

    switch = terminal_switch(curve, terminal_decline_annual)
    last_observed, first_period = _observed_window(production_periods)
    window = np.arange(last_observed + 1, last_observed + 1 + months)
    dates = _period_dates(first_period, window)
    rates = _rate_with_terminal_switch(curve, switch, window)
    periods = pd.DataFrame(
        {
            "date": dates,
            "elapsed_months": window,
            "qo": rates,
            "volume_bbl": rates * dates.days_in_month.to_numpy(dtype="float64"),
        }
    )
    return Forecast(
        periods=periods.loc[:, list(FORECAST_COLUMNS)],
        curve=curve,
        switch=switch,
        terminal_decline_annual=float(terminal_decline_annual),
    )


def _rate_with_terminal_switch(
    curve: DeclineCurve, switch: TerminalSwitch | None, elapsed_months: np.ndarray
) -> np.ndarray:
    """The decline curve's oil rate at each elapsed time, with the terminal switch applied.

    Before the switch the curve is evaluated by ``arps``, in production periods, which is
    where the single months-to-years conversion happens. After it the rate is the
    exponential continuation from :attr:`TerminalSwitch.q_switch_bbl_d` — never from
    ``qi``, which is the mistake the convention exists to prevent.

    The hyperbolic's own rate at the switch is what anchors the tail, so the two phases
    are the same number at the boundary and the forecast cannot step there. Where the
    switch falls between two production periods, each production period takes the phase
    it stands in.

    Two cases have no switch and no hyperbolic phase, and they are projected differently
    for a reason. The exponential Arps curve (``b == 0``) is projected as itself. A curve
    with curvature but a decline at or below the terminal decline is at the threshold at
    ``t = 0``, so the convention's answer is that there is no hyperbolic phase at all and
    the well is on its exponential from the start — projecting its hyperbolic would run a
    phase the convention has already ruled out.
    """
    elapsed = np.asarray(elapsed_months, dtype="float64")
    if switch is None:
        if decline_curvature(curve) > 0.0:
            return arps.exponential_rate(float(curve.qi), float(curve.Di), elapsed)
        return np.asarray(curve.rate_at(elapsed), dtype="float64")

    before = elapsed <= switch.t_switch_months
    rates = np.asarray(curve.rate_at(elapsed), dtype="float64")
    tail = switch.q_switch_bbl_d * np.exp(
        -switch.tail_effective_decline * (arps.to_years(elapsed) - switch.t_switch_years)
    )
    return np.where(before, rates, tail)


def _require_terminal_decline(terminal_decline_annual: float) -> None:
    """Reject a terminal decline that would make the tail a rising rate.

    ``0.0`` is allowed and meaningful — it is the most conservative tail there is, a well
    that holds its rate forever. A negative threshold is not: the exponential tail would
    grow, which is not a decline curve, and it would silently attribute rising
    production to a well whose own curve falls.
    """
    if not np.isfinite(terminal_decline_annual) or terminal_decline_annual < 0.0:
        raise ValueError(
            "terminal_decline_annual must be a finite, non-negative nominal fraction "
            f"per year, got {terminal_decline_annual}"
        )


@dataclass(frozen=True)
class TerminalSwitch:
    """The moment a decline curve hands over to its exponential tail.

    Attributes:
        t_switch_years: Elapsed time of the switch from the well's ``t = 0``, in **years**
            — years, because both declines in the switch equation are per year and
            ``ln(1 + x)`` does not commute with a change of time unit.
        q_switch_bbl_d: The oil rate the curve had reached at the switch, bbl/d. The
            exponential tail is anchored to *this*, never to ``qi``.
        terminal_decline_annual: The nominal fraction per year the switch was solved at.
            Required rather than defaulted, and kept on the switch, because the tail has to
            run at the threshold the switch time was solved for: a default here would let a
            caller who asked for a different terminal decline get a switch at one rate and
            a tail at another.
    """

    t_switch_years: float
    q_switch_bbl_d: float
    terminal_decline_annual: float

    @property
    def t_switch_months(self) -> float:
        """Elapsed time of the switch in production periods, the unit the forecast uses."""
        return self.t_switch_years * arps.MONTHS_PER_YEAR

    @property
    def tail_effective_decline(self) -> float:
        """The effective annual decline the tail runs at, derived and never stored.

        ``ln(1 + terminal_decline_annual)``, derived here rather than carried around as
        a field, so the nominal ``terminal_decline_annual`` stays the single source of
        truth (ADR-0001).
        """
        return arps.effective_decline_from_nominal(self.terminal_decline_annual)


def _calendar_start(production_periods: pd.DataFrame | pd.Timestamp | str) -> pd.Timestamp:
    """The well's ``t = 0``: the earliest production period it has.

    The forecast and the EUR both hang their calendar off this date, so it is derived in
    one place and both accept the same argument: a well's production periods, or the
    first production period itself. A frame is measured on its **earliest** ``date`` rather
    than its first row, because a production CSV may list a well's production periods in
    any order.

    Raises:
        ValueError: A frame of production periods was passed with no rows, so there is no
            ``t = 0`` for either to measure against.
    """
    if isinstance(production_periods, (pd.Timestamp, str)):
        return pd.Timestamp(production_periods)
    if production_periods.empty:
        raise ValueError(
            "at least one observed production period is needed to measure a forecast or "
            "an EUR from, got an empty frame"
        )
    return pd.Timestamp(production_periods["date"].min())


def _observed_window(
    production_periods: pd.DataFrame | pd.Timestamp | str,
) -> tuple[int, pd.Timestamp]:
    """Where a well's data stops, and when its ``t = 0`` was.

    The forecast follows on from the largest elapsed time rather than from a count of
    rows, so a production period missing out of the middle of a well's history does not
    make the forecast overlap data that was already observed.

    Args:
        production_periods: The well's production periods, or its first production
            period as a ``Timestamp`` or an ISO date string.

    Returns:
        ``(last_observed_months, first_production_period)``.

    Raises:
        ValueError: A frame of production periods was passed with no rows, so there is
            no ``t = 0`` to measure the forecast from.
    """
    if isinstance(production_periods, (pd.Timestamp, str)):
        first = pd.Timestamp(production_periods)
        return -1, first
    if production_periods.empty:
        raise ValueError(
            "the forecast needs at least one observed production period to measure "
            "the forecast window from, got an empty frame"
        )
    ordered = production_periods.sort_values("date", kind="mergesort")
    return int(arps.elapsed_months(ordered).max()), _calendar_start(ordered)


def _period_dates(first: pd.Timestamp, elapsed_months: np.ndarray) -> pd.DatetimeIndex:
    """The calendar month each elapsed time falls in, from the well's first period.

    Built with ``DateOffset(months=...)``, the same month arithmetic
    ``arps.elapsed_months`` counts with, so the dates and the elapsed times cannot drift
    apart across a year boundary or a February.
    """
    return pd.DatetimeIndex(
        [first + pd.DateOffset(months=int(step)) for step in np.asarray(elapsed_months)]
    )


def eur(
    curve: DeclineCurve,
    production_periods: pd.DataFrame | pd.Timestamp | str,
    *,
    economic_limit_rate_bbl_d: float = DEFAULT_ECONOMIC_LIMIT_RATE_BBL_D,
    max_horizon_months: int = DEFAULT_MAX_HORIZON_MONTHS,
    terminal_decline_annual: float = DEFAULT_TERMINAL_DECLINE_ANNUAL,
) -> EurEstimate:
    """The well's EUR: the volume its decline curve makes before it is uneconomic.

    The decline curve is integrated from ``t = 0`` — the well's first production period —
    over the production periods where the curve is still at or above the economic limit
    rate, with the terminal decline switch applied as in :func:`forecast`. Each
    production period contributes ``rate x the days in that month``, the project's single
    days-per-period rule, so an EUR and a cumulative oil ``Np`` can be checked against
    each other.

    The integration stops at whichever binds first, the economic limit rate or the horizon
    cap, and :class:`EurEstimate` reports which — which is the difference between "this
    well is dead" and "the model ran out of horizon on a well that is still producing".

    Args:
        curve: The well's decline curve: a ``DeclineCurveSelection`` from
            ``arps.select_decline_curve``, or one fitted curve on its own. An analyst's
            override is honoured by passing the overridden selection.
        production_periods: The well's production periods as
            ``decline_curve_lab.io.load_production`` returns them, from which ``t = 0`` and
            the calendar of the integrated production periods are taken. A ``Timestamp``
            or an ISO ``YYYY-MM-DD`` string naming the well's first production period is
            accepted too, for a caller that has only the date.
        economic_limit_rate_bbl_d: The rate, bbl/d, below which the well is dead and the
            EUR stops accumulating. Defaults to
            :data:`DEFAULT_ECONOMIC_LIMIT_RATE_BBL_D`.
        max_horizon_months: The most production periods the EUR may integrate — the cap
            that bounds a hyperbolic or harmonic tail. Defaults to
            :data:`DEFAULT_MAX_HORIZON_MONTHS`.
        terminal_decline_annual: The terminal decline, as a nominal fraction per year, at
            which the hyperbolic hands over to its exponential tail. Defaults to
            :data:`DEFAULT_TERMINAL_DECLINE_ANNUAL`.

    Returns:
        An :class:`EurEstimate`: the EUR in bbl, where it stopped and why, and enough of
        the parameters it was read from to reproduce it.

    Raises:
        ValueError: ``economic_limit_rate_bbl_d`` is not positive (a zero or negative
            limit would mean integrating toward zero, which ADR-0003 rules out),
            ``max_horizon_months`` is less than one, or ``terminal_decline_annual`` is
            negative.
    """
    if not np.isfinite(economic_limit_rate_bbl_d) or economic_limit_rate_bbl_d <= 0.0:
        raise ValueError(
            "the economic limit rate must be a finite, positive oil rate in bbl/d, got "
            f"{economic_limit_rate_bbl_d}; a well is dead below the economic limit rate, "
            "so the EUR never integrates toward zero (ADR-0003)"
        )
    if max_horizon_months < 1:
        raise ValueError(
            f"the EUR horizon must cover at least 1 production period, got "
            f"{max_horizon_months}"
        )

    switch = terminal_switch(curve, terminal_decline_annual)
    first_period = _calendar_start(production_periods)
    elapsed = np.arange(max_horizon_months)
    dates = _period_dates(first_period, elapsed)
    rates = _rate_with_terminal_switch(curve, switch, elapsed)

    # Both phases of the curve fall, so the production periods that are still above the
    # economic limit rate are a prefix of the horizon: the count is also the index of the
    # last production period counted.
    producing = int((rates >= economic_limit_rate_bbl_d).sum())
    days = dates.days_in_month.to_numpy(dtype="float64")[:producing]
    stop_reason = (
        STOP_AT_HORIZON_CAP
        if producing == max_horizon_months
        else STOP_AT_ECONOMIC_LIMIT
    )
    return EurEstimate(
        eur_bbl=float(rates[:producing] @ days),
        stop_reason=stop_reason,
        final_period=dates[producing - 1] if producing else None,
        n_production_periods=producing,
        economic_limit_rate_bbl_d=float(economic_limit_rate_bbl_d),
        max_horizon_months=int(max_horizon_months),
        terminal_decline_annual=float(terminal_decline_annual),
        switch=switch,
    )


def eur_table(
    production: pd.DataFrame,
    *,
    override_well_id: str | None = None,
    override: str | None = None,
    terminal_decline_annual: float = DEFAULT_TERMINAL_DECLINE_ANNUAL,
    economic_limit_rate_bbl_d: float = DEFAULT_ECONOMIC_LIMIT_RATE_BBL_D,
    max_horizon_months: int = DEFAULT_MAX_HORIZON_MONTHS,
    sort_by: str = EUR_COLUMN,
    descending: bool = True,
) -> pd.DataFrame:
    """One row per well: its decline curve, its parameters and its EUR, ordered.

    The fleet-wide comparison, assembled from the same pieces a single-well caller would
    use: ``arps`` fits both Arps curves and selects between them, and :func:`eur` cuts each
    one at the economic limit rate. This only lays the results out side by side.

    **Ordering is an argument, not something a caller redoes.** ``sort_by`` and
    ``descending`` are the whole of a sort control: the largest EUR first by default, and
    any reported column in either direction. Ties break on ``well_id``, so the same data
    always produces the same order.

    **A well that cannot be fitted is reported, not dropped.** A single production period
    is not a decline curve, so a table that quietly left such a well out would under-report
    the fleet it looked at. Those wells are named in
    ``frame.attrs["unfitted_well_ids"]`` and absent from the rows.

    Args:
        production: Production periods as
            :func:`decline_curve_lab.io.load_production` returns them, for one well or for
            many. Only ``well_id``, ``date`` and ``qo`` are read.
        override_well_id: The well an ``override`` applies to. Scoped to one well on
            purpose: an analyst comparing one well's two Arps curves should not silently
            change every other well's numbers. Required whenever ``override`` is given.
        override: Force one well's decline curve to :data:`arps.EXPONENTIAL_CURVE` or
            :data:`arps.HYPERBOLIC_CURVE`, overriding the RMSE comparison for that well.
            ``None`` (the default) lets every well be chosen by RMSE.
        terminal_decline_annual: The terminal decline, as a nominal fraction per year, at
            which the hyperbolic hands over to its exponential tail. Defaults to
            :data:`DEFAULT_TERMINAL_DECLINE_ANNUAL`.
        economic_limit_rate_bbl_d: The rate, bbl/d, below which the well is dead and the
            EUR stops accumulating. Defaults to
            :data:`DEFAULT_ECONOMIC_LIMIT_RATE_BBL_D`.
        max_horizon_months: The most production periods any well's EUR may integrate.
            Defaults to :data:`DEFAULT_MAX_HORIZON_MONTHS`.
        sort_by: Which reported column to order by. Defaults to :data:`EUR_COLUMN`.
        descending: Whether the ordering runs from the largest value down.

    Returns:
        A new frame with one row per fitted well, carrying :data:`EUR_TABLE_COLUMNS`,
        ordered by ``sort_by``. ``attrs["unfitted_well_ids"]`` holds the wells that were
        left out. The input is not mutated.

    Raises:
        SchemaError: A column the table reads is missing. The message names them.
        ValueError: ``sort_by`` is not one of :data:`EUR_TABLE_COLUMNS`, ``override`` is
            given without a well to apply it to, or the economic limit rate and horizon are
            not usable — with the same messages :func:`eur` gives.
    """
    _require_production_columns(production)
    if sort_by not in EUR_TABLE_COLUMNS:
        raise ValueError(
            f"cannot sort the EUR table by {sort_by!r}: the table reports "
            f"{list(EUR_TABLE_COLUMNS)}"
        )
    if override is not None and override_well_id is None:
        raise ValueError(
            "an override applies to one well, so name it: pass override_well_id as well as "
            "override, or omit override to let every well be chosen by RMSE"
        )

    ordered = production.sort_values(["well_id", "date"], kind="mergesort").reset_index(
        drop=True
    )
    rows: list[dict[str, object]] = []
    unfitted: list[str] = []
    for well_id, periods in ordered.groupby("well_id", sort=True):
        elapsed = arps.elapsed_months(periods)
        oil_rate = periods["qo"].to_numpy()
        try:
            exponential = arps.fit_exponential(elapsed, oil_rate)
        except arps.FitError:
            # One production period is not a decline curve. Named rather than dropped, so
            # the table says which well it could not speak for.
            unfitted.append(str(well_id))
            continue
        try:
            hyperbolic = arps.fit_hyperbolic(elapsed, oil_rate)
        except arps.FitError:
            # A well the hyperbolic cannot be fitted to still has a decline curve: the
            # exponential, which is what `arps` falls back on too.
            hyperbolic = None

        selection = arps.select_decline_curve(
            exponential,
            hyperbolic,
            override=override if well_id == override_well_id else None,
        )
        estimate = eur(
            selection,
            periods,
            economic_limit_rate_bbl_d=economic_limit_rate_bbl_d,
            max_horizon_months=max_horizon_months,
            terminal_decline_annual=terminal_decline_annual,
        )
        rows.append(
            {
                "well_id": well_id,
                "curve": selection.curve,
                "chosen_by": selection.chosen_by,
                "qi": selection.qi,
                "Di": selection.Di,
                "b": selection.b,
                "rmse_bbl_d": selection.rmse_bbl_d,
                EUR_COLUMN: estimate.eur_bbl,
                "economic_limit_rate_bbl_d": estimate.economic_limit_rate_bbl_d,
                "stop_reason": estimate.stop_reason,
            }
        )

    table = pd.DataFrame(rows, columns=list(EUR_TABLE_COLUMNS))
    # `sort_by` is the primary key and `well_id` only breaks its ties, so the order is
    # reproducible in either direction and never depends on the row order rows arrived in.
    keys = [sort_by] if sort_by == "well_id" else [sort_by, "well_id"]
    table = table.sort_values(
        keys,
        ascending=[not descending] + [True] * (len(keys) - 1),
        kind="mergesort",
    ).reset_index(drop=True)
    table.attrs["unfitted_well_ids"] = unfitted
    return table


def _require_production_columns(production: pd.DataFrame) -> None:
    """Reject a frame the EUR table cannot be read from, naming what is missing."""
    missing = [
        column for column in EUR_TABLE_INPUT_COLUMNS if column not in production.columns
    ]
    if missing:
        raise io.SchemaError(
            f"production schema error: missing required column(s) {missing}; the EUR table "
            f"reads {list(EUR_TABLE_INPUT_COLUMNS)} from the frame "
            "decline_curve_lab.io.load_production returns"
        )


@dataclass(frozen=True)
class EurEstimate:
    """A well's EUR in barrels, and everything needed to say where it stopped.

    A bare float would answer "how much" and leave "why" to be re-derived at every call
    site, which is the question an analyst actually has next: a EUR that ended at the
    economic limit rate is a well that died, and one that ended at the horizon cap is a
    well the model ran out of years on. Both are legitimate answers and they are not the
    same answer, so both travel with the number.

    Attributes:
        eur_bbl: The EUR, bbl — the volume the decline curve makes over the integrated
            production periods, each contributing ``rate x the days in that month``.
        stop_reason: Which cutoff ended the integration, :data:`STOP_AT_ECONOMIC_LIMIT`
            or :data:`STOP_AT_HORIZON_CAP`. :data:`EUR_STOP_LABELS` holds the wording.
        final_period: The calendar month of the last production period counted, or
            ``None`` when the well was already below the economic limit rate at ``t = 0``
            and nothing was counted.
        n_production_periods: How many production periods the EUR covers: the integrated
            prefix of the horizon, ``0`` when the well starts below the limit rate.
        economic_limit_rate_bbl_d: The economic limit rate used, bbl/d.
        max_horizon_months: The horizon cap used, in production periods.
        terminal_decline_annual: The terminal decline applied, as a nominal fraction per
            year.
        switch: Where the curve handed over to its exponential tail, or ``None`` when it
            had no hyperbolic phase to hand over from.
    """

    eur_bbl: float
    stop_reason: str
    final_period: pd.Timestamp | None
    n_production_periods: int
    economic_limit_rate_bbl_d: float
    max_horizon_months: int
    terminal_decline_annual: float
    switch: TerminalSwitch | None = None

    @property
    def final_elapsed_months(self) -> int | None:
        """Elapsed time of the last production period counted, or ``None`` if there was
        none."""
        return None if self.n_production_periods == 0 else self.n_production_periods - 1

    @property
    def switch_elapsed_months(self) -> float:
        """Elapsed time of the terminal switch in production periods; ``nan`` if none."""
        return float("nan") if self.switch is None else self.switch.t_switch_months

    @property
    def switch_rate_bbl_d(self) -> float:
        """Oil rate at the terminal switch, bbl/d; ``nan`` if there is no switch."""
        return float("nan") if self.switch is None else self.switch.q_switch_bbl_d

    @property
    def terminal_switch_bounds_eur(self) -> bool:
        """Whether the exponential tail fell inside the integrated production periods.

        ``False`` for the many wells whose terminal decline is never reached at all, and
        also for one that is reached only after the EUR already stopped — a switch at
        0.03 bbl/d is irrelevant to a well that is dead at 1 bbl/d.
        """
        if self.switch is None:
            return False
        return self.switch.t_switch_months < self.n_production_periods


@dataclass(frozen=True)
class Forecast:
    """One well's forecast production periods, and the decline curve behind them.

    A frame of numbers alone would force every caller to re-derive where the curve
    changed shape in order to describe it, so the things a reader has to *interpret* —
    which terminal decline was applied, where the curve switches, at what rate — travel
    with the numbers rather than being rediscovered at each call site.

    Attributes:
        periods: The forecast production periods, carrying :data:`FORECAST_COLUMNS`.
        curve: The decline curve that was projected.
        switch: Where the hyperbolic handed over to the exponential tail, or ``None``
            when there is no hyperbolic phase to hand over from.
        terminal_decline_annual: The terminal decline this forecast applied, as a nominal
            fraction per year. On the forecast and not only on the switch, because a well
            with no switch still had a threshold to be measured against, and the threshold
            it was measured against is what a reader needs to see.
    """

    periods: pd.DataFrame
    curve: DeclineCurve
    switch: TerminalSwitch | None = None
    terminal_decline_annual: float = DEFAULT_TERMINAL_DECLINE_ANNUAL

    @property
    def switch_elapsed_months(self) -> float:
        """Elapsed time of the terminal switch in production periods; ``nan`` if none.

        ``nan`` rather than zero when the curve has no hyperbolic phase: a well that is
        already at or below the terminal decline at ``t = 0`` has *no* switch, which is a
        different statement from one that switches immediately, and only one of them is
        true of such a well.
        """
        return float("nan") if self.switch is None else self.switch.t_switch_months

    @property
    def switch_rate_bbl_d(self) -> float:
        """Oil rate at the terminal switch, bbl/d; ``nan`` if there is no switch."""
        return float("nan") if self.switch is None else self.switch.q_switch_bbl_d

    @property
    def switch_within_window(self) -> bool:
        """Whether the terminal switch falls inside this forecast's production periods."""
        if self.switch is None:
            return False
        elapsed = self.periods["elapsed_months"].to_numpy()
        return bool(elapsed.min() <= self.switch.t_switch_months <= elapsed.max())