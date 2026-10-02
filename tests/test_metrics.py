"""Behaviour of the derived per-production-period metrics.

Water cut, gas-oil ratio and cumulative oil `Np` are all derived from the daily
average rates of one production period (ADR-0002). Every expected value below is
worked out by hand in the comment beside it, from the rates written in the fixture,
so a reader can check the arithmetic without running anything.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from decline_curve_lab import io, metrics

# One well, three production periods. The rates are chosen so each hand calculation
# is a round number, and so the well both crosses the 0.7 water cut a lift-candidate
# screen looks for and falls below the 100 bbl/d rate it looks for.
#
# 2024 is a leap year, so the middle production period has 29 days. A fixture in a
# common year would let a hard-coded February length pass unnoticed.
W1_ROWS = """\
date,well_id,qo,qw,qg,wellhead_pressure,choke
2024-01-01,W-1,100.0,25.0,2000.0,250.0,0.25
2024-02-01,W-1,80.0,20.0,1200.0,244.0,0.234375
2024-03-01,W-1,50.0,150.0,500.0,238.5,0.21875
"""

# Two wells, listed interleaved in the file so that accumulating over the file's row
# order rather than per well gives a visibly different answer.
TWO_WELLS_ROWS = """\
date,well_id,qo,qw,qg,wellhead_pressure,choke
2024-01-01,W-1,100.0,10.0,2000.0,250.0,0.25
2024-01-01,W-2,10.0,1.0,500.0,180.0,0.125
2024-02-01,W-1,50.0,25.0,1000.0,244.0,0.25
2024-02-01,W-2,20.0,2.0,1000.0,180.0,0.125
"""

# A shut-in well: no liquid at all, then water only, then oil only. The first
# production period has no liquid to take a fraction of; the second has no oil to
# take a gas-oil ratio against; the first two also show that a production period with
# no oil adds nothing to cumulative oil.
NO_OIL_ROWS = """\
date,well_id,qo,qw,qg,wellhead_pressure,choke
2024-01-01,W-3,0.0,0.0,0.0,150.0,0.0625
2024-02-01,W-3,0.0,40.0,0.0,150.0,0.0625
2024-03-01,W-3,40.0,0.0,800.0,150.0,0.0625
"""

# The thresholds a lift-candidate screen will use. They are fixtures for these
# tests, not tuning knobs: what matters is that the sample data holds these shapes.
LIFT_CANDIDATE_RATE_BBL_D = 100.0
HIGH_WATER_CUT = 0.7


def write_production(tmp_path, text: str, name: str = "production.csv"):
    """Write a production CSV for these tests to read back through the reader."""
    csv_path = tmp_path / name
    csv_path.write_text(text, encoding="utf-8")
    return csv_path


def read_production(tmp_path, text: str, name: str = "production.csv") -> pd.DataFrame:
    """Read a production CSV through the library's reader, the way the dashboard does.

    Building the input frame by hand would risk testing a frame the reader never
    produces: the dates and well ids here are the ones the library actually hands to
    the metrics.
    """
    return io.load_production(write_production(tmp_path, text, name))


def read_metrics(tmp_path, text: str, name: str = "production.csv") -> pd.DataFrame:
    """Read a production CSV and compute its metrics, end to end through the seam."""
    return metrics.compute_metrics(read_production(tmp_path, text, name))


def by_production_period(frame: pd.DataFrame) -> pd.DataFrame:
    """Index a frame by well and date, so two row orders can be compared."""
    return frame.set_index(["well_id", "date"]).sort_index()


def test_adds_water_cut_gas_oil_ratio_and_cumulative_oil_to_every_production_period(
    tmp_path,
):
    measured = read_metrics(tmp_path, W1_ROWS)

    assert tuple(measured.columns) == io.PRODUCTION_COLUMNS + metrics.METRIC_COLUMNS


def test_water_cut_is_the_water_share_of_the_liquid_produced(tmp_path):
    measured = read_metrics(tmp_path, W1_ROWS)

    # 2024-01: qw 25  / (qo 100 + qw 25)  = 25 / 125  = 0.20
    # 2024-02: qw 20  / (qo  80 + qw 20)  = 20 / 100  = 0.20
    # 2024-03: qw 150 / (qo  50 + qw 150) = 150 / 200 = 0.75
    assert measured["water_cut"].tolist() == [0.2, 0.2, 0.75]


def test_water_cut_rises_through_0_7_as_the_well_ages(tmp_path):
    """The water-cut shape a lift-candidate screen depends on has to be reachable.

    The 0.7 threshold itself belongs to a later ticket. What matters here is that the
    fixture's third production period is genuinely above it, so a screen written
    against this data has a case to find.
    """
    measured = read_metrics(tmp_path, W1_ROWS)

    assert (measured["water_cut"].iloc[:2] < HIGH_WATER_CUT).all()
    assert measured["water_cut"].iloc[2] > HIGH_WATER_CUT


def test_water_cut_is_zero_for_an_all_liquid_production_period(tmp_path):
    measured = read_metrics(tmp_path, NO_OIL_ROWS)

    # 2024-03: qw 0 / (qo 40 + qw 0) = 0 / 40 = 0.0
    assert measured["water_cut"].iloc[2] == 0.0


def test_water_cut_is_one_for_an_all_water_production_period(tmp_path):
    measured = read_metrics(tmp_path, NO_OIL_ROWS)

    # 2024-02: qw 40 / (qo 0 + qw 40) = 40 / 40 = 1.0
    assert measured["water_cut"].iloc[1] == 1.0


def test_water_cut_is_undefined_for_a_production_period_that_produced_no_liquid(
    tmp_path,
):
    """There is no fraction of zero liquid, so the ratio is undefined rather than zero."""
    measured = read_metrics(tmp_path, NO_OIL_ROWS)

    assert np.isnan(measured["water_cut"].iloc[0])


def test_gas_oil_ratio_is_the_gas_volume_produced_per_barrel_of_oil(tmp_path):
    measured = read_metrics(tmp_path, W1_ROWS)

    # 2024-01: qg 2000 scf/d / qo 100 bbl/d = 20 scf/bbl
    # 2024-02: qg 1200 scf/d / qo  80 bbl/d = 15 scf/bbl
    # 2024-03: qg  500 scf/d / qo  50 bbl/d = 10 scf/bbl
    assert measured["GOR"].tolist() == [20.0, 15.0, 10.0]


def test_gas_oil_ratio_is_undefined_for_a_production_period_with_no_oil(tmp_path):
    """No oil means no barrels to divide the gas by, so the ratio is undefined.

    Undefined rather than infinite: an infinite gas-oil ratio would read as "very
    gassy" and drag up any average it took part in, whereas a missing value stays
    missing and compares false against every threshold.
    """
    measured = read_metrics(tmp_path, NO_OIL_ROWS)

    assert np.isnan(measured["GOR"].iloc[0])
    assert np.isnan(measured["GOR"].iloc[1])


def test_cumulative_oil_is_the_running_total_of_the_volume_of_each_production_period(
    tmp_path,
):
    """Volume is the daily-average rate times the length of its own production period.

    2024-01 has 31 days: 100.0 bbl/d * 31 d = 3100 bbl, so Np = 3100.
    2024-02 has 29 days, because 2024 is a leap year: 80.0 bbl/d * 29 d = 2320 bbl,
    so Np = 3100 + 2320 = 5420.
    2024-03 has 31 days: 50.0 bbl/d * 31 d = 1550 bbl,
    so Np = 5420 + 1550 = 6970.
    """
    measured = read_metrics(tmp_path, W1_ROWS)

    assert measured["Np"].tolist() == [3100.0, 5420.0, 6970.0]


def test_cumulative_oil_uses_the_length_of_each_production_period_not_a_fixed_month(
    tmp_path,
):
    """EIA's 30.4-day average month is not used; the date fixes each period's length.

    The same arithmetic as the test above, stated as the two plausible wrong answers:
    a flat 30-day month would give 7000 bbl by 2024-03 instead of 6970, and 30.4 days
    would give 6991.2.
    """
    measured = read_metrics(tmp_path, W1_ROWS)

    assert measured["Np"].iloc[1] == 5420.0  # 29-day February, not 30 and not 30.4
    assert measured["Np"].iloc[2] != 7000.0


def test_cumulative_oil_restarts_for_each_well(tmp_path):
    """Wells are independent, so each well's cumulative oil starts from its own zero.

    W-1: 2024-01 100.0 bbl/d * 31 d = 3100 bbl; 2024-02 50.0 bbl/d * 29 d = 1450 bbl,
         so Np = 3100 and then 3100 + 1450 = 4550.
    W-2: 2024-01  10.0 bbl/d * 31 d =  310 bbl; 2024-02 20.0 bbl/d * 29 d =  580 bbl,
         so Np = 310 and then 310 + 580 = 890.
    Accumulating over the file's row order instead would give W-2 a first cumulative
    oil of 3100 + 310 = 3410.
    """
    measured = read_metrics(tmp_path, TWO_WELLS_ROWS)

    w1 = measured[measured["well_id"] == "W-1"]["Np"].tolist()
    w2 = measured[measured["well_id"] == "W-2"]["Np"].tolist()

    assert w1 == [3100.0, 4550.0]
    assert w2 == [310.0, 890.0]


def test_cumulative_oil_does_not_advance_during_a_production_period_with_no_oil(tmp_path):
    measured = read_metrics(tmp_path, NO_OIL_ROWS)

    # Both of W-3's first two production periods produced 0.0 bbl/d, so cumulative
    # oil stays at 0 until 2024-03: 40.0 bbl/d * 31 d = 1240 bbl.
    assert measured["Np"].tolist() == [0.0, 0.0, 1240.0]


def test_metrics_do_not_depend_on_the_order_of_the_input_production_periods(tmp_path):
    """The same production periods in any order give the same metrics.

    Production periods arrive in whatever order a CSV happens to list them, so a
    well's cumulative oil cannot depend on where its rows sit in the file.
    """
    production = read_production(tmp_path, TWO_WELLS_ROWS)

    from_ordered = metrics.compute_metrics(production)
    from_shuffled = metrics.compute_metrics(production.sample(frac=1.0, random_state=0))
    from_reversed = metrics.compute_metrics(production.iloc[::-1])

    pd.testing.assert_frame_equal(from_shuffled, from_ordered)
    pd.testing.assert_frame_equal(from_reversed, from_ordered)


def test_metrics_are_the_same_per_production_period_whatever_the_row_order(tmp_path):
    """Row order carries no meaning, so read them back by well and date to compare."""
    production = read_production(tmp_path, TWO_WELLS_ROWS)

    ordered = metrics.compute_metrics(production)
    shuffled = metrics.compute_metrics(production.sample(frac=1.0, random_state=0))

    pd.testing.assert_frame_equal(by_production_period(shuffled), by_production_period(ordered))


def test_lists_each_wells_production_periods_in_time_order(tmp_path):
    """The result is sorted by well then date, so it does not inherit the file's order."""
    production = read_production(tmp_path, TWO_WELLS_ROWS)

    measured = metrics.compute_metrics(production)

    assert list(measured["well_id"]) == ["W-1", "W-1", "W-2", "W-2"]
    for _, periods in measured.groupby("well_id", sort=False):
        assert periods["date"].is_monotonic_increasing


