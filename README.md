# decline-curve-lab

Decline-curve analysis (DCA) of oil wells, and the surveillance rules that screen wells for
engineering review. A pure-function analysis library over a seeded synthetic well set, with a
minimal Streamlit dashboard as a thin adapter on top.

The project exists to make the arithmetic of decline-curve analysis **legible**: every
convention it commits to is written down in an ADR, the vocabulary is fixed in
[`GLOSSARY.md`](GLOSSARY.md), and the maths is pinned by tests that check it against a closed
form or an exact identity wherever a closed form exists — a monthly sum against the continuous
integral of the same curve, a forecast against `qi`, `Di` and `b` read straight off the fit, a
recovered parameter against the one a noise-free series was generated from.

---

## Quick start

A fresh clone needs exactly two things already on the machine: **[uv](https://docs.astral.sh/uv/)**
and **Python 3.10 or newer**. Nothing else — no venv to create, no `pip install`, no `activate`.

```sh
make run
```

That is the one command. It resolves the environment from `pyproject.toml` and the committed
`uv.lock` into a gitignored `.venv/`, installs this package and its dependencies there, and
serves the dashboard on <http://localhost:8501>. It runs headless, so it works on a bare
terminal, over SSH and in CI without stopping to ask for an email address or trying to open a
browser. With a warm wheel cache it is a couple of seconds; on a cold cache the first run also
downloads ~100 MB of wheels, and every run after that is instant.

```sh
make test     # the whole test suite: 159 tests
make help     # every target
```

`make` is a thin front for `uv`, and the raw `uv` commands are here if you would rather skip
it or are not on a machine with `make`:

| what | via `make` | raw `uv` |
|---|---|---|
| serve the dashboard | `make run` | `uv run --extra dev streamlit run src/decline_curve_lab/dashboard.py --server.headless true` |
| run the tests | `make test` | `uv run --extra dev python -m pytest -q` |
| create/refresh only the env | `make setup` | `uv sync --extra dev` |
| regenerate the sample data | `make sample-data` | `uv run --extra dev python -m decline_curve_lab` |

`uv run` re-resolves the environment from the lock file on each invocation, so "set up and
run" is one step rather than two that can drift apart, and the dashboard runs inside that
resolved environment rather than whichever one happens to be active in your shell. That is
the whole reason `uv` rather than a `venv` + `pip install -e .` pair in a shell script.

`--extra dev` is pytest, asked for in both targets on purpose: `uv run` re-syncs, so if only
one target asked for it the other would uninstall it.

**Lint and typecheck: none.** The project configures no linter and no type checker —
`pyproject.toml` holds the build system, the dependency list and the pytest configuration and
nothing else, and adding a linter or a type checker to an educational project would be
tooling this project does not need. `pytest --strict-markers` is the only check that runs, and
it is the check that matters: it is 159 tests over the analysis library.

### Regenerating the sample data

```sh
make sample-data
```

The generator is a pure function of its seed (`synthetic.DEFAULT_SEED = 20260902`), so this
rewrites `data/sample_wells.csv` **byte for byte** unless the generator itself changed.
`tests/test_synthetic.py` regenerates the file in memory and fails with "regenerate it" if the
two ever drift apart.

Without an installed package the same thing runs with `PYTHONPATH=src python -m decline_curve_lab`,
and `--seed N` uses a different seed. With the package installed there is also a
`decline-curve-lab-sample-data` console script that calls the same `main()`.

The command runs the package's entry point (`src/decline_curve_lab/__main__.py`) rather than
`python -m decline_curve_lab.synthetic`, and the difference is not cosmetic. The package
`__init__` imports the generator, so `-m decline_curve_lab.synthetic` asks `runpy` to execute
a module that is *already* in `sys.modules`; `runpy` warns about exactly that ("found in
`sys.modules` … may result in unpredictable behaviour"), and anywhere warnings are promoted to
errors — `-W error::RuntimeWarning`, `PYTHONWARNINGS`, a test runner — the copy-paste command
aborts before it writes anything. `python -m decline_curve_lab` imports the generator
normally and calls `main()` once, so it is warning-free. `-m decline_curve_lab.synthetic`
still works and produces the same bytes;
`tests/test_synthetic.py` pins both, the first under `-W error::RuntimeWarning`.

---

## What the dashboard shows

One page, one well selector, five sections:

1. **Production history** — the well's production periods with the derived `water_cut`, `GOR`
   and cumulative oil `Np`.
2. **Decline curve** — the oil rate on a **log axis** with *both* fitted Arps curves drawn on
   it, the one the library selected by RMSE labelled, the parameters `qi` / `Di` / `b`, both
   RMSEs, and a control to **override** the selection (which the forecast, the EUR and that
   well's row in the EUR table all follow).
3. **Lift candidates for engineering review** — the wells the screening rules flagged, and
   every reason that fired, not just the first.
4. **12-month forecast and EUR** — the selected decline curve projected twelve production
   periods past the last observed one, the forecast periods as a table, and the EUR with the
   reason it stopped.
5. **EUR by well** — the whole fleet side by side, with a working sort control (column and
   direction).

It holds **no business logic**. Every threshold, every rule and every number comes from the
library below, so the file is safe to delete and rewrite.

---

## The four study sources

These are what the project's conventions rest on. The URLs below were fetched on 2026-10-02
(the REP 06 PDF is the one exception, cited as corroboration and not fetched), and what
follows is stated as carefully as the evidence allows — including where the evidence runs out.

1. **Arps, J. J. (1945).** "Analysis of Decline Curves." *Transactions of the AIME*, **194**,
   228–232.
   <https://blasingame.engr.tamu.edu/z_WPA/z_WPA_(Generic)/WPA_Various_Tech_Papers_(Prod_Data_Anl)/SPE_00000_Arps_Decline_Curve_Analysis.pdf>

   The origin of the three-curve family — exponential, hyperbolic, harmonic — and of the
   curvature exponent `b`, and the source of the `Di` as the decline parameter that appears
   inside the equation.

   **Cited by reference only.** The only reachable copy is a scanned PDF with no text layer
   (zero extractable characters), so nothing here is quoted from Arps and nothing is put in
   quotation marks. The formulas this project implements are taken from the EIA page and from
   Blasingame Lecture 8, both of which reproduce them explicitly.

2. **U.S. Energy Information Administration.** "Production Decline Curve Analysis in the
   *Annual Energy Outlook*," AEO2022 edition, released 2023-03-16 (the page is banner-marked
   as discontinued).
   <https://www.eia.gov/analysis/drilling/curve_analysis>
   · archived 2020 edition: <https://www.eia.gov/analysis/drilling/curve_analysis/2020/>
   · the same wording in longer form, with every symbol named, in
   [*NEMS Model Documentation 2017: Oil and Gas Supply Module*, Appendix 2.C, p. 166](https://www.eia.gov/outlooks/aeo/nems/documentation/ogsm/pdf/m063%282017%29.pdf)

   The source that fixes the terminal-decline convention: the curve converts from hyperbolic
   to exponential when the monthly decline rate falls to 0.8 % (10 % annual decline), and the
   EUR runs through month 360 (30 years). EIA fits `Di` **per month** and normalises every
   month to 30.4 days; this project fits `Di` per year and takes the real length of each
   calendar month from the `date` column instead.

   EIA **never uses the words "nominal" or "effective"** anywhere in this material. The
   convention below is therefore *attributed* to this source from its arithmetic and internal
   consistency, not quoted from it as a first-hand statement of the words.

3. **Wattenbarger, R. A., Waters, G. B., and Rushing, J. A. (1996).** "Production forecasting
   decline curve analysis." SPE 8428 (OnePetro).
   <https://onepetro.org/spe/general-information/1996/Production-forecasting-decline-curve-analysis>

   The reference that settles the *vocabulary*: the **nominal** decline factor is the one that
   goes inside the Arps equations and the one to store; the **effective** factor is the
   proportion by which the rate reduces over a period, and is derived from the nominal one.
   This is the provenance of ADR-0001's `D_eff = ln(1 + D_nom)`, and of why the `ln(1 + x)`
   transform must not be applied before the time unit is fixed.

   **Second-hand.** OnePetro returns **HTTP 403** to direct fetches; the wording was recovered
   through a search index of the page, not by loading it from OnePetro. The identical
   conversion is independently corroborated by the SPE's *Recommended Evaluation Practices on
   Decline Curves*, REP 06
   (<https://manual.whitson.com/files/dca/REP06-DeclineCurves.pdf>, not fetched here).

4. **Blasingame, T. A. (2016).** "Lecture 8 — Decline-Curve Analysis for Gas Wells," Petroleum
   Engineering 613: Natural Gas Engineering, Texas A&M University, slides dated 2016-04-13.
   <https://blasingame.engr.tamu.edu/z_zCourse_Archive/P613_16A/P613_16A_Lectures/20160413_P613_16A_Lec_08_%28DCA_Gas_Wells%29_%5BPDF%5D.pdf>
   · the textbook cited on every slide: Lee, W. J. and Wattenbarger, R. A., *Gas Reservoir
   Engineering*, SPE (1996).

   The cleanest single statement of the whole Arps family, written in dimensionless form so
   the members cannot be confused: with `t_D = Di·t` and `q_D = q/qi`, slide 2 lists
   exponential (`b = 0`), hyperbolic (`0 < b < 1`) and harmonic (`b = 1`) with both the rate
   and the cumulative relation for each.

   Two honest limits. It is a **gas** lecture — the Arps relations are fluid-independent, so
   the forms carry over, and Lee & Wattenbarger is the oil-appropriate textbook to cite
   alongside it. And it **never uses the words "nominal" or "effective"** (verified: zero
   occurrences across all 40 slides), so it **cannot** be cited as evidence about that
   question. It is cited for the curve forms and the `Np` integrals only.

Full detail, including the arithmetic that decides the convention and the residual doubt it
leaves open, is in
[`docs/research/eia-terminal-decline-convention.md`](docs/research/eia-terminal-decline-convention.md).

---

## The three conventions

Each one is an ADR, and each ADR says why the alternative was rejected.

### 1. Rates are daily averages — [ADR-0002](docs/adr/0002-rates-are-daily-averages.md)

Every rate in the production CSV is a **daily average** over its production period: bbl/d for
oil and water, scf/d for gas. Never a volume produced during the period.

This matters because the lift screen (`qo < 100` bbl/d) is the conventional ~100 bbl/d
artificial-lift heuristic and is meaningless read as a monthly volume — off by about thirty
times, enough to flag the whole fleet — and because fitting `qi` and `Di` needs a rate
consistent with the time axis. `io.load_production` reads rates exactly as written: it never
rescales, rounds or unit-guesses, and rejects anything ambiguous rather than guessing.

### 2. `Di` is nominal percent per year — [ADR-0001](docs/adr/0001-nominal-decline-is-canonical.md)

`Di` is the **nominal** decline as a fraction per year (`0.35` is 35 %/yr nominal) and is the
only decline this project stores or reports. The effective decline `D_eff = ln(1 + Di)` is
**derived only inside the solver** — by `arps.effective_decline_from_nominal` and, for the
exponential tail, by `forecast._tail_effective_decline` — and is never stored on a fit, put on
an exported type as a public attribute, or printed. `tests/test_package.py` asserts that no
class the package exports reports an effective decline at all, so the rule is enforced rather
than merely intended.

That is the difference the research note settles for the terminal decline, and the EIA
threshold is on the same footing: **`0.10` nominal per year**, which is `0.10/12 = 0.0083333`
nominal per month — exactly the `0.8 %/month` EIA prints. So
`forecast.DEFAULT_TERMINAL_DECLINE_ANNUAL = 0.10`, exposed as a parameter
(`forecast.terminal_switch`, `forecast.forecast`, `forecast.eur`, `forecast.eur_table` all take
`terminal_decline_annual`).

The one trap this convention exists to prevent: **nominal rates scale between time units by a
plain ratio; effective rates do not.** `12 · ln(1 + 0.10/12) ≠ ln(1 + 0.10)`. So `D_eff` is
derived *after* the time unit is fixed in years — `arps.to_years` is the only place months
become years — and never scaled from one unit to another.

ADR-0001 made itself conditional: *"if it turns out EIA uses effective decline, this ADR is
superseded."* The research note found no such evidence, so the ADR stands. The evidence is
strong but not conclusive, and the note says so in §5: EIA never writes the words, and a
reader could argue its code converts the annual figure through the effective relation instead.
That reading would require the threshold and `Di` to be in *different* conventions, which is
internally incoherent — but it cannot be ruled out from the published text.

### 3. The EUR ends at the economic limit rate — [ADR-0003](docs/adr/0003-eur-ends-at-economic-limit-rate.md)

The EUR integrates the fitted decline curve **from `t = 0` until the curve reaches the economic
limit rate**, never toward zero. Below that rate the well is "dead" *in this model* — below the
economic limit rate is a **rate**, not a decision; **abandonment is the decision, not the
rate**.

* `economic_limit_rate_bbl_d`, project default **1.0 bbl/d**. About 1 % of the 100 bbl/d
  lift-screening threshold, so a plausible rate for a mature well that has already lost
  interest to artificial lift, and it keeps EUR numbers in the same order of magnitude as the
  rest of the project. It is a parameter rather than a constant because the honest value
  depends on oil price, operating cost and lift method — all out of scope here, so this project
  can parameterise the economic limit but cannot derive it.
* `max_horizon_months`, default **360** (30 years, matching EIA), which bounds the hyperbolic and
  harmonic tails that would otherwise keep accumulating forever.

Both apply and the EUR stops at **whichever binds first**. `EurEstimate.stop_reason` says which,
and `forecast.EUR_STOP_LABELS` holds the wording:
`STOP_AT_ECONOMIC_LIMIT` ("the curve reached the economic limit rate" — the well was dead)
versus `STOP_AT_HORIZON_CAP` ("the horizon cap was reached first" — the model ran out of years on
a well that is still producing). Those are different answers and a caller has to tell them
apart.

---

## From the glossary to the code

Every term in [`GLOSSARY.md`](GLOSSARY.md), and the function, column or constant that
implements it. Verified against the code, not from the glossary's prose.

| glossary term | where it lives in the code |
|---|---|
| **Production period** | one CSV row, for one well. `io.PRODUCTION_COLUMNS` is the schema; `arps.elapsed_months` counts them from the well's own `t = 0`; `forecast.FORECAST_COLUMNS` is the forecast's own |
| **Well** | the `well_id` column, kept as text by `io.load_production`; `arps.elapsed_months` gives each well its own clock |
| **Decline curve** | `arps.select_decline_curve` → `arps.DeclineCurveSelection`, whose `.curve` names it and whose `.rate_at(t)` evaluates it |
| **Arps curve** | `arps.EXPONENTIAL_CURVE` / `arps.HYPERBOLIC_CURVE`; evaluated by `arps.exponential_rate` and `arps.hyperbolic_rate`. The harmonic is the `b = 1` case of the hyperbolic — a distinct curve, never collapsed into the exponential |
| **Initial rate `qi`** | `.qi` on `arps.ExponentialFit`, `arps.HyperbolicFit` and `arps.DeclineCurveSelection`; column `qi` in `forecast.EUR_TABLE_COLUMNS`. Back-extrapolated to `t = 0`, not observed |
| **Initial nominal decline `Di`** | `.Di` on those same three objects; column `Di`. Nominal fraction per year, ADR-0001 |
| **Effective decline `D_eff`** | **never stored and never reported.** Derived by `arps.effective_decline_from_nominal`, and by the module-private `forecast._tail_effective_decline` for the exponential tail. No class the package exports holds it as an attribute. ADR-0001 |
| **Decline curvature `b`** | `.b` on `arps.HyperbolicFit` and `arps.DeclineCurveSelection` (`0.0` for the exponential); column `b`; `forecast.decline_curvature(curve)` reads it off either kind; the fit's floor is `arps.MIN_CURVATURE` |
| **Terminal decline** | `forecast.DEFAULT_TERMINAL_DECLINE_ANNUAL`; the switch itself is `forecast.terminal_switch(curve) -> forecast.TerminalSwitch`, carried on `Forecast.switch` and `EurEstimate.switch` |
| **Cumulative oil `Np`** | `metrics.compute_metrics` → column `Np` (bbl), listed in `metrics.METRIC_COLUMNS`, accumulated per well from `qo × days in that month` |
| **Water cut `fw`** | `metrics.compute_metrics` → column **`water_cut`**, a decimal in `[0, 1]`. The glossary's identifier is `fw`; the column is spelled out in full on purpose, so the CSV states the convention instead of leaving it to a code reader |
| **Gas-oil ratio `GOR`** | `metrics.compute_metrics` → column `GOR` (scf/bbl) |
| **Wellhead pressure** | the `wellhead_pressure` CSV column (psi); read by `surveillance.SCREENING_INPUT_COLUMNS` and followed by `surveillance._sustained_pressure_decline` |
| **Choke** | the `choke` CSV column (inches); validated by `io.NUMERIC_COLUMNS`, produced by `synthetic._quantize_choke` at `synthetic.CHOKE_INCREMENT_IN` (1/64 in). **No analysis rule reads it** — it is context carried through the schema |
| **Economic limit rate** | `forecast.eur(..., economic_limit_rate_bbl_d=...)` and `forecast.eur_table(...)`, default `forecast.DEFAULT_ECONOMIC_LIMIT_RATE_BBL_D = 1.0`; reported on `EurEstimate.economic_limit_rate_bbl_d` and as a column of the EUR table. "Dead" is `forecast.STOP_AT_ECONOMIC_LIMIT` |
| **EUR** | `forecast.eur(...) -> forecast.EurEstimate`; the fleet view is `forecast.eur_table(...)` with `forecast.EUR_TABLE_COLUMNS` and `forecast.EUR_COLUMN = "eur_bbl"`; the horizon cap is `forecast.DEFAULT_MAX_HORIZON_MONTHS = 360` and the other stop reason is `forecast.STOP_AT_HORIZON_CAP` |
| **Lift candidate** | `surveillance.flag_lift_candidates(...)` → columns `candidate_lift` and `lift_reasons` (`surveillance.SCREENING_COLUMNS`), with the rules' stable codes in `surveillance.LIFT_REASONS` and their wording in `surveillance.LIFT_REASON_LABELS` |

---

## The data format

One row of the production CSV is one **production period** for one **well**.

| column | unit |
|---|---|
| `date` | production period start date, ISO `YYYY-MM-DD`, read as `datetime64` |
| `well_id` | text identifier of the well |
| `qo` | **bbl/d, daily average** oil rate |
| `qw` | **bbl/d, daily average** water rate |
| `qg` | **scf/d, daily average** gas rate |
| `wellhead_pressure` | psi, at the surface |
| `choke` | inches, the surface flow-control setting |

* **Every rate is a daily average, never the volume produced during the period** (ADR-0002). A
  `qo` of `100` means the well made 100 barrels of oil on an average day, not in the month.
* **A production period is a calendar month**, and the `date` column gives its first day. Its
  volume is therefore

  ```
  volume over a production period [bbl] = rate [bbl/d] × days in that month [d]
  ```

  28, 29, 30 or 31 days, never a constant. **That one rule** builds cumulative oil `Np`, every
  forecast row's `volume_bbl`, and the EUR, so a hand calculation can check any of the three.
  (EIA normalises every month to 30.4 days; this project does not, because `date` is exact.)
* Elapsed time `t` counts months from each well's **own** first production period, starting at
  `t = 0`. The shipped wells start in different calendar months, so a shared clock would put one
  well's `t = 0` at another well's `t = 7`.
* `io.load_production` is strict: it rejects a missing or duplicated column, a date that is not
  exactly `YYYY-MM-DD`, a non-numeric or non-finite value, and a negative measurement, naming
  the offending column in the message. It imputes nothing, renames nothing and drops nothing.
  Extra columns are ignored.

Full detail on the committed data: [`data/README.md`](data/README.md).

---

## Module layout, and the single test seam

```
src/decline_curve_lab/
  __init__.py      # public API and __all__
  io.py            # CSV read + schema/dtype validation — the only file-reading seam
  synthetic.py     # seeded generator and the sample-CSV writer
  metrics.py       # water cut, GOR, cumulative Np
  arps.py          # rate equations, the two fits, decline-curve selection
  forecast.py      # forecast with the terminal-decline switch, EUR, EUR table
  surveillance.py  # lift-candidate screening rules
  dashboard.py     # Streamlit app: thin adapter, no business logic
data/sample_wells.csv   # committed, byte-identical output of the seeded generator
tests/                  # all tests live here, at the analysis-library seam
```

`decline_curve_lab.forecast` is a **module**. The oil-rate forecast is called as
`decline_curve_lab.forecast.forecast(...)` and is deliberately **not** re-exported at package
level: `forecast` is already the name of the module, and a package attribute cannot be both
the module and the function inside it. Everything else that module offers — the
terminal-decline switch, `eur`, `eur_table`, the documented defaults — *is* re-exported at
package level.

### The one test seam

**A single seam: the pure-function analysis library.** All 159 tests exercise library
behaviour, inputs to outputs, named after the module they cover. The Streamlit app and the
`decline_curve_lab.synthetic` CLI are thin adapters and get **no direct tests**. No mock,
monkeypatch or fake appears anywhere in the suite today; mocks are permitted only at the
CSV-read boundary, and none has been needed yet.

**The consequence is worth stating plainly: pytest never imports `dashboard.py`, so a broken
app passes the suite silently.** Nothing in the test run tells you the dashboard renders. That
is a deliberate consequence of the seam, not an oversight, and it is why the dashboard was
smoke-checked separately for this release, with `streamlit.testing.v1.AppTest` driving the real
script for all six sample wells and with a headless server start (`make run`, health endpoint
answering 200). Neither check lives in `tests/`, so the seam stays one seam.

---

## What the shipped sample data actually shows

Six wells (`DCL-01` … `DCL-06`), 330 production periods, every well reporting through
2026-09. Measured from `data/sample_wells.csv`; the fitted numbers below are what
`forecast.eur_table` returns.

| well | periods | from | `qi` bbl/d | `Di` /yr | `b` | curve selected | RMSE bbl/d | EUR MMbbl | stop reason | terminal switch, period |
|---|---|---|---|---|---|---|---|---|---|---|
| `DCL-01` | 48 | 2022-10 | 817.8 | 0.622 | 0.871 | hyperbolic | 3.82 | 1.451 | `horizon_cap` | 116 |
| `DCL-05` | 60 | 2021-10 | 522.2 | 0.304 | 0.557 | hyperbolic | 2.76 | 1.172 | `horizon_cap` | 145 |
| `DCL-03` | 36 | 2023-10 | 410.0 | 0.395 | 0.409 | hyperbolic | 1.29 | 0.693 | `horizon_cap` | 219 |
| `DCL-02` | 72 | 2020-10 | 259.9 | 0.180 | 0.000 | **exponential** | 1.53 | 0.574 | `horizon_cap` | none (`b = 0`) |
| `DCL-06` | 54 | 2022-04 | 240.2 | 0.549 | 1.000 | hyperbolic | 1.25 | 0.484 | `horizon_cap` | 98 |
| `DCL-04` | 60 | 2021-10 | 181.0 | 0.531 | 0.722 | hyperbolic | 0.84 | 0.320 | `horizon_cap` | 135 |

`DCL-02` selects the exponential Arps curve; the other five select the hyperbolic. **Do not
call `DCL-06` harmonic.** Its fitted `b` is `1.000`, which *is* the harmonic by definition, but
`arps.select_decline_curve` only ever chooses between two names — `exponential` and `hyperbolic`
— so the EUR table reports it as `hyperbolic`. The generator built `DCL-06` with `b = 1` on
purpose, and `data/README.md` describes that ground truth as harmonic; the fitted label and the
generating parameter are two different things.

### Three things the sample data does *not* show, which are easy to get wrong

1. **The terminal-decline switch never fires inside a 12-month forecast window.** For the five
   hyperbolic wells it lands at production period 98 to 219 — 8 to 18 years out, far beyond
   their three-to-six-year histories. The 12-month forecasts are therefore pure hyperbolic
   projections; the exponential tail never enters them. The switch is fully implemented and
   tested on synthetic series that *do* cross it (continuity of the rate, continuity of its
   derivative, a tail that is not the hyperbolic run on, a tail not re-anchored to `qi`), but
   do not read it into these wells' 12-month forecasts.

2. **All six EURs stop at the 360-production-period horizon cap, not at the economic limit
   rate.** Not one of these wells falls to 1.0 bbl/d inside 30 years; `DCL-02`, the slowest, is
   still at 1.86 bbl/d in production period 359 — the last one the horizon covers — so it never
   reaches the limit rate at all. The economic-limit path is implemented, configurable and
   tested, including a round trip and a parameter sweep on these very wells — at
   `economic_limit_rate_bbl_d=250`, all six stop at the economic limit instead, and two of them
   (`DCL-04`, `DCL-06`, both already below 250 bbl/d at `t = 0`) have no EUR at all — but at the
   default it does not bind on this data. Every row above reads `horizon_cap`, and that is the
   honest answer.

3. **Why the switch lands where it does, and what it does and does not guarantee.**
   `t_switch = (1/D_tail_eff − 1/D_eff)/b`, and that has **no general bound**: it is
   unbounded above as `b → 0`, and arbitrarily close to `t = 0` as `Di → 0.10` from above,
   since a `Di` just past the threshold has effectively reached it at `t = 0`. The often-quoted
   `1/ln(1.10) ≈ 10.49` years — production period 126 — is an upper bound **only at `b = 1`**;
   for `b < 1` the switch comes later. So "the switch bounds the EUR" is a per-well fact, not
   a consequence of the convention: these six have `b` between 0.41 and 1.00, which puts their
   switches at production period 98 to 219, inside the 360-period EUR for all five hyperbolic
   wells at 19 to 127 bbl/d — still above the economic limit rate, so the tail really is
   counted. A gently-curved well (`b = 0.10`, `Di = 0.30`, `qi = 800` bbl/d) switches at
   production period 802: past the horizon, and by then at 0.032 bbl/d, below the economic limit
   rate, so its tail is never counted at all. `EurEstimate.terminal_switch_bounds_eur` is the
   flag that tells you which case you are in.

### What the screening rules flag

`surveillance.flag_lift_candidates` flags exactly two of the six: **`DCL-04`** on low oil rate
with high water cut (50.6 bbl/d, water cut 0.85 on its most recent production period) and
**`DCL-03`** on a sustained wellhead-pressure decline (245 → 72 psi, falling in every one of
its 36 production periods). `DCL-05` is the deliberate control: pressure builds, GOR falls,
and nothing about it should ever be flagged.

---

## Scope and honest limitations

**This is an educational project.** Clarity over sophistication: the goal is that every
convention, unit and formula can be read and checked, not that the analysis be the most
sophisticated one available.

Out of scope, deliberately:

* **No real field data.** The wells are synthetic, from a seeded generator. Nothing here has
  been run against a real production history.
* **No Duong, stretch-exponential or type curves.** Arps only. (Note that Arps' own `b` is not
  bounded above by 1 in practice; this project bounds it to `[MIN_CURVATURE, 1]` and says so.)
* **No gas forecasting.** `qg` is read, validated and turned into a GOR diagnostic; there is no
  gas decline curve and no gas EUR.
* **No economics.** No NPV, no oil price, no operating cost, no lift-cost optimisation. This is
  exactly why the economic limit rate is a *parameter* with a documented default rather than
  something the project derives — see ADR-0003.
* **No multi-user, deployment or internationalisation.** One user, one process, English.

Two honesty notes that belong anywhere a number is read:

* **A lift candidate is a screening flag for human engineering review, never a
  recommendation.** The rules are deliberately simple: `qo < 100` bbl/d **and** `fw > 0.7` on
  the well's most recent production period, or wellhead pressure falling across 3 consecutive
  production periods. Both thresholds are conventions, not measurements, and both are
  parameters a field can argue with. Nothing in this project decides that a well should go on
  artificial lift, and `candidate_lift = True` means "a reviewer should look at this".
* **An EUR here is a DCA extrapolation, not a reserves classification.** It is the integral of
  one fitted curve under three documented conventions. It is not proved, 2P or 3P, and it does
  not claim to be.

---

## Reproducibility

* **Generator seed:** `synthetic.DEFAULT_SEED = 20260902`, documented in
  [`data/README.md`](data/README.md) and asserted by `tests/test_synthetic.py`.
* **The sample CSV is committed and byte-identical on regeneration.** Each well's noise stream
  is derived from the seed *and* the well id, so changing one well's parameters leaves every
  other well's bytes untouched.
* **`uv.lock` is committed**, so `make run` and `make test` resolve to the same dependency
  versions on every machine.
* **Regenerate with `make sample-data`** (or `PYTHONPATH=src python -m decline_curve_lab`).
  A regeneration that differs byte-for-byte means the generator changed, not that the run was
  noisy — and `tests/test_synthetic.py` fails with "regenerate it" if the two drift apart.

---

## Repository map

| path | what it is |
|---|---|
| `GLOSSARY.md` | the canonical vocabulary, with the terms to avoid for each |
| `docs/adr/0001-nominal-decline-is-canonical.md` | `Di` is nominal %/yr; `D_eff` is derived only |
| `docs/adr/0002-rates-are-daily-averages.md` | every CSV rate is a daily average, never a monthly volume |
| `docs/adr/0003-eur-ends-at-economic-limit-rate.md` | the EUR ends at a configurable economic limit rate |
| `docs/research/eia-terminal-decline-convention.md` | the evidence for the 10 %/yr terminal decline, and its limits |
| `docs/research/spec-domain-reconciliation.md` | where the original spec and the domain model disagreed, and how that was resolved |
| `docs/agents/` | how the engineering skills consume this repo's domain docs |
| `data/README.md` | the sample data: seed, units, and the case each well was built to provide |