# Nominal decline is the canonical Di

Arps (1945) and the EIA curve-analysis convention express the decline rate and the
10%/yr terminal threshold as *nominal* decline, while much of modern decline-curve
literature works in *effective* (continuous) decline. The two differ by roughly 5% at
the 10% level (`D_eff = ln(1 + D_nom)`, so 10% nominal ≈ 9.53% effective) and the gap
compounds across a multi-decade EUR. We chose **nominal as the canonical `Di`** and
define the terminal-decline switch in nominal terms to stay coherent with the source
material; effective decline is derived only inside the continuous exponential solver
and is never stored or reported. We read the EIA source to confirm its exact convention
before implementing the switch; if it turns out EIA uses effective decline, this ADR is
superseded.