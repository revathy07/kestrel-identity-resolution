# Generated outputs

This directory is reserved for reproducible profiling, candidate-generation, matching,
clustering, and evaluation outputs. Compact, assessment-relevant summaries may be committed;
large reproducible intermediate tables remain ignored.

The dataset compliance validator currently writes its reports here:

```bash
python src/validate_generated_data.py --data-dir data/generated --output-dir outputs
```

Do not place source datasets or hand-edited results in this directory.

Phase 1 outputs and their publication policy are documented in
[`profiling/README.md`](profiling/README.md).

Phase 4 normalization outputs are documented in
[`normalization/README.md`](normalization/README.md).

Phase 5 production blocking and isolated evaluation outputs are documented in
[`blocking/README.md`](blocking/README.md).

Phase 6 production MCT scoring and frozen labelled evaluation outputs are documented in
[`scoring/README.md`](scoring/README.md).

Phase 7 transitive clustering, Rule 1 quarantine and isolated cluster evaluation outputs are
documented in [`clustering/README.md`](clustering/README.md).
