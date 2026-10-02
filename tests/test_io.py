"""Behaviour of the production schema reader.

The reader is the project's only file-reading seam, so these tests write real CSV
files and read them back through ``load_production``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from decline_curve_lab import io, synthetic

VALID_ROWS = """\
date,well_id,qo,qw,qg,wellhead_pressure,choke
2024-01-01,W-1,120.0,18.0,5400.0,250.0,0.25
2024-02-01,W-1,112.5,20.5,5100.0,244.0,0.25
2024-03-01,W-1,105.0,23.0,4800.0,238.5,0.234375
"""


def write_csv(tmp_path, text: str, name: str = "production.csv"):
    csv_path = tmp_path / name
    csv_path.write_text(text, encoding="utf-8")
    return csv_path


def test_reads_the_committed_sample_production_data():
    production = io.load_production(io.SAMPLE_CSV_PATH)

    assert tuple(production.columns) == io.PRODUCTION_COLUMNS
    assert len(production) == 330
    assert not production.isna().to_numpy().any()


def test_parses_production_period_dates_as_datetimes():
    production = io.load_production(io.SAMPLE_CSV_PATH)

    assert pd.api.types.is_datetime64_any_dtype(production["date"])


def test_holds_rates_and_pressure_as_floats_and_well_ids_as_text():
    production = io.load_production(io.SAMPLE_CSV_PATH)

    for column in ("qo", "qw", "qg", "wellhead_pressure", "choke"):
        assert production[column].dtype == "float64", f"{column} should be a float"
    assert pd.api.types.is_string_dtype(production["well_id"])


def test_accepts_integer_formatted_rates_by_widening_them_to_floats(tmp_path):
    csv_path = write_csv(
        tmp_path,
        "date,well_id,qo,qw,qg,wellhead_pressure,choke\n"
        "2024-01-01,W-1,120,18,5400,250,0.25\n",
    )

    production = io.load_production(csv_path)

    assert production["qo"].iloc[0] == 120.0
    assert production["qo"].dtype == "float64"


def test_leaves_rates_unscaled_so_they_stay_daily_averages():
    """ADR-0002: rates in the CSV are daily averages and must be read as-is.

    Nothing in the reader may rescale a rate. The shipped sample is generated from
    documented daily-average rates, so reading it back must return those same
    magnitudes, not a monthly volume.
    """
    production = io.load_production(io.SAMPLE_CSV_PATH)
    first_periods = production.groupby("well_id").first()

    for well in synthetic.DEFAULT_WELLS:
        observed = first_periods.loc[well.well_id, "qo"]
        assert observed == pytest.approx(well.q0_bbl_d, rel=well.rate_noise_fraction)


def test_accepts_a_file_with_the_schema_columns_but_no_production_periods(tmp_path):
    csv_path = write_csv(
        tmp_path,
        "date,well_id,qo,qw,qg,wellhead_pressure,choke\n",
    )

    production = io.load_production(csv_path)

    assert len(production) == 0
    assert tuple(production.columns) == io.PRODUCTION_COLUMNS


def test_rejects_a_missing_column_naming_it(tmp_path):
    csv_path = write_csv(
        tmp_path,
        "date,well_id,qo,qw,qg,wellhead_pressure\n2024-01-01,W-1,120.0,18.0,5400.0,250.0\n",
    )

    with pytest.raises(io.SchemaError, match="choke"):
        io.load_production(csv_path)


def test_rejects_a_negative_rate_naming_it(tmp_path):
    csv_path = write_csv(
        tmp_path,
        "date,well_id,qo,qw,qg,wellhead_pressure,choke\n"
        "2024-01-01,W-1,-120.0,18.0,5400.0,250.0,0.25\n",
    )

    with pytest.raises(io.SchemaError, match="qo"):
        io.load_production(csv_path)


def test_rejects_a_negative_wellhead_pressure_naming_it(tmp_path):
    csv_path = write_csv(
        tmp_path,
        "date,well_id,qo,qw,qg,wellhead_pressure,choke\n"
        "2024-01-01,W-1,120.0,18.0,5400.0,-250.0,0.25\n",
    )

    with pytest.raises(io.SchemaError, match="wellhead_pressure"):
        io.load_production(csv_path)


def test_rejects_a_non_numeric_rate_naming_it(tmp_path):
    csv_path = write_csv(
        tmp_path,
        "date,well_id,qo,qw,qg,wellhead_pressure,choke\n"
        "2024-01-01,W-1,not-a-rate,18.0,5400.0,250.0,0.25\n",
    )

    with pytest.raises(io.SchemaError, match="qo"):
        io.load_production(csv_path)


def test_rejects_a_missing_rate_value_naming_it(tmp_path):
    csv_path = write_csv(
        tmp_path,
        "date,well_id,qo,qw,qg,wellhead_pressure,choke\n"
        "2024-01-01,W-1,,18.0,5400.0,250.0,0.25\n",
    )

    with pytest.raises(io.SchemaError, match="qo"):
        io.load_production(csv_path)


def test_rejects_an_unparseable_date_naming_it(tmp_path):
    csv_path = write_csv(
        tmp_path,
        "date,well_id,qo,qw,qg,wellhead_pressure,choke\n"
        "not-a-date,W-1,120.0,18.0,5400.0,250.0,0.25\n",
    )

    with pytest.raises(io.SchemaError, match="date"):
        io.load_production(csv_path)


def test_rejects_an_ambiguous_date_rather_than_guessing_the_month_day_order(tmp_path):
    """``03/04/2024`` is March 4 in one convention and 3 April in another."""
    csv_path = write_csv(
        tmp_path,
        "date,well_id,qo,qw,qg,wellhead_pressure,choke\n"
        "03/04/2024,W-1,120.0,18.0,5400.0,250.0,0.25\n",
    )

    with pytest.raises(io.SchemaError, match="date"):
        io.load_production(csv_path)


def test_rejects_a_missing_well_id_naming_it(tmp_path):
    csv_path = write_csv(
        tmp_path,
        "date,well_id,qo,qw,qg,wellhead_pressure,choke\n"
        "2024-01-01,,120.0,18.0,5400.0,250.0,0.25\n",
    )

    with pytest.raises(io.SchemaError, match="well_id"):
        io.load_production(csv_path)


def test_rejects_a_missing_file_naming_the_path(tmp_path):
    csv_path = tmp_path / "absent.csv"

    with pytest.raises(FileNotFoundError, match="absent.csv"):
        io.load_production(csv_path)


def test_rejects_a_duplicated_column_naming_it(tmp_path):
    csv_path = write_csv(
        tmp_path,
        "date,well_id,qo,qo,qw,qg,wellhead_pressure,choke\n"
        "2024-01-01,W-1,120.0,121.0,18.0,5400.0,250.0,0.25\n",
    )

    with pytest.raises(io.SchemaError, match="qo"):
        io.load_production(csv_path)


def test_rejects_a_file_that_has_no_production_schema_columns_at_all(tmp_path):
    csv_path = write_csv(tmp_path, "alpha,beta\n1,2\n")

    with pytest.raises(io.SchemaError) as error:
        io.load_production(csv_path)

    assert "qo" in str(error.value)


def test_reads_a_valid_file_written_by_hand(tmp_path):
    csv_path = write_csv(tmp_path, VALID_ROWS)

    production = io.load_production(csv_path)

    assert list(production["well_id"]) == ["W-1"] * 3
    assert production["qo"].tolist() == [120.0, 112.5, 105.0]
    assert production["date"].tolist() == [
        pd.Timestamp("2024-01-01"),
        pd.Timestamp("2024-02-01"),
        pd.Timestamp("2024-03-01"),
    ]


def test_keeps_production_periods_in_the_order_the_file_lists_them(tmp_path):
    csv_path = write_csv(tmp_path, VALID_ROWS)

    production = io.load_production(csv_path)

    assert production["date"].is_monotonic_increasing