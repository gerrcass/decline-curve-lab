"""Behaviour of the seeded synthetic generator."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from decline_curve_lab import io, metrics, synthetic

#: The directory holding the package, so a subprocess can import it exactly the way the
#: documented command does. Taken from the imported package rather than from the working
#: directory, so the test does not care whether the suite runs from a checkout or against
#: an installed copy.
SOURCE_DIR = Path(io.__file__).resolve().parents[1]

# A well crosses the lift-candidate rate below 100 bbl/d and the water-cut
# threshold above 0.7. These are the screening thresholds the generator has to
# produce cases around, not tuning knobs of the generator itself.
LOW_RATE_BBL_D = 100.0
HIGH_WATER_CUT = 0.7


def water_cut(periods: pd.DataFrame) -> pd.Series:
    """Water cut of each production period, as a decimal fraction.

    `decline_curve_lab.metrics` owns water cut, so these tests read it from there
    rather than dividing ``qw`` by ``qo + qw`` a second time here.
    """
    return metrics.compute_metrics(periods)["water_cut"]


def test_default_seed_regenerates_the_committed_sample_csv_byte_for_byte():
    """The committed sample CSV must be reproducible from the documented seed."""
    regenerated = synthetic.production_csv_bytes()

    committed = (io.SAMPLE_DATA_DIR / io.SAMPLE_CSV_NAME).read_bytes()

    assert regenerated == committed, (
        "data/sample_wells.csv is stale: regenerate it with "
        "`python -m decline_curve_lab` and commit the result"
    )


def _run_generator(out: Path, *extra: str) -> subprocess.CompletedProcess:
    """Run the generator the way the documentation tells a reader to run it."""
    return subprocess.run(
        [sys.executable, *extra, "-m", "decline_curve_lab", "--out", str(out)],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(SOURCE_DIR), "PATH": "/usr/bin:/bin"},
    )


def test_the_documented_generation_command_emits_no_runtime_warning(tmp_path):
    """The documented command must be clean under ``-W error::RuntimeWarning``.

    The package's ``__init__`` imports the generator, so re-executing the *generator
    module* with ``-m decline_curve_lab.synthetic`` asks runpy to execute a module that is
    already in ``sys.modules``. runpy warns about exactly that, and ``-W
    error::RuntimeWarning`` turns the warning into a hard failure — so the command a reader
    is told to copy-paste would abort in any environment that promotes warnings to errors.
    The documented command calls the package entry point instead, which imports the
    generator normally and runs :func:`decline_curve_lab.synthetic.main` once.
    """
    out = tmp_path / "sample_wells.csv"

    finished = _run_generator(out, "-W", "error::RuntimeWarning")

    assert finished.returncode == 0, (
        f"the documented generation command failed:\n{finished.stderr}"
    )
    assert "RuntimeWarning" not in finished.stderr
    assert out.read_bytes() == synthetic.production_csv_bytes()


def test_the_generator_module_can_still_be_run_with_dash_m(tmp_path):
    """``-m decline_curve_lab.synthetic`` keeps working, warning and all.

    It is re-executing the module rather than calling the entry point, so the warning
    above is inherent to it; it stays supported because it is a documented spelling
    readers may already have in their shell history, and it produces the same bytes.
    """
    out = tmp_path / "sample_wells.csv"

    finished = subprocess.run(
        [
            sys.executable,
            "-m",
            "decline_curve_lab.synthetic",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(SOURCE_DIR), "PATH": "/usr/bin:/bin"},
    )

    assert finished.returncode == 0, finished.stderr
    assert out.read_bytes() == synthetic.production_csv_bytes()


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