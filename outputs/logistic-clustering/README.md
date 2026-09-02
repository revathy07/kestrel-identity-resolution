# Logistic clustering challenger outputs

This directory preserves the selected-logistic clustering run separately from the earlier
heuristic baseline while promotion is audited.

- `clustering_manifest.json` and `clustering_report.md` describe truth-free Rule 1 clustering.
- `cluster_evaluation.json` and `cluster_evaluation.md` open hidden truth only afterward.
- `cluster_comparison.json` and `cluster_comparison.md` apply explicit promotion gates against
  the heuristic baseline.
- The 420,000-row assignment file is deterministic and intentionally excluded from Git.
