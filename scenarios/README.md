# Scenario Packages

Each validated or preview-ready scenario lives in a separate directory.

- `catalog.json`: machine-readable scenario index.
- `<scenario_id>/scenario_meta.json`: card and maturity metadata.
- `data/`: candidate pool and test conditions.
- `rules/`: deterministic constraints and priors.
- `evidence/`: structured evidence and paper metadata.
- `bundle/`: data consumed by the website.
- `runs/`: Agent round-by-round logs when available.
- `validation/`: baselines, ablation and reproduction results.

The directory structure is shared across scenarios; `data_level` in metadata controls which UI modules are enabled.
