"""Minimal Streamlit dashboard: list the synthetic wells and show one well's history.

This app is a thin adapter. It holds **no business logic**: it loads the sample
production CSV through the analysis library's reader, lets you pick a well, and renders
that well's production periods as a table with the metrics derived from them (water cut,
gas-oil ratio, cumulative oil). It then draws the well's decline curve — a log-rate
chart with **both** fitted Arps curves, the exponential and the hyperbolic, the one the
library selected by RMSE, and a control to override that choice — reports the wells
``decline_curve_lab.surveillance`` flagged as lift candidates for engineering review, and
closes with the two extrapolation sections: the well's **12-month oil-rate forecast** with
the terminal-decline switch applied, and a **fleet-wide EUR table** with a sort control.
Every rule about what the numbers mean lives in ``decline_curve_lab.io`` and the modules
that extend it, so this file is safe to delete and rewrite.

The analyst's curve override is honoured throughout: the forecast, the EUR and the
selected well's row in the EUR table all follow the curve the override control chose, and
the EUR table names the curve and how it was chosen on every row.

Run it with, from a fresh clone and with nothing installed but ``uv``:

    make run

which resolves the environment from ``pyproject.toml`` and ``uv.lock`` into ``.venv/`` and
then serves this file. To serve an already-resolved environment directly:

    uv run --extra dev streamlit run src/decline_curve_lab/dashboard.py --server.headless true

The ``decline-curve-lab-dashboard`` console script installed by ``pyproject.toml`` calls
:func:`main` directly, which Streamlit executes in "bare mode": the whole code path runs
headlessly and exits, so it is a smoke check on the code, not a server. Nothing here holds
any logic, so nothing is lost by running the script directly.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from decline_curve_lab import arps, forecast, io, metrics, surveillance


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

    selection = _show_decline_curve_selection(well_id, well_production_periods)
    _show_lift_candidates(metrics.compute_metrics(production))
    _show_forecast(well_id, well_production_periods, selection)
    _show_eur_table(production, well_id, selection)


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
) -> arps.DeclineCurveSelection | None:
    """Chart a well's oil rate on a log axis with **both** fitted Arps curves on it.

    Still no business logic here: the elapsed-time axis, both fitted curves, the
    parameters, the RMSE comparison and the choice of decline curve all come from
    ``decline_curve_lab.arps``. This draws them, labels which curve was selected, and
    offers the analyst the override (spec user story 10). The only decision made in
    this file is whether the analyst picked something other than what the RMSE
    comparison chose — which is what the override argument is for.

    The selection is returned so the sections below can follow the analyst's choice
    rather than the RMSE one. ``None`` when no decline curve could be fitted at all, in
    which case there is nothing for them to project.
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
        return None

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
    return selection


