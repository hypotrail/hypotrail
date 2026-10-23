"""``hypotrail export azureml`` (chantier B): a study as a team-azureml-v1 project.

Modules: :mod:`.command` (the command), :mod:`.snapshot` (the consumer of chantier A's
``read_export_source``), :mod:`.artifact` (the captured predictor), :mod:`.profile` (the
destination profile), :mod:`.render` (the deterministic generator), :mod:`.layout` (the
versioned template and AZ-STRUCT-02), :mod:`.writer` (atomic publication), and the
standalone modules copied into the project: :mod:`.canonical`, :mod:`.projection`,
:mod:`.transfer`, :mod:`.azure_yaml`.
"""
from .command import SCHEMA, export_azureml  # noqa: F401
