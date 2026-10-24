"""The deployment snapshot ``hypotrail.deployment_snapshot/1`` (export spec §08, contract §6).

The export never reads the study's internal tables. It calls chantier A's
``read_export_source(study_path, expected_revision)``, which reads one consistent revision
without fitting and without any new exposure, and builds the snapshot from the returned
``ExportSource`` only. Until chantier A's function exists in this checkout, the export
refuses with ``optional_dependency_missing`` (there is no fallback reader): tests pass a
private test double through ``reader=``.

``ExportSource`` fields read here (contract v1 §6; the exact structure belongs to A, the
names below are the ones this consumer expects and are listed as an interface point to
confirm at merge in ``docs/handoff/AZUREML-EXPORT-V1.md``): ``study_id``, ``revision``,
``scientific_contracts.model_recipe``, ``scientific_contracts.data_contract``,
``decisions`` (confirmed ones), ``results`` (references with ``current``), ``validity``,
``development_plan``, ``predictor`` (``bundle_dir`` or null), ``limitations``, and the
optional ``case``, ``metrics``, ``conclusion``, ``development_data``. A Pydantic object is
read through ``model_dump(mode='json')``. The predictor's ``status`` and ``evidence_status``
and ``final_test.status`` decide what is exported: only a ``captured`` predictor (a current
capture of the confirmed selection) is transported, with the evidence status the study
records; a ``stale`` one is refused while the final test is sealed and left out (recipe
only) after the opening, except a capture whose choice only awaits re-confirmation in the
chat (``scientific_contracts.selection.capture``), which is refused with a remediation that
says so. A recipe selected at an earlier confirmation is accepted only under the engine's
rule: the captured configuration equals the confirmed one and the capture is current. The
bundle found at the recorded path must be the recorded predictor (same predictor id, and
recipe and data contract digests); another bundle is ``artifact_integrity_failed``. A
``hypotrail_runtime`` ``ContractError`` of the reader is answered as an export refusal
(:func:`from_contract_error`).
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from . import canonical as cj
from .errors import CODES, CONTRACT_ALIASES, ExportError

SCHEMA = 'hypotrail.deployment_snapshot/1'
PLAN_SCHEMA = 'hypotrail.development_plan/1'
SOURCE_MODULE = 'mlkit.contracts.export_source'
SOURCE_FUNCTION = 'read_export_source'
RUNTIME_MODULE = 'hypotrail_runtime'
RECIPE_SCHEMA = 'hypotrail.model_recipe/1'
DATA_CONTRACT_SCHEMA = 'hypotrail.data_contract/1'
RECIPE_KEYS = ('schema_version', 'task', 'family', 'parameters', 'features', 'feature_types',
               'preprocessing', 'target', 'seeds', 'output_contract', 'selection_reference',
               'method_contract_version', 'runtime_api_version')
DATA_CONTRACT_KEYS = ('schema_version', 'dataset_id', 'source_sha256', 'format', 'parser',
                      'columns', 'row_identity', 'exclusions', 'inference_policy')
DEVELOPMENT_ROLES = ('train', 'validation', 'development')
FOLD_PREFIX = 'fold_'
PREDICTOR_ROLES = ('development_fit', 'fold_fit', 'final_development_refit', 'rebuilt_candidate')


def _plain(value: Any) -> Any:
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    return value


def field(obj: Any, name: str, default: Any = ...) -> Any:
    """``obj[name]`` or ``obj.name``; ``contract_invalid`` when absent and no default."""
    obj = _plain(obj)
    if isinstance(obj, Mapping):
        if name in obj:
            return _plain(obj[name])
    elif hasattr(obj, name):
        return _plain(getattr(obj, name))
    if default is ...:
        raise ExportError('contract_invalid', f'The export source has no {name!r}.',
                          path=f'export_source.{name}',
                          remediation='Update the engine: read_export_source must return '
                                      'this field (contract v1 §6).')
    return default


def read_source(study, expected_revision: int, reader: Callable | None = None):
    """Chantier A's ``ExportSource`` of ``study`` at ``expected_revision``."""
    if reader is None:
        try:
            module = importlib.import_module(SOURCE_MODULE)
            reader = getattr(module, SOURCE_FUNCTION)
        except (ImportError, AttributeError) as error:
            raise ExportError('optional_dependency_missing',
                              'This engine has no read_export_source yet (chantier A, '
                              'contract v1 §6), so no study can be exported to Azure ML.',
                              path=f'{SOURCE_MODULE}.{SOURCE_FUNCTION}',
                              remediation='Use an engine version that ships '
                                          'read_export_source; nothing was read or written.'
                              ) from error
    try:
        source = reader(Path(study), expected_revision)
    except ExportError:
        raise
    except Exception as error:
        refusal = from_contract_error(error)
        if refusal is None:
            raise
        raise refusal from error
    revision = field(source, 'revision')
    if type(revision) is not int:
        raise ExportError('contract_invalid', 'The export source revision is not an integer.',
                          path='export_source.revision', remediation='Fix the engine.')
    if revision != expected_revision:
        raise ExportError('stale_revision',
                          f'The study is at revision {revision}, not {expected_revision}: read '
                          'it again before exporting; nothing was written.',
                          path='expected_revision', remediation='Pass the current revision.',
                          details={'expected_revision': expected_revision,
                                   'current_revision': revision})
    return source


