"""Production schema and the one file-reading seam for decline-curve-lab.

Contract of the production schema
=================================

One row of the production CSV is one **production period** for one **well**. Columns,
in order:

``date``
    The production period's start date, ISO ``YYYY-MM-DD``, parsed to
    ``datetime64[ns]`` on read.
``well_id``
    Identifier of the well the production period belongs to.
``qo``
    Oil rate for the production period, **bbl/d, daily average**.
``qw``
    Water rate for the production period, **bbl/d, daily average**.
``qg``
    Gas rate for the production period, **scf/d, daily average**.
``wellhead_pressure``
    Wellhead pressure measured at the surface for the production period, psi.
``choke``
    Surface flow-control setting for the production period, inches.

Every rate is a **daily average** over the production period, never the volume
produced during it, per ADR-0002 (``docs/adr/0002-rates-are-daily-averages.md``).
A monthly-volume column would silently break both the decline-curve fits and the
~100 bbl/d lift heuristic, so the reader states the convention here rather than
inferring it.

Coercion decisions (strict, and deliberately not generous)
----------------------------------------------------------

The reader coerces in exactly two places, both lossless for a well-formed file:

1. **Rate and pressure columns** are read as ``float64``. Integer-formatted rates
   (``820``, ``0``) are accepted and widened; anything non-numeric, or any missing
   or infinite value, is rejected. Rates are *not* rounded, scaled or unit-guessed.
2. **``date``** must be ISO ``YYYY-MM-DD`` exactly. An ambiguous date such as
   ``03/04/2024`` is rejected rather than guessed at, because guessing picks a
   month/day order silently and mis-dates the production period. Empty dates are
   rejected, never replaced.

Everything else is rejected as-is. No column is renamed, no missing column is
invented, no bad value is imputed, and nothing is silently dropped: a malformed
production period raises :class:`SchemaError` naming the offending column.

To keep error messages faithful, values are read as the literal text they hold in
the file, so a rate written as ``n/a`` is reported as ``n/a`` rather than as the
null it would otherwise become.

Columns beyond the schema are ignored, since a production CSV may carry extra
context (operator, region, notes) that this schema has no place for.

"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd

__all__ = [
    "PRODUCTION_COLUMNS",
    "SAMPLE_CSV_NAME",
    "SAMPLE_CSV_PATH",
    "SAMPLE_DATA_DIR",
    "SchemaError",
    "days_in_production_period",
    "load_production",
    "require_columns",
]

#: Production schema columns, in the order they appear in the CSV.
PRODUCTION_COLUMNS: tuple[str, ...] = (
    "date",
    "well_id",
    "qo",
    "qw",
    "qg",
    "wellhead_pressure",
    "choke",
)

#: Columns holding daily-average rates, with their units. Rates are daily averages
#: per ADR-0002; these are the columns that must never be read as monthly volumes.
RATE_COLUMNS: dict[str, str] = {
    "qo": "bbl/d",
    "qw": "bbl/d",
    "qg": "scf/d",
}

#: Repository directory holding the committed sample production data.
SAMPLE_DATA_DIR: Path = Path(__file__).resolve().parents[2] / "data"

#: File name of the committed sample production CSV.
SAMPLE_CSV_NAME: str = "sample_wells.csv"

#: Path of the committed sample production CSV.
SAMPLE_CSV_PATH: Path = SAMPLE_DATA_DIR / SAMPLE_CSV_NAME

#: The reader's own trailing sentence for the shared column check: it is the schema itself,
#: so there is no narrower set of columns to point a reader at.
_PRODUCTION_SCHEMA_DETAIL: str = f"required columns are {list(PRODUCTION_COLUMNS)}"


class SchemaError(ValueError):
    """Raised when production data does not satisfy the production schema.

    The message always names the offending column, so a malformed production CSV
    can be diagnosed from the error alone.
    """


#: Columns holding a non-negative numeric measurement: rates, pressure and choke.
NUMERIC_COLUMNS: tuple[str, ...] = ("qo", "qw", "qg", "wellhead_pressure", "choke")


#: The one date format the reader accepts, so an ambiguous date is never guessed at.
DATE_FORMAT: str = "%Y-%m-%d"

#: The same format as a human reads it, for error messages.
DATE_PATTERN_HINT: str = "YYYY-MM-DD"


def load_production(csv_path: Path | str) -> pd.DataFrame:
    """Read and validate a production CSV, returning its production periods.

    One row of the result is one **production period** for one **well**. Every rate
    is a **daily average** — bbl/d for oil and water, scf/d for gas — never a volume
    produced during the period (ADR-0002). Rates are read exactly as written: the
    reader never rescales, rounds or unit-guesses them.

    Args:
        csv_path: Path of the production CSV.

    Returns:
        A DataFrame with exactly the production schema columns, in schema order:
        ``date`` as ``datetime64``, ``well_id`` as text, and ``qo``, ``qw``, ``qg``,
        ``wellhead_pressure`` and ``choke`` as ``float64``. Production periods are
        returned in the order the file lists them.

    Raises:
        FileNotFoundError: ``csv_path`` does not exist.
        SchemaError: The file violates the production schema. The message always
            names the offending column.
    """
    csv_path = Path(csv_path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"production CSV not found: {csv_path}")

    raw = pd.read_csv(csv_path, keep_default_na=False, na_values=[])

    require_columns(raw, PRODUCTION_COLUMNS, detail=_PRODUCTION_SCHEMA_DETAIL)
    _require_unique_columns(_header_columns(csv_path))
    production = _validated_columns(raw)
    return production[list(PRODUCTION_COLUMNS)]


def days_in_production_period(
    production_periods: pd.DataFrame | pd.Series | pd.Index,
) -> np.ndarray:
    """The length in days of each production period, taken from its own calendar month.

    A production period is a calendar month and the ``date`` column gives its first day, so
    the length is whatever the calendar says that month has — 28, 29, 30 or 31 days, never a
    constant. That makes this the project's single conversion from a rate in bbl/d to a
    volume in bbl:

        volume over a production period [bbl] = rate [bbl/d] * days in that month [d]

    Cumulative oil ``Np``, a forecast's ``volume_bbl`` and the EUR all need it, and they all
    need it to be the *same* rule: if they each read the length off ``days_in_month``
    themselves they can drift, and a well's observed ``Np`` and its EUR would quietly stop
    agreeing. This function lives here because ``io`` owns the ``date`` column and its
    contract, so every monthly series reads the rule from the schema that defines it.

    EIA normalises every month to 30.4 days. This project does not, because the ``date``
    column is exact and the month's own length is available.

    Args:
        production_periods: The production periods' ``date`` values — a frame carrying a
            ``date`` column, that column on its own, or the run of dates a forecast or an
            EUR covers.

    Returns:
        The length of each production period in days, as ``float64``, one per production
        period, in the order given.
    """
    dates = (
        production_periods["date"]
        if isinstance(production_periods, pd.DataFrame)
        else production_periods
    )
    return pd.DatetimeIndex(dates).days_in_month.to_numpy(dtype="float64")


def require_columns(frame: pd.DataFrame, required: tuple[str, ...], *, detail: str) -> None:
    """Reject a frame that is missing columns something needs to read, naming what is missing.

    This module owns the production schema, so the column check lives here and every module
    that extends the schema — the metrics, the screening rules, the EUR table — routes
    through it rather than reimplementing the same list comprehension and the same message
    prefix. One implementation means one rule for what a missing column is reported as.

    ``detail`` is the caller's own sentence: which columns it reads and which frame it
    expects to be handed. The shared half of the message is the same everywhere — it is a
    production-schema error, here are the columns that are missing — and the caller's half
    is what makes it diagnosable, because "the EUR table reads ['well_id', 'date', 'qo']"
    says which function refused the frame and why.

    Args:
        frame: The frame about to be read.
        required: The columns the caller needs, in the order it needs them.
        detail: The caller's trailing sentence for the error message, which should name the
            columns ``required`` holds and where they were expected to come from.

    Raises:
        SchemaError: A column in ``required`` is absent from ``frame``.
    """
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise SchemaError(
            f"production schema error: missing required column(s) {missing}; {detail}"
        )


def _header_columns(csv_path: Path) -> list[str]:
    """Return the CSV header line as written.

    Read separately from the frame because ``pandas`` silently renames a repeated
    column (``qo`` becomes ``qo.1``), which would hide a duplicated column from the
    schema check. ``utf-8-sig`` matches how ``pandas`` reads the same file.
    """
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        return next(csv.reader(handle), [])


def _require_unique_columns(header: list[str]) -> None:
    duplicated = [column for column in PRODUCTION_COLUMNS if header.count(column) > 1]
    if duplicated:
        raise SchemaError(
            f"production schema error: column(s) {duplicated} appear more than once "
            f"in the production CSV header; each column must appear exactly once"
        )


def _validated_columns(raw: pd.DataFrame) -> pd.DataFrame:
    """Coerce each schema column, rejecting anything that violates the schema."""
    validated = {"date": _parse_dates(raw), "well_id": _read_well_ids(raw)}
    for column in NUMERIC_COLUMNS:
        validated[column] = _read_non_negative(raw, column)
    return pd.DataFrame(validated)


def _show(value: object) -> str:
    """Render a rejected value for an error message, without leaking a numpy repr."""
    if isinstance(value, (float, np.floating)):
        return str(float(value))
    return repr(value)


def _parse_dates(raw: pd.DataFrame) -> pd.Series:
    dates = pd.to_datetime(raw["date"], format=DATE_FORMAT, errors="coerce")
    unparseable = dates.isna()
    if unparseable.any():
        position = int(dates.index[unparseable][0])
        offender = raw["date"].iloc[position]
        raise SchemaError(
            f"production schema error: column 'date' holds an unparseable date "
            f"({_show(offender)}) at production period {position + 1}; dates must be "
            f"exactly {DATE_PATTERN_HINT}, e.g. 2024-01-01"
        )
    return dates


def _read_well_ids(raw: pd.DataFrame) -> pd.Series:
    well_ids = raw["well_id"].astype("string")
    missing = well_ids.isna() | (well_ids.str.strip() == "")
    if missing.any():
        position = int(well_ids.index[missing][0])
        raise SchemaError(
            f"production schema error: column 'well_id' is missing a well id at "
            f"production period {position + 1}; every production period must "
            f"identify its well"
        )
    return well_ids


def _read_non_negative(raw: pd.DataFrame, column: str) -> pd.Series:
    values = pd.to_numeric(raw[column], errors="coerce")
    not_a_number = values.isna()
    if not_a_number.any():
        position = int(values.index[not_a_number][0])
        offender = raw[column].iloc[position]
        raise SchemaError(
            f"production schema error: column '{column}' holds a value that is not "
            f"a number ({_show(offender)}) at production period {position + 1}; "
            f"{column} must be numeric on every production period"
        )
    infinite = ~np.isfinite(values.to_numpy(dtype="float64"))
    if infinite.any():
        position = int(values.index[infinite][0])
        offender = raw[column].iloc[position]
        raise SchemaError(
            f"production schema error: column '{column}' holds a non-finite value "
            f"({_show(offender)}) at production period {position + 1}"
        )
    negative = values < 0.0
    if negative.any():
        position = int(values.index[negative][0])
        offender = float(values.iloc[position])
        raise SchemaError(
            f"production schema error: column '{column}' holds a negative value "
            f"({offender}) at production period {position + 1}; "
            f"{column} must be non-negative on every production period"
        )
    return values.astype("float64")