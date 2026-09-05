# Kestrel Identity Resolution Control Room

This is the optional Phase 14A stakeholder dashboard. It presents the already generated
technical and business results; it does not score raw records, alter MCT thresholds, write
clusters or retrain a model.

## Run locally

From the repository root:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run dashboard/app.py
```

Streamlit prints a local URL, normally `http://localhost:8501`.

## Views

- **Executive brief:** customer-count bridge, range, source volumes and review workload.
- **Technical audit:** blocking reduction, model comparison, MCT decisions, Rule 1 results
  and source-pair recall.
- **MCT decision lab:** educational scoring of prepared event combinations using the exact
  frozen logistic coefficients and fixed thresholds.
- **Methods & limits:** assessment rules, project design choices, failed approaches and
  production limitations.

## Data boundary

[`data_loader.py`](data_loader.py) uses a fixed allow-list of compact aggregate artifacts
under `outputs/`. It refuses inconsistent counts and an evaluation that claims hidden
identifiers were emitted. It never loads:

- raw source-system files;
- `person_map.csv`;
- row-level candidate, score, cluster or classification files; or
- any customer/person identifier.

The hidden-truth evaluation contributes aggregate synthetic-test measurements only. Every
view labels the evidence as synthetic and avoids claiming guaranteed production precision.

## Decision-lab limitation

The lab is an explanation aid. An arbitrary event combination may be outside the training
distribution, and the model intercept reflects the already-blocked candidate population.
Rule 2 and blocking happen before scoring; Rule 1 happens afterward. The lab cannot execute
any merge.
