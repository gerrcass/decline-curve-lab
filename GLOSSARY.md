# Production Surveillance (decline-curve-lab)

The vocabulary for decline-curve analysis (DCA) of oil wells and the surveillance
rules that screen wells for engineering review.

## Language

**Production period**:
One monthly observation of a well's production. Each row of the production CSV
is one production period for one well. Rates are daily averages (bbl/d for
liquid, scf/d for gas); each period carries a single representative rate.
_Avoid_: record, row, sample, data point, month (as a data unit)

**Well**:
A single producing borehole, identified by `well_id`, whose production is
tracked over time as a series of production periods.
_Avoid_: borehole, wellbore

**Decline curve**:
A fitted model of how a well's oil rate falls over time, from which future
production and EUR are extrapolated. In this project always one of the three
Arps curves.
_Avoid_: trend, forecast, projection

**Arps curve**:
One of three decline models in the Arps family — exponential, hyperbolic, or
harmonic — each identified by a decline curvature parameter `b`. "Exponential",
"hyperbolic", and "harmonic" always mean these specific curves.
_Avoid_: bare "exponential"/"hyperbolic" (too generic), DCA model, decay curve

**Initial rate (`qi`)**:
The oil rate a fitted decline curve predicts at `t = 0`, back-extrapolated
from the fitted window rather than observed. A model parameter, not a
measurement.
_Avoid_: initial production rate, IP, starting rate

**Initial nominal decline (`Di`)**:
The Arps nominal decline rate at `t = 0`, expressed in nominal percent per
year. The canonical decline parameter in this project (Arps 1945, and the EIA
convention).
_Avoid_: decline rate (unqualified), initial decline (unqualified), decay rate

**Effective decline (`D_eff`)**:
The continuous-rate counterpart of nominal decline, `D_eff = ln(1 + Di)`
(10% nominal ≈ 9.53% effective). Derived only to solve the continuous
exponential; never stored or reported as the canonical `Di`.
_Avoid_: continuous decline, actual decline, true decline

**Decline curvature (`b`)**:
The Arps parameter shaping a decline curve: `b = 0` is exponential, `b = 1` is
harmonic, values strictly between are hyperbolic. Bounded to [0, 1]. Distinct
from the formation volume factor `B`, a different petroleum symbol.
_Avoid_: b-factor (ambiguous with formation volume factor), curvature alone

**Terminal decline**:
The effective annual decline rate at which the forecast switches from the
hyperbolic curve to the exponential tail (10% nominal per the EIA convention),
so the tail does not overstate long-term recovery. The switch occurs when the
hyperbolic decline reaches this rate.
_Avoid_: switch point, cutoff rate, hyperbolic cap, b-cutoff

**Cumulative oil (`Np`)**:
The running total of oil produced by a well over its production periods to
date.
_Avoid_: cumulative production (unqualified), Cum oil, reserves

**Water cut (`fw`)**:
The fraction of total liquid that is water, `qw / (qo + qw)`, expressed as a
decimal in [0, 1] (not a percentage).
_Avoid_: water fraction (redundant), WOR, water percentage

**Gas-oil ratio (`GOR`)**:
The volume of gas produced per unit of oil produced, `qg / qo` (scf/bbl).
A diagnostic of the production mechanism.
_Avoid_: GORR, gas ratio

**Wellhead pressure**:
The pressure measured at the wellhead at the surface (psi).
_Avoid_: WHP, tubing pressure, bottomhole pressure

**Choke**:
The surface flow-control device or setting that meters production from the
well.
_Avoid_: choke size (unqualified), bean size

**Economic limit rate**:
The oil rate below which producing the well stops being worthwhile; the endpoint
where cumulative production stops accumulating and EUR is cut off. A
configurable parameter, not a physical constant. The point at which a well is
"dead" in this model.
_Avoid_: death, dead, killed, economic death, abandonment (the decision, not the rate)

**EUR (Estimated Ultimate Recovery)**:
The total oil a well is expected to produce from `t = 0` until the economic
limit rate, under the fitted decline curve and terminal-decline switch. A DCA
extrapolation — distinct from a formal reserves classification (proved / 2P /
3P).
_Avoid_: reserves, ultimate recovery, recovery factor, EUR (as reserves)

**Lift candidate**:
A well flagged by a simple screening rule (low oil rate, high water cut, or
sustained wellhead-pressure decline) as warranting engineering review for
artificial lift. A screening flag for a human — never a recommendation.
_Avoid_: needs lift, recommend lift, lift well, workover candidate