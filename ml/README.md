# Local ML

Specification: [ML-01](../docs/app-ml/ML-01-problem-and-evaluation.md).
Commands, artifact schema, fixtures and limits: [ML-02](../docs/app-ml/ML-02-feature-and-training.md).
Data readiness and evidence gates: [ML-03 audit](../docs/app-ml/ML-03-readiness-audit.md).

Install local dependencies from `ml/requirements.txt`, separately from Airflow.
Run commands from repository root: `python3 -m ml.cli --help`.

```bash
python3 -m pytest ml/tests -q
```

Build/train/evaluate use synthetic fixtures only. Scores are smoke-test diagnostics, not evidence of model quality. The `audit` command checks readiness without training; its ClickHouse source reports unavailable until APP-07 implements it, with no fixture fallback. Generated data/models/reports belong in a new temporary directory or ignored `ml/runs/`, not the source fixture directory.
