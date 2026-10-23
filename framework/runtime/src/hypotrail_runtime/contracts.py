"""Shared contracts v1 (CONTRAT-COMMUN-v1 §2–§7): strict Pydantic models.

Pydantic is the authority for the scientific schemas; the JSON schemas in
``hypotrail_runtime/schemas/`` are generated from these models (``python -m
hypotrail_runtime.schemas``) and versioned with them.

Rules common to every document:

* ``schema_version`` is the literal ``hypotrail.<type>/1``; an unknown major version is
  refused with ``schema_version_unsupported`` before any other check;
* strict types: the string ``"3"`` or ``true`` never satisfies an integer, ``1`` never a
  boolean; NaN and infinities are refused everywhere (an undefined value is ``null`` with
  its reason);
* unknown fields are refused, except under ``extensions``: a mapping whose keys are
  namespaced (``<namespace>.<name>``, lower case) and whose values are JSON;
* structure is checked by the model; meaning (a feature listed in its types, the target
  outside the features, a positive label for a binary task, ...) by :func:`semantic_issues`
  and the ``validate_*`` functions, separately. A valid structure never confirms a
  decision.
"""
from __future__ import annotations

import math
import re
from typing import Annotated, Any, Literal, Mapping, Optional, Type, TypeVar, Union

from pydantic import (BaseModel, ConfigDict, Field, JsonValue, StrictBool, StrictFloat,
                      StrictInt, StrictStr, StringConstraints, ValidationError, model_validator)

from . import canonical
from .errors import ContractError, from_pydantic

SHA256 = Annotated[str, StringConstraints(strict=True, pattern=r'^[0-9a-f]{64}$')]
NAME = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=512)]
NAMESPACED = Annotated[str, StringConstraints(
    strict=True, pattern=r'^[a-z][a-z0-9_-]*(\.[a-z0-9_-]+)+$')]
RELPATH = Annotated[str, StringConstraints(
    strict=True, min_length=1, max_length=512,
    pattern=r'^[A-Za-z0-9_@+-][A-Za-z0-9._@+-]*(/[A-Za-z0-9_@+-][A-Za-z0-9._@+-]*)*$')]
# Each segment starts with a letter, a digit, "_", "@", "+" or "-": no "..", no absolute
# path, no backslash, no hidden file.
JsonScalar = Union[StrictBool, StrictInt, StrictFloat, StrictStr, None]
Extensions = dict[NAMESPACED, JsonValue]

SCHEMA_PREFIX = 'hypotrail.'
_SCHEMA_RE = re.compile(r'^hypotrail\.([a-z_]+)/(\d+)$')


def _finite(value: Any, path: str = '') -> None:
    """Refuse NaN and infinities anywhere (Pydantic's JSON mode would print them null)."""
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f'non-finite number at {path or "<root>"}; use null with a reason')
    if isinstance(value, Mapping):
        for k, v in value.items():
            _finite(v, f'{path}/{k}')
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _finite(v, f'{path}/{i}')


class Contract(BaseModel):
    """Base of every v1 contract model."""
    model_config = ConfigDict(strict=True, extra='forbid', frozen=True, allow_inf_nan=False,
                              validate_default=True)

    @model_validator(mode='after')
    def _no_non_finite(self):
        _finite(self.model_dump(mode='python'))
        return self

    def canonical(self) -> bytes:
        return canonical.dumps(self)

    def digest(self) -> str:
        return canonical.scientific_id(self)


class Part(Contract):
    """A nested object of a contract (no schema_version of its own)."""


# --- ModelRecipe (§2) -----------------------------------------------------------------------

Task = Literal['regression', 'binary']
SemanticType = Literal['numeric', 'category', 'boolean']
PhysicalType = Literal['float64', 'int64', 'bool', 'string']


class FeatureType(Part):
    semantic: SemanticType
    physical: PhysicalType


PreprocessingOperation = Literal[
    'category_as_text', 'special_value_indicator', 'missing_indicator', 'rare_category',
    'cap_quantiles', 'signed_log', 'numeric_median_impute_scale',
    'categorical_mode_impute_onehot']


class PreprocessingStep(Part):
    operation: PreprocessingOperation
    version: StrictInt = Field(ge=1)
    parameters: dict[NAME, JsonValue]


