# EIA terminal-decline convention

**What this is.** A research note recording which decline convention the U.S. EIA uses for
the hyperbolic-to-exponential switch in its decline-curve analysis, so that this project's
canonical `Di` and its terminal-decline threshold are implemented against the source rather
than against an assumption.

**All URLs in this note were fetched on 2026-10-02.**

---

> ## VERDICT
>
> | | |
> |---|---|
> | **EIA's terminal decline is** | **NOMINAL** decline, not effective |
> | **ADR-0001 status** | **CONFIRMED — NOT superseded** |
> | **Threshold to implement** | **`0.10` nominal per year** |
> | **Equivalent nominal per month** | `0.0083333` (= `0.10/12`) — this is EIA's printed `0.8 %` |
> | **Effective equivalent** | `ln(1 + 0.10) = 0.0953102` per year — derived **only inside the exponential solver**, never stored or reported |
>
> The threshold belongs in the same convention as the `D_i` that sits inside EIA's own Arps
> equation, and that convention is nominal.

### Numbers to hard-code

| quantity | value | note |
|---|---|---|
| `TERMINAL_DECLINE_ANNUAL` | `0.10` | nominal, per year. **This is the value to hard-code** — matches EIA's "10 % annual decline" |
| terminal decline, nominal, per month | `0.0083333` | `0.10 / 12`; the same threshold at a different time scale. EIA prints this as `0.8 %` |
| terminal decline, effective, per year | `0.0953102` | `ln(1.10)`. Solver-internal only — never stored, never reported |
| terminal decline, effective, per month | `0.0082988` | `ln(1 + 0.0083333)`. Solver-internal only |
| *trap* — EIA's literal printed figure | `0.008` | annualises to **9.6 %/yr nominal**, about 4 % below 10 %. Do **not** hard-code this as if it were the threshold |

---

## 1. Sources

### 1.1 EIA Drilling Productivity Report series — curve-analysis page

- **URL:** <https://www.eia.gov/analysis/drilling/curve_analysis>
- **Title:** *Production Decline Curve Analysis in the Annual Energy Outlook*
- **Edition:** AEO2022, release date stated on page as 16 March 2023. Page banner:
  "This analysis was conducted for AEO2022 and has been discontinued."

The single sentence that governs the switch, **verbatim**:

> "The decline curve converts from a hyperbolic decline to an exponential decline when the
> monthly decline rate falls to 0.8% (10% annual decline)."

For completeness, the EUR rule from the same page, **verbatim**:

> "The EUR for a well is calculated as the sum of the observed monthly production values
> plus the sum of the monthly production values estimated using the decline curve,
> starting the month after the last observed production month through month 360
> (30 years in total)."

The page renders the rate equation as an image, not as selectable text. The image was
downloaded and read; it is the standard Arps hyperbolic `q(t) = qi / (1 + b·Di·t)^(1/b)`.

