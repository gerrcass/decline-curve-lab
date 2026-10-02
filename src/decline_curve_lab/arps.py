"""Arps decline-curve rate equations and the exponential fit.

Conventions this module holds to
================================

*Time* (see ``docs/adr/0001-nominal-decline-is-canonical.md``). Elapsed time ``t`` is
counted in months from a well's **own first production period**, so ``t = 0`` is that
period. :func:`elapsed_months` is the only place that clock is derived, and
:func:`to_years` is the only place it is converted, because ``Di`` is nominal per
*year* while production periods are months. Converting once, at the boundary, keeps
``Di * t`` dimensionless — the one dimensional constraint in the whole family.

*Decline.* ``Di`` is the **nominal** decline as a fraction per year (``0.35`` is
35 %/yr nominal) and is the only decline this module stores or reports. The
effective decline ``D_eff = ln(1 + Di)`` is what the continuous exponential is solved
with, so :func:`effective_decline_from_nominal` derives it and nothing else does.

*The Arps family.* With ``t`` in years, ``qi`` in bbl/d (a daily average, ADR-0002) and
``D = D_eff``:

========================  ===================================================
exponential (``b = 0``)  ``q(t) = qi * exp(-D * t)``
hyperbolic (``0 < b <= 1``)  ``q(t) = qi * (1 + b * D * t) ** (-1 / b)``
harmonic (``b = 1``)     the ``b = 1`` case of the hyperbolic
========================  ===================================================

The exponential is the ``b -> 0`` limit of the hyperbolic and the harmonic is its
``b = 1`` case, so the exponential and the harmonic are **different curves** and are
never collapsed: at ``Di = 0.35`` and three years in, the harmonic sits at 263 bbl/d
and the exponential at 203 bbl/d. Both curves are fitted to a well's production
periods, and the one that fits better on the rate scale is the well's decline curve —
:func:`select_decline_curve`.

"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import OptimizeWarning, curve_fit

__all__ = [
    "CURVATURE_CEILING_BOUND",
    "CURVATURE_FLOOR_BOUND",
    "CURVE_BY_OVERRIDE",
    "CURVE_BY_RMSE",
    "CURVE_ONLY_AVAILABLE",
    "EXPONENTIAL_CURVE",
    "HYPERBOLIC_CURVE",
    "MAX_NOMINAL_DECLINE",
    "MIN_CURVATURE",
    "MIN_NOMINAL_DECLINE",
    "MIN_RELATIVE_RMSE_IMPROVEMENT",
    "NOMINAL_DECLINE_CEILING_BOUND",
    "NOMINAL_DECLINE_FLOOR_BOUND",
    "DeclineCurveSelection",
    "ExponentialFit",
    "FitError",
    "HyperbolicFit",
    "MONTHS_PER_YEAR",
    "effective_decline_from_nominal",
    "elapsed_months",
    "exponential_rate",
    "fit_exponential",
    "fit_hyperbolic",
    "hyperbolic_rate",
    "positive_rate_mask",
    "select_decline_curve",
    "to_years",
]

#: Production periods are months, so this is the months-per-year factor that
#: :func:`to_years` divides by. Declines are nominal per year, production periods are
#: not.
MONTHS_PER_YEAR: int = 12

#: The two names of the Arps curve that can be a well's decline curve, and the values
#: :attr:`DeclineCurveSelection.curve` and the ``override`` argument take. They are the
#: glossary's curve names, not ad-hoc labels, so a caller never has to guess what a
#: string means.
EXPONENTIAL_CURVE: str = "exponential"
HYPERBOLIC_CURVE: str = "hyperbolic"

#: Values of :attr:`DeclineCurveSelection.chosen_by`, saying *how* the decline curve was
#: chosen: by the RMSE comparison, by the analyst's manual override, or because the
#: hyperbolic fit does not exist for that well.
CURVE_BY_RMSE: str = "rmse"
CURVE_BY_OVERRIDE: str = "override"
CURVE_ONLY_AVAILABLE: str = "only_available"

#: Smallest decline curvature ``b`` the hyperbolic fit may return. The rate equation
#: **divides by** ``b`` and ``b = 0`` is the exponential, which is fitted separately by
#: :func:`fit_exponential`, so the fit is bounded away from zero rather than allowed to
#: evaluate ``1 / 0``. It is a numerical guard rather than a claim about wells — real fitted
#: wells do come back at ``b = 1.41`` — and it narrows the glossary's ``[0, 1]`` to
#: ``[MIN_CURVATURE, 1]``. See :func:`fit_hyperbolic` for what the floor costs and buys, and
#: :attr:`HyperbolicFit.bounds_active` for how a caller sees it binding.
MIN_CURVATURE: float = 1e-4

#: Smallest initial nominal decline ``Di`` the hyperbolic fit may return, as a fraction per
#: year. An Arps curve cannot represent a rising well and ``Di <= 0`` would break
#: ``1 + b * D * t >= 1`` at every production period, so the base could go negative, ``nan``
#: or infinite anywhere the optimiser goes. This is a numerical guard, not a physical claim,
#: and it has a real cost: a rising well keeps its exponential — which has no such bound, so
#: it does represent growth — and wins the RMSE comparison on the enormous margin the
#: clamped hyperbolic leaves behind. Published rather than private so a caller can see a
#: well's ``Di`` stop at the floor and know a guard did it.
MIN_NOMINAL_DECLINE: float = 1e-9

#: Largest nominal decline the hyperbolic fit may return, as a fraction per year. No well
#: declines at 1000 %/yr, so this is a numerical guard, not a physical claim: past it the
#: rate underflows to zero within the fitted window and the residual surface goes flat, which
#: is what a bounded fit is for. On any well with at most a few decades of history the floor
#: of the curve underflows long before this bound does, so it is the one bound here that no
#: real data reaches; it is published so that the range is stated rather than implied.
MAX_NOMINAL_DECLINE: float = 10.0

#: Name :attr:`HyperbolicFit.bounds_active` reports when a fitted decline curvature sits on
#: :data:`MIN_CURVATURE` — the guard against the ``1 / b`` the rate equation would otherwise
#: evaluate.
CURVATURE_FLOOR_BOUND: str = "curvature_floor"

#: Name :attr:`HyperbolicFit.bounds_active` reports when a fitted decline curvature sits on
#: ``b = 1``, the top of the Arps family and the harmonic curve.
CURVATURE_CEILING_BOUND: str = "curvature_ceiling"

#: Name :attr:`HyperbolicFit.bounds_active` reports when a fitted nominal decline sits on
#: :data:`MIN_NOMINAL_DECLINE`, which is what happens on a well whose rate rises.
NOMINAL_DECLINE_FLOOR_BOUND: str = "nominal_decline_floor"

#: Name :attr:`HyperbolicFit.bounds_active` reports when a fitted nominal decline sits on
#: :data:`MAX_NOMINAL_DECLINE`. See that constant: no real history reaches it.
NOMINAL_DECLINE_CEILING_BOUND: str = "nominal_decline_ceiling"

#: How close to a bound a fitted parameter has to be to count as sitting on it. The
#: optimiser is stopped by the bound, not snapped to it, so a binding parameter lands on it
#: to within its own tolerance rather than exactly.
_AT_BOUND_TOLERANCE: float = 1e-9

#: How much better the hyperbolic curve's RMSE has to be, as a fraction of the
#: exponential curve's RMSE, before the hyperbolic is selected. Default ``0.02``: see
#: :func:`select_decline_curve` for why a bare lower-RMSE rule is not enough and what
#: this band measures.
MIN_RELATIVE_RMSE_IMPROVEMENT: float = 0.02

#: Starting value for ``b`` when fitting the hyperbolic: the middle of the bounded
#: ``[0, 1]`` range. Fits seeded from here converged for every well shape and noise level
#: measured (including a deliberately hostile accelerating decline), so it is a starting
#: point and not a reported result.
_INITIAL_CURVATURE: float = 0.5

#: Smallest ``qi`` the optimiser may propose. ``qi`` is bounded below so the fit cannot
#: propose a zero or negative initial rate, which is not a rate at all.
_MIN_QI: float = 1e-9


def elapsed_months(periods: pd.DataFrame) -> np.ndarray:
    """Elapsed months from a well's first production period, for each of its periods.

    One well's production periods, in ascending date order: ``[0, 1, 2, ...]``. The
    clock is the well's *own*, because the shipped wells start in different calendar
    months, so a shared clock would put one well's ``t = 0`` at another well's
    ``t = 7``.

    Args:
        periods: One well's production periods, as returned by
            :func:`decline_curve_lab.io.load_production`, in ascending date order.

    Returns:
        An ``int64`` array of elapsed months, one per production period.
    """
    dates = pd.DatetimeIndex(periods["date"])
    first = dates[0]
    months = 12 * (dates.year.to_numpy() - first.year) + (
        dates.month.to_numpy() - first.month
    )
    return months.astype("int64")


def to_years(elapsed_months: np.ndarray | float) -> np.ndarray:
    """Convert elapsed months to years, so every rate-per-year quantity is annual.

    The project's ``Di`` is nominal per year while ``t`` arrives in months, so this
    conversion happens exactly once, at the boundary, and never by scaling an
    effective decline between time units — the transform that does not commute with
    the time unit and is the most common bug in this domain.

    Args:
        elapsed_months: Elapsed time in production periods. A scalar, an array or a
            Series is all accepted.

    Returns:
        Elapsed time in years, as float.
    """
    return np.asarray(elapsed_months, dtype="float64") / MONTHS_PER_YEAR


def effective_decline_from_nominal(di_nominal: float) -> float:
    """Derive the effective decline ``D_eff = ln(1 + Di)`` from a nominal ``Di``.

    The effective decline is what the continuous exponential is solved with. Per
    ADR-0001 it is **derived only, never stored and never reported**: the canonical
    decline parameter is the nominal ``Di``. This function exists so that derivation
    happens in one place — ``D_eff`` must be derived *after* the time unit is fixed,
    because ``ln(1 + x)`` does not commute with a change of time unit.

    Args:
        di_nominal: Nominal decline as a fraction per year. Must be greater than
            ``-1``.

    Returns:
        The effective decline per year.
    """
    if di_nominal <= -1.0:
        raise ValueError(f"nominal decline must be greater than -1, got {di_nominal}")
    return float(np.log1p(di_nominal))


def exponential_rate(
    qi: float, di_nominal: float, elapsed_months: np.ndarray | float
) -> np.ndarray:
    """Oil rate on the exponential Arps curve, in bbl/d (a daily average).

    ``q(t) = qi * exp(-D_eff * t_yr)``, the ``b = 0`` member of the Arps family, with
    ``D_eff = ln(1 + Di)`` derived here and ``t_yr`` from :func:`to_years` so that
    ``Di * t`` stays dimensionless.

    Args:
        qi: Initial rate ``qi``, the rate the curve predicts at ``t = 0``, bbl/d.
        di_nominal: Nominal decline ``Di`` as a fraction per year. Reported and
            stored as nominal, per ADR-0001.
        elapsed_months: Elapsed time in production periods from the well's first
            production period.

    Returns:
        The curve's rate at each elapsed time, bbl/d, shaped like
        ``elapsed_months`` (a 0-d array for a scalar argument).
    """
    d_eff = effective_decline_from_nominal(di_nominal)
    return qi * np.exp(-d_eff * to_years(elapsed_months))


def hyperbolic_rate(
    qi: float, di_nominal: float, b: float, elapsed_months: np.ndarray | float
) -> np.ndarray:
    """Oil rate on the hyperbolic Arps curve, in bbl/d (a daily average).

    ``q(t) = qi * (1 + b * D_eff * t_yr) ** (-1 / b)``, with ``D_eff = ln(1 + Di)``
    derived here and ``t_yr`` from :func:`to_years` so that ``Di * t`` stays
    dimensionless — the same two derivations :func:`exponential_rate` makes, and for the
    same reason (ADR-0001).

    Evaluated as ``exp(-ln(1 + b * D_eff * t) / b)`` rather than
    ``(1 + b * D_eff * t) ** (-1 / b)`` because the logarithm form is stable as ``b``
    approaches zero, where the two arguments cancel: ``ln1p`` is accurate for a small
    argument, so the quotient stays exact where the power form would round.

    ``b = 1`` is the harmonic curve ``qi / (1 + D_eff * t)``, which is **not** the
    exponential. ``b = 0`` is the exponential, which this function refuses to evaluate:
    the equation divides by ``b``, so ``b = 0`` is :func:`exponential_rate`'s job.

    Args:
        qi: Initial rate ``qi``, the rate the curve predicts at ``t = 0``, bbl/d.
        di_nominal: Nominal decline ``Di`` as a fraction per year. Reported and stored
            as nominal, per ADR-0001.
        b: Decline curvature ``b``, the Arps parameter that shapes the curve: ``1`` is
            harmonic, values strictly between 0 and 1 are hyperbolic. Must be positive.
        elapsed_months: Elapsed time in production periods from the well's first
            production period.

    Returns:
        The curve's rate at each elapsed time, bbl/d, shaped like
        ``elapsed_months`` (a 0-d array for a scalar argument).

    Raises:
        ValueError: ``b`` is not positive, so the equation cannot be evaluated.
    """
    if b <= 0.0:
        raise ValueError(
            f"decline curvature b must be positive, got {b}: b = 0 is the exponential "
            "Arps curve, which is exponential_rate()"
        )
    d_eff = effective_decline_from_nominal(di_nominal)
    return qi * np.exp(-np.log1p(b * d_eff * to_years(elapsed_months)) / b)


class FitError(ValueError):
    """Raised when a decline curve cannot be fitted to the production periods given.

    A fit fails when the production periods carry no usable information: too few
    positive rates to fit a line through, or a single elapsed time. Both are stated
    in the message rather than left as a ``nan`` the caller has to notice.
    """


@dataclass(frozen=True)
class ExponentialFit:
    """A fitted exponential Arps decline curve.

    Attributes:
        qi: Initial rate ``qi`` — the curve's rate at ``t = 0``, **back-extrapolated**
            from the fitted production periods, in bbl/d. A model parameter, not a
            measurement: it need not equal the well's first observed rate, and
            normally does not.
        Di: Initial nominal decline, as a fraction per **year** (``0.35`` is 35 %/yr
            nominal), per ADR-0001. The canonical decline parameter; the effective
            decline it implies is derived inside the solver and never stored here.
        r_squared: Goodness of fit on the **rate scale**: ``1 - SS_res / SS_tot`` of the
            fitted curve against the observed rates. Deliberately *not* the
            regression's own ``R**2`` on ``log q``: a rate-scale number carries bbl/d
            meaning, is comparable with :attr:`rmse_bbl_d`, and stays comparable with
            the hyperbolic fit added later, which is not a log-linear regression.
            ``nan`` when every observed rate is equal, which is the honest answer for a
            well that never declined — ``R**2`` is undefined against a constant
            response — rather than a misleading 1.0.
        rmse_bbl_d: Root-mean-square residual of the fitted curve against the
            observed rates, **in rate units (bbl/d)** — how far the curve sits from
            the data in production units. Log-scale residuals are a different number
            in different (dimensionless) units and are not what this reports.
        n_production_periods: How many production periods the regression actually
            used, i.e. after the non-positive rates were dropped.
        n_dropped: How many production periods were left out because their oil rate
            was not positive. ``ln q`` is undefined at or below zero — a shut-in or a
            zeroed production period — so such a period cannot enter a log-linear fit.
            They are dropped, never imputed, and counted here.
    """

    qi: float
    Di: float
    r_squared: float
    rmse_bbl_d: float
    n_production_periods: int
    n_dropped: int

    def rate_at(self, elapsed_months: np.ndarray | float) -> np.ndarray:
        """The fitted curve's oil rate at each elapsed time, bbl/d.

        Args:
            elapsed_months: Elapsed time in production periods from the well's first
                production period. ``0`` gives :attr:`qi` by definition.

        Returns:
            The fitted rate at each elapsed time, bbl/d, shaped like
            ``elapsed_months`` (a 0-d array for a scalar argument, so wrap it in
            ``float()`` to print it).
        """
        return exponential_rate(self.qi, self.Di, elapsed_months)


def positive_rate_mask(oil_rate_bbl_d: np.ndarray | float) -> np.ndarray:
    """Which production periods can enter a log-linear decline fit.

    A log-linear fit regresses ``ln q`` on time, so a production period at or below
    zero oil rate has no place in it: ``ln q`` is undefined there. Such a period is a
    shut-in or a zeroed month, and it is **dropped from the fit, never imputed** —
    carrying it forward would invent a rate the well did not produce.

    Exposed because a log-scale chart has the same requirement, so the dashboard can
    ask the same question of the same data instead of re-deriving the rule.

    Args:
        oil_rate_bbl_d: Oil rate of each production period, bbl/d.

    Returns:
        A boolean array, true for each production period with a positive oil rate.
    """
    return np.asarray(oil_rate_bbl_d, dtype="float64") > 0.0


def _fittable_production_periods(
    elapsed_months: np.ndarray,
    oil_rate_bbl_d: np.ndarray,
    minimum_periods: int,
    curve_name: str,
) -> tuple[np.ndarray, np.ndarray, int, int]:
    """The production periods one decline-curve fit may use, and how they were chosen.

    Both fits go through here so that they see **the same production periods**. They are
    compared on RMSE by :func:`select_decline_curve`, and an RMSE computed over two
    different sets of production periods is not a comparison of anything.

    Args:
        elapsed_months: Elapsed time of each production period, production periods.
        oil_rate_bbl_d: Oil rate of each production period, bbl/d daily average.
        minimum_periods: How many usable production periods this curve needs — two for
            the exponential's two parameters, three for the hyperbolic's three.
        curve_name: The curve's name, for the error message.

    Returns:
        The elapsed times and rates of the usable production periods, how many there
        are, and how many were dropped.

    Raises:
        FitError: The arrays differ in length, fewer than ``minimum_periods`` production
            periods have a positive oil rate, or every usable production period shares
            one elapsed time (so there is no time axis to fit against).
    """
    elapsed = np.asarray(elapsed_months, dtype="float64")
    rates = np.asarray(oil_rate_bbl_d, dtype="float64")
    if elapsed.shape != rates.shape:
        raise FitError(
            "elapsed time and oil rate must have the same length, got "
            f"{elapsed.shape[0]} and {rates.shape[0]}"
        )

    keep = positive_rate_mask(rates)
    n_kept = int(keep.sum())
    if n_kept < minimum_periods:
        raise FitError(
            f"{curve_name} needs at least {minimum_periods} production periods with a "
            f"positive oil rate, got {n_kept}"
        )

    fittable_elapsed = elapsed[keep]
    if float(((fittable_elapsed - fittable_elapsed.mean()) ** 2).sum()) == 0.0:
        raise FitError(
            "every production period shares one elapsed time, so the decline cannot be "
            "fitted: the curve needs at least two distinct elapsed times"
        )

    return fittable_elapsed, rates[keep], n_kept, int((~keep).sum())


def _goodness_of_fit(observed: np.ndarray, fitted: np.ndarray) -> tuple[float, float]:
    """Rate-scale ``R**2`` and RMSE, in the units the rates are in.

    One definition, shared by both fits, so that a ``rmse_bbl_d`` from the exponential
    and one from the hyperbolic answer the same question and can be compared.
    Deliberately on the **rate scale**, not ``ln q``: a log-scale residual is a different
    number in different (dimensionless) units, and the hyperbolic fit is not a
    log-linear regression, so a log-scale number would not be comparable across the two.

    Args:
        observed: Observed oil rate of the fitted production periods, bbl/d.
        fitted: The fitted curve's rate at the same production periods, bbl/d.

    Returns:
        ``(r_squared, rmse_bbl_d)``, with ``r_squared`` ``nan`` when every observed rate
        is equal — the honest answer for a well that never declined, since ``R**2`` is
        then undefined rather than 1.
    """
    residuals = observed - fitted
    ss_residual = float((residuals**2).sum())
    ss_total = float(((observed - observed.mean()) ** 2).sum())
    r_squared = 1.0 - ss_residual / ss_total if ss_total > 0.0 else float("nan")
    return r_squared, float(np.sqrt((residuals**2).mean()))


def fit_exponential(elapsed_months: np.ndarray, oil_rate_bbl_d: np.ndarray) -> ExponentialFit:
    """Fit the exponential Arps decline curve to a well's oil rate.

    Ordinary least squares of ``ln q`` against elapsed time in **years**, which is
    linear in ``ln qi`` and ``D_eff``::

        ln q(t) = ln qi - D_eff * t_yr

    so the slope of that regression *is* ``-D_eff`` and the intercept *is* ``ln qi``.
    The parameters are then converted once, on the way out:

    ==========================  ===============================================
    ``qi = exp(intercept)``     the back-extrapolated rate at ``t = 0``, bbl/d
    ``Di = exp(-slope) - 1``    the **nominal** decline as a fraction per year
    ==========================  ===============================================

    Note the sign: the slope of ``ln q`` against time is **negative** for a declining
    well, so the effective decline is ``-slope`` and ``Di`` is ``exp(-slope) - 1``.
    Reporting the effective decline here instead would be an ~8 % error at
    ``Di = 0.18`` and a growing one beyond it (ADR-0001).

    Production periods whose oil rate is not positive cannot be logged and are
    dropped; see :func:`positive_rate_mask` and :class:`ExponentialFit`.

    **Degradation.** Every way this fit can fail raises :class:`FitError`, never a bare
    ``ValueError`` from the rate equation underneath — including the hostile case of a
    rising well whose ``Di`` the regression rounds to exactly ``-1.0``, which the rate
    equation cannot evaluate. Callers above handle ``FitError`` and nothing else:
    :func:`decline_curve_lab.forecast.eur_table` names such a well in its ``unfitted_well_ids``
    and the dashboard shows a warning and carries on.

    Args:
        elapsed_months: Elapsed time of each production period from the well's own
            first production period, as :func:`elapsed_months` returns it.
        oil_rate_bbl_d: Oil rate of each production period, bbl/d daily average.

    Returns:
        The fitted curve's ``qi`` and nominal ``Di``, its goodness of fit, and how
        many production periods it used.

    Raises:
        FitError: Fewer than two production periods have a positive oil rate, every
            production period shares one elapsed time (so ``Di * t`` cannot be resolved and
            no slope exists), or the fitted curve cannot be evaluated.
    """
    fittable_elapsed, fittable_rates, n_kept, n_dropped = _fittable_production_periods(
        elapsed_months, oil_rate_bbl_d, 2, "an exponential decline curve"
    )
    t_yr = to_years(fittable_elapsed)
    ln_rate = np.log(fittable_rates)

    # Ordinary least squares, written out so the slope and the intercept that the
    # parameters come from are visible rather than hidden behind a polyfit call.
    mean_t = t_yr.mean()
    mean_ln_rate = ln_rate.mean()
    spread_t = float(((t_yr - mean_t) ** 2).sum())
    slope = float(((t_yr - mean_t) * (ln_rate - mean_ln_rate)).sum() / spread_t)
    intercept = mean_ln_rate - slope * mean_t

    qi = float(np.exp(intercept))
    # Di nominal per year, from the effective decline the slope carries (ADR-0001).
    di_nominal = float(np.expm1(-slope))

    # Goodness of fit on the rate scale, so it is in bbl/d and comparable across the
    # Arps curve models rather than only meaningful for a log-linear regression.
    try:
        fitted = exponential_rate(qi, di_nominal, fittable_elapsed)
    except ValueError as error:
        # `Di` came off the regression, not off a parameter list, so nothing upstream can
        # have bounded it. A well whose oil rate rises by tens of orders of magnitude gives
        # a slope steep enough that `expm1` rounds `Di` to exactly -1.0, and the rate
        # equation cannot take `ln(1 + Di)` of that. The caller above this wants a FitError,
        # because `eur_table` and the dashboard handle FitError and nothing else, so a bare
        # ValueError from underneath would escape both.
        raise FitError(
            f"an exponential decline curve could not be evaluated for this well: {error}"
        ) from error
    r_squared, rmse_bbl_d = _goodness_of_fit(fittable_rates, fitted)

    return ExponentialFit(
        qi=qi,
        Di=di_nominal,
        r_squared=r_squared,
        rmse_bbl_d=rmse_bbl_d,
        n_production_periods=n_kept,
        n_dropped=n_dropped,
    )


@dataclass(frozen=True)
class HyperbolicFit:
    """A fitted hyperbolic Arps decline curve.

    Carries the same fields as :class:`ExponentialFit` plus the decline curvature ``b``,
    so the two fits can be compared field by field — in particular their
    :attr:`rmse_bbl_d`, which :func:`select_decline_curve` does.

    Attributes:
        qi: Initial rate ``qi`` — the curve's rate at ``t = 0``, **back-extrapolated**
            from the fitted production periods, in bbl/d. A model parameter, not a
            measurement, exactly as on :class:`ExponentialFit`.
        Di: Initial nominal decline, as a fraction per **year**, per ADR-0001. The
            canonical decline parameter; the effective decline it implies is derived
            inside the solver and never stored here. Bounded to
            ``[MIN_NOMINAL_DECLINE, MAX_NOMINAL_DECLINE]``; a well whose rate rises
            comes back at the floor, and :attr:`bounds_active` reports that it did.
        b: Decline curvature ``b``, the Arps parameter that shapes the curve. ``0`` is
            the exponential, ``1`` the harmonic, values between are hyperbolic.
            Bounded to ``[MIN_CURVATURE, 1]``; a series that wants more than 1 comes
            back clamped at 1, and :attr:`bounds_active` reports that it did.
        r_squared: Goodness of fit on the **rate scale**, ``1 - SS_res / SS_tot``, from
            the same definition the exponential fit uses so the two are comparable.
            ``nan`` when every observed rate is equal.
        rmse_bbl_d: Root-mean-square residual against the observed rates, **in rate
            units (bbl/d)** — the same scale, and the same definition, as
            :attr:`ExponentialFit.rmse_bbl_d`, which is what makes the two comparable.
        n_production_periods: How many production periods the fit used, i.e. after the
            non-positive rates were dropped.
        n_dropped: How many production periods were left out because their oil rate was
            not positive. Dropped, never imputed, and the same count the exponential fit
            reports — the two fits see the same production periods.
    """

    qi: float
    Di: float
    b: float
    r_squared: float
    rmse_bbl_d: float
    n_production_periods: int
    n_dropped: int

    @property
    def bounds_active(self) -> tuple[str, ...]:
        """Which of the fit's bounds the returned parameters are sitting on, in a fixed order.

        The hyperbolic fit is bounded on two parameters and both bounds are numerical
        guards rather than claims about wells, so a fit can come back pinned against one
        and say so. :attr:`b` and :attr:`Di` on their own do not distinguish "the data said
        this" from "the guard would not let the optimiser go further", and those are
        different claims about the well: a ``b`` of 1 is the harmonic curve when the data
        wanted it and "the Arps family stops here" when the clamp decided it. The names are
        :data:`CURVATURE_FLOOR_BOUND`, :data:`CURVATURE_CEILING_BOUND`,
        :data:`NOMINAL_DECLINE_FLOOR_BOUND` and :data:`NOMINAL_DECLINE_CEILING_BOUND`.

        The common case is the empty tuple, which is what makes a non-empty one informative:
        every shipped well is inside every bound, and the rising-well case that pins
        :data:`MIN_NOMINAL_DECLINE` is the one this exists to make visible.

        Returns:
            The bounds the returned parameters sit on, in the order curvature floor,
            curvature ceiling, nominal decline floor, nominal decline ceiling. Empty when
            the fit stayed inside every bound.
        """
        active = []
        if self.b <= MIN_CURVATURE + _AT_BOUND_TOLERANCE:
            active.append(CURVATURE_FLOOR_BOUND)
        if self.b >= 1.0 - _AT_BOUND_TOLERANCE:
            active.append(CURVATURE_CEILING_BOUND)
        if self.Di <= MIN_NOMINAL_DECLINE + _AT_BOUND_TOLERANCE:
            active.append(NOMINAL_DECLINE_FLOOR_BOUND)
        if self.Di >= MAX_NOMINAL_DECLINE - _AT_BOUND_TOLERANCE:
            active.append(NOMINAL_DECLINE_CEILING_BOUND)
        return tuple(active)

    def rate_at(self, elapsed_months: np.ndarray | float) -> np.ndarray:
        """The fitted curve's oil rate at each elapsed time, bbl/d.

        Args:
            elapsed_months: Elapsed time in production periods from the well's first
                production period. ``0`` gives :attr:`qi` by definition.

        Returns:
            The fitted rate at each elapsed time, bbl/d, shaped like
            ``elapsed_months`` (a 0-d array for a scalar argument, so wrap it in
            ``float()`` to print it).
        """
        return hyperbolic_rate(self.qi, self.Di, self.b, elapsed_months)


def _hyperbolic_model(
    elapsed_years: np.ndarray, qi: float, di_nominal: float, b: float
) -> np.ndarray:
    """The hyperbolic rate equation in the shape ``scipy.optimize.curve_fit`` wants.

    ``curve_fit`` passes the independent variable first and then the parameters, so the
    elapsed time is already in years here and is not converted again. The effective
    decline is derived from the nominal ``Di`` *inside* the model, after the time unit is
    fixed, because ``ln(1 + x)`` does not commute with a change of time unit.
    """
    d_eff = np.log1p(di_nominal)
    return qi * np.exp(-np.log1p(b * d_eff * elapsed_years) / b)


def fit_hyperbolic(
    elapsed_months: np.ndarray, oil_rate_bbl_d: np.ndarray
) -> HyperbolicFit:
    """Fit the hyperbolic Arps decline curve to a well's oil rate.

    Non-linear least squares by ``scipy.optimize.curve_fit`` on the **rate scale**, so
    the objective minimised is the very RMSE the fit reports and
    :func:`select_decline_curve` compares. (Fitting ``ln q`` instead was measured and
    rejected: it is less accurate on the curvature, and on a noisy exponential series it
    left ``b`` wandering to 0.15 and inverted the RMSE comparison that model selection
    turns on.)

    **The ``b -> 0`` singularity.** The rate equation divides by ``b``, and ``b = 0`` is
    the exponential — which :func:`fit_exponential` fits exactly, with no optimiser. So
    the fit is bounded below at :data:`MIN_CURVATURE` and the exponential's ``b = 0``
    limit is never evaluated. The floor is small enough that the hyperbolic still
    reproduces an exponential series: on a noise-free exponential the fit comes back at
    ``b = 1e-4`` with the exponential's own ``qi`` and ``Di``, and on the shipped
    exponential well ``DCL-02`` at ``b = 0.02``.

    **Starting point and bounds.** The starting guess is the exponential fit's ``qi`` and
    ``Di`` — a two-parameter fit of the same data, so a sound place to start — with ``b``
    at the middle of its range. The two bounds are **numerical guards, not claims about
    wells**, and both have a real cost, so they are stated rather than buried:

    ==============================  ===================================================
    ``b`` in ``[MIN_CURVATURE, 1]``  ``1 / b`` in the rate equation, and ``b > 1`` is a real
                                     fitted-well shape (the background research records EIA
                                     rows at ``b = 1.41`` and ``b = 1.44``), so the glossary's
                                     ``[0, 1]`` is narrowed at the bottom and pinned at the top
    ``Di`` in ``[MIN_NOMINAL_DECLINE,``
    ``MAX_NOMINAL_DECLINE]``          ``1 + b * D_eff * t >= 1`` at every production period,
                                     so the equation cannot produce a negative base, a ``nan``
                                     or an infinite rate anywhere the optimiser goes — which
                                     is what keeps a dashboard from crashing on a hostile well
    ==============================  ===================================================

    Bounding ``Di`` at zero does not hide a rising well, but it does change its decline
    curve: the exponential fit has no such bound, so it represents growth and wins such a
    well on RMSE, by a margin of five orders of magnitude in the case of a well rising at
    30 %/yr. No real history reaches :data:`MAX_NOMINAL_DECLINE` — with a few decades of
    production periods the curve underflows to zero long before that bound does — so it is a
    guard on the guard. :attr:`HyperbolicFit.bounds_active` reports which bound, if any, the
    returned parameters sit on, so a caller never has to guess whether a pinned parameter is
    the data speaking or the guard deciding.

    **Degradation.** Every failure mode raises :class:`FitError` — too few usable
    production periods (three parameters need three), one elapsed time, a solver that
    did not converge, or a result that is not a usable curve. No ``scipy`` exception
    escapes this function, and a caller that gets a :class:`FitError` still has
    :func:`fit_exponential` to fall back on; :func:`select_decline_curve` does exactly
    that when the hyperbolic fit is ``None``.

    Production periods whose oil rate is not positive are dropped, by the same rule and
    to the same effect as the exponential fit's — see :func:`positive_rate_mask` and
    :class:`HyperbolicFit`.

    Args:
        elapsed_months: Elapsed time of each production period from the well's own
            first production period, as :func:`elapsed_months` returns it.
        oil_rate_bbl_d: Oil rate of each production period, bbl/d daily average.

    Returns:
        The fitted curve's ``qi``, nominal ``Di`` and decline curvature ``b``, its
        goodness of fit, and how many production periods it used.

    Raises:
        FitError: Fewer than three production periods have a positive oil rate, every
            production period shares one elapsed time, the fit did not converge, or the
            fit returned parameters that are not a usable decline curve.
    """
    fittable_elapsed, fittable_rates, n_kept, n_dropped = _fittable_production_periods(
        elapsed_months, oil_rate_bbl_d, 3, "a hyperbolic decline curve"
    )
    t_yr = to_years(fittable_elapsed)

    # Start from the exponential fit of the very same production periods: a two-parameter
    # fit of the same data is a sound place to start a three-parameter one. Clipped into
    # the hyperbolic's bounds, because the exponential's nominal decline can be negative
    # (a rising well) or absurdly steep, and the hyperbolic cannot represent either.
    exponential = fit_exponential(fittable_elapsed, fittable_rates)
    initial_guess = np.clip(
        [exponential.qi, exponential.Di, _INITIAL_CURVATURE],
        [_MIN_QI, MIN_NOMINAL_DECLINE, MIN_CURVATURE],
        [np.inf, MAX_NOMINAL_DECLINE, 1.0],
    )

    try:
        with warnings.catch_warnings():
            # OptimizeWarning means the optimiser could not estimate the parameter
            # covariance. Nothing here uses the covariance — the fitted curve and its
            # RMSE are what callers need — and a dashboard has no business printing it.
            warnings.simplefilter("ignore", OptimizeWarning)
            parameters, _ = curve_fit(
                _hyperbolic_model,
                t_yr,
                fittable_rates,
                p0=initial_guess,
                bounds=(
                    [_MIN_QI, MIN_NOMINAL_DECLINE, MIN_CURVATURE],
                    [np.inf, MAX_NOMINAL_DECLINE, 1.0],
                ),
                max_nfev=20000,
            )
    except (RuntimeError, ValueError) as error:
        # curve_fit raises RuntimeError when it does not converge and ValueError for a
        # problem with the inputs or the bounds. Either way the caller wants a FitError,
        # because the dashboard above this handles FitError and nothing else.
        raise FitError(
            f"a hyperbolic decline curve could not be fitted: {error}"
        ) from error

    qi, di_nominal, b = (float(value) for value in parameters)
    if not (
        np.isfinite([qi, di_nominal, b]).all()
        and qi > 0.0
        and di_nominal > 0.0
        and MIN_CURVATURE <= b <= 1.0
    ):
        raise FitError(
            "the hyperbolic decline curve fit returned parameters that are not a "
            f"decline curve: qi {qi}, Di {di_nominal}, b {b}"
        )

    fitted = hyperbolic_rate(qi, di_nominal, b, fittable_elapsed)
    r_squared, rmse_bbl_d = _goodness_of_fit(fittable_rates, fitted)

    return HyperbolicFit(
        qi=qi,
        Di=di_nominal,
        b=b,
        r_squared=r_squared,
        rmse_bbl_d=rmse_bbl_d,
        n_production_periods=n_kept,
        n_dropped=n_dropped,
    )


@dataclass(frozen=True)
class DeclineCurveSelection:
    """The well's decline curve: which of the two Arps curves it is, and its parameters.

    What a caller gets back from :func:`select_decline_curve`, so that nothing downstream
    has to ask which curve it is holding or re-derive the comparison that chose it. The
    parameters are flattened onto the selection, so a forecast can read ``qi``, ``Di``,
    ``b`` and :meth:`rate_at` without branching on the curve: the exponential's decline
    curvature is ``b = 0``, which is what "exponential" means.

    Attributes:
        curve: Which Arps curve is the decline curve, :data:`EXPONENTIAL_CURVE` or
            :data:`HYPERBOLIC_CURVE`.
        chosen_by: How that was decided: :data:`CURVE_BY_RMSE`,
            :data:`CURVE_BY_OVERRIDE` or :data:`CURVE_ONLY_AVAILABLE`.
        qi: Initial rate of the selected curve, bbl/d, back-extrapolated to ``t = 0``.
        Di: Initial nominal decline of the selected curve, as a fraction per year.
        b: Decline curvature of the selected curve. ``0.0`` for the exponential.
        r_squared: Rate-scale goodness of fit of the selected curve.
        rmse_bbl_d: Rate-scale RMSE of the selected curve, bbl/d.
        selected: The fitted curve that won, as its own fit object.
        exponential: The exponential fit, whether it won or not, so the comparison stays
            visible.
        hyperbolic: The hyperbolic fit, or ``None`` when it could not be fitted.
    """

    curve: str
    chosen_by: str
    qi: float
    Di: float
    b: float
    r_squared: float
    rmse_bbl_d: float
    selected: ExponentialFit | HyperbolicFit
    exponential: ExponentialFit
    hyperbolic: HyperbolicFit | None

    @property
    def rival_rmse_bbl_d(self) -> float:
        """RMSE of the curve that was **not** selected, bbl/d; ``nan`` if there is none.

        The rival is the other fitted curve, so this is what a reader needs to see the
        selection was earned rather than asserted. ``nan`` only when the hyperbolic fit
        does not exist, in which case there was nothing to compare against.
        """
        if self.curve == EXPONENTIAL_CURVE:
            return float("nan") if self.hyperbolic is None else self.hyperbolic.rmse_bbl_d
        return self.exponential.rmse_bbl_d

    @property
    def n_production_periods(self) -> int:
        """How many production periods the selected curve was fitted to."""
        return self.selected.n_production_periods

    @property
    def n_dropped(self) -> int:
        """How many production periods were dropped for a non-positive oil rate."""
        return self.selected.n_dropped

    def rate_at(self, elapsed_months: np.ndarray | float) -> np.ndarray:
        """The selected decline curve's oil rate at each elapsed time, bbl/d.

        Args:
            elapsed_months: Elapsed time in production periods from the well's first
                production period. ``0`` gives :attr:`qi` by definition.

        Returns:
            The selected curve's rate at each elapsed time, bbl/d, shaped like
            ``elapsed_months`` (a 0-d array for a scalar argument).
        """
        return self.selected.rate_at(elapsed_months)


def select_decline_curve(
    exponential: ExponentialFit,
    hyperbolic: HyperbolicFit | None = None,
    override: str | None = None,
    *,
    min_relative_improvement: float = MIN_RELATIVE_RMSE_IMPROVEMENT,
) -> DeclineCurveSelection:
    """Choose the well's decline curve: the lower-RMSE Arps curve, or an override.

    **Why a tie band and not simply the lower RMSE.** The exponential is the ``b -> 0``
    member of the Arps family, so the hyperbolic **contains** it and can never fit
    worse — it has one more parameter to spend. A bare lower-RMSE rule therefore
    degenerates to "always hyperbolic": measured over 720 draws of a genuinely
    exponential series with this project's ``+/- 1.5 %`` noise, it picked the hyperbolic
    on 44 % of them, from the extra parameter's freedom alone. So the hyperbolic is
    selected only when it improves the RMSE by more than ``min_relative_improvement``;
    inside that band the two curves are a tie.

    **Ties break to the exponential Arps curve.** With no evidence for the third
    parameter, the simpler two-parameter curve is the honest answer. The default band is
    2 % of the exponential's RMSE, measured as: 89.6 % of truly exponential wells land
    inside it, while every genuinely hyperbolic series measured at ``b >= 0.15`` beats
    the exponential by 27 % to 80 % — an order of magnitude outside it. The band
    suppresses that error rate rather than eliminating it, and it is a documented default
    rather than a guarantee: ``min_relative_improvement=0`` restores the bare comparison,
    and the shipped wells are unambiguous either way.

    **Override.** ``override`` forces the named curve, which is how an analyst
    experiments with the fits in the dashboard (spec user story 10). The RMSE comparison
    is still reported — :attr:`DeclineCurveSelection.chosen_by` says the choice was an
    override and :attr:`DeclineCurveSelection.rival_rmse_bbl_d` shows what it beat — so an
    override is visible as a departure from the comparison rather than a replacement of
    it.

    Args:
        exponential: The exponential fit for the well.
        hyperbolic: The hyperbolic fit for the well, or ``None`` if it could not be
            fitted. Either way the exponential is then the decline curve.
        override: Force a curve: :data:`EXPONENTIAL_CURVE` or :data:`HYPERBOLIC_CURVE`.
            ``None`` (the default) lets the RMSE comparison decide.
        min_relative_improvement: The tie band, as a fraction of the exponential's
            RMSE, that the hyperbolic has to beat to be selected. Defaults to
            :data:`MIN_RELATIVE_RMSE_IMPROVEMENT`.

    Returns:
        The decline curve as a :class:`DeclineCurveSelection`: which curve it is, why,
        its parameters, and both fits so the comparison stays inspectable.

    Raises:
        ValueError: ``override`` is not one of the two curve names, or it names a curve
            that was not fitted.
    """
    if override is not None:
        if override not in (EXPONENTIAL_CURVE, HYPERBOLIC_CURVE):
            raise ValueError(
                f"unknown decline curve {override!r} to override with: expected "
                f"{EXPONENTIAL_CURVE!r} or {HYPERBOLIC_CURVE!r}"
            )
        if override == HYPERBOLIC_CURVE and hyperbolic is None:
            raise ValueError(
                f"cannot override to the {HYPERBOLIC_CURVE!r} Arps curve: no "
                f"{HYPERBOLIC_CURVE} fit was supplied for this well"
            )
        curve, chosen_by = override, CURVE_BY_OVERRIDE
    elif hyperbolic is None:
        curve, chosen_by = EXPONENTIAL_CURVE, CURVE_ONLY_AVAILABLE
    elif hyperbolic.rmse_bbl_d < exponential.rmse_bbl_d * (
        1.0 - min_relative_improvement
    ):
        curve, chosen_by = HYPERBOLIC_CURVE, CURVE_BY_RMSE
    else:
        curve, chosen_by = EXPONENTIAL_CURVE, CURVE_BY_RMSE

    selected: ExponentialFit | HyperbolicFit = (
        exponential if curve == EXPONENTIAL_CURVE else hyperbolic
    )
    return DeclineCurveSelection(
        curve=curve,
        chosen_by=chosen_by,
        qi=selected.qi,
        Di=selected.Di,
        b=0.0 if curve == EXPONENTIAL_CURVE else float(selected.b),
        r_squared=selected.r_squared,
        rmse_bbl_d=selected.rmse_bbl_d,
        selected=selected,
        exponential=exponential,
        hyperbolic=hyperbolic,
    )
