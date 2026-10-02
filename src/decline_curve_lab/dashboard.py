"""Minimal Streamlit dashboard: list the synthetic wells and show one well's history.

This app is a thin adapter. It holds **no business logic**: it loads the sample
production CSV through the analysis library's reader, lets you pick a well, and renders
that well's production periods as a table with the metrics derived from them (water cut,
gas-oil ratio, cumulative oil). It then draws the well's decline curve — a log-rate
chart with **both** fitted Arps curves, the exponential and the hyperbolic, the one the
library selected by RMSE, and a control to override that choice — and closes with a
fleet-wide panel of the wells ``decline_curve_lab.surveillance`` flagged as lift
candidates for engineering review. Every rule about what the numbers mean lives in
``decline_curve_lab.io`` and the modules that extend it, so this file is safe to delete
and rewrite.

Run it with:

    /tmp/opencode/dcl-venv/bin/streamlit run src/decline_curve_lab/dashboard.py

or, once the project has an installed single-command run:

    decline-curve-lab-dashboard
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from decline_curve_lab import arps, io, metrics, surveillance


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
    selected_well = production[production["well_id"] == well_id]
    well_production_periods = metrics.compute_metrics(selected_well)

    st.subheader(f"Production history for {well_id}")
    st.dataframe(well_production_periods, width="stretch", hide_index=True)
    st.caption(
        f"{len(well_production_periods)} production periods, "
        f"{well_production_periods['date'].min():%B %Y} to "
        f"{well_production_periods['date'].max():%B %Y}. `water_cut` is the fraction "
        f"of liquid that is water (0-1), `GOR` is scf/bbl, and `Np` is cumulative oil "
        f"in bbl over this well's own production periods."
    )

    _show_decline_curve_selection(well_id, well_production_periods)
    _show_lift_candidates(metrics.compute_metrics(production))


def _show_lift_candidates(measured: pd.DataFrame) -> None:
    """Panel listing the wells the screening rules flagged, and why each one tripped.

    Still no business logic: ``decline_curve_lab.surveillance`` holds every threshold and
    every rule, and reports which reasons fired for each well. This only reads that
    result and lays it out. A lift candidate is a screening flag for a human engineer to
    review, so the wording says so and stops there — it is not a recommendation to put
    a well on artificial lift.
    """
    screened = surveillance.flag_lift_candidates(measured)
    flagged = screened[screened["candidate_lift"]]

    st.subheader("Lift candidates for engineering review")
    if flagged.empty:
        st.info("No wells flagged by the lift-candidate screening rules.")
        return

    # `lift_reasons` carries stable codes; the wording for each lives with the rule in
    # the library, so the panel reads its labels off the same place the screen writes
    # its reasons rather than keeping its own copy of the sentences.
    panel = flagged[["well_id", "latest_date", "qo", "water_cut", "lift_reasons"]].copy()
    panel["reasons"] = [
        ", ".join(surveillance.LIFT_REASON_LABELS[reason] for reason in reasons)
        for reasons in panel["lift_reasons"]
    ]
    st.dataframe(
        panel[["well_id", "latest_date", "qo", "water_cut", "reasons"]],
        width="stretch",
        hide_index=True,
    )
    st.caption(
        f"{len(flagged)} of {len(screened)} wells flagged, on each well's most recent "
        f"production period. Flagging is a screen, not a recommendation: a well is "
        f"listed when its oil rate is below "
        f"{surveillance.DEFAULT_LIFT_RATE_BBL_D:,.0f} bbl/d with a water cut above "
        f"{surveillance.DEFAULT_HIGH_WATER_CUT}, or its wellhead pressure fell across "
        f"{surveillance.DEFAULT_PRESSURE_DECLINE_COUNT} consecutive production periods. "
        f"`qo` is bbl/d as a daily average (ADR-0002), `water_cut` is a decimal in "
        f"[0, 1], and `lift_reasons` lists every rule that fired, not just the first."
    )


def _show_decline_curve_selection(
    well_id: str, well_production_periods: pd.DataFrame
) -> None:
    """Chart a well's oil rate on a log axis with **both** fitted Arps curves on it.

    Still no business logic here: the elapsed-time axis, both fitted curves, the
    parameters, the RMSE comparison and the choice of decline curve all come from
    ``decline_curve_lab.arps``. This draws them, labels which curve was selected, and
    offers the analyst the override (spec user story 10). The only decision made in
    this file is whether the analyst picked something other than what the RMSE
    comparison chose — which is what the override argument is for.
    """
    elapsed = arps.elapsed_months(well_production_periods)
    oil_rate = well_production_periods["qo"].to_numpy()

    # A log axis and both fits need positive rates, so the library decides which
    # production periods those are and the chart plots exactly those.
    fittable = arps.positive_rate_mask(oil_rate)

    st.subheader(f"Decline curve for {well_id}")
    try:
        exponential = arps.fit_exponential(elapsed, oil_rate)
    except arps.FitError as error:
        st.warning(f"Could not fit an exponential Arps curve to {well_id}: {error}")
        return

    try:
        hyperbolic = arps.fit_hyperbolic(elapsed, oil_rate)
    except arps.FitError as error:
        # A well the hyperbolic cannot be fitted to still has a decline curve: the
        # exponential. The library is told, not asked to work it out here.
        hyperbolic = None
        st.warning(f"Could not fit a hyperbolic Arps curve to {well_id}: {error}")

    by_rmse = arps.select_decline_curve(exponential, hyperbolic)
    choices = [arps.EXPONENTIAL_CURVE]
    if hyperbolic is not None:
        choices.append(arps.HYPERBOLIC_CURVE)
    override_choice = st.selectbox(
        "Decline curve to use (defaults to the lower-RMSE curve)",
        choices,
        index=choices.index(by_rmse.curve),
        key=f"decline_curve_{well_id}",
    )
    override = None if override_choice == by_rmse.curve else override_choice
    selection = arps.select_decline_curve(exponential, hyperbolic, override=override)

    figure, axes = plt.subplots(figsize=(10, 4.5))
    try:
        axes.scatter(
            elapsed[fittable], oil_rate[fittable], s=18, label="observed oil rate", zorder=3
        )
        for curve, fit in (
            (arps.EXPONENTIAL_CURVE, exponential),
            (arps.HYPERBOLIC_CURVE, hyperbolic),
        ):
            if fit is None:
                continue
            selected = curve == selection.curve
            axes.plot(
                elapsed,
                fit.rate_at(elapsed),
                label=f"fitted {curve} Arps curve"
                + (" (selected)" if selected else ""),
                linewidth=2.5 if selected else 1.5,
                linestyle="-" if selected else "--",
                zorder=2,
            )
        axes.set_yscale("log")
        axes.set_xlabel("Elapsed time (production periods from the well's first)")
        axes.set_ylabel("Oil rate (bbl/d, daily average)")
        axes.set_title(
            f"{well_id}: oil rate on a log scale, with both fitted Arps curves"
        )
        axes.grid(True, which="both", alpha=0.3)
        axes.legend()
        st.pyplot(figure)
    finally:
        plt.close(figure)

    st.markdown(
        f"**Selected decline curve: the {selection.curve} Arps curve**, chosen by "
        + (
            "the lower RMSE."
            if selection.chosen_by == arps.CURVE_BY_RMSE
            else "your override."
        )
    )
    qi_column, di_column, b_column = st.columns(3)
    qi_column.metric(
        "Initial rate `qi` (back-extrapolated to t = 0)", f"{selection.qi:,.1f} bbl/d"
    )
    di_column.metric(
        "Initial nominal decline `Di` (per year, ADR-0001)", f"{selection.Di:.1%}"
    )
    b_column.metric(
        "Decline curvature `b` (0 exponential, 1 harmonic)", f"{selection.b:.3f}"
    )
    rmse_column, rival_column, r_squared_column = st.columns(3)
    rmse_column.metric("RMSE of the selected curve", f"{selection.rmse_bbl_d:,.2f} bbl/d")
    rival_rmse = selection.rival_rmse_bbl_d
    rival_column.metric(
        "RMSE of the other fitted curve",
        "not fitted" if np.isnan(rival_rmse) else f"{rival_rmse:,.2f} bbl/d",
    )
    r_squared_column.metric(
        "Goodness of fit on the rate scale", f"R² {selection.r_squared:.4f}"
    )
    st.caption(
        f"`qi` is the fitted curve's rate at `t = 0`, back-extrapolated rather than "
        f"observed, and `b` is the decline curvature that shapes the curve — `b = 0` is "
        f"the exponential, `b = 1` the harmonic. Goodness of fit is on the **rate scale**, "
        f"so both RMSEs are in bbl/d and can be compared. The two curves were fitted to "
        f"the same {selection.n_production_periods} production periods"
        + (
            f", {selection.n_dropped} of them dropped for a non-positive oil rate."
            if selection.n_dropped
            else "."
        )
    )


if __name__ == "__main__":
    main()