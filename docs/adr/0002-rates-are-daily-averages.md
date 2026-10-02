# Production rates are daily averages, not monthly volumes

Real production CSVs report `qo`/`qw`/`qg` inconsistently — some as the volume produced
during the month (bbl/month), others as the average daily rate (bbl/day). We canonicalize
on **daily-average rates**. The lift-candidate screen (`qo < 100`) is the well-known
artificial-lift heuristic at ~100 bbl/day and is meaningless as a monthly volume, and
fitting `qi`/`Di` requires a rate consistent with the time axis. Accepting monthly
volumes would silently break both. The loader rejects or normalizes ambiguous inputs
rather than guessing.