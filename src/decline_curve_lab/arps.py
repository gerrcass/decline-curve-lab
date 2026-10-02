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

=======================  ===================================================
exponential (``b = 0``)  ``q(t) = qi * exp(-D * t)``
hyperbolic               ``q(t) = qi * (1 + b * D * t) ** (-1 / b)``
harmonic (``b = 1``)     the ``b = 1`` case of the hyperbolic
=======================  ===================================================

The hyperbolic and the harmonic do not exist yet; they land in a later ticket along
with model selection. The exponential is the ``b -> 0`` limit of the hyperbolic, so
what is here is the base the rest of the family is added to.

"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

__all__ = [
    "ExponentialFit",
    "FitError",
    "MONTHS_PER_YEAR",
    "effective_decline_from_nominal",
    "elapsed_months",
    "exponential_rate",
    "fit_exponential",
    "positive_rate_mask",
    "to_years",
]

#: Production periods are months, so this is the months-per-year factor that
#: :func:`to_years` divides by. Declines are nominal per year, production periods are
#: not.
MONTHS_PER_YEAR: int = 12


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

    Args:
        elapsed_months: Elapsed time of each production period from the well's own
            first production period, as :func:`elapsed_months` returns it.
        oil_rate_bbl_d: Oil rate of each production period, bbl/d daily average.

    Returns:
        The fitted curve's ``qi`` and nominal ``Di``, its goodness of fit, and how
        many production periods it used.

    Raises:
        FitError: Fewer than two production periods have a positive oil rate, or
            every production period shares one elapsed time (so ``Di * t`` cannot be
            resolved and no slope exists).
    """
    elapsed = np.asarray(elapsed_months, dtype="float64")
    rates = np.asarray(oil_rate_bbl_d, dtype="float64")
    if elapsed.shape != rates.shape:
        raise FitError(
            "elapsed time and oil rate must have the same length, got "
            f"{elapsed.shape[0]} and {rates.shape[0]}"
        )

    keep = positive_rate_mask(rates)
    n_dropped = int((~keep).sum())
    if int(keep.sum()) < 2:
        raise FitError(
            f"an exponential decline curve needs at least two production periods with "
            f"a positive oil rate, got {int(keep.sum())}"
        )

    t_yr = to_years(elapsed[keep])
    ln_rate = np.log(rates[keep])

    # Ordinary least squares, written out so the slope and the intercept that the
    # parameters come from are visible rather than hidden behind a polyfit call.
    mean_t = t_yr.mean()
    mean_ln_rate = ln_rate.mean()
    spread_t = float(((t_yr - mean_t) ** 2).sum())
    if spread_t == 0.0:
        raise FitError(
            "every production period shares one elapsed time, so the decline cannot "
            "be fitted: the curve needs at least two distinct elapsed times"
        )
    slope = float(((t_yr - mean_t) * (ln_rate - mean_ln_rate)).sum() / spread_t)
    intercept = mean_ln_rate - slope * mean_t

    qi = float(np.exp(intercept))
    # Di nominal per year, from the effective decline the slope carries (ADR-0001).
    di_nominal = float(np.expm1(-slope))

    # Goodness of fit on the rate scale, so it is in bbl/d and comparable across the
    # Arps curve models rather than only meaningful for a log-linear regression.
    fitted = exponential_rate(qi, di_nominal, elapsed[keep])
    residuals = rates[keep] - fitted
    ss_residual = float((residuals**2).sum())
    ss_total = float(((rates[keep] - rates[keep].mean()) ** 2).sum())
    r_squared = 1.0 - ss_residual / ss_total if ss_total > 0.0 else float("nan")
    rmse_bbl_d = float(np.sqrt((residuals**2).mean()))

    return ExponentialFit(
        qi=qi,
        Di=di_nominal,
        r_squared=r_squared,
        rmse_bbl_d=rmse_bbl_d,
        n_production_periods=int(keep.sum()),
        n_dropped=n_dropped,
    )