def test_leaves_the_production_periods_it_was_given_unchanged(tmp_path):
    """The metrics are added to a copy, so the caller's frame stays valid input."""
    production = read_production(tmp_path, W1_ROWS)
    before = production.copy(deep=True)

    metrics.compute_metrics(production)

    pd.testing.assert_frame_equal(production, before)


def test_computes_metrics_for_a_file_with_no_production_periods(tmp_path):
    measured = read_metrics(tmp_path, "date,well_id,qo,qw,qg,wellhead_pressure,choke\n")

    assert len(measured) == 0
    assert tuple(measured.columns) == io.PRODUCTION_COLUMNS + metrics.METRIC_COLUMNS


def test_rejects_a_frame_missing_the_rates_the_metrics_are_derived_from():
    """Name the column that is missing, rather than failing deep inside a division."""
    incomplete = pd.DataFrame({"well_id": ["W-1"], "qo": [100.0], "qw": [10.0]})

    with pytest.raises(io.SchemaError, match="qg"):
        metrics.compute_metrics(incomplete)


def test_cumulative_oil_never_falls_within_a_well_in_the_sample_data():
    """Cumulative oil is a running total, so it cannot fall inside one well."""
    measured = metrics.compute_metrics(io.load_production(io.SAMPLE_CSV_PATH))

    for well_id, periods in measured.groupby("well_id"):
        assert (periods["Np"].diff().dropna() >= 0).all(), (
            f"{well_id} cumulative oil should never fall"
        )


