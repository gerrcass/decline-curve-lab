"""Behaviour of the Arps decline-curve rate equations and the exponential fit.

The one seam for this project is the pure-function analysis library, so everything
here is exercised through ``decline_curve_lab.arps``: no mocks, no Streamlit.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from decline_curve_lab import arps, forecast, io


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


# ---------------------------------------------------------------------------
# The hyperbolic Arps curve, its fit, and the selection between the two curves
# ---------------------------------------------------------------------------

#: The low-noise multiplier used by the round-trip tests below: multiplicative uniform
#: ``+/- 1.5 %`` on each production period's oil rate, which is the noise level the
#: committed sample wells carry.
LOW_NOISE_FRACTION = 0.015

#: Ground truth for the round-trip tests: the ``DCL-01`` shape, a steep hyperbolic
#: decline that a curve fit has to recover out of noise.
QI_TRUE, DI_TRUE, B_TRUE, N_PERIODS_TRUE = 820.0, 0.62, 0.85, 48


def _low_noise_hyperbolic(seed: int = 20260902) -> tuple[np.ndarray, np.ndarray]:
    """A hyperbolic series with ``+/- 1.5 %`` multiplicative measurement noise."""
    elapsed = np.arange(N_PERIODS_TRUE)
    clean = arps.hyperbolic_rate(QI_TRUE, DI_TRUE, B_TRUE, elapsed)
    noise = 1.0 + LOW_NOISE_FRACTION * np.random.default_rng(seed).uniform(
        -1.0, 1.0, size=N_PERIODS_TRUE
    )
    return elapsed, clean * noise


def test_the_harmonic_arps_curve_is_a_different_curve_from_the_exponential_one():
    """``b = 1`` is the harmonic case of the hyperbolic, not the exponential ``b = 0``.

    Both are cited in the glossary as members of the same Arps family, which is exactly
    why they get collapsed by accident: at ``Di = 0.35`` and three years in, the harmonic
    sits at ``263.11`` bbl/d and the exponential at ``203.22`` bbl/d, a 59.9 bbl/d gap on
    a 263 bbl/d well. The literal values are worked out from the convention — the
    harmonic is ``qi / (1 + D_eff * t_yr)`` and the exponential is
    ``qi * exp(-D_eff * t_yr)``, with ``D_eff = ln(1 + Di)`` — so the assertion is a
    known-good literal rather than a restatement of the implementation.
    """
    harmonic = arps.hyperbolic_rate(500.0, 0.35, 1.0, [36])
    exponential = arps.exponential_rate(500.0, 0.35, [36])

    assert harmonic[0] == pytest.approx(263.11444244591354, rel=1e-12)
    assert exponential[0] == pytest.approx(203.22105370116347, rel=1e-12)
    assert harmonic[0] > exponential[0]


def test_the_hyperbolic_arps_curve_uses_the_effective_decline_and_not_the_nominal_one():
    """The rate equation is solved with ``D_eff = ln(1 + Di)``, per ADR-0001.

    The harmonic case is the cheapest way to see it, because its denominator is linear:
    ``qi / (1 + D_eff * 1 yr)`` is ``384.58`` bbl/d while the nominal-decline reading
    ``qi / (1 + Di * 1 yr)`` gives ``370.37`` bbl/d — which is precisely the exponential
    curve's one-year value. Reading ``Di`` straight into the equation would silently
    turn every harmonic into an exponential.
    """
    harmonic_after_a_year = arps.hyperbolic_rate(500.0, 0.35, 1.0, [12])

    assert harmonic_after_a_year[0] == pytest.approx(384.5844425929133, rel=1e-12)
    assert harmonic_after_a_year[0] != pytest.approx(500.0 / (1.0 + 0.35), rel=1e-3)


def test_the_hyperbolic_arps_curve_tends_to_the_exponential_one_as_b_goes_to_zero():
    """``b -> 0`` is the exponential, so a small curvature reproduces it.

    The limit is the reason the fit needs a floor on ``b`` (the equation divides by
    ``b``), and this test is what pins the *direction* of that limit: at the fit's own
    documented floor the harmonic-style and exponential curves agree to within the
    floor's own order of magnitude, and they are never equal away from it.
    """
    elapsed = [0.0, 12.0, 36.0, 60.0]

    nearly_exponential = arps.hyperbolic_rate(500.0, 0.35, arps.MIN_CURVATURE, elapsed)
    exponential = arps.exponential_rate(500.0, 0.35, elapsed)

    assert np.allclose(nearly_exponential, exponential, rtol=2.0e-2)
    assert arps.hyperbolic_rate(500.0, 0.35, 1.0, elapsed)[-1] != pytest.approx(
        exponential[-1], rel=1e-3
    )


def test_the_hyperbolic_arps_curve_starts_at_its_qi_and_falls():
    """``qi`` is the curve's rate at ``t = 0``, and the curve only ever falls."""
    rates = arps.hyperbolic_rate(260.0, 0.18, 0.55, [0, 6, 12, 36])

    assert rates[0] == pytest.approx(260.0)
    assert (np.diff(rates) < 0).all()


