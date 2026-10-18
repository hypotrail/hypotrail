"""Junior study engine (``hypotrail``): case contract, study state, and activities.

This package is the entry point of the junior workflow. It is isolated from the
legacy pilot: it imports none of ``mlkit.pilot``, ``drift``, ``ensemble``,
``automl``, ``monitor``, ``holdout``, ``gate``, ``run``, ``evaluate``,
``baselines``, ``quality``, or ``config``. In particular it never reads
``config.ROOT``: every function receives the study or case directory explicitly.
``framework/tests/study/test_isolation.py`` enforces these rules.
"""
