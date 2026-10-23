"""Optional and base library adapters of the engine (library integration v1).

Workstream A: ``pandera_validation`` (base), ``scipy_bootstrap`` (base),
``evidently_diagnostics`` (extra ``diagnostics``), ``mapie_uncertainty`` (extra
``uncertainty``). Workstream B: ``mlflow_packaging``. Optional backends are imported lazily,
inside the functions that need them; importing this package imports none of them.
"""