def test_recovers_the_known_qi_di_and_b_of_a_noise_free_hyperbolic():
    """A noise-free hyperbolic series must come back as itself, ``b`` included.

    **Tolerance: ``abs=1e-8`` on the decline curvature ``b`` and ``rel=1e-8`` on ``qi``
    and ``Di``.** The parameter the optimiser has to nail hardest is ``b``, because the
    equation divides by it, so the surviving error is floating-point round-off through
    ``log1p``/``exp`` amplified by ``1/b`` — worst at small ``b``, where the curve is
    flattest in ``b``. Measured over eight shapes spanning ``b = 0.15`` to ``b = 1.0``
    (36 to 60 production periods), the worst observed deviation is ``1.6e-10`` on ``b``,
    ``1.7e-10`` relative on ``Di`` and ``2.2e-11`` on ``qi``, so ``1e-8`` is roughly 60x
    margin over the arithmetic while staying far tighter than any convention this project
    can get wrong: reporting the effective decline instead of the nominal one is an 8.1 %
    error at ``Di = 0.18``, and forgetting the months-to-years step is a factor of 12.
    """
    elapsed = np.arange(N_PERIODS_TRUE)
    rates = arps.hyperbolic_rate(QI_TRUE, DI_TRUE, B_TRUE, elapsed)

    fit = arps.fit_hyperbolic(elapsed, rates)

    assert fit.b == pytest.approx(B_TRUE, abs=1e-8)
    assert fit.Di == pytest.approx(DI_TRUE, rel=1e-8)
    assert fit.qi == pytest.approx(QI_TRUE, rel=1e-8)
    assert fit.rmse_bbl_d == pytest.approx(0.0, abs=1e-6)
    assert fit.r_squared == pytest.approx(1.0, abs=1e-9)


def test_recovers_the_known_parameters_of_a_low_noise_hyperbolic():
    """The same round trip with the sample wells' own ``+/- 1.5 %`` noise level.

    **Tolerances: ``abs=0.15`` on ``b``, ``rel=0.15`` on ``Di``, ``rel=0.03`` on
    ``qi``.** Over 300 draws of that noise on this well's shape the observed envelope is
    ``|db| <= 0.11``, ``Di`` within 9.4 % and ``qi`` within 1.3 %, so these bands sit
    outside the whole envelope while remaining tight enough to catch a convention slip
    (the months-to-years error is a factor of 12 on ``Di``). They cannot be tightened to
    the noise-free bands because ``b`` is the least-identified parameter of the family
    over a four-year window: on a series that is exponential to within the noise, the
    curvature is only identified as "small".
    """
    elapsed, rates = _low_noise_hyperbolic()

    fit = arps.fit_hyperbolic(elapsed, rates)

    assert fit.b == pytest.approx(B_TRUE, abs=0.15)
    assert fit.Di == pytest.approx(DI_TRUE, rel=0.10)
    assert fit.qi == pytest.approx(QI_TRUE, rel=0.03)


def test_the_hyperbolic_fit_bounds_the_decline_curvature_to_one():
    """A series built from a ``b > 1`` curve comes back clamped at the top of the range.

    ``b > 1`` occurs in real fitted wells — the background research records EIA rows at
    ``b = 1.41`` and ``b = 1.44`` — and the glossary bounds the decline curvature ``b`` to
    ``[0, 1]``, so the bound is a deliberate project decision rather than an oversight.
    This series is generated from the extended family's ``b = 1.4`` member, and its
    unconstrained optimum is exactly ``b = 1.4``, so the bounded fit is pinned against
    the bound rather than against the data: it must come back at ``b = 1`` and still be a
    usable curve, because the analyst gets the best answer the project allows rather than
    a crash or a curve outside the Arps family.
    """
    elapsed = np.arange(60)
    faster_than_harmonic = arps.hyperbolic_rate(300.0, 0.5, 1.4, elapsed)

    fit = arps.fit_hyperbolic(elapsed, faster_than_harmonic)

    assert 0.0 <= fit.b <= 1.0
    assert fit.b == pytest.approx(1.0, abs=1e-6)
    assert fit.qi == pytest.approx(300.0, rel=0.05)
    assert np.isfinite(fit.rmse_bbl_d)
    assert (np.diff(fit.rate_at(elapsed)) <= 0).all()


