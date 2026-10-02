"""Minimal Streamlit dashboard: list the synthetic wells and show one well's history.

This app is a thin adapter. It holds **no business logic**: it loads the sample
production CSV through the analysis library's reader, lets you pick a well, and
renders that well's production periods as a table. Every rule about what the numbers
mean lives in `decline_curve_lab.io` and the modules that extend it, so this file is
safe to delete and rewrite.

Run it with:

    /tmp/opencode/dcl-venv/bin/streamlit run src/decline_curve_lab/dashboard.py

or, once the project has an installed single-command run:

    decline-curve-lab-dashboard
"""

from __future__ import annotations

import streamlit as st

from decline_curve_lab import io


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


if __name__ == "__main__":
    main()