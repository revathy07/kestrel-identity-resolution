# Recall improvement plan

## Purpose

This phase identifies where the selected logistic MCT loses true matches before proposing
new features. It protects the released `v1.0.0` baseline and does not lower the assessment's
0.88 auto-merge threshold, change the 0.62 review threshold, weaken Rule 2, or bypass Rule 1.

The analyzer reads only `labelled_development_set.csv.gz` and
`labelled_validation_set.csv.gz`. The frozen test is deliberately excluded from the code
path. All outputs are aggregate: no source-record key, physical ordinal or hidden person ID
is published.

## Reproduce the analysis

```powershell
python -m src.evaluation.analyze_recall_gaps `
  --labelled-dir outputs/logistic `
  --output-dir outputs/recall-analysis
```

The one-command pipeline also runs this diagnostic after the three-model comparison:

```powershell
python scripts/run_pipeline.py
```

## Measured findings

| Development + validation result | Value |
|---|---:|
| True candidate matches | 93,799 |
| Automatically merged true pairs | 70,148 |
| True pairs routed to review | 12,642 |
| True pairs left separate | 11,009 |
| Automatic recall | 74.7854% |
| Assisted recall | 88.2632% |
| Recall opportunity already in review | 13.4778 percentage points |

The gap is concentrated in ticketing relationships:

| Source pair | Share of unresolved development/validation matches |
|---|---:|
| App users + ticketing | 72.4705% |
| Social logins + ticketing | 26.0623% |
| Ticketing + ticketing | 1.4460% |

These three groups account for approximately 99.98% of the unresolved true candidate pairs.
The dominant pattern is a name-and-city agreement accompanied by an email conflict. That
pattern occurs in both genuine matches and non-matches, so it cannot safely be promoted by
lowering a threshold.

Below the review band, 10,266 of 11,009 true pairs (93.2509%) are app/ticketing or
social/ticketing pairs with an exact device agreement but conflicting email and name. A
device-only promotion would be unsafe because the hard-negative design deliberately includes
different people sharing university and kiosk devices. Recovering these cases safely requires
new independent evidence or source-specific corroboration, not a larger device weight.

## Recommended experiment order

1. Build source-aware ticketing interactions using the existing evidence and conflict
   vocabulary.
2. Add conservative continuous name and email similarity, with independent corroboration
   required before automatic merging.
3. Evaluate event/city/time consistency for ticketing records where the source semantics
   support it.
4. Add address or postcode similarity only for source pairs where both fields actually
   exist; ticketing itself does not currently supply them.
5. Prioritize high-yield review relationships and collect double-adjudicated labels for a
   future training set.
6. Compare the logistic baseline with one interpretable nonlinear challenger, such as an
   explainable boosting or gradient-boosted tree model.

## Promotion gates

A recall challenger is eligible only when all of these remain true:

- zero observed validation false auto-merges;
- no explicit hard negative auto-merges;
- automatic recall exceeds the selected baseline;
- assisted recall exceeds the selected baseline;
- no mixed-person components after transitive clustering;
- Rule 1 accepts size 12 and quarantines size 13 or greater in full;
- every Rule 2 value continues to carry zero matching weight;
- review and candidate volume remain operationally explainable; and
- final confirmation occurs on a new, untouched synthetic seed.

Validation is now being used for diagnosis, so it may guide a development experiment but
cannot provide the sole final performance claim for a new release. The existing frozen test
also remains a `v1.0.0` characterization set rather than becoming a repeatedly tuned target.

## Outputs

- `recall_gap_analysis.json`: machine-readable metrics and isolation evidence.
- `recall_gap_analysis.md`: mentor-readable interpretation.
- `recall_gap_by_source_pair.csv`: source-level concentration of missed matches.
- `unresolved_patterns.csv`: aggregate evidence/conflict signatures.
- `score_proximity.csv`: match prevalence around the fixed decision bands.

The analysis does not implement or promote new matching features. That separation prevents
an exploratory finding from silently changing the verified production-style result.

## Experiment 1 result: ticketing source context

The first v1.1 experiment added three declared source-pair contexts and all 57 context-by-
base-event interactions to the existing 190-term logistic design. The resulting 250-term
challenger used development labels only for fitting and the current validation partition for
the predeclared comparison against `v1.0`.

| Validation model | False auto-merges | Auto recall | Assisted recall | Decision |
|---|---:|---:|---:|---|
| v1.0 logistic baseline | 0 | 74.1027% | 88.0763% | Retain |
| Context L2=0.0001 | 225 | 91.2299% | 91.8531% | Reject: unsafe |
| Context L2=0.001 | 131 | 86.8561% | 91.8531% | Reject: unsafe |
| Context L2=0.01 | 5 | 72.7249% | 91.8006% | Reject: unsafe and lower auto recall |
| Context L2=0.1 | 0 | 43.9330% | 87.8886% | Reject: worse recall |

Source context made the synthetic ticketing patterns easier to recognize but was not an
independent identity signal. The validation gate behaved as intended: no candidate combined
zero false auto-merges with improved automatic and assisted recall. No challenger model was
published, no cluster was built and no frozen-test or new-seed confirmation was opened.

The next justified experiment is not a larger source-context model. It is conservative
ticketing corroboration from attributes with a defensible identity meaning. Device-only
pairs with conflicting email and name remain unresolved unless an additional identifier can
distinguish a returning person from two people sharing a device.