def from_contract_error(error: BaseException) -> ExportError | None:
    """The export refusal of a ``hypotrail_runtime`` ``ContractError`` raised while the
    study is read (for example ``stale_revision``), or None for any other exception. The
    contract code, path and remediation are kept; a contract code the export does not
    answer with is reported as ``contract_invalid`` (``details.contract_code`` keeps it)."""
    try:
        from hypotrail_runtime.errors import ContractError
    except ImportError:
        return None
    if not isinstance(error, ContractError):
        return None
    export_code = CONTRACT_ALIASES.get(error.code, error.code)
    if export_code not in CODES:
        export_code = 'contract_invalid'
    details = {k: v for k, v in error.details.items()
               if k not in ('path', 'remediation', 'contract_code')}
    if error.issues:
        details['issues'] = error.issues
    out = ExportError(export_code, error.message, path=error.path or None,
                      remediation=error.remediation
                      or 'Read the study status again, then export; nothing was written.',
                      details=details)
    out.details['contract_code'] = error.code
    return out


def runtime(required_for: str):
    try:
        return importlib.import_module(RUNTIME_MODULE)
    except ImportError as error:
        raise ExportError('optional_dependency_missing',
                          f'hypotrail_runtime is needed to {required_for}.',
                          path=RUNTIME_MODULE,
                          remediation='Install the runtime distribution of the engine '
                                      '(chantier A) in this environment.') from error


# --- validation of the scientific contracts (the fields the export uses) ---------------

def _require(document: Any, keys: tuple, schema: str, where: str) -> dict:
    if not isinstance(document, Mapping):
        raise ExportError('contract_invalid', f'{where} is not a JSON object.', path=where,
                          remediation='Fix the engine output.')
    version = document.get('schema_version')
    if not isinstance(version, str) or not version.startswith(schema.rsplit('/', 1)[0] + '/'):
        raise ExportError('contract_invalid', f'{where} is not {schema}.',
                          path=f'{where}.schema_version', remediation='Fix the engine output.')
    if version != schema:
        raise ExportError('schema_version_unsupported',
                          f'{where} has version {version}; this exporter reads {schema}.',
                          path=f'{where}.schema_version',
                          remediation='Use an exporter that supports this version.')
    missing = [k for k in keys if k not in document]
    if missing:
        raise ExportError('contract_invalid', f'{where} misses required fields.', path=where,
                          remediation='Fix the engine output.', details={'missing': missing})
    try:
        return cj.normalise(document, where)
    except cj.CanonicalError as error:
        raise ExportError('contract_invalid', str(error), path=error.path,
                          remediation='Contract documents hold strict JSON values.') from error


