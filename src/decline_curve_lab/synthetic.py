"""Seeded synthetic wells for decline-curve analysis.

The generator produces a handful of wells whose oil rate follows an Arps decline,
with water cut rising, gas-oil ratio evolving, wellhead pressure falling and choke
settings stepped down. Everything is a deterministic function of the seed: the same
seed produces byte-identical output on every run, which is what lets
``data/sample_wells.csv`` be committed and regenerated.

Running it
==========

:func:`main` is the entry point: ``python -m decline_curve_lab`` (or
``make sample-data``, or the ``decline-curve-lab-sample-data`` console script). ``--seed N``
picks a different seed and ``--out PATH`` writes somewhere other than
``data/sample_wells.csv``.

Arps convention
===============

This module uses the project's canonical convention (``docs/adr/0001``): the decline
parameter ``Di`` is a **nominal fraction per YEAR**, and the decline factor that
appears in the rate equation is the effective rate ``D_eff = ln(1 + Di)``, derived
here only to evaluate the curve. With ``t_yr`` in years from the first production
period (``t_yr = t_months / 12``):

===========================  =================================================
exponential (``b == 0``)     ``q(t) = qi * exp(-D_eff * t)``
hyperbolic (``0 < b <= 1``)  ``q(t) = qi * (1 + b * D_eff * t) ** (-1 / b)``
harmonic (``b == 1``)        the ``b = 1`` case of the hyperbolic
===========================  =================================================

The decline implemented here is deliberately **independent of the fitter** that later
tickets add to ``arps.py``. A curve fit that recovered these parameters by comparing
against the very function it is fitting would prove nothing, so the generator keeps
its own ground-truth curve.

Naming
======

``q0_bbl_d`` is the *true* oil rate at ``t = 0`` — the well's first production
period — for this generated well. It is not the glossary's ``qi``, which is a
*fitted* back-extrapolated model parameter. Later round-trip fit tests compare a
recovered ``qi`` against ``q0_bbl_d``.

What the noise does
===================

Measurement noise is multiplicative and applied independently to each measured
column. Two consequences matter to later tickets:

- The water cut actually present in the data is only *near* a well's specified
  water cut, because ``qw`` carries its own noise on top of ``qo``'s. With the
  shipped noise levels the two agree to within about 0.01 of water cut, so a
  water-cut check must allow for that rather than expect an exact match.
- The oil rate of a well's first production period sits within
  ``rate_noise_fraction`` of ``q0_bbl_d``, and the noise-free decline is what
  ``q0_bbl_d``, ``nominal_decline_per_year`` and ``decline_curvature`` describe.
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from decline_curve_lab import io

__all__ = [
    "DEFAULT_SEED",
    "DEFAULT_WELLS",
    "WellSpec",
    "generate_production",
    "production_csv_bytes",
    "write_sample_csv",
    "main",
]

#: Documented default seed for the committed sample data. Chosen as the date this
#: project's first spike was written (2026-09-02) so it is memorable and stable.
DEFAULT_SEED: int = 20260902

MONTHS_PER_YEAR: int = 12

#: Choke settings are quantised to this increment, in inches (1/64 in).
CHOKE_INCREMENT_IN: float = 1.0 / 64.0


@dataclass(frozen=True)
class WellSpec:
    """Ground truth for one synthetic well.

    Rates are daily averages over each monthly production period (ADR-0002).
    Elapsed time is integer months from the well's first production period
    (``t = 0``); the decline equations convert that to years once, at this
    boundary.

    Attributes:
        well_id: Identifier written to the ``well_id`` column.
        q0_bbl_d: True oil rate at ``t = 0`` (first production period), bbl/d
            daily average. The generator's ground truth; distinct from a fitted
            ``qi``.
        nominal_decline_per_year: ``Di``, the nominal decline at ``t = 0`` as a
            fraction per year (ADR-0001).
        decline_curvature: ``b``, the Arps decline curvature: 0 is exponential,
            1 is harmonic, values between are hyperbolic.
        n_production_periods: Number of monthly production periods to generate.
        first_production_period: ISO date of the ``t = 0`` production period.
        fw_first: Water cut at ``t = 0``, a decimal in [0, 1].
        fw_asymptote: Water cut this well approaches as it ages; keep below 1 so
            the water rate stays finite.
        fw_rise_per_year: Rate at which water cut approaches its asymptote.
        gor_first_scf_bbl: Gas-oil ratio at ``t = 0``, scf/bbl.
        gor_asymptote_scf_bbl: Gas-oil ratio this well approaches as it ages.
        gor_rise_per_year: Rate at which the gas-oil ratio approaches its
            asymptote. Negative means the ratio falls, as in a liquid-loading well.
        wellhead_pressure_first_psi: Wellhead pressure at ``t = 0``, psi.
        wellhead_pressure_decay_per_year: Exponential decay of wellhead pressure
            with time. Negative means pressure builds, as in a liquid-loading well.
        choke_first_in: Choke setting at ``t = 0``, inches.
        rate_noise_fraction: Measurement noise on the liquid and gas daily-average
            rates, as a fraction of the noise-free rate.
        wellhead_pressure_noise_fraction: Measurement noise on wellhead pressure,
            as a fraction of the noise-free pressure. Kept small enough that a
            well's wellhead-pressure trend stays unambiguous from period to period.
    """

    well_id: str
    q0_bbl_d: float
    nominal_decline_per_year: float
    decline_curvature: float
    n_production_periods: int
    first_production_period: str
    fw_first: float
    fw_asymptote: float
    fw_rise_per_year: float
    gor_first_scf_bbl: float
    gor_asymptote_scf_bbl: float
    gor_rise_per_year: float
    wellhead_pressure_first_psi: float
    wellhead_pressure_decay_per_year: float
    choke_first_in: float
    rate_noise_fraction: float = 0.015
    wellhead_pressure_noise_fraction: float = 0.0015


#: The wells written to ``data/sample_wells.csv``. Each exists to give later
#: tickets a distinct, unambiguous case:
#:
#: * ``DCL-01`` — steep hyperbolic decline at a high rate.
#: * ``DCL-02`` — shallow, exponential decline (``b = 0``).
#: * ``DCL-03`` — the only well whose wellhead pressure falls. It declines steeply
#:   and cleanly in *every* production period, while the well stays above 100 bbl/d
#:   with water cut well below 0.7, so the wellhead-pressure signal is isolated.
#: * ``DCL-04`` — a late-life well that falls below 100 bbl/d while water cut rises
#:   above 0.7.
#: * ``DCL-05`` — a liquid-loading well: wellhead pressure builds and the gas-oil
#:   ratio falls. The control well that no screening rule should flag.
#: * ``DCL-06`` — harmonic decline (``b = 1``), which is a distinct curve from the
#:   exponential, not a limit of it.
#:
#: Every well except ``DCL-03`` holds its wellhead pressure roughly steady, building
#: slightly under a held choke. That keeps ``DCL-03`` the single unambiguous
#: wellhead-pressure-decline case whichever way a later screening rule is written.
DEFAULT_WELLS: tuple[WellSpec, ...] = (
    WellSpec(
        well_id="DCL-01",
        q0_bbl_d=820.0,
        nominal_decline_per_year=0.62,
        decline_curvature=0.85,
        n_production_periods=48,
        first_production_period="2022-10-01",
        fw_first=0.10,
        fw_asymptote=0.52,
        fw_rise_per_year=0.16,
        gor_first_scf_bbl=210.0,
        gor_asymptote_scf_bbl=680.0,
        gor_rise_per_year=0.22,
        wellhead_pressure_first_psi=310.0,
        wellhead_pressure_decay_per_year=-0.04,
        choke_first_in=0.5,
    ),
    WellSpec(
        well_id="DCL-02",
        q0_bbl_d=260.0,
        nominal_decline_per_year=0.18,
        decline_curvature=0.0,
        n_production_periods=72,
        first_production_period="2020-10-01",
        fw_first=0.06,
        fw_asymptote=0.38,
        fw_rise_per_year=0.13,
        gor_first_scf_bbl=140.0,
        gor_asymptote_scf_bbl=410.0,
        gor_rise_per_year=0.18,
        wellhead_pressure_first_psi=225.0,
        wellhead_pressure_decay_per_year=-0.04,
        choke_first_in=0.25,
    ),
    WellSpec(
        well_id="DCL-03",
        q0_bbl_d=410.0,
        nominal_decline_per_year=0.40,
        decline_curvature=0.45,
        n_production_periods=36,
        first_production_period="2023-10-01",
        fw_first=0.18,
        fw_asymptote=0.45,
        fw_rise_per_year=0.30,
        gor_first_scf_bbl=320.0,
        gor_asymptote_scf_bbl=760.0,
        gor_rise_per_year=0.26,
        wellhead_pressure_first_psi=245.0,
        wellhead_pressure_decay_per_year=0.42,
        choke_first_in=0.375,
        rate_noise_fraction=0.01,
    ),
    WellSpec(
        well_id="DCL-04",
        q0_bbl_d=180.0,
        nominal_decline_per_year=0.52,
        decline_curvature=0.70,
        n_production_periods=60,
        first_production_period="2021-10-01",
        fw_first=0.28,
        fw_asymptote=0.92,
        fw_rise_per_year=0.45,
        gor_first_scf_bbl=260.0,
        gor_asymptote_scf_bbl=900.0,
        gor_rise_per_year=0.20,
        wellhead_pressure_first_psi=265.0,
        wellhead_pressure_decay_per_year=-0.04,
        choke_first_in=0.3125,
    ),
    WellSpec(
        well_id="DCL-05",
        q0_bbl_d=520.0,
        nominal_decline_per_year=0.30,
        decline_curvature=0.55,
        n_production_periods=60,
        first_production_period="2021-10-01",
        fw_first=0.12,
        fw_asymptote=0.30,
        fw_rise_per_year=0.25,
        gor_first_scf_bbl=900.0,
        gor_asymptote_scf_bbl=380.0,
        gor_rise_per_year=0.30,
        wellhead_pressure_first_psi=180.0,
        wellhead_pressure_decay_per_year=-0.04,
        choke_first_in=0.4375,
    ),
    WellSpec(
        well_id="DCL-06",
        q0_bbl_d=240.0,
        nominal_decline_per_year=0.55,
        decline_curvature=1.0,
        n_production_periods=54,
        first_production_period="2022-04-01",
        fw_first=0.22,
        fw_asymptote=0.55,
        fw_rise_per_year=0.35,
        gor_first_scf_bbl=280.0,
        gor_asymptote_scf_bbl=640.0,
        gor_rise_per_year=0.24,
        wellhead_pressure_first_psi=255.0,
        wellhead_pressure_decay_per_year=-0.04,
        choke_first_in=0.3125,
    ),
)


def _well_rng(seed: int, well_id: str) -> np.random.Generator:
    """Return the noise stream for one well.

    The stream is derived from the seed *and* the well id, not from the well's
    position in :data:`DEFAULT_WELLS`, so changing or inserting one well leaves
    every other well's noise byte-identical.
    """
    stream = int.from_bytes(hashlib.sha256(well_id.encode("utf-8")).digest()[:8], "big")
    return np.random.default_rng(np.random.SeedSequence(entropy=seed, spawn_key=(stream,)))


def _arps_oil_rate(q0: float, nominal_decline_per_year: float, decline_curvature: float,
                   elapsed_months: np.ndarray) -> np.ndarray:
    """Noise-free Arps oil rate, bbl/d daily average, at each elapsed time.

    The canonical decline is ``Di`` nominal per year (ADR-0001), so the effective
    decline ``D_eff = ln(1 + Di)`` is derived here and the time axis is converted
    from months to years first, keeping ``Di * t`` dimensionless.
    """
    t_yr = elapsed_months / MONTHS_PER_YEAR
    d_eff = np.log1p(nominal_decline_per_year)
    if decline_curvature == 0.0:
        return q0 * np.exp(-d_eff * t_yr)
    return q0 * (1.0 + decline_curvature * d_eff * t_yr) ** (-1.0 / decline_curvature)


def _approach(value_first: float, asymptote: float, rate_per_year: float,
              elapsed_months: np.ndarray) -> np.ndarray:
    """Exponential approach from a starting value to an asymptote over time."""
    t_yr = elapsed_months / MONTHS_PER_YEAR
    return asymptote + (value_first - asymptote) * np.exp(-rate_per_year * t_yr)


def _quantize_choke(choke_first_in: float, deliverability: np.ndarray) -> np.ndarray:
    """Step a choke setting down with deliverability, in fixed increments.

    Choke changes are discrete operational actions, so the setting is quantised to
    :data:`CHOKE_INCREMENT_IN` rather than drifting continuously. Choke is computed
    from the noise-free oil rate so measurement noise cannot make it flap between
    neighbouring steps.
    """
    stepped = np.floor(choke_first_in * deliverability / CHOKE_INCREMENT_IN)
    stepped = np.maximum(stepped, 4.0)  # never smaller than 4/64 in
    return stepped * CHOKE_INCREMENT_IN


def _well_production_periods(well: WellSpec, seed: int) -> pd.DataFrame:
    """Generate one well's production periods as a DataFrame."""
    rng = _well_rng(seed, well.well_id)
    elapsed_months = np.arange(well.n_production_periods, dtype=float)

    oil_rate = _arps_oil_rate(
        well.q0_bbl_d, well.nominal_decline_per_year, well.decline_curvature, elapsed_months
    )
    water_cut = _approach(well.fw_first, well.fw_asymptote, well.fw_rise_per_year, elapsed_months)
    gor = _approach(
        well.gor_first_scf_bbl, well.gor_asymptote_scf_bbl, well.gor_rise_per_year, elapsed_months
    )
    wellhead_pressure = well.wellhead_pressure_first_psi * np.exp(
        -well.wellhead_pressure_decay_per_year * elapsed_months / MONTHS_PER_YEAR
    )

    # Water rate follows from water cut: fw = qw / (qo + qw), so qw = qo * fw / (1 - fw).
    water_rate = oil_rate * water_cut / (1.0 - water_cut)
    gas_rate = oil_rate * gor
    choke = _quantize_choke(well.choke_first_in, oil_rate / well.q0_bbl_d)

    def noisy(values: np.ndarray, fraction: float) -> np.ndarray:
        return values * (1.0 + fraction * rng.uniform(-1.0, 1.0, size=values.shape))

    oil_rate = noisy(oil_rate, well.rate_noise_fraction)
    water_rate = noisy(water_rate, well.rate_noise_fraction)
    gas_rate = noisy(gas_rate, well.rate_noise_fraction)
    wellhead_pressure = noisy(wellhead_pressure, well.wellhead_pressure_noise_fraction)

    # Round to fixed decimals so the committed CSV is stable and readable, and
    # keep every rate non-negative despite noise on a small rate.
    return pd.DataFrame(
        {
            "date": pd.date_range(
                start=well.first_production_period, periods=well.n_production_periods, freq="MS"
            ),
            "well_id": well.well_id,
            "qo": np.round(np.maximum(oil_rate, 0.0), 2),
            "qw": np.round(np.maximum(water_rate, 0.0), 2),
            "qg": np.round(np.maximum(gas_rate, 0.0), 2),
            "wellhead_pressure": np.round(np.maximum(wellhead_pressure, 0.0), 1),
            "choke": np.round(choke, 6),
        }
    )