def test_the_hyperbolic_fit_bounds_the_decline_curvature_away_from_zero():
    """An accelerating decline comes back clamped at the bottom of the range, not a ``nan``.

    Every member of the Arps family has a *decreasing* instantaneous decline rate, so a
    decline that accelerates — ``q = qi * exp(-k * t**2)``, whose decline rate rises with
    time — is outside the family, and its unconstrained optimum is a **negative**
    curvature (``-0.36`` here). The bound is what absorbs that: the fit comes back at
    :data:`arps.MIN_CURVATURE`, the flat end of the family, with a finite curve, instead
    of evaluating the ``1 / b`` it would otherwise need.
    """
    elapsed = np.arange(60)
    accelerating = 500.0 * np.exp(-0.35 * arps.to_years(elapsed) ** 2)

    fit = arps.fit_hyperbolic(elapsed, accelerating)

    assert fit.b == pytest.approx(arps.MIN_CURVATURE, abs=1e-8)
    assert np.isfinite(fit.rate_at(elapsed)).all()
    assert np.isfinite(fit.rmse_bbl_d)


def test_a_truly_exponential_series_fits_the_hyperbolic_curve_near_zero_curvature():
    """The hyperbolic fit must degenerate gracefully to the exponential, not diverge.

    The equation divides by ``b``, and ``b = 0`` *is* the exponential, which is fitted
    separately. So the fit is bounded away from zero (:data:`arps.MIN_CURVATURE`) and an
    exponential series has to come out at that bound with the exponential's own ``qi`` and
    ``Di``, not at some ``(qi, Di, b)`` combination that fits the window and says nothing
    about the well.
    """
    elapsed = np.arange(72)
    rates = arps.exponential_rate(260.0, 0.18, elapsed)

    fit = arps.fit_hyperbolic(elapsed, rates)

    assert fit.b <= arps.MIN_CURVATURE * 10
    assert fit.Di == pytest.approx(0.18, rel=1e-3)
    assert fit.qi == pytest.approx(260.0, rel=1e-3)


def test_the_hyperbolic_fit_leaves_out_the_same_production_periods_as_the_exponential():
    """Both curves must see the same production periods, or the RMSEs cannot be compared.

    The two fits are compared on RMSE, so they have to be fitted to the same production
    periods. ``ln q`` is undefined at and below zero, so zeroed months are dropped from
    both and counted by both.
    """
    elapsed = np.arange(72)
    rates = arps.hyperbolic_rate(500.0, 0.35, 0.5, elapsed)
    rates[[5, 6, 40]] = 0.0

    exponential = arps.fit_exponential(elapsed, rates)
    hyperbolic = arps.fit_hyperbolic(elapsed, rates)

    assert hyperbolic.n_production_periods == exponential.n_production_periods == 69
    assert hyperbolic.n_dropped == exponential.n_dropped == 3
    assert hyperbolic.b == pytest.approx(0.5, abs=1e-6)


def test_a_hyperbolic_fit_needs_three_production_periods_at_distinct_elapsed_times():
    """Three parameters need three production periods, and a slope needs two times.

    The exponential needs two production periods to fit a line through; the hyperbolic
    has three parameters, so two production periods can never identify it. Neither may
    come back as a silently wrong number, so both raise :class:`arps.FitError`.
    """
    elapsed = np.arange(4)
    rates = arps.hyperbolic_rate(300.0, 0.4, 0.5, elapsed)

    with pytest.raises(arps.FitError):
        arps.fit_hyperbolic(elapsed[:2], rates[:2])

    with pytest.raises(arps.FitError):
        arps.fit_hyperbolic(np.zeros(4), rates)


def test_a_well_with_too_little_history_still_fits_the_exponential_curve():
    """The degradation path: the hyperbolic raises, the exponential still answers.

    A well with two usable production periods is exactly the case where the dashboard
    must not fall over. :func:`arps.fit_hyperbolic` raises :class:`arps.FitError` for it,
    and :func:`arps.select_decline_curve` accepts a missing hyperbolic fit and keeps the
    exponential as the decline curve.
    """
    elapsed = np.arange(4)
    rates = arps.hyperbolic_rate(300.0, 0.4, 0.5, elapsed)
    truncated_elapsed, truncated_rates = elapsed[:2], rates[:2]

    exponential = arps.fit_exponential(truncated_elapsed, truncated_rates)
    selection = arps.select_decline_curve(exponential, None)

    assert selection.curve == arps.EXPONENTIAL_CURVE
    assert selection.b == 0.0
    assert selection.chosen_by == arps.CURVE_ONLY_AVAILABLE


