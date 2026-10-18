"""Junior study engine (``hypotrail``): case contract, study state, and activities.

This package is the entry point of the junior workflow. It is isolated from the
legacy pilot: it imports none of ``mlkit.pilot``, ``drift``, ``ensemble``,
``automl``, ``monitor``, ``holdout``, ``gate``, ``run``, ``evaluate``,
``baselines``, ``quality``, or ``config``. In particular it never reads
``config.ROOT``: every function receives the study or case directory explicitly.
``framework/tests/study/test_isolation.py`` enforces these rules.

Modules: ``case`` (case contract), ``migrate`` (companion migration), ``errors``
(structured refusals), ``lock`` (writer lock and execution leases), ``store``
(``.hypotrail/`` persistence and the ``apply_command`` store), ``state`` (schema
``hypotrail.study/1`` and derived plan), and ``data`` (dataset loading with row keys).
The generic command core is ``mlkit.reliability.apply_command``, which imports no
other ``mlkit`` module. ``state``, ``store``, and ``lock`` import neither pandas nor
scikit-learn; ``data`` imports pandas only when a dataset is loaded.
"""