class Target(Part):
    name: NAME
    unit: Optional[StrictStr]
    positive_label: JsonScalar


class OutputContract(Part):
    kind: Literal['regression_point', 'binary_score']
    columns: list[NAME] = Field(min_length=1)
    unit: Optional[StrictStr]
    positive_label: JsonScalar


class SelectionReference(Part):
    decision_id: NAME
    revision: StrictInt = Field(ge=0)
    evidence_ids: list[NAME]


class ModelRecipe(Contract):
    schema_version: Literal['hypotrail.model_recipe/1']
    task: Task
    family: NAME
    parameters: dict[NAME, JsonScalar]
    features: list[NAME] = Field(min_length=1)
    feature_types: dict[NAME, FeatureType]
    preprocessing: list[PreprocessingStep]
    target: Target
    seeds: dict[NAME, StrictInt]
    output_contract: OutputContract
    # null: no confirmed decision selected this recipe (a development candidate); a
    # recipe never carries an unconfirmed decision.
    selection_reference: Optional[SelectionReference]
    method_contract_version: NAME
    runtime_api_version: NAME
    extensions: Extensions = Field(default_factory=dict)


# --- DataContract (§3) ----------------------------------------------------------------------

class Parser(Part):
    encoding: NAME
    # One character, or ``whitespace`` (runs of blanks, the case contract's ``sep``).
    delimiter: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=16)]
    header: StrictBool
    quotechar: Optional[Annotated[str, StringConstraints(strict=True, min_length=1,
                                                          max_length=1)]]
    na_values: list[StrictStr]
    decimal: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1)] = '.'


class ColumnSpec(Part):
    name: NAME
    physical_type: PhysicalType
    semantic_type: SemanticType
    nullable: StrictBool
    allowed_values: Optional[list[JsonScalar]]
    role: Literal['feature', 'target', 'key', 'auxiliary']


class RowIdentity(Part):
    kind: Literal['stable_key', 'source_position']
    columns: list[NAME]
    source_hash_required: StrictBool


class Exclusion(Part):
    rule: NAME
    justification: NAME


class Conversion(Part):
    column: NAME
    source: NAME
    target: PhysicalType
    rule: NAME


class InferencePolicy(Part):
    required_columns: list[NAME]
    extra_columns: Literal['reject', 'ignore']
    conversions: list[Conversion]
    canonical_order: list[NAME]
    unknown_categories: Literal['reject', 'predictor_handles']


class DataContract(Contract):
    schema_version: Literal['hypotrail.data_contract/1']
    dataset_id: NAME
    source_sha256: SHA256
    materialization_sha256: Optional[SHA256] = None
    format: Literal['csv', 'dataframe']
    parser: Parser
    columns: list[ColumnSpec] = Field(min_length=1)
    row_identity: RowIdentity
    exclusions: list[Exclusion]
    inference_policy: InferencePolicy
    extensions: Extensions = Field(default_factory=dict)

    def column(self, name: str) -> ColumnSpec | None:
        return next((c for c in self.columns if c.name == name), None)

    def features(self) -> list[str]:
        return [c.name for c in self.columns if c.role == 'feature']


# --- ComputationContext (§4) ----------------------------------------------------------------

class InputRef(Part):
    id: NAME
    sha256: SHA256
    role: NAME


class PartitionRef(Part):
    id: NAME
    membership_sha256: SHA256
    role: Literal['train', 'validation', 'development', 'fold_train', 'fold_validation',
                  'calibration', 'final_test', 'monitoring', 'parity']
    exposure_status: Literal['unseen', 'reserved', 'exposed', 'consumed']


class Distribution(Part):
    distribution: NAME
    version: NAME


class ComputationContext(Contract):
    schema_version: Literal['hypotrail.computation_context/1']
    activity_id: NAME
    study_id: NAME
    expected_revision: StrictInt = Field(ge=0)
    protocol_id: Optional[NAME]
    decision_refs: list[NAME]
    input_refs: list[InputRef]
    partition_refs: list[PartitionRef]
    code_fingerprint: SHA256
    runtime_version: NAME
    backend: Optional[Distribution]
    method_contract_version: NAME
    semantic_dependencies: list[Distribution]
    environment_lock_sha256: Optional[SHA256]
    extensions: Extensions = Field(default_factory=dict)


