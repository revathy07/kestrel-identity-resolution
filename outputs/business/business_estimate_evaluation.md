# Phase 13 hidden-truth evaluation

**Count-range result: REVISE.** The frozen defensible range 304,896–333,000 does not contain the synthetic truth of 300,000 human entities.

## Estimate accuracy

The recommended estimate is **315,177**, an absolute error of **15,177** (5.0590%).
This diagnostic is opened after freezing; it is not an input to production scoring, traffic classification or Monte Carlo calibration.

## Observable automation detector

Record precision is **100.0000%** and recall is **100.0000%**. The all-members rule excludes **8,400** clusters: 8,400 pure-bot, 0 pure-human and 0 mixed-truth clusters.

## Internal QA policy audit

The observable QA policy excludes **1,500** clusters representing **1,500** hidden human entities. The truth map has no independent QA label, so this is a policy audit, not claimed QA-classifier precision.

## Isolation conclusion

The estimator manifest states that it did not read hidden person IDs or entity types. This evaluator is the only Phase 13 component that opens `person_map.csv`.
