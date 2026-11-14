# Local ML

Specification: [ML-01](../docs/app-ml/ML-01-problem-and-evaluation.md).
Commands, artifact schema, fixtures and limits: [ML-02](../docs/app-ml/ML-02-feature-and-training.md).

Install local dependencies from `ml/requirements.txt`, separately from Airflow.
Run commands from repository root: `python3 -m ml.cli --help`.

```bash
python3 -m pytest ml/tests -q
```

The CLI uses synthetic fixtures only. Scores are smoke-test diagnostics, not evidence of model quality. Generated data/models belong in a new temporary directory or ignored `ml/runs/`, not the source fixture directory.
