"""Shared test configuration.

The one test seam for this project is the pure-function analysis library
(``decline_curve_lab.io``, ``decline_curve_lab.synthetic``,
``decline_curve_lab.metrics``, ``decline_curve_lab.arps``,
``decline_curve_lab.forecast`` and ``decline_curve_lab.surveillance``). The Streamlit app
is a thin adapter and gets no direct tests, per the project's testing decisions.
"""