def test_selection_keeps_the_hyperbolic_curve_for_a_series_that_is_hyperbolic():
    """On a clearly hyperbolic series the hyperbolic curve has the lower RMSE.

    ``b = 0.85`` over 48 production periods: the hyperbolic fit's RMSE is about 3.9 bbl/d
    against the exponential's 23.6 bbl/d, so the hyperbolic wins by a factor of six, far
    outside the tie band :data:`arps.MIN_RELATIVE_RMSE_IMPROVEMENT` allows.
    """
    elapsed, rates = _low_noise_hyperbolic()
    exponential = arps.fit_exponential(elapsed, rates)
    hyperbolic = arps.fit_hyperbolic(elapsed, rates)

    selection = arps.select_decline_curve(exponential, hyperbolic)

    assert hyperbolic.rmse_bbl_d < exponential.rmse_bbl_d
    assert selection.curve == arps.HYPERBOLIC_CURVE
    assert selection.chosen_by == arps.CURVE_BY_RMSE
    assert selection.qi == pytest.approx(hyperbolic.qi)
    assert selection.Di == pytest.approx(hyperbolic.Di)
    assert selection.b == pytest.approx(hyperbolic.b)
    assert selection.rmse_bbl_d == pytest.approx(hyperbolic.rmse_bbl_d)
    assert selection.rival_rmse_bbl_d == pytest.approx(exponential.rmse_bbl_d)


def test_selection_keeps_the_exponential_curve_for_a_truly_exponential_series():
    """On an exponential series the exponential curve has the lower RMSE.

    This is the case the tie band exists for. The exponential is the ``b -> 0`` member of
    the Arps family, so the hyperbolic *contains* it and can never fit worse: on noise a
    bare lower-RMSE rule picked the hyperbolic on 44 % of truly exponential wells across
    720 draws, purely from the extra parameter's freedom. With the band, the exponential
    wins here on a decisive margin, because on a noise-free series the exponential's RMSE
    is 5e-14 bbl/d and the hyperbolic's is 6.6e-4 bbl/d.
    """
    elapsed = np.arange(72)
    rates = arps.exponential_rate(260.0, 0.18, elapsed)
    exponential = arps.fit_exponential(elapsed, rates)
    hyperbolic = arps.fit_hyperbolic(elapsed, rates)

    selection = arps.select_decline_curve(exponential, hyperbolic)

    assert exponential.rmse_bbl_d < hyperbolic.rmse_bbl_d
    assert selection.curve == arps.EXPONENTIAL_CURVE
    assert selection.b == 0.0
    assert selection.qi == pytest.approx(exponential.qi)
    assert selection.Di == pytest.approx(exponential.Di)
    assert selection.rival_rmse_bbl_d == pytest.approx(hyperbolic.rmse_bbl_d)


def test_selection_keeps_the_exponential_curve_on_the_shipped_exponential_well():
    """``DCL-02`` is the shipped ``b = 0`` well, and it has to select the exponential.

    ``DCL-02`` carries the generator's ``+/- 1.5 %`` noise like every other sample well,
    so this is the noisy version of the test above. The hyperbolic fit gains 0.2 % of
    RMSE there — inside the 2 % tie band — and so the exponential is selected, as the
    well's ground truth (``b = 0``) requires.
    """
    production = io.load_production(io.SAMPLE_CSV_PATH)
    periods = production[production["well_id"] == "DCL-02"]
    elapsed = arps.elapsed_months(periods)

    selection = arps.select_decline_curve(
        arps.fit_exponential(elapsed, periods["qo"]),
        arps.fit_hyperbolic(elapsed, periods["qo"]),
    )

    assert selection.curve == arps.EXPONENTIAL_CURVE
    assert selection.b == 0.0


def test_a_tie_in_rmse_goes_to_the_exponential_arps_curve():
    """Equal RMSE is a tie, and the tie breaks to the simpler two-parameter curve.

    When the two curves are indistinguishable on the data there is no evidence for the
    third parameter, so the exponential — one parameter fewer — is the honest answer.
    The tie band around equality is :data:`arps.MIN_RELATIVE_RMSE_IMPROVEMENT`, and this
    test pins the exact-equality end of it.
    """
    elapsed, rates = _low_noise_hyperbolic()
    exponential = arps.fit_exponential(elapsed, rates)
    tied = arps.HyperbolicFit(
        qi=900.0,
        Di=0.5,
        b=0.5,
        r_squared=exponential.r_squared,
        rmse_bbl_d=exponential.rmse_bbl_d,
        n_production_periods=exponential.n_production_periods,
        n_dropped=exponential.n_dropped,
    )

    selection = arps.select_decline_curve(exponential, tied)

    assert selection.curve == arps.EXPONENTIAL_CURVE
    assert selection.qi == pytest.approx(exponential.qi)
    assert selection.rmse_bbl_d == pytest.approx(exponential.rmse_bbl_d)