# --- PredictorArtifact, bundle, evidence binding (§5) ---------------------------------------

class PayloadFile(Part):
    relative_path: RELPATH
    size_bytes: StrictInt = Field(ge=0)
    sha256: SHA256


class RuntimeRef(Part):
    api_version: NAME
    distribution: NAME
    version: NAME
    wheel_relative_path: Optional[RELPATH]
    wheel_sha256: Optional[SHA256]


class EnvironmentRef(Part):
    python: NAME
    platform: NAME
    semantic_dependencies: list[Distribution]
    lock_relative_path: Optional[RELPATH]
    lock_sha256: Optional[SHA256]


class TrainingScope(Part):
    role: Literal['development_fit', 'fold_fit', 'final_development_refit',
                  'rebuilt_candidate']
    dataset_id: NAME
    membership_sha256: SHA256
    protocol_id: Optional[NAME]


class PredictorArtifact(Contract):
    """The content manifest of a predictor. ``predictor_id`` is the artifact id: the
    SHA-256 of this manifest's canonical content without ``predictor_id`` itself."""
    schema_version: Literal['hypotrail.predictor_artifact/1']
    predictor_id: SHA256
    recipe_sha256: SHA256
    data_contract_sha256: SHA256
    input_contract_sha256: SHA256
    output_contract: OutputContract
    native_format: Literal['sklearn_pickle/1']
    payload_files: list[PayloadFile] = Field(min_length=1)
    runtime: RuntimeRef
    environment: EnvironmentRef
    training_scope: TrainingScope
    code_fingerprint: SHA256
    extensions: Extensions = Field(default_factory=dict)


class Tolerance(Part):
    rtol: StrictFloat = Field(ge=0)
    atol: StrictFloat = Field(ge=0)
    exact: list[NAME]


class ParitySpec(Part):
    features_path: RELPATH
    expected_outputs_path: RELPATH
    sha256s: dict[RELPATH, SHA256]
    origin: Literal['synthetic', 'authorized_development']
    tolerance: Tolerance
    n_rows: StrictInt = Field(ge=1)


class OptionalPackage(Part):
    format: NAME
    artifact_id: SHA256
    relative_path: RELPATH
    manifest_sha256: SHA256


class PredictorBundle(Contract):
    schema_version: Literal['hypotrail.predictor_bundle/1']
    predictor_id: SHA256
    recipe_path: RELPATH
    data_contract_path: RELPATH
    predictor_manifest_path: RELPATH
    parity: ParitySpec
    optional_packages: list[OptionalPackage]
    evidence_binding_path: Optional[RELPATH]
    # Every immutable file of the bundle except this manifest and the evidence binding.
    files: list[PayloadFile] = Field(min_length=1)
    extensions: Extensions = Field(default_factory=dict)


class EvidenceBinding(Contract):
    schema_version: Literal['hypotrail.evidence_binding/1']
    predictor_id: SHA256
    final_result_id: Optional[NAME]
    study_revision: StrictInt = Field(ge=0)
    decision_refs: list[NAME]
    protocol_id: Optional[NAME]
    evaluation_context_id: Optional[NAME]
    status: Literal['evaluated', 'unassessed', 'stale']
    extensions: Extensions = Field(default_factory=dict)


# --- packaging extension (§6, implemented by workstream B) -------------------------------

class ParityResult(Contract):
    schema_version: Literal['hypotrail.parity_result/1']
    status: Literal['ok', 'failed']
    n_rows: StrictInt = Field(ge=0)
    max_abs_diff: Optional[StrictFloat]
    max_rel_diff: Optional[StrictFloat]
    exact_mismatches: StrictInt = Field(ge=0)
    tolerance: Tolerance
    reason: Optional[StrictStr]
    extensions: Extensions = Field(default_factory=dict)


class PackageDescriptor(Contract):
    schema_version: Literal['hypotrail.package_descriptor/1']
    format: NAME
    artifact_id: SHA256
    predictor_id: SHA256
    files: list[PayloadFile] = Field(min_length=1)
    signature: dict[NAME, JsonValue]
    environment: dict[NAME, JsonValue]
    parity_result: ParityResult
    extensions: Extensions = Field(default_factory=dict)


# --- adapter results (§7) -------------------------------------------------------------------

Status = Literal['ok', 'not_applicable', 'insufficient_data', 'failed']


