# Rejected ticketing-aware challenger

This directory preserves the compact evidence for the first post-`v1.0` recall experiment.
The 250-term logistic design adds declared ticketing source contexts and context-by-event
interactions.

- `logistic_candidates.json` contains four development-trained L2 candidates.
- `logistic_coefficients.csv` records every fitted coefficient.
- `logistic_validation.json` and `.md` record the rejection decision.

No selected model, full candidate scores, clusters or frozen-test evaluation are published.
Every candidate failed either the zero-false-auto-merge gate or the requirement to improve
both automatic and assisted recall over `v1.0`.
