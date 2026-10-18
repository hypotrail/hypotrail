# Use cases

Each case owns its data, provenance, business context, and preparation scripts. The reusable engine lives in `../framework/`.

| Case | Task | Role |
|---|---|---|
| [Bank Marketing](bank-marketing/README.md) | Binary subscription classification | First junior workflow acceptance case |
| [Auto MPG](auto-mpg/README.md) | Regression in mpg | Second case for adaptation checks |
| [Breast Cancer Wisconsin](breast-cancer-wdbc/README.md) | Binary malignant/benign classification | Generality check (M3); data copied from scikit-learn by `prepare.py`, not committed |
| [Diabetes progression](diabetes/README.md) | Regression without a time column | Generality check (M3); data copied from scikit-learn by `prepare.py`, not committed |

Current `registry.json`, `project.json`, and `results.json` files are tutorial contracts (Bank Marketing and Auto MPG only; the two scikit-learn cases have a generated `case.yaml` and no tutorial contract). Their data and results are real, but they do not represent future junior study state. Preserve provenance and never import tutorial choices as confirmed human decisions.

The tutorial preparation scripts (`prepare_bank.py`, `prepare_auto_mpg.py`) train models when explicitly executed; the `prepare.py` of the scikit-learn cases only copies data. Simply opening existing outputs does not train a model. The experimental runtime's `prepare_discovery.py` enriches tutorial contracts and is not the new workflow entry point.
