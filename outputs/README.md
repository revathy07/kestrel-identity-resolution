# Generated outputs

This directory is reserved for reproducible profiling, candidate-generation, matching,
clustering, and evaluation outputs. Generated files are ignored by Git until the downstream
pipeline defines which compact, assessment-relevant artifacts should be published.

The dataset compliance validator currently writes its reports here:

```bash
python src/validate_generated_data.py --data-dir data/generated --output-dir outputs
```

Do not place source datasets or hand-edited results in this directory.