class Method(Part):
    name: NAME
    version: NAME
    parameters: dict[NAME, JsonValue]


class AdapterResult(Contract):
    result_id: SHA256
    status: Status
    reason: Optional[StrictStr]
    context: Optional[ComputationContext]
    backend: Optional[Distribution]
    method: Method
    warnings: list[StrictStr]
    artifact_refs: list[NAME]
    extensions: Extensions = Field(default_factory=dict)

    @model_validator(mode='after')
    def _reason_when_not_ok(self):
        if self.status != 'ok' and not self.reason:
            raise ValueError('a result that is not ok states its reason')
        return self


class DiagnosticCheck(Part):
    id: NAME
    family: Literal['data_quality', 'marginal_distribution', 'relationship', 'performance']
    column_or_pair: list[NAME]
    reference_partition: Optional[NAME]
    current_partition: NAME
    n_reference: Optional[StrictInt]
    n_current: StrictInt
    statistic_name: Optional[NAME]
    statistic_value: Optional[StrictFloat]
    p_value: Optional[StrictFloat]
    adjusted_p_value: Optional[StrictFloat]
    effect_size: Optional[StrictFloat]
    threshold: Optional[StrictFloat]
    comparison: Optional[Literal['lt', 'le', 'gt', 'ge']]
    alert: Optional[StrictBool]
    status: Status
    reason: Optional[StrictStr]

    @model_validator(mode='after')
    def _alert_needs_ok(self):
        if self.status != 'ok' and self.alert is not None:
            raise ValueError('a check that was not computed has alert null')
        if self.status == 'ok' and self.alert is not None and (
                self.threshold is None or self.comparison is None):
            raise ValueError('an alert states its threshold and comparison')
        return self


class DiagnosticResult(AdapterResult):
    schema_version: Literal['hypotrail.diagnostic_result/1']
    checks: list[DiagnosticCheck]
    alert: Optional[StrictBool]


class IntervalBound(Part):
    row: StrictInt = Field(ge=0)
    low: Optional[StrictFloat]
    high: Optional[StrictFloat]


class UncertaintyResult(AdapterResult):
    schema_version: Literal['hypotrail.uncertainty_result/1']
    target_quantity: NAME
    assumptions: list[StrictStr]
    eligibility: dict[NAME, JsonValue]
    calibration_ref: Optional[NAME]
    predictor_id: Optional[SHA256]
    confidence_level: Optional[StrictFloat]
    coverage_level: Optional[StrictFloat]
    risk_target: Optional[StrictFloat]
    selection_rule: Optional[StrictStr]
    valid_thresholds: Optional[list[StrictFloat]]
    selected_threshold: Optional[StrictFloat]
    interval_bounds: Optional[list[IntervalBound]]
    undefined_replicates: Optional[StrictInt]


# --- export source (engine side, read by workstream B) ---------------------------------------

class ExportDecision(Part):
    decision_id: NAME
    status: Literal['confirmed', 'reconfirm_required']
    value: JsonValue
    revision: StrictInt = Field(ge=0)
    basis: Optional[StrictStr]


class ExportResultRef(Part):
    slot: NAME
    result_id: NAME
    activity: NAME
    current: StrictBool
    reason: Optional[JsonValue]


class ExportPredictor(Part):
    status: Literal['captured', 'not_captured', 'stale', 'not_applicable']
    predictor_id: Optional[SHA256]
    capture_result_id: Optional[NAME]
    bundle_dir: Optional[StrictStr]
    recipe_sha256: Optional[SHA256]
    data_contract_sha256: Optional[SHA256]
    profile: Optional[NAME]
    packages: list[NAME]
    evidence_status: Literal['evaluated', 'unassessed', 'stale']
    final_result_id: Optional[NAME]


