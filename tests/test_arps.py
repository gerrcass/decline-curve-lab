"""Behaviour of the Arps decline-curve rate equations and the exponential fit.

The one seam for this project is the pure-function analysis library, so everything
here is exercised through ``decline_curve_lab.arps``: no mocks, no Streamlit.
"""

from __future__ import annotations

import numpy as np
import pytest

from decline_curve_lab import arps, io


def test_elapsed_months_counts_from_the_wells_own_first_production_period():
    """Each well's clock starts at its own first production period, not at a shared date.

    The wells start in different calendar months, so a shared clock would make one
    well's ``t = 0`` another well's ``t = 7``.
    """
    production = io.load_production(io.SAMPLE_CSV_PATH)

    for well_id, periods in production.groupby("well_id"):
        assert np.array_equal(
            arps.elapsed_months(periods), np.arange(len(periods))
        ), f"{well_id} elapsed time should be 0, 1, 2, ... from its own first period"


def test_years_from_months_is_the_single_time_axis_conversion():
    """``Di`` is nominal per *year* (ADR-0001), so months are converted once, here."""
    assert arps.to_years(24) == pytest.approx(2.0)
    assert arps.to_years(np.arange(13)) == pytest.approx(np.arange(13) / 12.0)


def test_the_exponential_arps_curve_drops_by_the_nominal_decline_over_a_year():
    """ADR-0001, as a number: one year multiplies the rate by ``1 / (1 + Di)``.

    This is the defining property of a *nominal* decline, and the reason the nominal
    rate is canonical here: at ``Di = 0.35`` the curve has fallen by exactly
    ``1 - 1/1.35 = 25.93 %`` after one year. It is not ``exp(-0.35)``, which is what a
    reader who treated ``Di`` as an effective decline would get.
    """
    qi, di_nominal = 500.0, 0.35

    after_a_year = arps.exponential_rate(qi, di_nominal, [12])[0]

    assert after_a_year == pytest.approx(qi / (1.0 + di_nominal), rel=1e-12)
    assert after_a_year == pytest.approx(370.3703703703704, rel=1e-12)


def test_the_exponential_arps_curve_starts_at_its_qi():
    """``qi`` is the curve's rate at ``t = 0``, by definition."""
    rates = arps.exponential_rate(260.0, 0.18, [0, 6, 12])

    assert rates[0] == pytest.approx(260.0)
    assert (np.diff(rates) < 0).all(), "an exponential decline curve falls"

def test_recovers_the_known_qi_and_di_of_a_noise_free_exponential():
    """A series generated from the curve equation must come back as itself.

    Tolerance ``rel=1e-9``: with no noise the regression is exact, so the only error
    left is floating-point round-off through ``exp``/``log1p`` — of order ``1e-15``
    relative, say ``1e-14`` after a few operations. ``1e-9`` leaves five orders of
    margin over that while staying far tighter than any real convention slip (see
    ``test_recovers_the_shipped_exponential_wells_qi_and_di_within_the_noise_tolerance``
    for what a slip costs), so the assertion cannot pass by luck and cannot fail on
    arithmetic.
    """
    qi, di_nominal = 500.0, 0.35
    elapsed = np.arange(72)
    rates = arps.exponential_rate(qi, di_nominal, elapsed)

    fit = arps.fit_exponential(elapsed, rates)

    assert fit.qi == pytest.approx(qi, rel=1e-9)
    assert fit.Di == pytest.approx(di_nominal, rel=1e-9)


def test_the_fitted_decline_is_the_nominal_one_and_not_the_effective_one():
    """ADR-0001: ``Di`` is stored nominal. The effective decline is derived, not stored.

    At ``Di = 0.35`` the effective decline is ``ln(1.35) = 0.30010``. Reporting that
    number instead would be a 14 % error, and the gap grows with every forecast year,
    so the distinction has to be pinned by a test rather than by convention alone.
    """
    di_nominal = 0.35
    elapsed = np.arange(72)
    rates = arps.exponential_rate(500.0, di_nominal, elapsed)

    fit = arps.fit_exponential(elapsed, rates)

    d_eff = arps.effective_decline_from_nominal(di_nominal)
    assert d_eff == pytest.approx(0.30010459245033805)
    assert fit.Di == pytest.approx(di_nominal, rel=1e-9)
    assert fit.Di != pytest.approx(arps.effective_decline_from_nominal(di_nominal), rel=1e-3)


