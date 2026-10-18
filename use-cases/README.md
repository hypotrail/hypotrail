# Use cases

Each case owns its data, provenance, business context, and preparation scripts. The reusable engine lives in `../framework/`.

| Case | Task | Role |
|---|---|---|
| [Bank Marketing](bank-marketing/README.md) | Binary subscription classification | First junior workflow acceptance case |
| [Auto MPG](auto-mpg/README.md) | Regression in mpg | Second case for adaptation checks |

Current `registry.json`, `project.json`, and `results.json` files are tutorial contracts. Their data and results are real, but they do not represent future junior study state. Preserve provenance and never import tutorial choices as confirmed human decisions.

Preparation scripts train models when explicitly executed. Simply opening existing outputs does not train a model. The experimental runtime's `prepare_discovery.py` enriches tutorial contracts and is not the new workflow entry point.
