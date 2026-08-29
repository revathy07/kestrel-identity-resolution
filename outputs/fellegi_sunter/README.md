# Fellegi-Sunter MCT challenger outputs

Train from person-disjoint development labels only:

```bash
python -m src.modeling.fellegi_sunter train --development-labels outputs/scoring/labelled_development_set.csv.gz --output-dir outputs/fellegi_sunter
```

Apply the frozen empirical model without labels:

```bash
python -m src.modeling.fellegi_sunter score --pair-features outputs/scoring/scored_candidate_pairs.csv.gz --model outputs/fellegi_sunter/fs_model.json --output-dir outputs/fellegi_sunter
```

Release development and validation before the frozen test:

```bash
python -m src.evaluation.evaluate_scoring --scored-path outputs/fellegi_sunter/fs_scored_candidate_pairs.csv.gz --scoring-manifest outputs/fellegi_sunter/fs_manifest.json --output-dir outputs/fellegi_sunter --scope validation
```

The learned model, event table, manifests and compact evaluation reports are committed. The
204,547-row score file and labelled pair sets are deterministic local artifacts and remain
ignored.