class ExportSource(Contract):
    """The read-only view of a study at one revision (CONTRAT-COMMUN-v1 §6,
    ``read_export_source``). It holds references and contracts, never data rows, labels or
    the study database."""
    schema_version: Literal['hypotrail.export_source/1']
    study_id: NAME
    revision: StrictInt = Field(ge=0)
    task: Task
    case: dict[NAME, JsonValue]
    dataset_sha256: SHA256
    scientific_contracts: dict[NAME, JsonValue]
    decisions: list[ExportDecision]
    results: list[ExportResultRef]
    development_plan: dict[NAME, JsonValue]
    final_test: dict[NAME, JsonValue]
    predictor: ExportPredictor
    limitations: list[StrictStr]
    # Read by the Azure ML export (workstream B): evidence state of the selection, the
    # metric names of the study's task, and the confirmed conclusion if any.
    validity: dict[NAME, JsonValue]
    metrics: list[NAME]
    conclusion: Optional[dict[NAME, JsonValue]]
    extensions: Extensions = Field(default_factory=dict)


MODELS: dict[str, Type[Contract]] = {
    'hypotrail.model_recipe/1': ModelRecipe,
    'hypotrail.data_contract/1': DataContract,
    'hypotrail.computation_context/1': ComputationContext,
    'hypotrail.predictor_artifact/1': PredictorArtifact,
    'hypotrail.predictor_bundle/1': PredictorBundle,
    'hypotrail.evidence_binding/1': EvidenceBinding,
    'hypotrail.parity_result/1': ParityResult,
    'hypotrail.package_descriptor/1': PackageDescriptor,
    'hypotrail.diagnostic_result/1': DiagnosticResult,
    'hypotrail.uncertainty_result/1': UncertaintyResult,
    'hypotrail.export_source/1': ExportSource,
}

M = TypeVar('M', bound=Contract)


def parse(model: Type[M], document: Mapping | str | bytes) -> M:
    """Validate ``document`` (a mapping, or JSON text) against ``model``: the version first
    (``schema_version_unsupported`` for another major of the same type), then the strict
    structure (``contract_invalid``). JSON text and Python mappings have the same
    semantics."""
    import json
    expected = model.model_fields['schema_version'].annotation.__args__[0]
    raw = document
    if isinstance(document, (str, bytes)):
        try:
            raw = json.loads(document, parse_constant=_refuse_constant)
        except ValueError as exc:
            raise ContractError('contract_invalid', f'The document is not JSON: {exc}',
                                remediation='Send one JSON object.') from None
    if not isinstance(raw, Mapping):
        raise ContractError('contract_invalid', 'A contract document is a JSON object.',
                            remediation='Send one JSON object.')
    version = raw.get('schema_version')
    m = _SCHEMA_RE.match(version) if isinstance(version, str) else None
    e = _SCHEMA_RE.match(expected)
    if m and m.group(1) == e.group(1) and m.group(2) != e.group(2):
        raise ContractError('schema_version_unsupported',
                            f'{version} is not supported; this runtime reads {expected}.',
                            path='schema_version',
                            remediation='Use a runtime that supports this major version, or '
                                        'export the document in the supported version.',
                            details={'found': version, 'supported': [expected]})
    if version != expected:
        raise ContractError('contract_invalid', f'schema_version is {version!r}; {expected} '
                            'is expected here.', path='schema_version',
                            remediation=f'Send a {expected} document.')
    try:
        if isinstance(document, (str, bytes)):
            return model.model_validate_json(document, strict=True)
        return model.model_validate(dict(raw), strict=True)
    except ValidationError as exc:
        raise from_pydantic(exc, schema=expected) from None


def _refuse_constant(name):
    raise ValueError(f'{name} is not allowed in a contract document')


# --- semantic checks (separate from structure) -----------------------------------------------