def _show_forecast(
    well_id: str,
    well_production_periods: pd.DataFrame,
    selection: arps.DeclineCurveSelection | None,
) -> None:
    """The well's 12-month oil-rate forecast, on its own chart beside the history.

    A separate chart rather than another line on the decline-curve chart above: that chart
    exists to judge the fit against the observed production periods, and the observed
    points and the two fitted curves are what a reader is looking at there. The forecast
    gets the observed history in a muted grey, the same decline curve carried over the whole
    span — with the terminal-decline switch applied, so the handover is visible when it is
    near — and the twelve forecast production periods in a third, distinct series.

    Still no business logic: every number here is read off ``forecast.forecast`` and
    ``forecast.eur``, including which decline curve is followed, so an analyst's override
    carries through to the forecast and the EUR without this file deciding anything.
    """
    st.subheader(f"12-month forecast and EUR for {well_id}")
    if selection is None:
        st.warning(
            f"No decline curve could be fitted to {well_id}, so there is nothing to "
            "forecast or to integrate an EUR from."
        )
        return

    twelve = forecast.forecast(selection, well_production_periods)
    # The same curve over the whole span — history and forecast together — so the two
    # phases of the forecast read as one line. `history_months` comes from the forecast
    # above rather than from counting rows here.
    history_months = int(twelve.periods["elapsed_months"].iloc[0])
    whole_span = forecast.forecast(
        selection,
        well_production_periods,
        months=history_months + forecast.DEFAULT_FORECAST_MONTHS,
    )
    estimate = forecast.eur(selection, well_production_periods)

    figure, axes = plt.subplots(figsize=(10, 4.5))
    try:
        observed = arps.positive_rate_mask(well_production_periods["qo"].to_numpy())
        elapsed = arps.elapsed_months(well_production_periods)
        axes.scatter(
            elapsed[observed],
            well_production_periods["qo"].to_numpy()[observed],
            s=14,
            color="0.6",
            label="observed oil rate",
            zorder=3,
        )
        axes.plot(
            whole_span.periods["elapsed_months"],
            whole_span.periods["qo"],
            color="tab:blue",
            linewidth=1.5,
            label="decline curve, with the terminal-decline switch",
            zorder=2,
        )
        axes.plot(
            twelve.periods["elapsed_months"],
            twelve.periods["qo"],
            color="tab:red",
            linewidth=2.5,
            marker="o",
            markersize=4,
            label=f"{len(twelve.periods)}-month forecast",
            zorder=4,
        )
        switch_months = twelve.switch_elapsed_months
        if not np.isnan(switch_months) and switch_months <= float(
            twelve.periods["elapsed_months"].iloc[-1]
        ):
            axes.axvline(
                switch_months,
                color="tab:green",
                linestyle=":",
                linewidth=1.5,
                label="terminal decline: exponential tail from here",
            )
        axes.set_yscale("log")
        axes.set_xlabel("Elapsed time (production periods from the well's first)")
        axes.set_ylabel("Oil rate (bbl/d, daily average)")
        axes.set_title(
            f"{well_id}: the {selection.curve} Arps curve carried forward "
            f"{forecast.DEFAULT_FORECAST_MONTHS} production periods past the last one"
        )
        axes.grid(True, which="both", alpha=0.3)
        axes.legend()
        st.pyplot(figure)
    finally:
        plt.close(figure)

    qi_column, di_column, b_column, volume_column, eur_column = st.columns(5)
    qi_column.metric("Initial rate `qi`", f"{selection.qi:,.1f} bbl/d")
    di_column.metric("Initial nominal decline `Di`", f"{selection.Di:.1%} /yr")
    b_column.metric("Decline curvature `b`", f"{selection.b:.3f}")
    volume_column.metric(
        f"Oil over the next {len(twelve.periods)} production periods",
        f"{twelve.periods['volume_bbl'].sum():,.0f} bbl",
    )
    eur_column.metric(
        f"EUR (to {estimate.economic_limit_rate_bbl_d:g} bbl/d, "
        f"{estimate.max_horizon_months} production periods)",
        f"{estimate.eur_bbl:,.0f} bbl",
    )
    st.caption(
        _forecast_note(selection, twelve, estimate)
    )

    st.dataframe(twelve.periods, width="stretch", hide_index=True)
    st.caption(
        "One row per forecast production period: `date` is the calendar month it stands "
        "for, `elapsed_months` counts from this well's own first production period, `qo` "
        "is the forecast oil rate in bbl/d as a daily average (ADR-0002), and `volume_bbl` "
        "is that rate times the days in the month — the same rule that builds `Np` above."
    )


