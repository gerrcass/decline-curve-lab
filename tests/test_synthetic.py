"""Behaviour of the seeded synthetic generator."""

from __future__ import annotations

import pandas as pd
import pytest

from decline_curve_lab import io, synthetic

# A well crosses the lift-candidate rate below 100 bbl/d and the water-cut
# threshold above 0.7. These are the screening thresholds the generator has to
# produce cases around, not tuning knobs of the generator itself.
LOW_RATE_BBL_D = 100.0
HIGH_WATER_CUT = 0.7


def water_cut(periods: pd.DataFrame) -> pd.Series:
    """Water cut of each production period, as a decimal fraction.

    Local to these tests: ``decline_curve_lab.metrics`` does not exist yet and owns
    water cut when it lands, at which point this should call it instead.
    """
    return periods["qw"] / (periods["qo"] + periods["qw"])


def test_default_seed_regenerates_the_committed_sample_csv_byte_for_byte():
    """The committed sample CSV must be reproducible from the documented seed."""
    regenerated = synthetic.production_csv_bytes()

    committed = (io.SAMPLE_DATA_DIR / io.SAMPLE_CSV_NAME).read_bytes()

    assert regenerated == committed, (
        "data/sample_wells.csv is stale: regenerate it with "
        "`PYTHONPATH=src python -m decline_curve_lab.synthetic` and commit the result"
    )


def test_generated_production_periods_have_exactly_the_production_schema():
    production = synthetic.generate_production()

    assert tuple(production.columns) == io.PRODUCTION_COLUMNS


def test_every_well_starts_at_its_first_production_period_and_advances_one_month():
    production = synthetic.generate_production()

    for well_id, periods in production.groupby("well_id"):
        dates = pd.to_datetime(periods["date"])
        elapsed_months = [
            (date.year - dates.iloc[0].year) * 12 + (date.month - dates.iloc[0].month)
            for date in dates
        ]
        assert elapsed_months == list(range(len(periods))), (
            f"{well_id} production periods must start at t = 0 and advance one month each"
        )


def test_every_rate_is_a_daily_average_not_a_monthly_volume():
    """ADR-0002: a production period's rate is a daily average over that period.

    The generator's ``q0_bbl_d`` is a daily-average rate, so the oil rate of a
    well's first production period must sit within the measurement noise of it. If
    the generator ever wrote monthly volumes, the rate would be ~30x larger.
    """
    production = synthetic.generate_production()
    first_periods = production.groupby("well_id").first()

    for well in synthetic.DEFAULT_WELLS:
        observed = first_periods.loc[well.well_id, "qo"]
        assert observed == pytest.approx(well.q0_bbl_d, rel=well.rate_noise_fraction), (
            f"{well.well_id} first production period should carry its daily-average "
            f"oil rate {well.q0_bbl_d} bbl/d, not a monthly volume"
        )


def test_water_cut_rises_for_every_well():
    production = synthetic.generate_production()

    for well_id, periods in production.groupby("well_id"):
        water_cuts = water_cut(periods)
        assert water_cuts.iloc[-1] > water_cuts.iloc[0] + 0.05, (
            f"{well_id} water cut should rise over its production history"
        )


def test_gas_oil_ratio_evolves_for_every_well():
    """Gas-oil ratio should change materially, not sit flat."""
    production = synthetic.generate_production()

    for well_id, periods in production.groupby("well_id"):
        gor = periods["qg"] / periods["qo"]
        change = abs(gor.iloc[-1] - gor.iloc[0]) / gor.iloc[0]
        assert change > 0.2, f"{well_id} gas-oil ratio should evolve materially"


def test_exactly_one_well_falls_below_100_bbl_d_with_water_cut_above_0_7():
    """The lift-candidate case: low oil rate together with high water cut."""
    production = synthetic.generate_production()
    flagged = production[
        (production["qo"] < LOW_RATE_BBL_D)
        & (water_cut(production) > HIGH_WATER_CUT)
    ]

    flagged_wells = sorted(set(flagged["well_id"]))
    assert flagged_wells == ["DCL-04"]
    assert len(flagged) > 5, "the case should hold over several production periods"


def test_exactly_one_well_declines_in_wellhead_pressure_in_every_production_period():
    """The sustained wellhead-pressure decline case, isolated from every other rule.

    The well must decline in *every* production period, so a screening rule needs
    no arbitrary threshold to find it, and it must stay above 100 bbl/d with water
    cut below 0.7 so that the wellhead-pressure signal is not confounded with the
    other lift-candidate signals.
    """
    production = synthetic.generate_production()

    declining_wells = [
        well_id
        for well_id, periods in production.groupby("well_id")
        if (periods["wellhead_pressure"].diff().dropna() < 0).all()
    ]
    assert declining_wells == ["DCL-03"]

    dcl_03 = production[production["well_id"] == "DCL-03"]
    assert (dcl_03["qo"] > LOW_RATE_BBL_D).all()
    assert (water_cut(dcl_03) < HIGH_WATER_CUT).all()


def test_no_well_is_on_a_flat_decline_or_an_increasing_oil_rate():
    """Every well must actually decline: a fitted decline curve needs a falling rate."""
    production = synthetic.generate_production()

    for well_id, periods in production.groupby("well_id"):
        assert periods["qo"].iloc[-1] < periods["qo"].iloc[0], (
            f"{well_id} oil rate should fall over its production history"
        )


def test_the_shipped_wells_span_the_arps_family():
    """Later tickets need an exponential, a hyperbolic and a harmonic case."""
    curvatures = {well.decline_curvature for well in synthetic.DEFAULT_WELLS}

    assert 0.0 in curvatures, "no exponential (b = 0) well"
    assert 1.0 in curvatures, "no harmonic (b = 1) well"
    assert any(0.0 < b < 1.0 for b in curvatures), "no hyperbolic well"


def test_the_shipped_wells_include_a_shallow_and_a_steep_decline():
    """A shallow case and a steep case, so model selection has something to choose."""
    nominal_declines = [well.nominal_decline_per_year for well in synthetic.DEFAULT_WELLS]

    assert min(nominal_declines) <= 0.2, "no shallow decline well"
    assert max(nominal_declines) >= 0.5, "no steep decline well"


def test_the_committed_sample_csv_covers_every_shipped_well():
    committed = pd.read_csv(io.SAMPLE_CSV_PATH)

    assert sorted(committed["well_id"].unique()) == sorted(
        well.well_id for well in synthetic.DEFAULT_WELLS
    )


def test_the_sample_data_documents_the_daily_average_units_and_the_seed():
    """The ticket requires the daily-average convention to be stated in the sample data.

    Guards the committed sample data's own documentation from drifting away from the
    generator, so a reader of the CSV alone can tell what the rates mean.
    """
    readme = (io.SAMPLE_DATA_DIR / "README.md").read_text(encoding="utf-8")

    assert str(synthetic.DEFAULT_SEED) in readme, "the seed is not stated"
    assert "daily average" in readme
    for unit in ("bbl/d", "scf/d", "psi"):
        assert unit in readme, f"the {unit} unit is not stated"
    assert "ADR-0002" in readme, "the daily-average decision is not cited"


def test_a_different_seed_changes_the_production_periods():
    """The seed has to actually drive the noise, or it is not a seed."""
    default = synthetic.production_csv_bytes(synthetic.DEFAULT_SEED)
    other = synthetic.production_csv_bytes(synthetic.DEFAULT_SEED + 1)

    assert default != other