def _check_recipe(recipe: dict, contract: dict) -> None:
    columns = {c.get('name'): c for c in contract['columns'] if isinstance(c, Mapping)}
    features = recipe['features']
    if not isinstance(features, list) or not features or \
            not all(isinstance(f, str) for f in features) or len(set(features)) != len(features):
        raise ExportError('contract_invalid', 'The recipe features are not a list of distinct '
                          'names.', path='model_recipe.features', remediation='Fix the recipe.')
    for name in features:
        column = columns.get(name)
        if column is None or column.get('role') != 'feature':
            raise ExportError('contract_invalid', f'Feature {name!r} is not a feature column '
                              'of the data contract.', path='model_recipe.features',
                              remediation='The recipe and data contract must agree.')
        if name not in recipe['feature_types']:
            raise ExportError('contract_invalid', f'Feature {name!r} has no type.',
                              path='model_recipe.feature_types', remediation='Fix the recipe.')
    target = recipe['target']
    column = columns.get(target.get('name')) if isinstance(target, Mapping) else None
    if column is None or column.get('role') != 'target':
        raise ExportError('contract_invalid', 'The recipe target is not the target column of '
                          'the data contract.', path='model_recipe.target.name',
                          remediation='The recipe and data contract must agree.')
    if recipe['task'] == 'binary' and target.get('positive_label') is None:
        raise ExportError('contract_invalid', 'A binary recipe names its positive label.',
                          path='model_recipe.target.positive_label', remediation='Fix the recipe.')


def _reconfirmed_capture(source, descriptor, predictor_status, contracts: Mapping,
                         selection: Mapping, revision: int, by_id: Mapping) -> bool:
    """Whether a recipe selected at an earlier confirmation is still the confirmed selection:
    the same rule as ``read_export_source`` (the engine's): the captured configuration
    equals the configuration confirmed now and the capture result is current. Only a
    captured bundle qualifies; another configuration confirmed after the capture never
    does."""
    state = contracts.get('selection')
    if not isinstance(state, Mapping) or predictor_status != 'captured' \
            or contracts.get('source') != 'captured_bundle' or state.get('capture') != 'selected':
        return False
    plan = field(source, 'development_plan', None)
    confirmed = plan.get('configuration') if isinstance(plan, Mapping) else None
    capture_rid = field(descriptor, 'capture_result_id', None)
    earlier = selection.get('revision')
    return (confirmed is not None
            and state.get('capture_configuration') == confirmed
            and state.get('confirmed_configuration') == confirmed
            and state.get('decision_id') == selection.get('decision_id')
            and state.get('decision_revision') == revision
            and state.get('capture_result_id') == capture_rid and capture_rid is not None
            and (by_id.get(capture_rid) or {}).get('current') is True
            and isinstance(earlier, int) and not isinstance(earlier, bool)
            and earlier <= revision)


def _same_predictor(descriptor, predictor: Mapping) -> None:
    """The bundle found at the recorded path is the predictor the capture recorded (and,
    through it, the one the final test evaluated): same predictor id, and the same recipe
    and data contract digests when the study records them. A self-consistent bundle put in
    its place is refused, never exported under the study's evidence."""
    expected = field(descriptor, 'predictor_id', None)
    manifest = predictor.get('manifest') or {}
    found = predictor.get('predictor_id')
    mismatched = []
    if not isinstance(expected, str) or not expected:
        raise ExportError('contract_invalid', 'The export source names no predictor id for its '
                          'captured predictor.', path='predictor.predictor_id',
                          remediation='Fix the engine: read_export_source names the captured '
                                      'predictor id.')
    if found != expected:
        mismatched.append('predictor_id')
    for key in ('recipe_sha256', 'data_contract_sha256'):
        recorded = field(descriptor, key, None)
        if recorded is not None and manifest.get(key) != recorded:
            mismatched.append(key)
    binding = predictor.get('binding') or {}
    final_rid = field(descriptor, 'final_result_id', None)
    if predictor.get('evidence_status') == 'evaluated' and (
            binding.get('predictor_id') != expected
            or (final_rid is not None and binding.get('final_result_id') != final_rid)):
        mismatched.append('evidence_binding')
    if mismatched:
        raise ExportError('artifact_integrity_failed', 'The bundle at the recorded path is not '
                          'the predictor the study captured and evaluated; nothing was '
                          'written.', path='predictor.bundle_dir',
                          remediation='Restore the captured bundle from a copy you trust (or '
                                      'capture again before opening the final test); never '
                                      'replace or edit a bundle.',
                          details={'reason': 'bundle_not_recorded_predictor',
                                   'mismatched': mismatched,
                                   'recorded_predictor_id': expected,
                                   'found_predictor_id': found})