def recipe_issues(recipe: ModelRecipe) -> list[dict]:
    from . import families
    issues = []
    if len(set(recipe.features)) != len(recipe.features):
        issues.append({'path': 'features', 'message': 'feature names are listed once'})
    if set(recipe.feature_types) != set(recipe.features):
        issues.append({'path': 'feature_types',
                       'message': 'feature_types names exactly the features',
                       'missing': sorted(set(recipe.features) - set(recipe.feature_types)),
                       'extra': sorted(set(recipe.feature_types) - set(recipe.features))})
    if recipe.target.name in recipe.features:
        issues.append({'path': 'target/name', 'message': 'the target is never a feature'})
    binary = recipe.task == 'binary'
    if binary and recipe.target.positive_label is None:
        issues.append({'path': 'target/positive_label',
                       'message': 'a binary recipe names its positive label'})
    if not binary and recipe.target.positive_label is not None:
        issues.append({'path': 'target/positive_label',
                       'message': 'a regression recipe has no positive label'})
    kind = 'binary_score' if binary else 'regression_point'
    if recipe.output_contract.kind != kind:
        issues.append({'path': 'output_contract/kind',
                       'message': f'a {recipe.task} recipe outputs {kind}'})
    if recipe.output_contract.positive_label != recipe.target.positive_label:
        issues.append({'path': 'output_contract/positive_label',
                       'message': 'the output names the target positive label'})
    if not binary and recipe.output_contract.unit != recipe.target.unit:
        issues.append({'path': 'output_contract/unit',
                       'message': 'a regression output is in the target unit'})
    issues.extend(families.parameter_issues(recipe.task, recipe.family, recipe.parameters))
    ops = [s.operation for s in recipe.preprocessing]
    for name in ('numeric_median_impute_scale', 'categorical_mode_impute_onehot'):
        if ops.count(name) != 1:
            issues.append({'path': 'preprocessing',
                           'message': f'{name} appears exactly once'})
    for s in recipe.preprocessing:
        for column in _step_columns(s):
            if column not in recipe.features:
                issues.append({'path': f'preprocessing/{s.operation}',
                               'message': f'{column!r} is not a feature'})
    return issues


def _step_columns(step: PreprocessingStep) -> list[str]:
    p = step.parameters
    if step.operation in ('category_as_text', 'missing_indicator', 'signed_log'):
        return [str(c) for c in p.get('columns') or []]
    if step.operation == 'special_value_indicator':
        return [str(v.get('column')) for v in p.get('values') or [] if isinstance(v, Mapping)]
    if step.operation == 'cap_quantiles':
        return [str(c) for c in (p.get('quantiles') or {})]
    return []


def contract_issues(contract: DataContract) -> list[dict]:
    issues = []
    names = [c.name for c in contract.columns]
    if len(set(names)) != len(names):
        issues.append({'path': 'columns', 'message': 'column names are listed once'})
    roles = {c.name: c.role for c in contract.columns}
    targets = [n for n, r in roles.items() if r == 'target']
    if len(targets) > 1:
        issues.append({'path': 'columns', 'message': 'at most one target column'})
    policy = contract.inference_policy
    for name in policy.required_columns:
        if roles.get(name) != 'feature':
            issues.append({'path': 'inference_policy/required_columns',
                           'message': f'{name!r} is not a feature column; the target and the '
                                      'keys are never required at inference'})
    if sorted(policy.canonical_order) != sorted(contract.features()):
        issues.append({'path': 'inference_policy/canonical_order',
                       'message': 'the canonical order lists every feature once'})
    for col in contract.columns:
        if col.allowed_values is not None and col.semantic_type == 'numeric':
            issues.append({'path': f'columns/{col.name}/allowed_values',
                           'message': 'numeric domains go in a versioned extension, not '
                                      'allowed_values'})
    for name in contract.row_identity.columns:
        if name not in roles:
            issues.append({'path': 'row_identity/columns', 'message': f'{name!r} is unknown'})
    if contract.row_identity.kind == 'source_position' \
            and not contract.row_identity.source_hash_required:
        issues.append({'path': 'row_identity/source_hash_required',
                       'message': 'positional keys depend on the source hash'})
    for conv in policy.conversions:
        if conv.column not in roles:
            issues.append({'path': 'inference_policy/conversions',
                           'message': f'{conv.column!r} is unknown'})
    return issues


def _raise_semantic(issues: list[dict], schema: str) -> None:
    if issues:
        raise ContractError(
            'contract_invalid', f'{schema}: {issues[0]["message"]} at {issues[0]["path"]}'
            + (f' (and {len(issues) - 1} more)' if len(issues) > 1 else ''),
            path=issues[0]['path'], remediation='Correct the document; its structure is '
                                                'valid but its content is inconsistent.',
            issues=[{'code': 'contract_invalid', **i} for i in issues])


def validate_recipe(document: Mapping | str | bytes) -> ModelRecipe:
    recipe = parse(ModelRecipe, document)
    _raise_semantic(recipe_issues(recipe), 'hypotrail.model_recipe/1')
    return recipe


def validate_data_contract(document: Mapping | str | bytes) -> DataContract:
    contract = parse(DataContract, document)
    _raise_semantic(contract_issues(contract), 'hypotrail.data_contract/1')
    return contract
