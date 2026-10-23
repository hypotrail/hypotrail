"""Computation contexts and their identity (CONTRAT-COMMUN-v1 §4, spec L-02, L-03).

A computation's reusable identity (:func:`computation_id`) is the canonical digest of its
scientific projection: the inputs, the partitions with their memberships, the decisions
used, the method contract version, the code fingerprint, the runtime version, the backend
and the versions of the engines *this method actually calls*
(:data:`METHOD_DEPENDENCIES`). It excludes the activity id (a run, not a question) and the
full environment lock, which is recorded for audit only: a new version of a package the
method does not call leaves the identity unchanged; a new version of a backend it calls
gives a new identity, even if its numbers happen to agree.

A method whose dependency is not installed has no identity (``optional_dependency_missing``):
an incomplete environment never inherits a known proof.
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Callable, Iterable, Mapping

from hypotrail_runtime import RUNTIME_API_VERSION, canonical
from hypotrail_runtime.contracts import ComputationContext, parse
from hypotrail_runtime.errors import ContractError

# The distributions whose code computes each method's numbers (numerical components
# included). Anything else in the environment does not enter the identity.
METHOD_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    'predictor.fit': ('numpy', 'pandas', 'scikit-learn', 'scipy', 'hypotrail-runtime'),
    'bootstrap.scipy_percentile': ('numpy', 'scipy'),
    'bootstrap.legacy_random': (),         # pure Python random.Random, no third-party engine
    'diagnostics.evidently': ('evidently', 'numpy', 'pandas', 'scipy'),
    'validation.pandera': ('pandera', 'pandas'),
    'uncertainty.mapie_risk': ('mapie', 'numpy', 'scikit-learn', 'scipy'),
    'uncertainty.mapie_split_conformal': ('mapie', 'numpy', 'scikit-learn'),
}
IDENTITY_EXCLUDED = ('activity_id', 'environment_lock_sha256')


def installed_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def semantic_dependencies(method: str,
                          lookup: Callable[[str], str | None] = installed_version) -> list[dict]:
    if method not in METHOD_DEPENDENCIES:
        raise ContractError('capability_not_supported', f'Unknown method {method!r}.',
                            path='method', remediation='Use a registered method.',
                            details={'known': sorted(METHOD_DEPENDENCIES)})
    out, missing = [], []
    for name in METHOD_DEPENDENCIES[method]:
        found = lookup(name)
        if found is None:
            missing.append(name)
        else:
            out.append({'distribution': name, 'version': found})
    if missing:
        raise ContractError('optional_dependency_missing',
                            f'{method} needs {", ".join(missing)}, which is not installed.',
                            path='semantic_dependencies',
                            remediation='Install the extra that provides it (diagnostics or '
                                        'uncertainty); the base workflow does not need it.',
                            details={'method': method, 'missing': missing})
    return out


def build(*, method: str, activity_id: str, study_id: str, expected_revision: int,
          code_fingerprint: str, protocol_id: str | None = None,
          decision_refs: Iterable[str] = (), input_refs: Iterable[Mapping] = (),
          partition_refs: Iterable[Mapping] = (), backend: Mapping | None = None,
          method_contract_version: str = 'hypotrail.method/1',
          environment_lock_sha256: str | None = None,
          lookup: Callable[[str], str | None] = installed_version) -> ComputationContext:
    doc = {'schema_version': 'hypotrail.computation_context/1', 'activity_id': activity_id,
           'study_id': study_id, 'expected_revision': int(expected_revision),
           'protocol_id': protocol_id, 'decision_refs': sorted(decision_refs),
           'input_refs': [dict(r) for r in input_refs],
           'partition_refs': [dict(r) for r in partition_refs],
           'code_fingerprint': code_fingerprint, 'runtime_version': RUNTIME_API_VERSION,
           'backend': dict(backend) if backend else None,
           'method_contract_version': method_contract_version,
           'semantic_dependencies': semantic_dependencies(method, lookup),
           'environment_lock_sha256': environment_lock_sha256,
           'extensions': {'hypotrail.method': method}}
    return parse(ComputationContext, doc)


def identity_projection(context: ComputationContext) -> dict:
    doc = context.model_dump(mode='json')
    return {k: v for k, v in doc.items() if k not in IDENTITY_EXCLUDED}


def computation_id(context: ComputationContext) -> str:
    return canonical.scientific_id(identity_projection(context))
