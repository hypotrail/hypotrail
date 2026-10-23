"""The packaging extension point (CONTRAT-COMMUN-v1 §6), implemented by workstream B.

The runtime never imports a packaging library. A packager is injected into
:func:`hypotrail_runtime.capture_predictor`; it reads the verified native bundle, writes
its package under ``packages/<format>/`` and returns a ``hypotrail.package_descriptor/1``;
``verify`` returns a ``hypotrail.parity_result/1`` computed on the bundle's parity rows. It
never fits and never reads labels. The first format is ``mlflow_pyfunc``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Mapping, Protocol, runtime_checkable

from .contracts import PackageDescriptor, ParityResult


@runtime_checkable
class ArtifactPackager(Protocol):
    format: str

    def package(self, native_bundle_dir: Path, output_dir: Path,
                parity_spec: Mapping) -> PackageDescriptor | Mapping: ...

    def verify(self, native_bundle_dir: Path, package_dir: Path,
               parity_spec: Mapping) -> ParityResult | Mapping: ...
