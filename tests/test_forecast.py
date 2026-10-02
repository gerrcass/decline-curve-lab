"""Behaviour of the oil-rate forecast, the terminal-decline switch and the EUR.

The one seam for this project is the pure-function analysis library, so everything here
is exercised through ``decline_curve_lab.forecast`` over decline curves ``arps``
selected: no mocks, no Streamlit.

Two conventions carry most of the assertions. The forecast window is the production
periods **after** the well's last observed one, on the well's own calendar, and every
volume is ``rate x the days in that calendar month`` — one production period is a
calendar month, so the month length is not a constant (2024-02-01 has 29 days and
2024-04-01 has 30). And the tail past the terminal decline is the EIA convention's
exponential continuation, *not* the hyperbolic curve run on, and *not* an exponential
re-anchored to ``qi``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from decline_curve_lab import arps, forecast, io


def production_periods(
    oil_rates, first: str = "2024-01-01", well_id: str = "W-1"
) -> pd.DataFrame:
    """One well's production periods carrying known oil rates, on a known calendar.

    Only ``date`` and ``qo`` matter to a forecast, so the other columns are written at
    zero rather than invented: a test about the forecast should not have to reason about
    a water cut it never mentions. The dates are the first of each month, as the
    generator writes them.
    """
    dates = pd.date_range(start=first, periods=len(oil_rates), freq="MS")
    return pd.DataFrame(
        {
            "date": dates,
            "well_id": well_id,
            "qo": np.asarray(oil_rates, dtype="float64"),
            "qw": 0.0,
            "qg": 0.0,
            "wellhead_pressure": 0.0,
            "choke": 0.0,
        }
    )


def selection_for(
    qi: float, di_nominal: float, b: float, elapsed: np.ndarray
) -> arps.DeclineCurveSelection:
    """A decline curve of exactly these parameters, selected through ``arps``.

    Builds the fits from the parameters rather than by fitting them, so a forecast test
    asserts against a curve it knows exactly and cannot be confused by fit error. The
    exponential is still supplied, because ``select_decline_curve`` needs it to decide
    between the two and the reader should be able to see the RMSE that won.
    """
    rates = (
        arps.exponential_rate(qi, di_nominal, elapsed)
        if b == 0.0
        else arps.hyperbolic_rate(qi, di_nominal, b, elapsed)
    )
    exponential = arps.fit_exponential(elapsed, rates)
    hyperbolic = (
        None if b == 0.0 else arps.fit_hyperbolic(elapsed, rates)
    )
    return arps.select_decline_curve(exponential, hyperbolic, override=None)


def test_the_forecast_covers_the_production_periods_after_the_last_observed_one():
    """The forecast starts at the production period after the well's last observed one.

    A 48-production-period well last produced at ``t = 47``, so the twelve forecast
    production periods are ``t = 48 .. 59`` — neither the observed window repeated nor
    the twelve *before* the last observation.
    """
    observed = 48
    elapsed = np.arange(observed)
    periods = production_periods(arps.exponential_rate(300.0, 0.40, elapsed))
    selection = selection_for(300.0, 0.40, 0.0, elapsed)

    result = forecast.forecast(selection, periods)

    assert result.periods["elapsed_months"].tolist() == list(range(observed, observed + 12))


def test_the_forecast_is_on_the_wells_own_calendar_months():
    """Each forecast production period carries the calendar month it stands for.

    A well whose first production period is 2020-01-01 and whose last is 2023-12-01
    forecasts 2024-01-01 through 2024-12-01. The dates follow from the well's *own*
    first production period, not from a fixed epoch: the shipped wells start in different
    months, so a shared clock would put one well's ``t = 0`` at another well's ``t = 7``.
    """
    observed = 48
    elapsed = np.arange(observed)
    periods = production_periods(
        arps.exponential_rate(300.0, 0.40, elapsed), first="2020-01-01"
    )
    selection = selection_for(300.0, 0.40, 0.0, elapsed)

    result = forecast.forecast(selection, periods)

    assert result.periods["date"].tolist() == list(
        pd.date_range("2024-01-01", periods=12, freq="MS")
    )


def test_a_forecast_volume_is_the_rate_times_the_days_in_that_calendar_month():
    """One production period is a calendar month, so its volume uses that month's days.

    This is the project's single rule for turning a daily-average rate into a volume, and
    it is the same rule ``metrics`` applies to cumulative oil ``Np``. The fixture forecasts
    2024, a leap year, so its month lengths are 31, 29, 31 and 30 days — a rule that used a
    constant 30.4 (EIA's), or a February that was not counted, would disagree with every
    one of them.
    """
    observed = 48
    elapsed = np.arange(observed)
    periods = production_periods(
        arps.exponential_rate(300.0, 0.40, elapsed), first="2020-01-01"
    )
    selection = selection_for(300.0, 0.40, 0.0, elapsed)

    result = forecast.forecast(selection, periods, months=4)
    days = result.periods["volume_bbl"] / result.periods["qo"]

    assert days.tolist() == pytest.approx([31.0, 29.0, 31.0, 30.0])
    assert result.periods["volume_bbl"].iloc[0] == pytest.approx(
        result.periods["qo"].iloc[0] * 31.0
    )


def test_the_forecast_rates_are_the_selected_decline_curves_own_rates():
    """A forecast reads ``qi``, ``Di`` and ``b`` off the selection and branches on nothing.

    The exponential is ``b = 0``, so the same code path serves both curves: with no
    terminal decline in play the forecast is exactly ``selection.rate_at`` at the forecast
    production periods.
    """
    elapsed = np.arange(60)
    for b in (0.0, 0.45, 1.0):
        rates = (
            arps.exponential_rate(400.0, 0.45, elapsed)
            if b == 0.0
            else arps.hyperbolic_rate(400.0, 0.45, b, elapsed)
        )
        periods = production_periods(rates)
        selection = selection_for(400.0, 0.45, b, elapsed)

        result = forecast.forecast(selection, periods, months=6)

        window = np.arange(60, 66)
        assert result.periods["qo"].to_numpy() == pytest.approx(
            selection.rate_at(window), rel=1e-12
        ), f"b = {b} should forecast the selected curve's own rates"

# A synthetic hyperbolic decline chosen so that the terminal switch falls *inside* the
# forecast window, which is what makes the switch observable rather than theoretical.
#
#   qi = 500 bbl/d, Di = 0.60 nominal/yr, b = 0.80, 120 observed production periods.
#
# With Di above the 0.10/yr terminal decline and b > 0, the instantaneous decline
# D(t) = D_eff / (1 + b * D_eff * t) falls from 0.4700/yr at t = 0 and reaches
# ln(1.10) = 0.09531/yr at
#
#   t_switch = (0.4700 / 0.09531 - 1) / (0.8 * 0.4700) = 10.4555 yr = 125.466 months
#   q_switch = 500 * (0.4700 / 0.09531) ** (-1/0.8)     = 68.0405 bbl/d
#
# so a twelve-month forecast over t = 120 .. 131 is hyperbolic for its first six
# production periods and on the exponential tail for its last six: the switch is a
# boundary inside the window, not a story about the far future.
SWITCH_QI, SWITCH_DI, SWITCH_B, SWITCH_HISTORY = 500.0, 0.60, 0.80, 120
SWITCH_T_YEARS = (np.log1p(0.60) / np.log1p(0.10) - 1.0) / (0.80 * np.log1p(0.60))
SWITCH_MONTHS = SWITCH_T_YEARS * 12.0
SWITCH_RATE_BBL_D = 500.0 * (np.log1p(0.60) / np.log1p(0.10)) ** (-1.0 / 0.80)


def switch_series() -> tuple[arps.DeclineCurveSelection, pd.DataFrame]:
    """The synthetic well above, as a decline curve and its production periods."""
    elapsed = np.arange(SWITCH_HISTORY)
    rates = arps.hyperbolic_rate(SWITCH_QI, SWITCH_DI, SWITCH_B, elapsed)
    return (
        selection_for(SWITCH_QI, SWITCH_DI, SWITCH_B, elapsed),
        production_periods(rates),
    )


def test_the_terminal_switch_falls_where_the_instantaneous_decline_reaches_the_terminal():
    """The switch happens at ``t = 125.466`` months, the worked-out switch time above.

    The instant the switch happens is the point of the convention: the hyperbolic runs
    until its own instantaneous decline ``D(t) = D_eff / (1 + b * D_eff * t)`` reaches the
    terminal decline, and not until some other production period or some fitted-window
    position.
    """
    selection, periods = switch_series()

    result = forecast.forecast(selection, periods)

    assert result.switch_elapsed_months == pytest.approx(SWITCH_MONTHS, rel=1e-12)
    assert result.switch_rate_bbl_d == pytest.approx(SWITCH_RATE_BBL_D, rel=1e-12)


def test_a_hyperbolic_forecast_that_crosses_the_terminal_decline_has_an_exponential_tail():
    """Past the switch the forecast is the exponential tail from the EIA convention.

    The expected values come from the convention's own formulas, worked out in the test
    and not read back from the module: ``t_switch`` and ``q_switch`` are literals derived
    above, and the tail is ``q_switch * exp(-D_tail_eff * (t - t_switch))`` with
    ``D_tail_eff = ln(1 + 0.10)``. Production periods ``t = 126 .. 131`` are the six past
    the switch at 125.466 months.
    """
    selection, periods = switch_series()

    result = forecast.forecast(selection, periods)
    tail_months = np.arange(126, 132)
    expected = SWITCH_RATE_BBL_D * np.exp(
        -np.log1p(0.10) * (tail_months / 12.0 - SWITCH_T_YEARS)
    )

    assert result.periods["elapsed_months"].tolist() == list(range(120, 132))
    assert result.periods["qo"].to_numpy()[6:] == pytest.approx(expected, rel=1e-12)


def test_the_rate_is_continuous_across_the_terminal_switch():
    """No jump in the rate at the switch: the two phases are the same number there.

    A switch that reset the tail to some other anchor — ``qi`` most of all — would make
    the forecast step at the boundary. Here the hyperbolic's own rate at the switch and
    the tail's rate there agree to twelve significant figures, because the tail is
    anchored to the rate *reached*, not to a starting value.
    """
    selection, periods = switch_series()

    result = forecast.forecast(selection, periods)
    at_the_switch = arps.hyperbolic_rate(
        SWITCH_QI, SWITCH_DI, SWITCH_B, result.switch_elapsed_months
    )
    tail_at_the_switch = SWITCH_RATE_BBL_D * np.exp(
        -np.log1p(0.10) * (result.switch_elapsed_months / 12.0 - SWITCH_T_YEARS)
    )

    assert float(at_the_switch) == pytest.approx(result.switch_rate_bbl_d, rel=1e-12)
    assert float(tail_at_the_switch) == pytest.approx(result.switch_rate_bbl_d, rel=1e-12)


def test_the_decline_rate_does_not_kink_at_the_terminal_switch():
    """Only curvature changes at the switch; the decline rate is continuous there.

    Two properties together. Across the boundary the one-sided slope of ``ln q`` is still
    the terminal decline — measured as a finite difference over the straddling production
    periods, so it is a property of the forecast's own numbers and not of a formula the
    module supplied. And along the tail ``ln q`` is *exactly* straight: its production
    period-to-production period differences are equal to twelve figures, which is what
    an exponential continuation means and what a ``(1 + D*(t - t_sw)) ** -1`` tail would
    not give.
    """
    selection, periods = switch_series()

    rates = forecast.forecast(selection, periods).periods["qo"].to_numpy()
    ln_rate = np.log(rates)
    tail_slope_per_month = np.diff(ln_rate)[6:]

    # A production period is a month, so a per-production-period decline multiplied by
    # twelve is the per-year one the terminal decline is quoted in.
    across_the_switch = -(ln_rate[6] - ln_rate[5]) * 12.0
    assert across_the_switch == pytest.approx(np.log1p(0.10), rel=1e-3)
    assert tail_slope_per_month == pytest.approx(
        [-np.log1p(0.10) / 12.0] * 5, rel=1e-12
    )


def test_the_forecast_tail_is_not_the_hyperbolic_decline_curve_run_on():
    """Past the switch the forecast is exponential, not the hyperbolic curve continued.

    The two curves agree in rate *and* slope at the switch, so twelve production periods
    later they are still within a few tenths of a percent of each other and comparing
    them there would prove nothing. Run far enough past the switch the difference is
    unmistakable: 29.5 years after the switch the tail has fallen to 26 % of what
    the un-switched hyperbolic would have given, which is the whole point of the
    terminal decline — it stops a long tail overstating recovery.
    """
    selection, periods = switch_series()

    result = forecast.forecast(selection, periods, months=360)
    last_month = result.periods["elapsed_months"].iloc[-1]
    un_switched = float(
        arps.hyperbolic_rate(SWITCH_QI, SWITCH_DI, SWITCH_B, last_month)
    )

    assert last_month == 479
    assert result.periods["qo"].iloc[-1] == pytest.approx(4.10480, rel=1e-4)
    assert result.periods["qo"].iloc[-1] < 0.30 * un_switched


def test_the_forecast_tail_starts_from_the_rate_at_the_switch_and_not_from_qi():
    """The tail continues from the rate reached at the switch, never re-anchored to ``qi``.

    Re-anchoring is the specific mistake the convention exists to prevent, and it is
    worth three times the oil here: an exponential restarted at ``qi`` at the switch would
    report 176.6 bbl/d where the tail actually reaches 65.1, because the hyperbolic has
    already fallen from 500 bbl/d to 68 bbl/d by the time the switch arrives.
    """
    selection, periods = switch_series()

    result = forecast.forecast(selection, periods)
    re_anchored = SWITCH_QI * np.exp(
        -np.log1p(0.10) * (result.periods["elapsed_months"].to_numpy() / 12.0)
    )

    assert result.periods["qo"].to_numpy()[-1] == pytest.approx(65.11477, rel=1e-4)
    assert result.periods["qo"].to_numpy()[-1] < 0.5 * re_anchored[-1]


def test_a_decline_at_or_below_the_terminal_rate_has_no_hyperbolic_phase():
    """``Di <= 0.10`` means the well is already at the terminal decline at ``t = 0``.

    There is no hyperbolic phase to run and nowhere for the switch to happen, so the
    forecast is the exponential Arps curve from the start and reports no switch time.
    Both sides of the boundary are exercised: the threshold exactly, and below it.
    """
    elapsed = np.arange(48)
    for di_nominal in (0.10, 0.08):
        rates = arps.hyperbolic_rate(500.0, di_nominal, 0.5, elapsed)
        periods = production_periods(rates)

        result = forecast.forecast(
            selection_for(500.0, di_nominal, 0.5, elapsed), periods
        )

        assert result.periods["qo"].to_numpy() == pytest.approx(
            arps.exponential_rate(500.0, di_nominal, np.arange(48, 60)), rel=1e-12
        ), f"Di = {di_nominal} should forecast the exponential from t = 0"
        assert np.isnan(result.switch_elapsed_months), "there is no switch to report"


def test_the_exponential_arps_curve_has_no_terminal_switch():
    """``b = 0`` already *is* the exponential, so the switch arithmetic is never reached.

    The switch time divides by ``b``, so this is the guard that keeps a selection whose
    decline curvature is ``0.0`` from dividing by zero and forecasting ``nan`` — the
    exponential is the common case, not an edge case.
    """
    elapsed = np.arange(48)
    rates = arps.exponential_rate(400.0, 0.45, elapsed)
    periods = production_periods(rates)

    result = forecast.forecast(selection_for(400.0, 0.45, 0.0, elapsed), periods)

    assert np.isfinite(result.periods["qo"].to_numpy()).all()
    assert result.periods["qo"].to_numpy() == pytest.approx(
        arps.exponential_rate(400.0, 0.45, np.arange(48, 60)), rel=1e-12
    )
    assert np.isnan(result.switch_elapsed_months)
    assert np.isnan(result.switch_rate_bbl_d)


def test_the_terminal_decline_is_ten_percent_nominal_a_year_by_default():
    """The documented default is EIA's threshold: 10 % nominal per year (ADR-0001).

    EIA prints it as "0.8 %/month", which is ``0.10/12``; the ``0.008`` that reading
    would give annualises to 9.6 %/yr and is recorded in the research note as a trap.
    """
    assert forecast.DEFAULT_TERMINAL_DECLINE_ANNUAL == 0.10
    # And a forecast reports the threshold it actually applied, so a reader of a forecast
    # that has no switch can still see what the curve was measured against.
    elapsed = np.arange(48)
    periods = production_periods(arps.exponential_rate(400.0, 0.45, elapsed))
    result = forecast.forecast(selection_for(400.0, 0.45, 0.0, elapsed), periods)

    assert result.terminal_decline_annual == 0.10


def test_the_terminal_decline_changes_where_the_forecast_switches():
    """A different terminal decline gives a different forecast, so the parameter binds.

    Raising the terminal decline to 0.20/yr moves the switch to 4.19646 yr = 50.3576
    months: before the whole forecast window, so every forecast production period is on
    the tail. Lowering it to 0.05/yr moves the switch to 22.96036 yr = 275.5244 months,
    well after the window, so the window is pure hyperbolic. The same well, the same fit,
    two visibly different forecasts.
    """
    selection, periods = switch_series()

    high = forecast.forecast(selection, periods, terminal_decline_annual=0.20)
    low = forecast.forecast(selection, periods, terminal_decline_annual=0.05)
    window = np.arange(120, 132)

    assert high.switch_elapsed_months == pytest.approx(50.3576, rel=1e-4)
    assert low.switch_elapsed_months == pytest.approx(275.5244, rel=1e-4)
    assert not high.switch_within_window and not low.switch_within_window
    # At 0.20/yr the whole window is past the switch and therefore on the tail: 44.95 bbl/d
    # at t = 131. At 0.05/yr the whole window is before it, so the window stays hyperbolic
    # at 65.16 bbl/d — 45 % higher, off the same fit and the same observed history.
    assert high.periods["qo"].iloc[-1] == pytest.approx(44.95490, rel=1e-5)
    assert low.periods["qo"].iloc[-1] == pytest.approx(
        float(arps.hyperbolic_rate(SWITCH_QI, SWITCH_DI, SWITCH_B, 131)), rel=1e-12
    )


# The EUR fixtures are exponential wells, because an exponential's integral is a closed
# form a reader can check by hand:
#
#     Np(t) [bbl yr / d] = (qi / D_eff) * (1 - exp(-D_eff * t_yr)),   D_eff = ln(1 + Di)
#
# The rate reaches a given economic limit rate at
# `t_end = ln(qi / q_min) / D_eff`, where `exp(-D_eff * t_end)` is exactly `q_min / qi`.
EUR_QI, EUR_DI, EUR_START = 1000.0, 0.30, "2020-01-01"
EUR_D_EFF = np.log1p(EUR_DI)


def exponential_well(qi: float, di_nominal: float) -> tuple[arps.DeclineCurveSelection, str]:
    """An exponential decline curve of exactly these parameters, with its first period."""
    return (
        selection_for(qi, di_nominal, 0.0, np.arange(12)),
        "2020-01-01",
    )


def eur_of(qi: float, di_nominal: float, **kwargs) -> forecast.EurEstimate:
    """The EUR of an exponential well of known parameters, read straight off the library."""
    curve, first_period = exponential_well(qi, di_nominal)
    return forecast.eur(curve, first_period, **kwargs)


def closed_form_eur_bbl(qi: float, di_nominal: float, q_min: float) -> float:
    """The continuous exponential integral from ``t = 0`` down to ``q_min``, in bbl.

    The project's own rule for turning a rate into a volume is ``rate x the days in that
    calendar month``, and ``Np_rate(t_yr) * 365.25`` is the *continuous* integral of the
    same curve. They are two estimators of the same volume and this function is the
    second one, used to check the first.
    """
    d_eff = np.log1p(di_nominal)
    t_end_years = np.log(qi / q_min) / d_eff
    return float((qi / d_eff) * (1.0 - np.exp(-d_eff * t_end_years)) * 365.25)


def test_the_eur_is_the_volume_down_to_the_economic_limit_rate_and_not_to_zero():
    """ADR-0003: the well is dead at the economic limit rate, so the EUR stops there.

    Below the economic limit rate the well is not producing, it is costing money, and
    counting that production would overstate its recovery. With ``qi = 1000 bbl/d``,
    ``Di = 0.30`` and an economic limit of 250 bbl/d, integrating all the way to zero would
    claim 1,392,148 bbl; the EUR is 1,059,675 bbl, 76 % of it. The cutoff is observable
    in the estimate: the last production period counted is still above the limit and the
    one after it is below.
    """
    result = eur_of(EUR_QI, EUR_DI, economic_limit_rate_bbl_d=250.0)

    to_zero = (EUR_QI / EUR_D_EFF) * 365.25
    assert to_zero == pytest.approx(1392148.4, rel=1e-6)
    assert result.eur_bbl == pytest.approx(1059675.1, rel=1e-5)
    assert result.eur_bbl < 0.80 * to_zero
    assert result.stop_reason == forecast.STOP_AT_ECONOMIC_LIMIT
    assert result.n_production_periods == 64


def test_the_eur_matches_the_closed_form_integral_down_to_the_economic_limit_rate():
    """The monthly sum and the continuous integral of the same curve agree to ~1 %.

    Both routes estimate the same volume and the conventions allow either, so they have to
    be checked against each other. They differ by about 1 %, in a direction the rule
    predicts: the project's days-per-period rule applies each production period's rate to
    the whole period, and a falling rate is therefore weighted at the *start* of every
    month. For this well that is ``(D_eff / 24) = 1.09 %`` per production period
    compounded, and the estimate is high by about that much — which is why a hand
    calculation checking an EUR needs this band rather than an equality.
    """
    result = eur_of(EUR_QI, EUR_DI)
    continuous = closed_form_eur_bbl(EUR_QI, EUR_DI, forecast.DEFAULT_ECONOMIC_LIMIT_RATE_BBL_D)

    assert continuous == pytest.approx(1390756.3, rel=1e-6)
    assert result.eur_bbl == pytest.approx(continuous, rel=0.02)
    assert result.eur_bbl > continuous


def test_raising_the_economic_limit_rate_raises_the_eur():
    """A lower economic limit credits the well more oil, monotonically.

    The economic limit rate is a parameter, not a constant, and this is the direction it
    has to move in: 1 bbl/d ends the well late and catches 1.41 MMbbl, 250 bbl/d ends it
    early and catches 1.06 MMbbl. A EUR that fell as the limit rose would be integrating
    something other than what it claims.
    """
    eurs = [eur_of(EUR_QI, EUR_DI, economic_limit_rate_bbl_d=q_min).eur_bbl
            for q_min in (1.0, 25.0, 100.0, 250.0, 500.0)]

    assert eurs == sorted(eurs, reverse=True)
    assert eurs[0] == pytest.approx(1405749.4, rel=1e-5)
    assert eurs[-1] == pytest.approx(708167.4, rel=1e-5)


def test_the_economic_limit_rate_binds_before_the_horizon_cap_on_an_ordinary_well():
    """A well that reaches the economic limit rate well inside the horizon stops there.

    ``qi = 1000 bbl/d`` at ``Di = 0.30`` reaches 1 bbl/d at 315.95 months, so the
    360-month cap never gets a chance to bind: the estimate says so, and reports the
    production period it ended on.
    """
    result = eur_of(EUR_QI, EUR_DI)

    assert result.stop_reason == forecast.STOP_AT_ECONOMIC_LIMIT
    assert result.n_production_periods == 316
    assert result.final_period == pd.Timestamp("2046-04-01")
    assert result.final_elapsed_months == 315


def test_the_horizon_cap_bounds_a_well_that_never_reaches_the_economic_limit_rate():
    """A shallow decline has not reached the economic limit when the cap runs out.

    At ``Di = 0.05`` the well is still at 232 bbl/d in production period 359, nowhere near
    1 bbl/d, so the cap is what ends the EUR and the estimate has to say so rather than
    report a well that is dead. Doubling the horizon to 720 months shows the cap is doing
    real work rather than coinciding with the answer: the EUR grows to 7.10 MMbbl, and it
    is still the cap that stops it, because the well is at 53.8 bbl/d then.
    """
    capped = eur_of(EUR_QI, 0.05, max_horizon_months=360)
    longer = eur_of(EUR_QI, 0.05, max_horizon_months=720)

    assert capped.stop_reason == forecast.STOP_AT_HORIZON_CAP
    assert capped.n_production_periods == 360
    assert capped.final_elapsed_months == 359
    assert capped.eur_bbl == pytest.approx(5765602.4, rel=1e-5)
    assert longer.stop_reason == forecast.STOP_AT_HORIZON_CAP
    assert longer.eur_bbl == pytest.approx(7099484.0, rel=1e-5)
    assert longer.eur_bbl > capped.eur_bbl


def test_a_well_already_at_the_economic_limit_rate_has_no_eur():
    """``qi`` at or below the economic limit rate means the well is dead from ``t = 0``.

    Not an error: a well whose back-extrapolated initial rate is already uneconomic has
    no economic production to integrate. The estimate is zero and still reports the
    economic limit as what stopped it.
    """
    result = eur_of(0.5, EUR_DI)

    assert result.eur_bbl == 0.0
    assert result.n_production_periods == 0
    assert result.final_period is None
    assert result.stop_reason == forecast.STOP_AT_ECONOMIC_LIMIT


def test_the_economic_limit_rate_is_one_barrel_per_day_by_default():
    """The documented default is ``q_min = 1.0`` bbl/d, with a 360-month horizon cap.

    1.0 bbl/d is about 1 % of the 100 bbl/d lift-screening threshold, so it is a plausible
    rate for a mature well that has already lost interest to artificial lift, and it keeps
    EUR numbers in the same order of magnitude as the rest of the project. The cap is
    EIA's 30 years (360 months), which bounds the hyperbolic and harmonic tails. Both are
    parameters: the real economic limit depends on oil price, operating cost and lift
    method, all of which are out of scope here, so the spec can only parameterise it.
    """
    assert forecast.DEFAULT_ECONOMIC_LIMIT_RATE_BBL_D == 1.0
    assert forecast.DEFAULT_MAX_HORIZON_MONTHS == 360


def test_a_harmonic_wells_eur_is_bounded_where_its_tail_would_not_be():
    """A harmonic tail is infinite, which is what the economic limit and the cap are for.

    A harmonic decline integrates to infinity: it would accumulate oil without end. Cut
    at the default economic limit rate it is a finite number, and cut at a horizon cap
    with an unreachable limit it is a different finite number. Both are the reason ADR-0003
    insists the EUR never runs toward zero.
    """
    elapsed = np.arange(24)
    rates = arps.hyperbolic_rate(200.0, 0.40, 1.0, elapsed)
    periods = production_periods(rates)
    curve = selection_for(200.0, 0.40, 1.0, elapsed)

    # 25 bbl/d is reachable inside the 360-month cap and 0.01 bbl/d is not, so the same
    # well exercises both cutoffs. Reaching 1 bbl/d on this harmonic takes 591 years.
    at_the_limit = forecast.eur(curve, periods, economic_limit_rate_bbl_d=25.0)
    at_the_cap = forecast.eur(curve, periods, economic_limit_rate_bbl_d=0.01)

    assert np.isfinite(at_the_limit.eur_bbl) and at_the_limit.eur_bbl > 0.0
    assert at_the_limit.stop_reason == forecast.STOP_AT_ECONOMIC_LIMIT
    assert at_the_limit.n_production_periods == 194
    assert at_the_cap.stop_reason == forecast.STOP_AT_HORIZON_CAP
    assert at_the_cap.n_production_periods == 360
    assert at_the_cap.eur_bbl > at_the_limit.eur_bbl


def test_the_eur_says_whether_the_terminal_switch_shaped_it():
    """The estimate reports whether the exponential tail was inside the integrated span.

    "The economic limit ended the EUR" and "an exponential tail shaped the EUR" are
    different stories and both occur on real wells. A steep, harmonic-ish well
    (``Di = 0.90``, ``b = 0.95``) switches at 112.85 months, inside a 360-production-period
    EUR. A shallow, gently-curved one (``Di = 0.30``, ``b = 0.10``) switches at 801.67
    months, well past the cap — and by then the curve has fallen to 0.032 bbl/d, below the
    economic limit rate, so its tail is never counted at all.

    **There is no general bound on where the switch can land.**
    ``t_switch = (D_eff / D_tail_eff - 1) / (b * D_eff) = (1 / D_tail_eff - 1 / D_eff) / b``,
    which is unbounded above as ``b -> 0`` and arbitrarily close to ``t = 0`` as
    ``Di -> 0.10`` from above. At ``b = 1`` only, it is below
    ``1 / D_tail_eff = 10.49`` years (production period 126). The ``late`` well above is
    ``b = 0.10`` and lands at production period 802 — past a 360-production-period horizon,
    and by then at 0.032 bbl/d, below the economic limit rate, so its exponential tail is
    never counted at all. So a hyperbolic's EUR is sometimes bounded by the terminal switch
    and sometimes not, and which one it is has to be measured per well, not assumed.
    """
    elapsed = np.arange(24)

    early = forecast.eur(
        selection_for(800.0, 0.90, 0.95, elapsed), "2020-01-01"
    )
    late = forecast.eur(
        selection_for(800.0, 0.30, 0.10, elapsed), "2020-01-01"
    )

    assert early.switch_elapsed_months == pytest.approx(112.8514, rel=1e-4)
    assert early.terminal_switch_bounds_eur
    assert late.switch_elapsed_months == pytest.approx(801.6677, rel=1e-4)
    assert not late.terminal_switch_bounds_eur
    assert late.switch_rate_bbl_d < forecast.DEFAULT_ECONOMIC_LIMIT_RATE_BBL_D


def fleet() -> pd.DataFrame:
    """The committed sample data, the fleet the EUR table reports on."""
    return io.load_production(io.SAMPLE_CSV_PATH)


def test_the_eur_table_reports_one_row_per_well_ordered_by_eur():
    """A fleet-wide EUR table, biggest well first, so wells can be compared and ranked.

    Ordering is the library's job rather than the dashboard's: an app that re-sorted the
    rows itself would have two places where "largest EUR first" is written down, and they
    would eventually disagree. Ties break on ``well_id`` so the order is reproducible.
    """
    table = forecast.eur_table(fleet())

    assert table["well_id"].tolist() == [
        "DCL-01",
        "DCL-05",
        "DCL-03",
        "DCL-02",
        "DCL-06",
        "DCL-04",
    ]
    assert table["eur_bbl"].is_monotonic_decreasing


def test_the_eur_table_carries_the_units_a_reader_needs_to_compare_wells():
    """Every column an analyst compares wells on, in the units the schema speaks.

    ``qi`` and ``Di`` are the fitted curve's own parameters: bbl/d, and nominal %/yr
    (ADR-0001, so it is reported as the fraction per year the library holds). ``b`` is the
    decline curvature, ``0`` for the exponential. The economic limit rate and the stop
    reason are on the row because they are what decided that well's EUR.
    """
    table = forecast.eur_table(fleet())

    assert table.columns.tolist() == list(forecast.EUR_TABLE_COLUMNS)
    row = table[table["well_id"] == "DCL-01"].iloc[0]
    assert row["curve"] == arps.HYPERBOLIC_CURVE
    assert row["chosen_by"] == arps.CURVE_BY_RMSE
    assert row["qi"] == pytest.approx(817.81, rel=1e-4)
    assert row["Di"] == pytest.approx(0.6221, rel=1e-3)
    assert row["b"] == pytest.approx(0.8709, rel=1e-3)
    assert row["rmse_bbl_d"] == pytest.approx(3.8177, rel=1e-4)
    assert row["economic_limit_rate_bbl_d"] == 1.0


def test_the_shipped_wells_round_trip_through_the_eur_table():
    """The committed sample data, end to end: EUR, curve, and what stopped each one.

    **All six wells are bounded by the 360-production-period horizon cap, not by the 1 bbl/d
    economic limit rate** — the slowest of them (``DCL-02``, the exponential) is still at
    1.86 bbl/d in production period 359, the last one the horizon covers, so it never reaches
    1 bbl/d at all. The terminal switch, on the other hand, *does* fire inside the horizon for
    the five hyperbolic wells, between production period 98 and 219, at rates between 19 and
    127 bbl/d — all of them still above the economic limit rate. So the switch shapes five of
    the six EURs and the cap ends all of them.

    The EURs are in a plausible range for wells of this size: 0.32 to 1.45 MMbbl, in the
    same order as the wells' own first-production-period rates.

    Those switches landing years beyond each well's 3-6 year history is a property of these six
    wells' fitted ``b`` and ``Di``, not of the convention: ``t_switch = (1 / D_tail_eff -
    1 / D_eff) / b`` is unbounded above as ``b -> 0`` and only bounded by
    ``1 / ln(1.10) = 10.5`` years at ``b = 1``, so a gently-curved well would switch past
    the horizon entirely. These six have ``b`` between 0.41 and 1.00, which puts every switch
    inside production period 219.
    """
    table = forecast.eur_table(fleet())
    production = fleet()

    assert table["eur_bbl"].tolist() == pytest.approx(
        [
            1451339.2,  # DCL-01
            1172029.0,  # DCL-05
            692993.6,  # DCL-03
            574462.7,  # DCL-02
            484379.3,  # DCL-06
            319851.1,  # DCL-04
        ],
        rel=1e-4,
    )
    assert table.set_index("well_id")["curve"].to_dict() == {
        "DCL-01": arps.HYPERBOLIC_CURVE,
        "DCL-02": arps.EXPONENTIAL_CURVE,
        "DCL-03": arps.HYPERBOLIC_CURVE,
        "DCL-04": arps.HYPERBOLIC_CURVE,
        "DCL-05": arps.HYPERBOLIC_CURVE,
        "DCL-06": arps.HYPERBOLIC_CURVE,
    }
    assert set(table["stop_reason"]) == {forecast.STOP_AT_HORIZON_CAP}

    switch_bounds = {}
    for well_id, periods in production.groupby("well_id"):
        elapsed = arps.elapsed_months(periods)
        selection = arps.select_decline_curve(
            arps.fit_exponential(elapsed, periods["qo"]),
            arps.fit_hyperbolic(elapsed, periods["qo"]),
        )
        switch_bounds[well_id] = forecast.eur(selection, periods).terminal_switch_bounds_eur

    assert switch_bounds == {
        "DCL-01": True,
        "DCL-02": False,  # the exponential Arps curve: no hyperbolic phase to switch
        "DCL-03": True,
        "DCL-04": True,
        "DCL-05": True,
        "DCL-06": True,
    }


def test_a_shipped_wells_eur_stops_at_the_economic_limit_rate_when_it_is_high_enough():
    """The economic limit path, exercised on real wells rather than a synthetic one.

    At the default 1.0 bbl/d no shipped well dies inside 30 years. At 250 bbl/d five of the
    six do, and two of those (``DCL-04`` at 181 bbl/d and ``DCL-06`` at 240 bbl/d) are
    already below the limit at ``t = 0`` and so have no EUR at all. This is the parameter
    doing the work ADR-0003 asks of it, and it is why the economic limit is an argument
    rather than a constant.
    """
    table = forecast.eur_table(fleet(), economic_limit_rate_bbl_d=250.0).set_index("well_id")

    assert set(table["stop_reason"]) == {forecast.STOP_AT_ECONOMIC_LIMIT}
    assert table.loc["DCL-04", "eur_bbl"] == 0.0
    assert table.loc["DCL-06", "eur_bbl"] == 0.0
    assert table.loc["DCL-02", "eur_bbl"] == pytest.approx(23588.0, rel=1e-3)
    assert table.loc["DCL-01", "eur_bbl"] == pytest.approx(691691.0, rel=1e-4)


def test_the_eur_table_follows_an_analysts_curve_override():
    """An override in the EUR table changes that well's curve and its EUR with it.

    The override is scoped to one well, because that is what the dashboard's control is: an
    analyst comparing one well's exponential against its hyperbolic should not silently
    change the other five wells' numbers. ``DCL-03`` under its RMSE-chosen hyperbolic has an
    EUR of 692,994 bbl; forced onto the exponential it falls to 529,010 bbl, because the
    exponential reaches the economic limit rate within the horizon where the hyperbolic does
    not — which also moves its stop reason.
    """
    by_rmse = forecast.eur_table(fleet()).set_index("well_id")
    overridden = forecast.eur_table(
        fleet(), override_well_id="DCL-03", override=arps.EXPONENTIAL_CURVE
    ).set_index("well_id")

    assert overridden.loc["DCL-03", "curve"] == arps.EXPONENTIAL_CURVE
    assert overridden.loc["DCL-03", "chosen_by"] == arps.CURVE_BY_OVERRIDE
    assert overridden.loc["DCL-03", "b"] == 0.0
    assert overridden.loc["DCL-03", "eur_bbl"] == pytest.approx(529009.9, rel=1e-4)
    assert overridden.loc["DCL-03", "stop_reason"] == forecast.STOP_AT_ECONOMIC_LIMIT
    # Every other well is untouched by a scoped override.
    assert overridden.drop("DCL-03")["eur_bbl"].tolist() == pytest.approx(
        by_rmse.drop("DCL-03")["eur_bbl"].tolist(), rel=1e-12
    )


def test_the_eur_table_sorts_by_any_column_in_either_direction():
    """The sort control in the dashboard is the library's ordering, so it has to work.

    Sorting is a parameter of :func:`eur_table`, not something the app does to the returned
    rows, and both directions have to be real: EUR descending for the default ranking, EUR
    ascending for "which wells are nearly done", and by RMSE for "which fits are worst".
    """
    fleet_production = fleet()

    ascending = forecast.eur_table(fleet_production, descending=False)
    by_rmse = forecast.eur_table(fleet_production, sort_by="rmse_bbl_d")
    by_worst_fit = forecast.eur_table(fleet_production, sort_by="rmse_bbl_d", descending=False)

    assert ascending["eur_bbl"].tolist() == sorted(ascending["eur_bbl"], reverse=False)
    assert by_rmse["rmse_bbl_d"].is_monotonic_decreasing
    assert by_worst_fit["rmse_bbl_d"].is_monotonic_increasing
    assert by_rmse["well_id"].iloc[0] == "DCL-01"
    # Ranking by EUR and ranking by fit quality are different orders, which is what makes
    # the column worth a control: the biggest well is not the worst fit here.
    assert by_rmse["well_id"].tolist() != ascending["well_id"].tolist()
    assert by_worst_fit["well_id"].tolist() == by_rmse["well_id"].tolist()[::-1]


def test_the_eur_table_reports_a_well_it_could_not_fit_rather_than_dropping_it():
    """A well with too little history to fit is reported, not silently missing.

    One production period is not a decline curve — ``arps`` needs two for the exponential —
    so a table that quietly left such a well out would under-report the fleet it looked at.
    The well is named on the returned frame instead.
    """
    production = pd.concat(
        [
            fleet(),
            pd.DataFrame(
                {
                    "date": [pd.Timestamp("2024-01-01")],
                    "well_id": ["DCL-99"],
                    "qo": [50.0],
                    "qw": [0.0],
                    "qg": [0.0],
                    "wellhead_pressure": [0.0],
                    "choke": [0.0],
                }
            ),
        ],
        ignore_index=True,
    )

    table = forecast.eur_table(production)

    assert table["well_id"].tolist() == [
        "DCL-01",
        "DCL-05",
        "DCL-03",
        "DCL-02",
        "DCL-06",
        "DCL-04",
    ]
    assert table.attrs["unfitted_well_ids"] == ["DCL-99"]


def test_the_eur_table_rejects_a_sort_column_it_does_not_report():
    """An unknown sort column is an error naming the columns it does report."""
    with pytest.raises(ValueError, match="eur_bbl"):
        forecast.eur_table(fleet(), sort_by="water_cut")


def test_floating_an_eur_gives_the_barrels_its_estimate_carries():
    """The library contract is a float of barrels; the estimate is that float, enriched.

    The spec's contract for ``eur`` is ``eur(fit, q_min=1.0, max_horizon_months=360) ->
    float`` in bbl, so a caller written against it should not have to reach inside the
    returned object for the number. Returning :class:`forecast.EurEstimate` instead is the
    better shape — it also carries where the integration stopped and why — so the gap is
    closed with ``__float__`` rather than by throwing the enrichment away. ``float(est)``
    has to be the same barrels as ``est.eur_bbl``, or the two ways of asking disagree.
    """
    estimate = eur_of(EUR_QI, EUR_DI, economic_limit_rate_bbl_d=250.0)

    assert float(estimate) == estimate.eur_bbl
    assert float(estimate) == pytest.approx(1059675.1, rel=1e-5)


def test_an_eur_estimate_compares_as_the_number_of_barrels_it_is():
    """``__float__`` makes the estimate usable where a number is expected.

    Sorting a list of estimates by recovery, or summing them across a fleet, has to give
    the same order and the same total as doing it on :attr:`EurEstimate.eur_bbl`, because
    both routes are asking for barrels.
    """
    eurs = [eur_of(EUR_QI, di) for di in (0.05, 0.30, 0.62)]
    by_attribute = [est.eur_bbl for est in eurs]

    assert sorted(eurs, key=float) == sorted(eurs, key=lambda est: est.eur_bbl)
    assert sum(float(est) for est in eurs) == pytest.approx(sum(by_attribute))
