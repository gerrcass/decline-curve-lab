# One-command run for decline-curve-lab.
#
#   make run          set up the environment and serve the dashboard
#   make test         set up the environment and run the test suite
#
# A fresh clone needs exactly two things already on the machine: `uv` and Python 3.10+.
# Nothing else. `uv sync` reads `pyproject.toml` and `uv.lock` and builds `.venv/`, which
# is gitignored, so the working tree stays clean apart from `.venv/`.
#
# Why `uv` and not a `venv` + `pip install -e .` pair in a shell script: `uv run` re-resolves
# the environment from the lock file on every invocation, so "set up and run" is one step
# rather than two that can drift apart, and it needs no activate dance, no PATH fiddling and
# no pip on the machine. It also runs the dashboard inside that same resolved environment
# rather than whichever one happens to be active in the caller's shell.

UV ?= uv

# The Streamlit entry point. Thin adapter: no business logic, safe to read in one sitting.
DASHBOARD := src/decline_curve_lab/dashboard.py

# `--extra dev` is pytest. Kept in one place so `make run` and `make test` always agree on
# what is installed; `uv run` re-syncs the environment, so both targets must ask for the
# same extras or one would uninstall what the other needs.
UV_FLAGS := --extra dev

# Headless, so the server starts on a terminal, in CI or over SSH without stopping to ask
# for an onboarding email address or trying to open a browser.
STREAMLIT_FLAGS := --server.headless true

.PHONY: help setup run test sample-data

help:
	@echo "make run          set up the environment and serve the dashboard"
	@echo "make test         run the test suite (159 tests at the analysis-library seam)"
	@echo "make setup        just create/refresh .venv from pyproject.toml and uv.lock"
	@echo "make sample-data  regenerate data/sample_wells.csv from the seeded generator"

setup:
	$(UV) sync $(UV_FLAGS)

run: setup
	$(UV) run $(UV_FLAGS) streamlit run $(DASHBOARD) $(STREAMLIT_FLAGS)

test: setup
	$(UV) run $(UV_FLAGS) python -m pytest -q

# The generator is fully deterministic, so this rewrites data/sample_wells.csv byte for
# byte unless the generator itself has changed. Run it after changing `synthetic.py`.
sample-data: setup
	$(UV) run $(UV_FLAGS) python -m decline_curve_lab.synthetic