def test_an_override_forces_the_other_arps_curve():
    """The manual override is spec user story 10: the analyst picks the curve.

    The RMSE comparison is still reported, so the override is visible as a departure
    from it rather than a replacement of it.
    """
    elapsed, rates = _low_noise_hyperbolic()
    exponential = arps.fit_exponential(elapsed, rates)
    hyperbolic = arps.fit_hyperbolic(elapsed, rates)

    forced = arps.select_decline_curve(
        exponential, hyperbolic, override=arps.EXPONENTIAL_CURVE
    )

    assert exponential.rmse_bbl_d > hyperbolic.rmse_bbl_d
    assert forced.curve == arps.EXPONENTIAL_CURVE
    assert forced.chosen_by == arps.CURVE_BY_OVERRIDE
    assert forced.qi == pytest.approx(exponential.qi)
    assert forced.b == 0.0
    assert forced.rival_rmse_bbl_d == pytest.approx(hyperbolic.rmse_bbl_d)


def test_an_override_that_names_a_curve_which_was_not_fitted_is_rejected():
    """An override cannot conjure a curve that does not exist, or invent a name."""
    elapsed, rates = _low_noise_hyperbolic()
    exponential = arps.fit_exponential(elapsed, rates)

    with pytest.raises(ValueError, match="hyperbolic"):
        arps.select_decline_curve(exponential, None, override=arps.HYPERBOLIC_CURVE)

    with pytest.raises(ValueError, match="power"):
        arps.select_decline_curve(exponential, None, override="power law")


def test_the_selected_curve_reads_as_its_own_parameters_whatever_won():
    """Whichever curve won, the selection is the whole decline curve in one object.

    Forecasts read ``qi``, ``Di``, ``b`` and a rate evaluator from this and never have to
    ask which curve it is holding, and never have to special-case the exponential's
    ``b = 0``.
    """
    elapsed, rates = _low_noise_hyperbolic()
    exponential = arps.fit_exponential(elapsed, rates)
    hyperbolic = arps.fit_hyperbolic(elapsed, rates)

    for selection in (
        arps.select_decline_curve(exponential, hyperbolic),
        arps.select_decline_curve(
            exponential, hyperbolic, override=arps.EXPONENTIAL_CURVE
        ),
    ):
        assert float(selection.rate_at(0)) == pytest.approx(selection.qi)
        assert selection.Di >= 0.0
        curved = getattr(selection.selected, "b", 0.0)
        assert selection.b == pytest.approx(curved)
        assert selection.n_production_periods == selection.selected.n_production_periods
        assert selection.n_dropped == selection.selected.n_dropped


def test_the_shipped_wells_select_the_curve_the_generator_built():
    """The six committed wells select the curve their ground truth says they are.

    ``DCL-02`` is the shipped exponential well (``b = 0``); ``DCL-01``, ``DCL-03``,
    ``DCL-04``, ``DCL-05`` and ``DCL-06`` are hyperbolic, the last at the harmonic
    ``b = 1``. Measured on the committed CSV the hyperbolic curve wins the five
    hyperbolic wells by RMSE ratios of 0.17, 0.37, 0.16, 0.35 and 0.17, and the
    exponential wins ``DCL-02`` with the hyperbolic 0.2 % behind — so the selection is
    unambiguous for every shipped well.
    """
    production = io.load_production(io.SAMPLE_CSV_PATH)
    expected = {
        "DCL-01": arps.HYPERBOLIC_CURVE,
        "DCL-02": arps.EXPONENTIAL_CURVE,
        "DCL-03": arps.HYPERBOLIC_CURVE,
        "DCL-04": arps.HYPERBOLIC_CURVE,
        "DCL-05": arps.HYPERBOLIC_CURVE,
        "DCL-06": arps.HYPERBOLIC_CURVE,
    }
    selected: dict[str, str] = {}

    for well_id, periods in production.groupby("well_id"):
        elapsed = arps.elapsed_months(periods)
        selection = arps.select_decline_curve(
            arps.fit_exponential(elapsed, periods["qo"]),
            arps.fit_hyperbolic(elapsed, periods["qo"]),
        )
        selected[well_id] = selection.curve

    assert selected == expected