**Wording is stable across years.** The AEO2020 edition of the same series
(<https://www.eia.gov/analysis/drilling/curve_analysis/2020/>, released 18 March 2020)
contains the identical switch sentence. No newer EIA restatement of the convention was
found.

### 1.2 EIA NEMS model documentation, Appendix 2.C

- **URL:** <https://www.eia.gov/outlooks/aeo/nems/documentation/ogsm/pdf/m063%282017%29.pdf>
- **Title:** *NEMS Model Documentation 2017: Oil and Gas Supply Module*, February 2017,
  DOE/EIA-063(2017)
- **Location:** Appendix 2.C, "Decline Curve Analysis", page 166 (PDF page 173 of 282)

This is the authoritative model-documentation form of the same wording, and it adds the
symbol glossary. **Verbatim:**

> "A key assumption in evaluating the expected profitability of drilling a well is the
> estimated ultimate recovery (EUR) of the well. EIA uses an automated routine to analyze
> the production decline curve of shale and tight oil and gas wells. The general form of
> the decline curve is a hyperbolic function given by
> Q_t = Q_i / (1 + b ∗ D_i ∗ t)^(1/b), where
> Q_t = Production in month t; Q_i = Production rate at time 0; b = Hyperbolic parameter
> (degree of curvature of the line); D_i = Initial decline rate; and t = Month in
> production."

> "When the monthly decline rate falls to 0.8% (10% annual decline), the decline curve
> converts from the hyperbolic decline to an exponential decline."

Two things follow directly from this quotation:

1. **`D_i` is a monthly rate and `t` is a month.** The threshold is stated in the same time
   unit as the fitted parameters.
2. **The threshold is compared against a quantity of EIA's own curve.** "The monthly
   decline rate" for a hyperbolic is `D(t) = Di / (1 + b·Di·t)` — the same arithmetic
   quantity as the `Di` inside the equation. See §2.2.

The model documentation and the public page agree verbatim. The same document's Table 2.C-1
lists fitted `(Qi, Di, b)` triples for roughly 90 tight-oil plays and counties — for example
`Bakken Eastern Dunn, ND … Qi 463, Di 0.666, b 1.442` and `Wolfcamp Lea, NM … Qi 707, Di 0.333,
b 0.534`. A `Di` of `0.666` means 66.6 % **per month**, which is the right order of magnitude
for a Bakken initial decline and confirms the monthly, Arps-form reading of the parameters.

### 1.3 Third EIA page — the only one that puts the switch on an annual footing

- **URL:** <https://www.eia.gov/outlooks/aeo/grt.php>
- **Title:** *Oil and Natural Gas Resources and Technology*, AEO2018 "Issues in Focus",
  author Dana Van Wagener, release date 26 March 2018
- **Location:** Endnote 3

**Verbatim:**

> "Monthly production is fit to a decline curve for each well drilled with initial
> production in 2008 or later and that has at least four months of production data
> available. The mathematical form of the curve is initially hyperbolic, but it shifts to
> exponential when the annual decline rate reaches 10%."

This is the only EIA statement that states the switch annually. It says `10 %` and says
nothing about nominal or effective.

### 1.4 Sources checked and excluded

The *Drilling Productivity Report: Report Background and Methodological Overview*
(<https://www.eia.gov/petroleum/drilling/pdf/dpr_methodology.pdf>, August 2014) was read in
full and **does not contain the Arps terminal-switch rule at all** — the DPR is a rig-count /
LOESS model, not an Arps curve fit. It is not a source for this question and should not be
cited as one.

---

## 2. The convention and the exact threshold

### 2.1 The arithmetic

EIA printed the same threshold twice: `0.8 %` per month and `10 %` per year. Under the
Arps nominal convention these are **exactly the same number at two time scales**:

| step | value |
|---|---|
| `0.10 / 12` | `0.0083333` |
| as a percentage | `0.83333 %` |
| rounded to one decimal — what EIA printed | **`0.8 %`** |
| and back the other way: `0.0083333 × 12` | `0.100000`, i.e. **exactly `10.000 %`** |

That exactness is the first clue. The competing annualisations of a `0.8 %`/month decline
do not land on `10 %`:

| annualising a `0.8 %`/month decline | result |
|---|---|
| nominal, simple ratio `× 12` | `9.600 %/yr` |
| discrete nominal, `1 − (1 − d)^12` | `9.189 %/yr` |
| effective / continuous, `−12·ln(1 − d)` | `9.639 %/yr` |

And conversely, which monthly rate *is* `10 %`/yr:

| target `10 %/yr` | implied monthly nominal rate | prints as |
|---|---|---|
| **nominal** (`D_mo = D_yr/12`) | `0.10/12 = 0.0083333` (`0.8333 %`) | **`0.8 %`** |
| discrete nominal (`1 − 0.9^(1/12)`) | `0.0087416` (`0.8742 %`) | `0.9 %` — does not match |
| effective / continuous (`1 − e^(−0.1/12)`) | `0.0082987` (`0.8299 %`) | `0.8 %` — matches, approximately |

Read honestly: the printed monthly figure is *exactly* consistent with the nominal reading
and *approximately* consistent with the effective reading. Arithmetic narrows it to two
candidates; it does not by itself settle it. The structural argument below does.

### 2.2 The structural argument — the decisive one

EIA's threshold is stated as **"the monthly decline rate"** — that is, a quantity of the
curve EIA itself writes. For EIA's own hyperbolic, the instantaneous decline rate is
`D(t) = Di / (1 + b·Di·t)`, the derivative of `ln q` against time. That is the only natural
reading of "the monthly decline rate falls to 0.8 %" for a hyperbolic curve, and it is
**the same arithmetic quantity as the `Di`** that EIA labels "initial decline rate" and places
inside its equation.

A threshold can only be compared against `Di` if the two share a convention. EIA compares
`D(t) = Di/(1 + b·Di·t)` against `0.008`. Therefore the threshold is expressed in `Di`'s
convention.

What convention is `Di` in the Arps form `(1 + b·Di·t)^(1/b)`? It is the SPE-named **nominal
decline factor**. The primary statement of that naming is Wattenbarger, Waters and Rushing
(1996), who define the nominal decline factor as "the negative slope of the curve
representing the natural logarithm of the production rate q vs. time t", and note that it
"is the decline factor that is used in the various mathematical equations relating to
decline curve analysis". Independently, Blasingame's Texas A&M lecture notes write the Arps
exponential as `q = qi·exp(−Di·t)` — again `Di` is unambiguously a slope-of-`ln q` quantity,
not a period-over-period drop.

Both routes converge on the same place: the convention of `Di` inside EIA's own equation is
nominal, so EIA's threshold is nominal.

### 2.3 Threshold to implement

- **`TERMINAL_DECLINE_ANNUAL = 0.10`, nominal, per year.** Expose it as a parameter.
- Its monthly form is `0.0083333` — obtain it by dividing by 12, **not** by any `ln(1 + x)`
  conversion.
- `ln(1.10) = 0.0953102`/yr is the **effective** equivalent. It is needed only because the
  exponential tail is written in continuous form. Derive it inside the solver; never store
  it and never report it.

**One trap to name explicitly.** The `ln(1 + x)` transform does **not** commute with the time
unit: `12 × ln(1 + 0.10/12) = 0.0995856`, which is *not* `ln(1 + 0.10) = 0.0953102`. So
`D_eff` must be derived **after** the time unit is fixed, never scaled between time units.
Only the nominal rates scale by a simple ratio. This is the single most common bug in this
domain and the project conventions flag it as such.

---

## 3. Consequence for the implementation

This is background for the forecast module; it is recorded here so the threshold above is
used with the right mechanics.

**The switch time is where the instantaneous decline reaches the threshold.** Run the fitted
hyperbolic until `D(t) = TERMINAL_DECLINE_ANNUAL`, then continue on the exponential tail. With
`t` in years, nominal `Di` and nominal `D_tail = 0.10`:

- `t_switch = (Di/D_eff_tail − 1) / (b · Di)`, with `D_eff_tail = ln(1 + 0.10)`. Note the
  numerator needs the *effective* value even though `Di` and `D_tail` stay nominal — this is
  the one place the solver derives it.
- **The tail continues from the rate reached at the switch, never re-anchored to `qi`.** The
  rate at the switch is `q_switch = qi × (Di/D_eff_tail)^(−1/b)`, which is exact because
  `1 + b·Di·t_switch` equals `Di/D_eff_tail` at the switch.
- **The tail is exponential in the continuous form:** `q(t) = q_switch × exp(−D_eff_tail ×
  (t − t_switch))`. Because the tail's decline rate at the switch equals the hyperbolic's
  instantaneous rate there, `ln q` is **C1 across the switch** — only curvature changes, not
  the decline rate. A tail written as `(1 + D_tail·(t − t_switch))^(−1)` would introduce a
  spurious second-derivative jump and is not what a hyperbolic-to-exponential switch means.

Two guards that follow from the threshold: if `Di <= TERMINAL_DECLINE_ANNUAL` the well is
already at or below the terminal decline at `t = 0`, so there is no hyperbolic phase and the
curve is exponential from the start; and if `b == 0` the fitted curve already *is* the
exponential, so there is no switch.

Note also that for well-behaved `b < 1` plays the switch often lands beyond a 30-year
horizon, or arrives when the rate has already fallen to a few tenths of a bbl/d. Combined
with the economic-limit rule (EUR stops at the economic limit rate, not at zero), the
economic limit will usually bind **before** the terminal switch does. The `b > 1` cases are
where the switch is early enough to matter.

---

## 4. ADR-0001: CONFIRMED, not superseded

`docs/adr/0001-nominal-decline-is-canonical.md` commits this project to nominal decline as
the canonical `Di`, and makes its own validity conditional on this research:

> "We read the EIA source to confirm its exact convention before implementing the switch; if
> it turns out EIA uses effective decline, this ADR is superseded."

**The condition is not met, so the ADR stands as written.**

| the condition | what the evidence shows | result |
|---|---|---|
| "if it turns out EIA uses **effective** decline" | EIA's threshold is compared against `D(t) = Di/(1 + b·Di·t)` — the same arithmetic quantity as the `Di` inside EIA's own Arps equation. That convention is nominal. | condition **not met** |

Two supporting points, neither of which contradicts the ADR:

- The ADR states the threshold annually (10 %/yr); EIA states it monthly (0.8 %/month).
  These are the **same threshold at two time scales**, and under the nominal convention the
  conversion between them is a plain ratio — **not** a `ln(1 + x)` conversion. This is a
  refinement for the implementer, not a contradiction.
- The ADR's arithmetic is confirmed by the source: 10 % nominal ≈ 9.53 % effective
  (`ln(1 + 0.10)`), the ~5 % gap it describes.

---

## 5. What this evidence does **not** establish

Stated plainly, because a reader relying on this note needs to know where it stops.

1. **EIA never writes the words "nominal" or "effective."** Checked and confirmed absent from
   the curve-analysis page, OGSM Appendix 2.C, the DPR methodology document, and the DPR
   FAQ. The verdict rests on **arithmetic and internal consistency, not on a quotation that
   says "nominal."** No EIA document states this convention in those words.

2. **One residual alternative reading cannot be excluded from the text.** A reader could
   instead argue that EIA's *code* stores `10 %/yr` and prints a monthly equivalent converted
   via the effective relation, which also lands on `0.8 %`. That reading cannot be ruled out
   from the published text. It was not adopted because (a) it requires the threshold and `Di`
   to be in *different* conventions, which is internally incoherent, and (b) the exact
   `0.10/12 → 0.8333 % → "0.8 %"` identity is too clean to be coincidence. The evidence does
   not contradict the reading adopted here.

3. **The SPE 8428 quotations are second-hand.** OnePetro returns **HTTP 403** to direct
   fetches. The Wattenbarger, Waters and Rushing (1996) nominal-decline wording quoted in
   §2.2 was recovered through a search index, **not** from a first-hand fetch of the paper.
   Treat those words as second-hand. The verdict does not rest on them alone: the
   Blasingame equation-form evidence, also in §2.2, is independent of OnePetro.

4. **Arps (1945) is citable by reference only.** The only reachable copy is a scan with no
   text layer, so **no verbatim quotation can be taken from it**. Cite Arps (1945) by
   reference; never in quotation marks.

5. **The exact threshold is a one-decimal published figure.** EIA prints `0.8 %`, which is
   `0.8333 %` rounded. Implementing EIA's literal `0.008` yields `9.6 %/yr`, about 4 % below
   the `10 %` EIA also states. This note adopts `0.10`/yr nominal as the threshold, which is
   the value consistent with EIA's own annual figure; that choice is deliberate and the
   ~4 % alternative is recorded in §2.3 rather than hidden.

---

## References

1. **Arps, J. J. (1945).** "Analysis of Decline Curves." *Transactions of the AIME* **194**,
   228–232. — Origin of the exponential / hyperbolic / harmonic family and of the curvature
   exponent `b`. *Cited by reference only: the reachable scan has no text layer (§5.4).*
2. **U.S. Energy Information Administration.** "Production Decline Curve Analysis in the
   Annual Energy Outlook," <https://www.eia.gov/analysis/drilling/curve_analysis> — AEO2022
   edition, released 2023-03-16; discontinued. AEO2020 edition:
   <https://www.eia.gov/analysis/drilling/curve_analysis/2020/>
3. **U.S. Energy Information Administration (2017).** *NEMS Model Documentation 2017: Oil and
   Gas Supply Module*, DOE/EIA-063(2017), February 2017. Appendix 2.C, "Decline Curve
   Analysis", p. 166. <https://www.eia.gov/outlooks/aeo/nems/documentation/ogsm/pdf/m063%282017%29.pdf>
4. **Van Wagener, D.** "Oil and Natural Gas Resources and Technology." AEO2018 "Issues in
   Focus", release date 2018-03-26. Endnote 3.
   <https://www.eia.gov/outlooks/aeo/grt.php>
5. **Wattenbarger, R. A., Waters, G. B., and Rushing, J. A. (1996).** "Production Forecasting:
   Decline Curve Analysis." SPE 8428.
   <https://onepetro.org/spe/general-information/1996/Production-forecasting-decline-curve-analysis>
   — Authoritative statement of the nominal-vs-effective naming. *OnePetro returns HTTP 403
   to direct fetch; these quotations are search-index text, not a first-hand fetch (§5.3).*
6. **Blasingame, T. A.** "Lecture 8 — Decline-Curve Analysis for Gas Wells," Petroleum
   Engineering 613, Texas A&M University, 2016-04-13.
   <https://blasingame.engr.tamu.edu/z_zCourse_Archive/P613_16A/P613_16A_Lectures/20160413_P613_16A_Lec_08_%28DCA_Gas_Wells%29_%5BPDF%5D.pdf>
   — Writes the Arps exponential as `q = qi·exp(−Di·t)`, supporting the slope-of-`ln q`
   reading of `Di`. *This lecture never uses the words "nominal" or "effective", so it cannot
   itself be cited as evidence on that question; it is cited here for the equation form.*
7. **U.S. Energy Information Administration (2014).** *Drilling Productivity Report: Report
   Background and Methodological Overview*, August 2014.
   <https://www.eia.gov/petroleum/drilling/pdf/dpr_methodology.pdf> — **Checked and
   excluded**: contains no Arps terminal-switch rule (§1.4).