@dataclass(frozen=True)
class Snapshot:
    """What the generator renders from: plain JSON documents, no live object."""

    document: dict              # hypotrail.deployment_snapshot/1
    snapshot_id: str
    recipe: dict
    data_contract: dict
    plan: dict                  # hypotrail.development_plan/1 (development keys only)
    recipe_sha256: str
    data_contract_sha256: str
    metrics: list
    predictor: dict | None      # {bundle_dir, manifest, bundle, binding, packages, ...}
    development_data: dict | None
    checks: list
    warnings: list


def _final_status(source) -> str | None:
    """The final test status of the source (``sealed``, ``opened``, ``absent``...)."""
    final = field(source, 'final_test', None)
    if not isinstance(final, Mapping):
        plan = field(source, 'development_plan', None)
        final = plan.get('final_test') if isinstance(plan, Mapping) else None
    status = final.get('status') if isinstance(final, Mapping) else None
    return status if isinstance(status, str) else None


def _evidence_status(study: Any, binding: str) -> str:
    """``evaluated`` only when the study's record and the bundle's binding both say so."""
    if study == 'evaluated' and binding == 'evaluated':
        return 'evaluated'
    if 'stale' in (study, binding):
        return 'stale'
    return 'unassessed'


def _refuse_without_recipe(source, predictor_status: str | None,
                           final_status: str | None) -> None:
    """Refuse an export whose source describes no recipe, with a remediation the junior can
    follow (or the reason none exists)."""
    limitations = [str(x) for x in (field(source, 'limitations', None) or [])]
    if predictor_status == 'not_applicable':
        remediation = ('This study was created before the final test and the model capture '
                       'existed: it has no selected model to export. Start a new study with '
                       'this engine to export a selected model to Azure ML.')
    elif final_status == 'absent':
        remediation = ('This study has no final test (it was created before the final test '
                       'existed): confirm the model choice in the chat (a model, not the '
                       'constant baseline), then export its recipe; no evaluated model can '
                       'be exported for it.')
    elif final_status == 'opened':
        remediation = ('The final test is opened, so the model can no longer be captured: '
                       'this selection has no exportable recipe (see details.limitations).')
    else:
        remediation = ('Confirm the model choice in the chat (a model, not the constant '
                       'baseline); for a tuned model, run hypotrail run predictor.capture '
                       'before opening the final test; then export.')
    raise ExportError('capability_not_supported', 'The study describes no recipe of a selected '
                      'model; nothing was written.', path='scientific_contracts.model_recipe',
                      remediation=remediation,
                      details={'reason': 'no_recipe', 'limitations': limitations})