def test_the_shipped_hyperbolic_wells_recover_their_known_parameters():
    """Round-trip the committed hyperbolic wells against the generator's ground truth.

    **Tolerances: ``abs=0.10`` on the decline curvature ``b``, ``rel=0.05`` on ``Di``
    and ``rel=0.03`` on ``qi``**, against each well's true ``q0``, ``Di`` and ``b``. Every
    shipped hyperbolic well is measured within 0.05 of its true curvature, 2 % of its
    nominal decline and 0.6 % of its initial rate, so these bands are roughly a
    2-5x envelope over the whole set while still catching every convention slip: the
    harmonic well ``DCL-06`` is the case that fails loudly if ``b = 1`` is collapsed into
    the exponential ``b = 0``.
    """
    production = io.load_production(io.SAMPLE_CSV_PATH)
    truths = {
        "DCL-01": (820.0, 0.62, 0.85),
        "DCL-03": (410.0, 0.40, 0.45),
        "DCL-04": (180.0, 0.52, 0.70),
        "DCL-05": (520.0, 0.30, 0.55),
        "DCL-06": (240.0, 0.55, 1.00),
    }
    measured: dict[str, tuple[float, float, float]] = {}

    for well_id, (q0, di, b) in truths.items():
        periods = production[production["well_id"] == well_id]
        fit = arps.fit_hyperbolic(arps.elapsed_months(periods), periods["qo"])
        measured[well_id] = (fit.qi, fit.Di, fit.b)

    for well_id, (q0, di, b) in truths.items():
        fitted_qi, fitted_di, fitted_b = measured[well_id]
        assert fitted_qi == pytest.approx(q0, rel=0.03), f"{well_id} qi"
        assert fitted_di == pytest.approx(di, rel=0.05), f"{well_id} Di"
        assert fitted_b == pytest.approx(b, abs=0.10), f"{well_id} b"


def test_a_fit_that_cannot_be_evaluated_raises_a_fit_error_and_not_a_bare_value_error():
    """The degradation contract covers the exponential fit too, not only the hyperbolic.

    ``fit_exponential`` reports "no fit here" by returning ``qi``, ``Di`` and an RMSE, so
    the only way it can refuse is by raising — and it promises :class:`arps.FitError`, which
    is what every caller above it catches (``eur_table`` names the well unfitted,
    ``select_decline_curve`` falls back to the other curve, the dashboard shows a warning
    and carries on). A plain ``ValueError`` from the rate equation underneath would sail
    straight past all three.

    A rising well is what reaches it. ``Di = expm1(-slope)``, so ``slope >= 40``/yr drives
    ``Di`` to exactly ``-1.0`` in float64 — ``expm1(-40) == -1.0`` — and the rate equation
    refuses to take a logarithm of ``1 + Di <= 0``. Two production periods 30 years apart
    can carry a slope that steep: the fit divides the log-rate spread by the time spread, so
    spanning 30 years turns a rise from ``1e-300`` to ``1e+300`` bbl/d into ``slope = 92``.
    """
    elapsed = np.array([0.0, 360.0])
    rising = np.array([1e-300, 1e300])

    with pytest.raises(arps.FitError):
        arps.fit_exponential(elapsed, rising)


def test_the_fleet_table_names_a_well_whose_exponential_fit_cannot_be_evaluated():
    """``eur_table`` catches :class:`arps.FitError`, so the well is named rather than raised on.

    This is the promise the module docstring makes — "a dashboard has no business crashing
    on a hostile well" — seen from the function a dashboard actually calls. The two
    production periods are the same hostile ones the fit refuses: a well whose oil rate rises
    by fifteen orders of magnitude across a 30-year history.
    """
    production = io.load_production(io.SAMPLE_CSV_PATH)
    hostile = pd.DataFrame(
        {
            "well_id": ["HOSTILE", "HOSTILE"],
            "date": pd.to_datetime(["2020-01-01", "2050-01-01"]),
            "qo": [1e-300, 1e300],
        }
    )
    table = forecast.eur_table(pd.concat([production, hostile], ignore_index=True))

    assert "HOSTILE" in table.attrs["unfitted_well_ids"]
    assert "HOSTILE" not in set(table["well_id"])