def generate_production(seed: int = DEFAULT_SEED,
                        wells: tuple[WellSpec, ...] = DEFAULT_WELLS) -> pd.DataFrame:
    """Generate the production periods for every well, as one DataFrame.

    Args:
        seed: Seed for the measurement noise. The same seed always produces the
            same output.
        wells: The wells to generate. Defaults to :data:`DEFAULT_WELLS`.

    Returns:
        A DataFrame with exactly the production schema columns in order: ``date``,
        ``well_id``, ``qo``, ``qw``, ``qg``, ``wellhead_pressure``, ``choke``. All
        rates are daily averages (ADR-0002). Production periods are grouped by well
        in the order given, and ascend in time within each well.
    """
    periods = [_well_production_periods(well, seed) for well in wells]
    return pd.concat(periods, ignore_index=True)[list(io.PRODUCTION_COLUMNS)]


def production_csv_bytes(seed: int = DEFAULT_SEED,
                         wells: tuple[WellSpec, ...] = DEFAULT_WELLS) -> bytes:
    """Return the production schema as CSV bytes, byte-identical for a given seed.

    Dates are written as ISO ``YYYY-MM-DD`` and the file always ends with a single
    trailing newline, so the bytes are stable across runs and platforms.
    """
    frame = generate_production(seed, wells)
    frame = frame.assign(date=frame["date"].dt.strftime("%Y-%m-%d"))
    return frame.to_csv(index=False, lineterminator="\n").encode("utf-8")


def write_sample_csv(csv_path: Path | None = None, seed: int = DEFAULT_SEED) -> Path:
    """Regenerate and write the committed sample production CSV.

    Args:
        csv_path: Where to write. Defaults to ``data/sample_wells.csv``.
        seed: Seed for the measurement noise. Defaults to the documented
            :data:`DEFAULT_SEED`.

    Returns:
        The path written.
    """
    csv_path = io.SAMPLE_CSV_PATH if csv_path is None else Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_bytes(production_csv_bytes(seed))
    return csv_path


def main(argv: list[str] | None = None) -> int:
    """Regenerate the committed sample CSV.

    The entry point behind ``make sample-data``, ``python -m decline_curve_lab`` (see
    ``src/decline_curve_lab/__main__.py`` for why the documented command calls this
    function instead of re-executing this module) and the
    ``decline-curve-lab-sample-data`` console script. ``--seed N`` picks a different seed
    and ``--out PATH`` writes somewhere other than ``data/sample_wells.csv``.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="generator seed")
    parser.add_argument("--out", type=Path, default=None, help="output CSV path")
    args = parser.parse_args(argv)
    written = write_sample_csv(args.out, args.seed)
    print(f"wrote {written} (seed={args.seed})")
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())