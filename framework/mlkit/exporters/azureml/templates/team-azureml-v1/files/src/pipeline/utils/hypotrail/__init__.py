"""Hypotrail support of this exported project (team-azureml-v1).

* ``errors``: the structured refusals (code, path, message, remediation).
* ``canonical``, ``projection``, ``mlflow_packaging``: byte copies of the generator's
  modules (their SHA-256 is in ``data/hypotrail/contracts/export-manifest.json``), so the
  project computes the same identities and packages a candidate the same way.
* ``contracts``: reads and verifies the contracts, the development plan and the checksums.
* ``config``: freezes the resolved Hydra configuration and refuses scientific changes.
* ``runtime_bridge``: imports ``hypotrail_runtime`` with a clear error when it is missing.
* ``steps``: the logic of the four steps, called by their ``main.py``.
"""