def test_the_nominal_decline_floor_is_a_documented_bound_rather_than_a_hidden_one():
    """The hyperbolic fit cannot represent a rising well, and says which guard stopped it.

    ``Di`` is bounded to ``[arps.MIN_NOMINAL_DECLINE, arps.MAX_NOMINAL_DECLINE]`` because the
    rate equation divides by nothing but does need ``1 + b * D_eff * t >= 1`` at every
    production period, which a non-positive ``Di`` would break. The floor was a private
    constant, so a caller could see a well's decline stop at ``Di = 1e-9`` with no way to
    find out that was a guard rather than the answer.

    A well rising at 30 %/yr is the case: its exponential fit says ``Di = -0.259`` — the
    Arps family has no such curve, so ``Di`` comes back at the floor, and the exponential
    wins the RMSE comparison by five orders of magnitude because the hyperbolic is the only
    curve here being forced to answer about a decline it does not see.
    """
    elapsed = np.arange(48)
    rising = 300.0 * np.exp(0.30 * arps.to_years(elapsed))

    exponential = arps.fit_exponential(elapsed, rising)
    hyperbolic = arps.fit_hyperbolic(elapsed, rising)
    selection = arps.select_decline_curve(exponential, hyperbolic)

    assert exponential.Di < 0.0, "the exponential has no such bound and can say so"
    assert hyperbolic.Di == pytest.approx(arps.MIN_NOMINAL_DECLINE)
    assert arps.NOMINAL_DECLINE_FLOOR_BOUND in hyperbolic.bounds_active
    assert selection.curve == arps.EXPONENTIAL_CURVE
    assert selection.rmse_bbl_d < hyperbolic.rmse_bbl_d


def test_a_clamped_decline_curvature_is_reported_on_the_fit():
    """``b > 1`` is a real fitted-well shape, so the clamp at 1 is worth surfacing.

    The glossary bounds decline curvature ``b`` to ``[0, 1]`` and the background research
    records EIA rows at ``b = 1.41`` and ``b = 1.44``, so a fit pinned against that ceiling is
    answering "the best the Arps family allows", not "the well declines harmonically". The
    fit reports which bound it sits on so a caller can tell those apart.
    """
    elapsed = np.arange(60)
    faster_than_harmonic = arps.hyperbolic_rate(300.0, 0.5, 1.4, elapsed)

    fit = arps.fit_hyperbolic(elapsed, faster_than_harmonic)

    assert fit.bounds_active == (arps.CURVATURE_CEILING_BOUND,)


def test_a_clamped_decline_curvature_at_the_floor_is_reported_on_the_fit():
    """An accelerating decline is outside the Arps family and comes back at the floor.

    Every member of the family has a *decreasing* instantaneous decline, so a decline whose
    rate rises with time is outside it and its unconstrained optimum is a negative curvature.
    The floor absorbs that, and the fit reports that the floor is what absorbed it.
    """
    elapsed = np.arange(60)
    accelerating = 500.0 * np.exp(-0.35 * arps.to_years(elapsed) ** 2)

    fit = arps.fit_hyperbolic(elapsed, accelerating)

    assert fit.bounds_active == (arps.CURVATURE_FLOOR_BOUND,)


def test_a_fit_that_stayed_inside_the_bounds_reports_none():
    """The common case has to be the empty answer, or the signal means nothing.

    Five of the six shipped wells fit well inside every bound — including ``DCL-02``, the
    exponential well, whose fitted curvature comes back at ``b = 0.018`` rather than pinned
    against the floor — so an active bound on some other well is informative rather than
    noise. ``DCL-06`` is the exception and the interesting one: the generator built it
    harmonic, its fit lands on ``b = 1``, and the bound it reports is the ceiling, which is
    the truthful reading of that well rather than a clamp that lost information.
    """
    production = io.load_production(io.SAMPLE_CSV_PATH)

    reported = {
        well_id: arps.fit_hyperbolic(arps.elapsed_months(periods), periods["qo"]).bounds_active
        for well_id, periods in production.groupby("well_id")
    }

    assert {well_id for well_id, bounds in reported.items() if bounds} == {"DCL-06"}
    assert reported["DCL-06"] == (arps.CURVATURE_CEILING_BOUND,)


def test_the_reason_for_a_selection_never_claims_a_lower_rmse_it_does_not_have():
    """The one sentence that says how the decline curve was chosen has to be true.

    The exponential is the ``b -> 0`` member of the Arps family, so the hyperbolic contains
    it and can never fit worse; :data:`arps.MIN_RELATIVE_RMSE_IMPROVEMENT` exists to stop the
    third parameter buying a selection from noise alone. The price is that inside that band
    the selected curve can have the **worse** RMSE, and a sentence that says "the lower RMSE"
    is then simply false — while the other curve's RMSE sits in the metric beside it. So the
    wording is derived from the comparison rather than typed out, and this walks all six
    shipped wells asserting it against the numbers.
    """
    production = io.load_production(io.SAMPLE_CSV_PATH)

    for well_id, periods in production.groupby("well_id"):
        elapsed = arps.elapsed_months(periods)
        selection = arps.select_decline_curve(
            arps.fit_exponential(elapsed, periods["qo"]),
            arps.fit_hyperbolic(elapsed, periods["qo"]),
        )
        reason = arps.selection_reason(selection)

        if selection.rmse_bbl_d < selection.rival_rmse_bbl_d:
            assert reason.startswith("the lower RMSE"), f"{well_id}: {reason!r}"
        else:
            assert not reason.startswith("the lower RMSE"), f"{well_id}: {reason!r}"
            assert "tie band" in reason, f"{well_id}: {reason!r}"