def test_water_cut_is_a_decimal_between_zero_and_one_throughout_the_sample_data():
    measured = metrics.compute_metrics(io.load_production(io.SAMPLE_CSV_PATH))

    assert measured["water_cut"].between(0.0, 1.0).all()
    assert measured["water_cut"].notna().all()


def test_the_sample_data_carries_the_cases_a_lift_candidate_screen_needs():
    """Pin the shapes later tickets screen for, so the sample data cannot lose them.

    Exactly one well crosses water cut above 0.7 (`DCL-04`), and exactly three wells
    fall below 100 bbl/d at some production period (`DCL-02`, `DCL-04`, `DCL-06`).
    """
    measured = metrics.compute_metrics(io.load_production(io.SAMPLE_CSV_PATH))

    high_water_cut = sorted(
        set(measured.loc[measured["water_cut"] > HIGH_WATER_CUT, "well_id"])
    )
    low_rate = sorted(
        set(measured.loc[measured["qo"] < LIFT_CANDIDATE_RATE_BBL_D, "well_id"])
    )

    assert high_water_cut == ["DCL-04"]
    assert low_rate == ["DCL-02", "DCL-04", "DCL-06"]


def test_the_days_per_production_period_rule_is_one_rule_for_every_monthly_series():
    """A production period's length is its calendar month's, and there is one place that says so.

    Cumulative oil ``Np``, the forecast's ``volume_bbl`` and the EUR all multiply a rate in
    bbl/d by the days in that production period. They are three call sites of a single rule —
    if they each read the length off ``days_in_month`` themselves they can drift, and a
    well's ``Np`` and its EUR would quietly end up on different bases. So the rule lives in
    ``io``, which owns the ``date`` column, and every monthly series reads it from there.

    EIA normalises every month to 30.4 days; this project does not, because the ``date``
    column is exact. So the answer for one calendar month has to come back exactly.
    """
    dates = pd.Series(pd.to_datetime(["2024-01-01", "2024-02-01", "2023-02-01", "2024-04-01"]))

    assert io.days_in_production_period(dates).tolist() == [31.0, 29.0, 28.0, 30.0]


def test_the_days_per_production_period_rule_accepts_a_frame_or_a_series_of_dates():
    """The rule is asked two ways — a whole frame and a bare run of dates — and agrees.

    ``metrics`` hands it a frame's ``date`` column; ``forecast`` holds a
    ``DatetimeIndex`` of the months a forecast or an EUR covers. Both must get the same
    numbers for the same months.
    """
    months = pd.date_range("2024-01-01", periods=4, freq="MS")
    frame = pd.DataFrame({"well_id": "W-1", "date": months})

    assert io.days_in_production_period(frame["date"]).tolist() == [31.0, 29.0, 31.0, 30.0]
    assert io.days_in_production_period(months).tolist() == [31.0, 29.0, 31.0, 30.0]
    assert io.days_in_production_period(frame).tolist() == [31.0, 29.0, 31.0, 30.0]