def _forecast_note(
    selection: arps.DeclineCurveSelection,
    twelve: forecast.Forecast,
    estimate: forecast.EurEstimate,
) -> str:
    """Say, in one sentence each, what carries the forecast forward and what stopped the EUR.

    Three different answers are possible and only one of them applies to a given well: the
    exponential Arps curve has no hyperbolic phase at all; a curve already at or below the
    terminal decline at ``t = 0`` is carried forward as the exponential from the start; and a
    hyperbolic hands over to the exponential tail at the terminal decline, either inside
    the forecast window or long after it.
    """
    switch_months = twelve.switch_elapsed_months
    if np.isnan(switch_months):
        if selection.b == 0.0:
            progression = (
                "The forecast follows the **exponential** Arps curve, which is already the "
                "exponential tail and so has no terminal decline to switch to."
            )
        else:
            progression = (
                f"`Di` is at or below the terminal decline of "
                f"{twelve.terminal_decline_annual:.0%} nominal/yr at `t = 0`, so the "
                "convention's answer is that there is no hyperbolic phase and the forecast "
                "is the **exponential** Arps curve from the start."
            )
    elif twelve.switch_within_window:
        progression = (
            f"The forecast runs the **{selection.curve}** Arps curve and switches to an "
            f"exponential tail at production period {switch_months:,.1f} "
            f"({switch_months / arps.MONTHS_PER_YEAR:.1f} years), at "
            f"{twelve.switch_rate_bbl_d:,.1f} bbl/d — the terminal decline of "
            f"{twelve.terminal_decline_annual:.0%} nominal/yr (EIA, ADR-0001), "
            "continued from the rate reached there rather than from `qi`."
        )
    else:
        progression = (
            f"The forecast runs the **{selection.curve}** Arps curve throughout; its "
            f"terminal decline falls at production period {switch_months:,.1f} "
            f"({switch_months / arps.MONTHS_PER_YEAR:.1f} years), beyond this "
            f"{len(twelve.periods)}-month window."
        )

    stopped_at = (
        f"The EUR stopped at production period {estimate.final_period:%B %Y} because "
        f"{forecast.EUR_STOP_LABELS[estimate.stop_reason]} (ADR-0003: the well is dead "
        f"below {estimate.economic_limit_rate_bbl_d:g} bbl/d, so the EUR is never "
        "integrated toward zero)"
        if estimate.n_production_periods
        else (
            f"This well was already below the economic limit rate of "
            f"{estimate.economic_limit_rate_bbl_d:g} bbl/d at `t = 0`, so it has no EUR."
        )
    )
    shaped_by_switch = (
        " The exponential tail is inside the integrated span, so the terminal decline "
        "shaped this EUR."
        if estimate.terminal_switch_bounds_eur
        else " The terminal decline is not reached inside the integrated span."
    )
    return f"{progression} {stopped_at}.{shaped_by_switch}"


def _show_eur_table(
    production: pd.DataFrame,
    well_id: str,
    selection: arps.DeclineCurveSelection | None,
) -> None:
    """Every well's EUR side by side, with a working sort control.

    Still no business logic, and the sort is the important part of that: the ordering is
    ``forecast.eur_table``'s, and this only hands it a column and a direction. An app that
    re-sorted the returned rows would have two places where "largest EUR first" is written
    down, and they would eventually disagree.

    The selected well's row follows the analyst's override, and every row names the curve
    and how it was chosen, so a row's EUR can always be traced back to a curve.
    """
    st.subheader("EUR by well")
    if selection is None:
        st.warning("No decline curve could be fitted, so there are no EURs to compare.")
        return

    override = (
        selection.curve if selection.chosen_by == arps.CURVE_BY_OVERRIDE else None
    )
    sort_column, direction = st.columns(2)
    column = sort_column.selectbox(
        "Sort the EUR table by",
        list(forecast.EUR_TABLE_COLUMNS),
        index=list(forecast.EUR_TABLE_COLUMNS).index(forecast.EUR_COLUMN),
    )
    largest_first = direction.selectbox(
        "Order", ["largest first", "smallest first"], index=0
    )

    table = forecast.eur_table(
        production,
        override_well_id=well_id,
        override=override,
        sort_by=column,
        descending=largest_first == "largest first",
    )
    st.dataframe(table, width="stretch", hide_index=True)
    caption = (
        f"{len(table)} wells, each with the Arps curve its decline curve is, how that "
        f"curve was chosen (`chosen_by` is `rmse`, `override` or `only_available`), its "
        f"fitted `qi` in bbl/d, `Di` as a nominal fraction per year (ADR-0001), the "
        f"decline curvature `b`, the RMSE of the selected curve in bbl/d, its `eur_bbl` in "
        f"bbl, the economic limit rate that EUR was cut at in bbl/d, and `stop_reason` — "
        f"`{forecast.STOP_AT_ECONOMIC_LIMIT}` when the well was dead by then, "
        f"`{forecast.STOP_AT_HORIZON_CAP}` when the model ran out of "
        f"{forecast.DEFAULT_MAX_HORIZON_MONTHS} production periods first. "
    )
    if override is not None:
        caption += (
            f"{well_id}'s row follows your override to the {override} Arps curve; every "
            "other well is chosen by RMSE. "
        )
    unfitted = table.attrs["unfitted_well_ids"]
    if unfitted:
        caption += (
            f"No decline curve could be fitted to {unfitted}, so those wells are not "
            "listed. "
        )
    st.caption(caption.strip())


if __name__ == "__main__":
    main()