def _plan(source_plan: Any, contract: dict) -> dict:
    """The development plan with development row keys only; the final test is metadata
    (status and row count), never keys or labels."""
    plan = _plain(source_plan)
    if not isinstance(plan, Mapping):
        raise ExportError('contract_invalid', 'The development plan is not an object.',
                          path='export_source.development_plan', remediation='Fix the engine.')
    partitions = []
    for i, part in enumerate(plan.get('partitions') or []):
        role = part.get('role') if isinstance(part, Mapping) else None
        where = f'development_plan.partitions[{i}]'
        if role == 'final_test':
            continue
        if not isinstance(role, str) or not (role in DEVELOPMENT_ROLES or
                                             (role.startswith(FOLD_PREFIX) and
                                              role[len(FOLD_PREFIX):].isdigit())):
            raise ExportError('capability_not_supported',
                              f'Partition role {role!r} is not replayed by this template.',
                              path=f'{where}.role',
                              remediation='Export a study whose plan uses train/validation or '
                                          'cross-validation folds.')
        keys = part.get('row_keys')
        if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys) \
                or len(set(keys)) != len(keys):
            raise ExportError('contract_invalid', 'A partition lists distinct string row keys.',
                              path=f'{where}.row_keys', remediation='Fix the engine.')
        partitions.append({'id': str(part.get('id') or role), 'role': role,
                           'row_keys': sorted(keys, key=_key_order),
                           'keys_sha256': cj.canonical_sha256(sorted(keys, key=_key_order)),
                           'membership_sha256': part.get('membership_sha256'),
                           'exposure_status': part.get('exposure_status')})
    if not partitions:
        raise ExportError('contract_invalid', 'The development plan has no development '
                          'partition.', path='development_plan.partitions',
                          remediation='Export a study whose split is confirmed.')
    partitions.sort(key=lambda p: (_role_order(p['role']), p['id']))
    development = sorted({k for p in partitions for k in p['row_keys']}, key=_key_order)
    final = next((p for p in plan.get('partitions') or []
                  if isinstance(p, Mapping) and p.get('role') == 'final_test'), None)
    final_keys = set(final.get('row_keys') or []) if final else set()
    if final_keys & set(development):
        raise ExportError('contract_invalid', 'A final-test row is listed as development.',
                          path='development_plan.partitions',
                          remediation='Fix the engine: the final test is disjoint.')
    final_meta = plan.get('final_test') if isinstance(plan.get('final_test'), Mapping) else {}
    protocol = plan.get('protocol_id')
    if not isinstance(protocol, str) or not protocol:
        raise ExportError('contract_invalid', 'The development plan names no protocol.',
                          path='development_plan.protocol_id', remediation='Fix the engine.')
    out = {
        'schema_version': PLAN_SCHEMA,
        'protocol_id': protocol,
        'dataset_id': contract['dataset_id'],
        'source_sha256': contract['source_sha256'],
        'row_identity': contract['row_identity'],
        'partitions': partitions,
        'development_keys_sha256': cj.canonical_sha256(development),
        'n_development_rows': len(development),
        'final_test': {'status': final_meta.get('status', 'unknown'),
                       'n_rows': final_meta.get('n_rows', len(final_keys) if final else None),
                       'labels_included': False, 'row_keys_included': False},
        'keys_sha256_rule': 'sha256 of the canonical JSON of the sorted row keys',
    }
    # How many records the engine read in the source file (development, final test and any
    # excluded row): materialize refuses a file that splits into another number of records.
    n_records = plan.get('n_source_records')
    if n_records is not None:
        if not isinstance(n_records, int) or isinstance(n_records, bool) or \
                n_records < len(development):
            raise ExportError('contract_invalid', 'The development plan counts fewer source '
                              'records than development rows.',
                              path='development_plan.n_source_records',
                              remediation='Fix the engine.')
        out['n_source_records'] = n_records
    out['keys_sha256'] = cj.canonical_sha256({p['id']: p['row_keys'] for p in partitions})
    return out


def _key_order(key: str):
    digits = key[1:] if key[:1].isalpha() else key
    return (0, int(digits), key) if digits.isdigit() else (1, 0, key)


def _role_order(role: str) -> int:
    return {'development': 0, 'train': 1, 'validation': 2}.get(role, 3)