def test_a_selection_won_outright_on_a_lower_rmse_says_so_and_by_how_much():
    """The outright case is the one that has to stay as simple as it ever was."""
    elapsed, rates = _low_noise_hyperbolic()
    selection = arps.select_decline_curve(
        arps.fit_exponential(elapsed, rates), arps.fit_hyperbolic(elapsed, rates)
    )

    assert selection.curve == arps.HYPERBOLIC_CURVE
    assert not selection.tie_band_decided
    assert selection.rmse_margin == pytest.approx(
        (selection.exponential.rmse_bbl_d - selection.rmse_bbl_d)
        / selection.exponential.rmse_bbl_d
    )
    assert arps.selection_reason(selection) == (
        f"the lower RMSE, by {selection.rmse_margin:.0%}"
    )


def test_a_selection_the_tie_band_decided_names_the_band_and_the_size_of_the_gap():
    """``DCL-02`` is the shipped exponential well, and it is chosen **on the band**.

    Its ground truth is ``b = 0``, so the exponential must win — but it wins with the *worse*
    RMSE: 1.5259 against the hyperbolic's 1.5217 bbl/d, a 0.3 % gap inside the 2 % band. So
    this is exactly the case where "chosen by the lower RMSE" is a lie, and the reason has to
    say what actually happened: a tie inside the band, and the tie going to the curve with one
    parameter fewer.
    """
    production = io.load_production(io.SAMPLE_CSV_PATH)
    periods = production[production["well_id"] == "DCL-02"]
    elapsed = arps.elapsed_months(periods)

    selection = arps.select_decline_curve(
        arps.fit_exponential(elapsed, periods["qo"]),
        arps.fit_hyperbolic(elapsed, periods["qo"]),
    )

    assert selection.curve == arps.EXPONENTIAL_CURVE
    assert selection.rmse_bbl_d > selection.rival_rmse_bbl_d, "the premise of this test"
    assert selection.tie_band_decided
    assert selection.rmse_margin < 0.0
    reason = arps.selection_reason(selection)
    assert "2% RMSE tie band" in reason
    assert "0.3% lower" in reason


def test_the_selection_records_the_band_it_decided_on():
    """The band is visible on the result, so a reader is never guessing at the criterion."""
    production = io.load_production(io.SAMPLE_CSV_PATH)
    periods = production[production["well_id"] == "DCL-02"]
    elapsed = arps.elapsed_months(periods)
    exponential = arps.fit_exponential(elapsed, periods["qo"])
    hyperbolic = arps.fit_hyperbolic(elapsed, periods["qo"])

    on_the_band = arps.select_decline_curve(exponential, hyperbolic)
    without_a_band = arps.select_decline_curve(
        exponential, hyperbolic, min_relative_improvement=0.0
    )

    assert on_the_band.rmse_tie_band == arps.MIN_RELATIVE_RMSE_IMPROVEMENT
    assert on_the_band.tie_band_decided
    assert without_a_band.rmse_tie_band == 0.0
    assert not without_a_band.tie_band_decided
    assert without_a_band.curve == arps.HYPERBOLIC_CURVE, "no band means the bare comparison"


def test_a_selection_that_was_not_an_rmse_comparison_says_which_it_was():
    """An override and a well with no hyperbolic curve are not RMSE decisions at all."""
    elapsed, rates = _low_noise_hyperbolic()
    exponential = arps.fit_exponential(elapsed, rates)
    hyperbolic = arps.fit_hyperbolic(elapsed, rates)

    override = arps.select_decline_curve(
        exponential, hyperbolic, override=arps.EXPONENTIAL_CURVE
    )
    only_available = arps.select_decline_curve(exponential, None)

    assert "override" in arps.selection_reason(override)
    assert not override.tie_band_decided
    assert "no hyperbolic Arps curve" in arps.selection_reason(only_available)
    assert not only_available.tie_band_decided
    assert np.isnan(only_available.rmse_margin), "there was no rival to compare against"