def test_recovers_the_shipped_exponential_wells_qi_and_di_within_the_noise_tolerance():
    """Round-trip the committed sample data against the generator's ground truth.

    ``DCL-02`` is the shipped exponential well (``b = 0``): true ``q0 = 260 bbl/d`` at
    ``t = 0``, true ``Di = 0.18`` nominal per year, 72 production periods spanning 5.9
    years, oil rate carrying the generator's ``+/- 1.5 %`` multiplicative measurement
    noise.

    **Tolerances: 2 % on ``qi`` and 3 % on ``Di``.** Multiplicative uniform noise of
    fraction ``f`` puts a standard deviation of ``f/sqrt(3) = 0.87 %`` on ``ln q``;
    propagated over this well's 72 production periods and 5.9-year span that is a 1
    sigma of about 0.2 % on ``qi`` and 0.3 % on ``Di``. So these bands are roughly a
    10 sigma envelope around the propagated noise — wide enough that the test never
    fails on the seed's draw, and tight enough that it catches every convention this
    project can get wrong:

    ==========================  ==========  ===============================
    mistake                     ``Di`` error  caught by a 3 % band?
    ==========================  ==========  ===============================
    report effective, not nominal  -8.1 %     yes
    forget the months-to-years step  x12     yes
    ``Di * t`` with ``t`` in months  x12      yes
    ==========================  ==========  ===============================
    """
    production = io.load_production(io.SAMPLE_CSV_PATH)
    periods = production[production["well_id"] == "DCL-02"]

    fit = arps.fit_exponential(arps.elapsed_months(periods), periods["qo"])

    assert fit.qi == pytest.approx(260.0, rel=0.02)
    assert fit.Di == pytest.approx(0.18, rel=0.03)


def test_qi_is_the_back_extrapolated_rate_at_zero_and_not_the_first_observed_rate():
    """``qi`` is a model parameter at ``t = 0``, not the rate the well first produced.

    The fitted window starts a year into the well's history, so the curve's rate at
    ``t = 0`` is *higher* than anything observed: with ``Di = 0.35`` nominal the curve
    has fallen by ``1 - 1/1.35 = 25.93 %`` over that year, so ``qi`` must sit at
    ``1.35 x`` the first observed rate. Reading ``qi`` as a measurement would
    understate the well by 26 % here.
    """
    qi_true, di_nominal = 500.0, 0.35
    first_elapsed = 12
    elapsed = np.arange(first_elapsed, 84)
    rates = arps.exponential_rate(qi_true, di_nominal, elapsed)

    fit = arps.fit_exponential(elapsed, rates)

    assert fit.qi == pytest.approx(qi_true, rel=1e-9)
    assert float(fit.rate_at(0)) == pytest.approx(qi_true, rel=1e-9)
    assert fit.qi == pytest.approx(rates[0] * (1.0 + di_nominal), rel=1e-9)
    assert fit.qi > rates[0]


def test_the_fit_does_not_depend_on_where_the_fitted_window_starts():
    """A fit recovers the same curve from any window of the same noise-free decline.

    ``qi`` is defined at ``t = 0``, so a window that begins later must back-extrapolate
    to the same ``qi`` rather than re-anchoring at its own first production period.
    """
    qi_true, di_nominal = 260.0, 0.18
    whole_history = np.arange(72)
    rates = arps.exponential_rate(qi_true, di_nominal, whole_history)

    full = arps.fit_exponential(whole_history, rates)
    late = arps.fit_exponential(whole_history[12:], rates[12:])

    assert late.qi == pytest.approx(full.qi, rel=1e-9)
    assert late.Di == pytest.approx(full.Di, rel=1e-9)
    assert float(late.rate_at(0)) == pytest.approx(qi_true, rel=1e-9)


# An *absolute* +50 bbl/d offset on the exponential. The offset has to be additive, not
# multiplicative: a multiplicative bump is absorbed exactly by qi (a bumped exponential
# is still an exponential with a different qi), so it leaves no residual at all and
# cannot tell the two candidate scales apart. An additive offset lies outside the
# two-parameter exponential family, and its size bounds what each scale can report.
OFFSET_QI, OFFSET_DI, OFFSET_MONTHS, OFFSET_BBL_D = 500.0, 0.35, 72, 50.0


def test_the_rmse_is_a_rate_error_in_bbl_d_and_not_a_log_rate_error():
    """``rmse_bbl_d`` is measured on the rate scale, so it answers "how many bbl/d".

    The curve runs 500 -> 84.7 bbl/d over the 72 production periods and every observed
    rate carries a ``+50 bbl/d`` offset. That size pins the scale from both sides,
    without recomputing anything:

    * A **rate-scale** error can never exceed the size of the perturbation, so the
      RMSE is at most ``50`` bbl/d.
    * A **log-scale** error is bounded by the largest log residual any point can
      produce, ``ln(1 + 50/84.7) = 0.474``, so it cannot exceed 0.474 — and it comes
      out at 0.019 in practice, because the offset is small in ``ln q`` where the rates
      are large.

    The reported value is 6.07 bbl/d: inside the rate band, three hundred times the
    log-scale number.
    """
    elapsed = np.arange(OFFSET_MONTHS)
    rates = arps.exponential_rate(OFFSET_QI, OFFSET_DI, elapsed) + OFFSET_BBL_D

    fit = arps.fit_exponential(elapsed, rates)

    assert 1.0 < fit.rmse_bbl_d <= OFFSET_BBL_D, (
        f"rmse_bbl_d of {fit.rmse_bbl_d} is not a rate-scale error in bbl/d"
    )