def build(source, *, template_capabilities: list, verify_predictor: Callable | None = None
          ) -> Snapshot:
    """The snapshot of an ``ExportSource``; refuses an export that would not be faithful.

    ``verify_predictor(bundle_dir, recipe, data_contract)`` returns the predictor record
    (see :mod:`mlkit.exporters.azureml.artifact`); it is called only when the source
    names a captured predictor."""
    descriptor = field(source, 'predictor', None)
    predictor_status = field(descriptor, 'status', 'captured') if descriptor else None
    final_status = _final_status(source)
    contracts = field(source, 'scientific_contracts')
    selection_state = (contracts.get('selection') if isinstance(contracts, Mapping) else None)
    selection_state = selection_state if isinstance(selection_state, Mapping) else {}
    if predictor_status == 'stale' and selection_state.get('capture') == 'awaiting_reconfirmation':
        # The model choice is on hold after its confirmation: the capture (and the final
        # evaluation that scored it) is kept, the choice only has to be confirmed again.
        raise ExportError('contract_invalid', 'The model choice awaits re-confirmation in the '
                          'chat, so no selection is confirmed now; nothing was written.',
                          path='predictor.status',
                          remediation='Confirm the same model choice again in the chat (the '
                                      'captured predictor and its final evaluation are kept); '
                                      'that makes the export possible again. Then export.',
                          details={'reason': 'selection_awaits_reconfirmation',
                                   'decision_id': selection_state.get('decision_id'),
                                   'capture_result_id': field(descriptor, 'capture_result_id',
                                                              None),
                                   'limitations': [str(x) for x in
                                                   (field(source, 'limitations', None) or [])]})
    if predictor_status == 'stale' and final_status == 'sealed':
        # Before the opening a capture of the confirmed selection is still possible: the
        # export neither ships the superseded model nor drops it silently.
        raise ExportError('model_not_captured', 'The captured predictor is not the current '
                          'confirmed selection (another configuration confirmed after it, or '
                          'a change since the capture that made it not current); the export '
                          'does not substitute it and nothing was written.', path='predictor.status',
                          remediation='Run hypotrail run predictor.capture again, so the '
                                      'capture is the confirmed selection, then export.',
                          details={'reason': 'capture_not_current_selection',
                                   'capture_result_id': field(descriptor, 'capture_result_id',
                                                              None)})
    if not isinstance(contracts, Mapping) or contracts.get('model_recipe') is None:
        _refuse_without_recipe(source, predictor_status, final_status)
    recipe = _require(field(contracts, 'model_recipe'), RECIPE_KEYS, RECIPE_SCHEMA,
                      'model_recipe')
    contract = _require(field(contracts, 'data_contract'), DATA_CONTRACT_KEYS,
                        DATA_CONTRACT_SCHEMA, 'data_contract')
    _check_recipe(recipe, contract)
    checks, warnings = [], []
    capability = next((c for c in template_capabilities
                       if c['task'] == recipe['task'] and c['family'] == recipe['family']
                       and c['output_kind'] == recipe['output_contract'].get('kind')), None)
    if capability is None:
        raise ExportError('capability_not_supported',
                          f'This template does not qualify the {recipe["task"]} family '
                          f'{recipe["family"]!r} with output '
                          f'{recipe["output_contract"].get("kind")!r}; the selected model is '
                          'kept and not replaced.', path='model_recipe.family',
                          remediation='Export a study whose selected model is in the '
                                      'template support matrix, or qualify this family first.',
                          details={'supported': template_capabilities})
    for name in ('calibration', 'intervals', 'threshold_policy'):
        if (recipe.get('extensions') or {}).get(f'hypotrail.{name}') is not None or \
                recipe.get(name) is not None:
            raise ExportError('capability_not_supported',
                              f'The recipe carries a {name} capability, which this template '
                              'does not qualify for Azure ML; it is not removed to export.',
                              path=f'model_recipe.{name}',
                              remediation='Export without requesting this capability only if '
                                          'the study selected a model without it.')
    checks.append({'id': 'family_supported', 'status': 'passed'})
    decisions = [_plain(d) for d in field(source, 'decisions')]
    confirmed = {d.get('decision_id'): d for d in decisions
                 if isinstance(d, Mapping) and d.get('status') == 'confirmed'}
    selection = recipe['selection_reference']
    if selection.get('decision_id') not in confirmed:
        raise ExportError('contract_invalid', 'The selected model rests on a decision that is '
                          'not confirmed; a proposal is not a decision.',
                          path='model_recipe.selection_reference.decision_id',
                          remediation='Confirm the model choice in the chat, then export.',
                          details={'reason': 'selection_not_confirmed'})
    decision = confirmed[selection.get('decision_id')]
    revision = decision.get('revision')
    results = [_plain(r) for r in field(source, 'results')]
    by_id = {r.get('result_id'): r for r in results if isinstance(r, Mapping)}
    if not isinstance(revision, int) or isinstance(revision, bool) or (
            revision != selection.get('revision')
            and not _reconfirmed_capture(source, descriptor, predictor_status, contracts,
                                         selection, revision, by_id)):
        raise ExportError('contract_invalid', 'The recipe was selected by another confirmation '
                          'than the one in force; the export does not substitute a model and '
                          'nothing was written.',
                          path='model_recipe.selection_reference.revision',
                          remediation='Capture the confirmed model choice again (hypotrail run '
                                      'predictor.capture) before the final test is opened, '
                                      'then export.',
                          details={'reason': 'selection_not_current_decision',
                                   'selection_revision': selection.get('revision'),
                                   'decision_revision': decision.get('revision')})
    checks.append({'id': 'selection_confirmed', 'status': 'passed'})
    for rid in selection.get('evidence_ids') or []:
        item = by_id.get(rid)
        if item is None or item.get('current') is not True:
            raise ExportError('contract_invalid', 'A result the selection rests on is not '
                              'current.', path='model_recipe.selection_reference.evidence_ids',
                              remediation='Run the stale activity again and confirm, then '
                                          'export.',
                              details={'reason': 'selected_result_not_current', 'result_id': rid})
    checks.append({'id': 'selected_results_current', 'status': 'passed'})
    plan = _plan(field(source, 'development_plan'), contract)
    metrics = field(source, 'metrics', None) or []
    if not isinstance(metrics, list) or not all(isinstance(m, str) for m in metrics):
        raise ExportError('contract_invalid', 'The metrics are not a list of names.',
                          path='export_source.metrics', remediation='Fix the engine.')
    recipe_sha = cj.canonical_sha256(recipe)
    contract_sha = cj.canonical_sha256(contract)
    predictor = None
    # A's ExportSource always describes the predictor; only a bundle makes it captured
    # (a stale capture no longer describes the chosen configuration: it is not exported).
    if descriptor and field(descriptor, 'bundle_dir', None) and predictor_status == 'captured':
        bundle_dir = field(descriptor, 'bundle_dir')
        if verify_predictor is None:
            raise ExportError('optional_dependency_missing', 'No predictor verifier.',
                              path='predictor', remediation='Internal: pass verify_predictor.')
        predictor = verify_predictor(Path(bundle_dir), recipe, contract)
        _same_predictor(descriptor, predictor)
        checks += predictor['checks']
        warnings += predictor['warnings']
        # The study's own record decides the evidence status; the binding beside the bundle
        # is an editable file and can only lower it.
        evidence = _evidence_status(field(descriptor, 'evidence_status', None),
                                    predictor['evidence_status'])
        if evidence != predictor['evidence_status']:
            warnings.append('evidence_binding_disagrees_with_study')
        predictor = {**predictor, 'evidence_status': evidence}
    else:
        checks.append({'id': 'predictor_captured', 'status': 'missing',
                       'detail': 'No captured predictor: the recipe is exported, the evaluated '
                                 'model is not (artifact_status missing).'})
        warnings.append('artifact_missing')
    case = field(source, 'case', None) or {}
    conclusion = field(source, 'conclusion', None)
    limitations = [str(x) for x in (field(source, 'limitations', None) or [])]
    validity = field(source, 'validity', None) or {}
    development_data = field(source, 'development_data', None)
    document = {
        'schema_version': SCHEMA,
        'study_id': str(field(source, 'study_id')),
        'study_revision': field(source, 'revision'),
        'case': {k: case.get(k) for k in ('id', 'title') if isinstance(case, Mapping)},
        'task': recipe['task'],
        'selected': {'decision_id': selection.get('decision_id'),
                     'revision': selection.get('revision'),
                     'evidence_ids': list(selection.get('evidence_ids') or []),
                     'family': recipe['family'], 'parameters': recipe['parameters']},
        'decisions': sorted(({'decision_id': d, 'value': confirmed[d].get('value')}
                             for d in confirmed), key=lambda d: d['decision_id']),
        'results': sorted(({'result_id': r.get('result_id'), 'activity': r.get('activity'),
                            'current': r.get('current')} for r in results),
                          key=lambda r: str(r['result_id'])),
        'evaluation_plan': {'protocol_id': plan['protocol_id'],
                            'keys_sha256': plan['keys_sha256'],
                            'roles': [p['role'] for p in plan['partitions']],
                            'n_development_rows': plan['n_development_rows'],
                            'final_test': plan['final_test']},
        'evidence_state': validity,
        'conclusion': conclusion,
        'limitations': limitations,
        'metrics': metrics,
        'recipe_sha256': recipe_sha,
        'data_contract_sha256': contract_sha,
        'predictor': None if predictor is None else {
            'predictor_id': predictor['predictor_id'], 'role': predictor['role'],
            'evidence_status': predictor['evidence_status'],
            'artifact_status': predictor['artifact_status']},
    }
    try:
        document = cj.normalise(document, 'snapshot')
    except cj.CanonicalError as error:
        raise ExportError('contract_invalid', str(error), path=error.path,
                          remediation='The engine returned a non-JSON value.') from error
    return Snapshot(document, cj.canonical_sha256(document), recipe, contract, plan,
                    recipe_sha, contract_sha, metrics, predictor,
                    _plain(development_data) if development_data else None, checks, warnings)
