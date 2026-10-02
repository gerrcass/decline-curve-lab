# The EUR ends at a configurable economic limit rate

The brief asked "when does the well die" and separately asked for a EUR. We define the
end of a well as a configurable **economic limit rate** (`q_min`, the oil rate below
which producing stops paying), and the EUR integrates only until the fitted curve reaches
it. Integrating a decline curve toward zero would attribute uneconomic production to the
well and overstate EUR. "Dead" is defined as "below the economic limit rate"; the exact
rate depends on oil price, operating cost, and lift method, so it is a parameter rather
than a hardcoded constant.