def test_r_squared_is_measured_on_the_rate_scale_and_not_on_log_q():
    """``r_squared`` is the rate-scale ``1 - SS_res / SS_tot``, comparable across models.

    The same ``+50 bbl/d`` offset. A log-scale ``R**2`` would come out at 0.99788 here,
    because the offset is small in ``ln q`` at these rates, so the assertion band below
    — which excludes 0.9976 — rules it out. A rate-scale ``R**2`` cannot be defended
    that way, so it is also checked against the definition it claims to implement,
    restated from the public fitted curve. That second assertion pins the *scale*, not
    the arithmetic, and the fit's own arithmetic is pinned by the tests above.
    """
    elapsed = np.arange(OFFSET_MONTHS)
    observed = arps.exponential_rate(OFFSET_QI, OFFSET_DI, elapsed) + OFFSET_BBL_D

    fit = arps.fit_exponential(elapsed, observed)

    assert fit.r_squared < 0.9976, (
        "r_squared came out as the log-scale value, which is not comparable with the "
        "hyperbolic fit added later, since that is not a log-linear regression"
    )

    residuals = observed - fit.rate_at(elapsed)
    ss_residual = (residuals**2).sum()
    ss_total = ((observed - observed.mean()) ** 2).sum()
    rate_scale_r_squared = 1.0 - ss_residual / ss_total
    assert fit.r_squared == pytest.approx(rate_scale_r_squared, rel=1e-12)


def test_a_clean_fit_reports_a_perfect_goodness_of_fit():
    """On a noise-free exponential the curve passes through every point.

    ``r_squared`` saturates at 1 and ``rmse_bbl_d`` at 0 — and ``r_squared`` must *not*
    be ``nan``, which is what an unguarded ``SS_tot == 0`` division would produce.
    """
    elapsed = np.arange(72)
    rates = arps.exponential_rate(500.0, 0.35, elapsed)

    fit = arps.fit_exponential(elapsed, rates)

    assert fit.r_squared == pytest.approx(1.0, abs=1e-12)
    assert fit.rmse_bbl_d == pytest.approx(0.0, abs=1e-9)


def test_production_periods_at_or_below_zero_oil_rate_are_left_out_of_the_fit():
    """A shut-in or zeroed month cannot enter a log-linear fit, and is never imputed.

    ``ln q`` is undefined at and below zero. Two periods are zeroed out of an otherwise
    exact exponential, and the curve recovered from what remains must be the original
    one — which is only true if the zeros were dropped rather than replaced by a
    substitute rate.
    """
    elapsed = np.arange(72)
    rates = arps.exponential_rate(500.0, 0.35, elapsed)
    rates[[10, 11]] = 0.0

    fit = arps.fit_exponential(elapsed, rates)

    assert fit.qi == pytest.approx(500.0, rel=1e-9)
    assert fit.Di == pytest.approx(0.35, rel=1e-9)
    assert fit.n_production_periods == 70
    assert fit.n_dropped == 2


def test_a_fit_needs_two_positive_production_periods_at_different_elapsed_times():
    """Both ways of having nothing to fit raise, rather than returning ``nan``.

    With fewer than two usable production periods there is no line to fit; with every
    production period at one elapsed time there is no slope, so ``Di * t`` cannot be
    resolved. Neither may come back as a silently wrong number.
    """
    elapsed = np.arange(6)

    with pytest.raises(arps.FitError):
        arps.fit_exponential(elapsed[:1], np.array([120.0]))

    with pytest.raises(arps.FitError):
        arps.fit_exponential(np.zeros(4), np.array([120.0, 90.0, 60.0, 40.0]))


def test_a_well_that_never_declined_reports_no_r_squared_rather_than_a_perfect_one():
    """A flat oil rate leaves ``R**2`` undefined, and that is the honest answer.

    ``SS_tot`` is zero when every observed rate is equal, so the definition of
    ``R**2`` divides by zero. A well held flat on a plateau is a real possibility, and
    reporting ``R**2 = 1.0`` there would claim the exponential explained the data when
    in truth there was no decline to explain.
    """
    elapsed = np.arange(12)
    rates = np.full(12, 150.0)

    fit = arps.fit_exponential(elapsed, rates)

    assert np.isnan(fit.r_squared)
    assert fit.rmse_bbl_d == pytest.approx(0.0)
    assert fit.Di == pytest.approx(0.0)
