"""The closed registry of model families (CONTRAT-COMMUN-v1 §2, §5).

Each family lists its task, its parameters (name, JSON type, constraint) and whether the
runtime is *qualified* to export it. A family not in the registry, an unknown parameter or
a parameter of the wrong type is refused: there is no fallback. A known family that is not
qualified (the boosting families of the engine) is refused at fit and capture with
``capability_not_supported``; it is never replaced by a qualified one.

The estimators reproduce :func:`mlkit.classical.pipeline` and :func:`mlkit.study.fit._fit_predict`
exactly: ``LogisticRegression(max_iter=1000, random_state=seed)`` with the engine's solver,
tolerance and ``C``; ``LinearRegression()``; ``Ridge(alpha)``.
"""
from __future__ import annotations

from typing import Any, Mapping

from .errors import ContractError

# name -> (python types, check, description). bool is never accepted for a number.
_POSITIVE = (lambda v: v > 0, 'a positive number')
_ANY = (lambda v: True, 'any value of its type')

FAMILIES: dict[str, dict] = {
    'linear': {'task': 'regression', 'qualified': True,
               'estimator': 'sklearn.linear_model.LinearRegression',
               'parameters': {}},
    'ridge': {'task': 'regression', 'qualified': True,
              'estimator': 'sklearn.linear_model.Ridge',
              'parameters': {'alpha': ((int, float), *_POSITIVE)}},
    'logistic': {'task': 'binary', 'qualified': True,
                 'estimator': 'sklearn.linear_model.LogisticRegression',
                 'parameters': {'C': ((int, float), *_POSITIVE),
                                'solver': ((str,), *_ANY),
                                'tol': ((int, float), *_POSITIVE),
                                'max_iter': ((int,), *_POSITIVE)}},
    # Known to the engine (WP-F1), not qualified for export in v1.
    'ebm': {'task': None, 'qualified': False, 'estimator': 'interpret.glassbox',
            'parameters': None},
    'hgb': {'task': None, 'qualified': False,
            'estimator': 'sklearn.ensemble.HistGradientBoosting*', 'parameters': None},
}
QUALIFIED = tuple(name for name, f in FAMILIES.items() if f['qualified'])
REQUIRED_SEEDS = {'logistic': ('estimator',)}


def parameter_issues(task: str, family: str, parameters: Mapping[str, Any]) -> list[dict]:
    spec = FAMILIES.get(family)
    if spec is None:
        return [{'path': 'family', 'message': f'{family!r} is not a registered family',
                 'known': sorted(FAMILIES)}]
    if spec['parameters'] is None:
        return []           # refused as not qualified where it matters (fit, capture)
    issues = []
    if spec['task'] != task:
        issues.append({'path': 'family', 'message': f'{family} is a {spec["task"]} family'})
    for name, value in parameters.items():
        if name not in spec['parameters']:
            issues.append({'path': f'parameters/{name}',
                           'message': f'{family} has no parameter {name!r}'})
            continue
        types, check, what = spec['parameters'][name]
        if isinstance(value, bool) or not isinstance(value, types) or not check(value):
            issues.append({'path': f'parameters/{name}', 'message': f'{name} is {what}'})
    return issues


def require_qualified(family: str) -> None:
    spec = FAMILIES.get(family)
    if spec is None or not spec['qualified']:
        raise ContractError(
            'capability_not_supported',
            f'The family {family!r} is not qualified for the predictor runtime v1; only '
            f'{", ".join(QUALIFIED)} are.', path='family',
            remediation='Keep the chosen model and report the export as unavailable; the '
                        'runtime never substitutes another family.',
            details={'family': family, 'qualified': list(QUALIFIED)})


def estimator(family: str, parameters: Mapping[str, Any], seeds: Mapping[str, int]):
    require_qualified(family)
    from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
    if family == 'linear':
        return LinearRegression()
    if family == 'ridge':
        return Ridge(alpha=float(parameters['alpha']))
    if 'estimator' not in seeds:
        raise ContractError('contract_invalid', 'A logistic recipe records its estimator seed.',
                            path='seeds/estimator', remediation='Record seeds.estimator.')
    model = LogisticRegression(max_iter=int(parameters.get('max_iter', 1000)),
                               random_state=int(seeds['estimator']))
    if parameters.get('solver') is not None:
        model.set_params(solver=str(parameters['solver']))
    if parameters.get('tol') is not None:
        model.set_params(tol=float(parameters['tol']))
    if parameters.get('C') is not None:
        model.set_params(C=float(parameters['C']))
    return model
