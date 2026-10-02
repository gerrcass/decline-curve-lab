"""Minimal Streamlit dashboard: list the synthetic wells and show one well's history.

This app is a thin adapter. It holds **no business logic**: it loads the sample
production CSV through the analysis library's reader, lets you pick a well, and renders
that well's production periods as a table and, from
``decline_curve_lab.arps``, a log-rate-vs-time chart with the well's fitted exponential
Arps curve. Every rule about what the numbers mean lives in
``decline_curve_lab.io`` and the modules that extend it, so this file is safe to delete
and rewrite.

Run it with:

    /tmp/opencode/dcl-venv/bin/streamlit run src/decline_curve_lab/dashboard.py

or, once the project has an installed single-command run:

    decline-curve-lab-dashboard
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from decline_curve_lab import arps, io


def main() -> None:
    """Render the dashboard."""
    st.set_page_config(page_title="Well production surveillance", layout="wide")
    st.title("Well production surveillance")
    st.caption(
        "Synthetic wells from the seeded generator. Every rate is a **daily average** "
        "(bbl/d oil and water, scf/d gas) over one monthly production period, per "
        "ADR-0002."
    )

    try:
        production = io.load_production(io.SAMPLE_CSV_PATH)
    except (io.SchemaError, FileNotFoundError) as error:
        st.error(f"Could not read the sample production data: {error}")
        return

    well_ids = sorted(production["well_id"].unique())
    well_id = st.selectbox("Well", well_ids)
    well_production_periods = production[production["well_id"] == well_id]

    st.subheader(f"Production history for {well_id}")
    st.dataframe(well_production_periods, width="stretch", hide_index=True)
    st.caption(
        f"{len(well_production_periods)} production periods, "
        f"{well_production_periods['date'].min():%B %Y} to "
        f"{well_production_periods['date'].max():%B %Y}."
    )

    _show_exponential_decline_curve(well_id, well_production_periods)


def _show_exponential_decline_curve(well_id: str, well_production_periods: pd.DataFrame) -> None:
    """Chart a well's oil rate against time on a log axis, with its fitted Arps curve.

    Still no business logic here: the elapsed-time axis, the fitted exponential and its
    parameters all come from ``decline_curve_lab.arps``. This only draws them.
    """
    elapsed = arps.elapsed_months(well_production_periods)
    oil_rate = well_production_periods["qo"].to_numpy()

    # A log axis and a log-linear fit both need positive rates, so the library decides
    # which production periods those are and the chart plots exactly those.
    fittable = arps.positive_rate_mask(oil_rate)

    st.subheader(f"Exponential Arps curve for {well_id}")
    try:
        fit = arps.fit_exponential(elapsed, oil_rate)
    except arps.FitError as error:
        st.warning(f"Could not fit an exponential Arps curve to {well_id}: {error}")
        return

    figure, axes = plt.subplots(figsize=(10, 4.5))
    try:
        axes.scatter(
            elapsed[fittable], oil_rate[fittable], s=18, label="observed oil rate", zorder=3
        )
        axes.plot(
            elapsed, fit.rate_at(elapsed), label="fitted exponential Arps curve", zorder=2
        )
        axes.set_yscale("log")
        axes.set_xlabel("Elapsed time (production periods from the well's first)")
        axes.set_ylabel("Oil rate (bbl/d, daily average)")
        axes.set_title(f"{well_id}: oil rate on a log scale, with the fitted exponential")
        axes.grid(True, which="both", alpha=0.3)
        axes.legend()
        st.pyplot(figure)
    finally:
        plt.close(figure)

    value_column, other_column = st.columns(2)
    value_column.metric(
        "Initial rate `qi` (back-extrapolated to t = 0)", f"{fit.qi:,.1f} bbl/d"
    )
    other_column.metric("Initial nominal decline `Di` (per year, ADR-0001)", f"{fit.Di:.1%}")
    st.caption(
        f"Exponential Arps curve (decline curvature `b = 0`). `qi` is the fitted curve's "
        f"rate at `t = 0`, back-extrapolated rather than observed. Goodness of fit on the "
        f"rate scale: R² {fit.r_squared:.4f}, RMSE {fit.rmse_bbl_d:,.2f} bbl/d over "
        f"{fit.n_production_periods} production periods"
        + (
            f", {fit.n_dropped} dropped for a non-positive oil rate."
            if fit.n_dropped
            else "."
        )
    )


if __name__ == "__main__":
    main()