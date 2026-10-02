# Spec #1 reconciled with the domain model

**Date:** 2026-10-02
**Issue:** #2 — Fix glossary/ADR divergence in spec #1
**Spec edited:** #1 — "P1: Well Decline & Production Surveillance — proyecto educativo (MVP)"

Spec #1 was written before the domain model existed. `GLOSSARY.md` and ADR-0001/0002/0003
landed afterwards (commit `978d719`) and contradicted the spec on three points. This note
records the divergences and the resolution applied to the spec body, so that the
implementation tickets (#3–#10) all build one coherent set of conventions.

Rule going forward: where spec #1 and the domain model disagree, **the domain model wins**
(that precedence is now stated in the spec's Further Notes).

## Divergence 1 — Units were "unit-agnostic"

| | |
|---|---|
| **Spec said** | "Unidades agnósticas: las tasas se tratan como *unidades por periodo* (registros mensuales). Se documenta el supuesto; las reglas con umbrales (`qo < 100`) usan las unidades del CSV tal cual." |
| **Domain model says** | ADR-0002: every rate in the CSV is a **daily average** — `qo`/`qw` in bbl/d, `qg` in scf/d. A production period is one month whose rate is a daily average, never a monthly volume. The loader rejects or normalizes ambiguous inputs rather than guessing. |
| **Resolution** | The "unit-agnostic" bullet is replaced by a "Unidades (ADR-0002)" bullet: daily-average rates, explicit units per column, thresholds compared against bbl/d as-is, `water_cut` a decimal in [0, 1]. |

Why it matters: the lift screen `qo < 100` is the well-known ~100 bbl/d artificial-lift
heuristic and is meaningless as a monthly volume, and fitting `qi`/`Di` needs a rate
consistent with the time axis. Accepting monthly volumes would silently break both.

Corrected passages: "Alcance del pronóstico" (now states bbl/d, the production-period time
axis with `t = 0` at the well's first production period, and a single conversion of the time
axis to years at the boundary); the units bullet itself; the "Unidades agnósticas" phrase
deleted; the surveillance-rules bullet (`qo < 100 bbl/d`); user stories 13 and 14; and the
Testing Decisions boundary bullet (`qo = 100` bbl/d).

## Divergence 2 — Nominal vs effective `Di`

| | |
|---|---|
| **Spec said** | "cambio hiperbólica→exponencial al 10% anual (convención EIA)" and user story 11: "cuando la declinación anual **efectiva** llega al 10%" — neither says nominal or effective consistently. |
| **Domain model says** | ADR-0001: **nominal is the canonical `Di`**, in nominal %/year. `D_eff = ln(1 + Di)` is derived only inside the continuous exponential solver, never stored or reported. Confirmed by the EIA research note (`docs/research/eia-terminal-decline-convention.md`, ticket #4): EIA's switch is 10 %/yr **nominal** = `0.10/12 = 0.008333`/month, which is exactly the "0.8 %/month" EIA prints. ADR-0001's supersession clause is therefore **not** triggered. |
| **Resolution** | The "Cambio terminal" bullet becomes "Declinación terminal (convención EIA, ADR-0001)" and names the exact threshold: `terminal_decline_annual = 0.10` nominal/yr ≡ `0.008333` nominal/month ≡ the EIA's printed "0.8%/mes"; the solver's effective equivalent is `ln(1.10) = 0.0953102`/yr, derived internally only. The exponential tail continues **from the rate reached at the switch**, never re-anchored to `qi`. |

The two conventions differ by ~5% at the 10% level and the gap compounds across a
multi-decade EUR, so this is not cosmetic. One trap is called out explicitly in the spec:
nominal rates scale between time units by a plain ratio (`Di_mes = Di_año / 12`) but
effective rates do not (`12·ln(1+0.10/12) ≠ ln(1+0.10)`).

Corrected passages: Solution; user story 11 (dropped "efectiva"); the `forecast(...)`
contract; the modules bullet; the Testing Decisions terminal-decline bullet; the EIA entry
in Further Notes; and a new "Parámetros derivados" bullet stating where `Di` is stored and
that `D_eff` is never reported.

## Divergence 3 — Where the EUR ends

| | |
|---|---|
| **Spec said** | "EUR: integral del modelo hasta que la tasa cruza el límite económico `q_min` (parámetro configurable con default documentado), con un horizonte máximo (p. ej. 30 años)". The Problem Statement asks "cuándo *muere*" and the Testing Decisions call it "until the well dies", with no default. |
| **Domain model says** | ADR-0003: the EUR integrates **from `t = 0` until the fitted curve reaches the economic limit rate `q_min`**, never toward zero — integrating to zero would credit uneconomic production. "Dead" is defined as *below the economic limit rate*; abandonment is the decision, not the rate. `q_min` is a parameter, not a hardcoded constant. |
| **Resolution** | The EUR bullet now says exactly that, and documents `q_min = 1.0` bbl/d as the project default with a 30-year / 360-month horizon cap; EUR stops at whichever comes first. |

**Default `q_min = 1.0` bbl/d.** Rationale recorded in the spec: it is ~1% of the 100 bbl/d
lift-screening threshold, i.e. a plausible rate for a mature well that has already lost
interest to artificial lift, and it keeps EUR numbers in the same order of magnitude as the
rest of the project. It is a parameter rather than a constant because the real value depends
on oil price, operating cost and lift method — all of which are Out of Scope, so the spec
cannot derive it, only parameterize it.

Corrected passages: the EUR bullet; the `eur(...)` contract (now
`eur(fit, q_min=1.0, max_horizon_months=360) -> float`, in bbl); user story 13; the modules
bullet; and a new Testing Decisions EUR bullet covering both cutoffs separately.

## Vocabulary alignment (GLOSSARY `_Avoid_` lists)

Beyond the three divergences, these terms were corrected to the glossary's canonical
vocabulary, without rewriting the user stories wholesale:

- "registro" → **periodo de producción** (user stories 3 and 4, and the surveillance-rules
  bullet's "el último registro de cada pozo"). The glossary lists record/row/sample as
  avoided.
- "cambio terminal" / "punto de cambio" → **declinación terminal** (the glossary avoids
  "switch point", "cutoff rate", "hyperbolic cap", "b-cutoff").
- "muerto"/"abandono" now defined explicitly as a **rate**, not a decision.
- `candidate_lift` described as a **lift candidate** screening flag for engineering review,
  never a recommendation.
- "cambio hiperbólica→exponencial al 10%" annotated as **nominal** wherever it appears.

### Deliberately left alone

- **Problem Statement**: keeps "cuándo *muere*" as plain-language framing of the learning
  goal. The EUR and glossary now define that term precisely, so the casual phrasing is
  defined rather than wrong.
- **`water_cut` as a column/identifier name**: the glossary's canonical identifier is `fw`,
  but renaming it would touch the CSV schema and every ticket that references the column.
  Out of scope for a reconciliation; units and the decimal range are now stated instead.
- **`qi` and `Di` left un-qualified in user stories 6, 7 and 20**: those stories are about
  recovering parameters, and the units convention is stated once centrally in
  Implementation Decisions rather than repeated per story.

## Applying the edit safely

The spec body is ~14 KB with Markdown, accents and code spans, so it was edited through a
file, never a shell-quoted string:

```
gh issue view 1 --json body --jq .body > /tmp/opencode/spec-body-1-orig.md
# edit /tmp/opencode/spec-body-1.md, then
diff -u /tmp/opencode/spec-body-1-orig.md /tmp/opencode/spec-body-1.md   # review
gh issue edit 1 --body-file /tmp/opencode/spec-body-1.md
gh issue view 1 --json body --jq .body > /tmp/opencode/spec-body-1-readback.md
diff -u /tmp/opencode/spec-body-1.md /tmp/opencode/spec-body-1-readback.md
```

The readback diff is clean: the only difference is the single trailing newline GitHub
appends to every issue body. All content — Markdown, accents, `≠`/`·`/`→`/`∈`, code spans —
is byte-identical.