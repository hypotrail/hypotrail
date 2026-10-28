"""MAPIE adapters (extra ``uncertainty``; spec L-15–L-17; AC13–AC16).

Two independent capabilities, two contracts, one calibration discipline.

**Calibration (L-15).** A calibration partition is a role of its own: reserved before use,
disjoint from every other partition (training, tuning, selection, the final test, and the
engine's validation rows and folds), never explored. Its eligibility is checked *before*
anything is computed (:func:`eligibility`): a study without such a partition (every study
the engine creates today) gets ``not_applicable``; explored or overlapping rows never become
a fresh calibration by renaming. Every use is recorded in a
durable ledger (:class:`CalibrationLedger`): the first procedure that uses a partition binds
it; repeating that exact procedure reproduces it; another procedure (another model, recipe,
positive class, threshold family or objective) is refused as adaptive reuse
(``calibration_not_eligible``) — and a changed model invalidates the calibrated object
without ever making the partition unseen again. The ledger keys a use on the *rows*, not on
the partition's name: the membership digest of ``calibration_ref`` (the same rows under
another id are the same calibration) and the per-row digests of the row keys, which every
claim must pass (a superset or any overlap of rows already used is refused unless it is
the very same membership and procedure). A claim is atomic: it reads, checks and appends
under a file lock, so two concurrent claims never both bind. A ledger is read strictly
(review A, round 3): only a torn last line (an append cut by a crash, no final newline) is
ignored, and the next claim rewrites the ledger atomically without it, under the lock, and
says so (:class:`LedgerRepaired`); any other unreadable line is ``contract_invalid``, never
a raw exception, and nothing is claimed past it.

**Risk control (L-16).** Binary classification, scores of a *fixed* model, a threshold grid
fixed in advance, the per-row rule ``threshold:t``. The target is a minimum precision with a
confidence level (Learn-Then-Test with Hoeffding–Bentkus p-values and Bonferroni–Holm
family-wise control, :class:`mapie.risk_control.BinaryClassificationController`). The
adapter checks that the installed MAPIE's ``precision`` risk is the expected quantity
(1 − precision over predicted positives, an empty selection never controlled) before use.
The result keeps every admissible threshold, the pre-specified choice rule, the selected
threshold, the calibration size and the controller's parameters. No admissible threshold is
``insufficient_data`` with ``reason: no_admissible_threshold`` and **no** threshold: the
empirically best threshold is never substituted. ``capacity``/``share`` (top-k) rules are
refused in this first scope. The guarantee is about the procedure: under exchangeability of
calibration and future rows, the probability that it certifies a threshold whose precision is
below the target is at most 1 − confidence; it is not a precision promised on every future
batch, and a precision floor is not a gain over a reference.

**Intervals (L-17).** Split-conformal regression: a fixed model, absolute residuals on an
independent calibration set, the finite-sample quantile of rank ⌈(n+1)(1−α)⌉; marginal
coverage only (no conditional guarantee: subgroup figures are descriptive). Too few
calibration rows for the requested level is ``insufficient_data`` (never an infinite bound in
JSON). Width and empirical coverage are reported on authorised labelled rows only.

The boundary rank (review A, 2026-10-24). The adapter's rule is the finite-sample one: the
interval is finite when the rank ⌈(n+1)·level⌉ is at most n. MAPIE 1.x is stricter and
refuses ``n < max(1/α, 1/(1 − α))``, which at usual levels is exactly the case rank = n
(for example 19 rows at 95 %). There the adapter keeps its own rule and computes the same
quantile itself (the residual of that rank, here the largest, of the fixed model) rather
than reporting ``insufficient_data`` for a calibration size its rule accepts; the result
says so (``hypotrail.quantile``: ``adapter_rank_rule``, and a warning). Otherwise the
quantile is MAPIE's (``hypotrail.quantile``: ``mapie``).

A known conservative difference below 0.5 (review A, round 2, observation N4; behaviour
unchanged). MAPIE receives the level, works with α = 1 − level and computes its rank from
1 − α, which in floating point can exceed the level (1 − (1 − 0.3) = 0.30000000000000004).
When (n+1)·level is an integer, MAPIE's ceiling then lands one rank above the adapter's
rule ⌈(n+1)·level⌉ (computed with a 1e-12 guard), so its interval is the next residual up:
wider, never narrower, and only at levels below 0.5, which are not usual coverage levels.
At 0.5 and above the two ranks agree on every calibration size the tests sweep.

Exporting a calibrated capability is not qualified (parity, environment and signature of
MAPIE objects in the exported project are untested): :func:`require_exportable` refuses it
explicitly rather than dropping it.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import tempfile
import warnings
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from hypotrail_runtime import canonical
from hypotrail_runtime.contracts import UncertaintyResult, parse
from hypotrail_runtime.errors import ContractError

RULES = ('threshold',)
REFUSED_RULES = ('capacity', 'share', 'top_k')
SELECTION_RULES = {'max_recall': 'recall', 'max_selected_fraction': 'predicted_positive_fraction'}
FWER = 'bonferroni_holm'
EXPORT_QUALIFIED = False
LEDGER_SCHEMA = 'hypotrail.calibration_use/1'
FORBIDDEN_OVERLAP = ('train', 'tuning', 'selection', 'final_test')


def _backend() -> dict:
    try:
        import mapie
    except ImportError as exc:
        raise ContractError('optional_dependency_missing', 'MAPIE is not installed.',
                            remediation='Install the uncertainty extra; the base workflow does '
                                        'not need it.', details={'error': str(exc)}) from None
    return {'distribution': 'mapie', 'version': mapie.__version__}


# --- calibration partitions ----------------------------------------------------------------

def eligibility(calibration: Mapping | None, *, other_partitions: Mapping[str, Iterable[str]],
                exposures: Iterable[Mapping] = ()) -> dict:
    """``{eligible, reasons, calibration_ref, n_rows}`` of a calibration partition.

    ``calibration``: ``{id, role, keys, reserved_revision, frozen_revision}`` (the model and
    the rule family were frozen at ``frozen_revision``); ``other_partitions``: the row keys of
    every other membership of the study, by name (``train``, ``tuning``, ``selection``,
    ``final_test``, and the engine's own ``validation``, ``fold_<k>``, ``development``...);
    ``exposures``: the exposure records of the calibration rows (any purpose other than
    ``reserved`` means they were looked at).

    The calibration rows must be disjoint from every partition given, whatever its name
    (round 9, R9AB-4): a name outside :data:`FORBIDDEN_OVERLAP` was silently ignored before,
    so a calibration overlapping the engine's ``validation`` or ``fold_1`` rows was eligible.
    The reasons list the four named roles first, then the other names in sorted order."""
    if calibration is None:
        return {'eligible': False, 'calibration_ref': None, 'n_rows': 0,
                'reasons': ['no_calibration_partition: the study reserved no calibration rows '
                            'before use; exposed rows are never split after the fact']}
    reasons = []
    keys = set(calibration.get('keys') or ())
    if calibration.get('role') != 'calibration':
        reasons.append('role_not_calibration')
    if not keys:
        reasons.append('empty_calibration')
    names = [n for n in FORBIDDEN_OVERLAP if n in other_partitions] + \
        sorted((n for n in other_partitions if n not in FORBIDDEN_OVERLAP), key=str)
    for name in names:
        if keys & set(other_partitions.get(name) or ()):
            reasons.append(f'overlaps_{name}')
    reserved, frozen = calibration.get('reserved_revision'), calibration.get('frozen_revision')
    if not isinstance(reserved, int) or not isinstance(frozen, int) or reserved > frozen:
        reasons.append('not_reserved_before_the_model_was_frozen')
    looked = sorted({e.get('purpose') for e in exposures
                     if e.get('purpose') not in ('reserved', 'sealed')
                     and keys & set(e.get('row_keys') or ())})
    if looked:
        reasons.append('explored:' + ','.join(looked))
    membership = canonical.sha256_hex('\n'.join(sorted(keys)).encode()) if keys else None
    return {'eligible': not reasons, 'reasons': reasons, 'n_rows': len(keys),
            'calibration_ref': (f'{calibration.get("id")}@{membership}' if membership else None)}


class LedgerRepaired(UserWarning):
    """A claim removed a torn last line from the calibration ledger before appending (round
    3, R3-A6). ``details`` names the ledger, the line number and the digest of the dropped
    bytes."""

    def __init__(self, message: str, details: Mapping):
        super().__init__(message)
        self.details = dict(details)


def _ledger_refusal(path: Path, line: int, problem: str) -> ContractError:
    return ContractError('contract_invalid', f'The calibration ledger {path.name} is unreadable '
                         f'at line {line} ({problem}); no claim is recorded past it.',
                         path=f'ledger/{line}',
                         remediation='Restore the ledger from its backup or inspect that line; '
                                     'never delete recorded uses (exposure is never undone). '
                                     'Only a torn last line without a final newline is '
                                     'repaired automatically.',
                         details={'ledger': path.name, 'line': line, 'problem': problem})


class CalibrationLedger:
    """Durable record of the procedures that used a calibration partition (append-only,
    one JSON line per use, fsync'd). Exposure is never undone by an invalidation.

    Every claim names its rows (``keys``, mandatory since review A4 round 2): a use is
    keyed on the membership digest and on per-row digests, so an overlap or a superset of
    rows already used is always recognised. A claim reads the ledger, checks it and appends
    under an exclusive ``flock`` on ``<ledger>.lock``, so two concurrent claims cannot both
    bind the same rows (POSIX only, as the study writer lock)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.repairs: list[dict] = []

    def _read(self) -> tuple[list[dict], dict | None, bool]:
        """``(uses, torn, terminated)``: the recorded uses; when the last line is torn (no
        final newline and not a complete use), what a repair drops; whether the file ends
        with a newline (or is empty). Any other unreadable line is ``contract_invalid``."""
        if not self.path.exists():
            return [], None, True
        data = self.path.read_bytes()
        lines = data.split(b'\n')
        complete, tail = lines[:-1], lines[-1]      # tail: bytes after the last newline
        uses = []
        for number, raw in enumerate(complete, start=1):
            if raw.strip():
                uses.append(self._parse_line(raw, number))
        torn = None
        if tail.strip():
            number = len(complete) + 1
            try:
                json.loads(tail.decode('utf-8'))
            except (UnicodeDecodeError, ValueError):
                # An append cut short: a prefix of a record is never a JSON document.
                torn = {'ledger': self.path.name, 'line': number, 'size_bytes': len(tail),
                        'sha256': canonical.sha256_hex(tail)}
            else:
                uses.append(self._parse_line(tail, number))      # complete, newline missing
        return uses, torn, not tail

    def _parse_line(self, raw: bytes, number: int) -> dict:
        try:
            use = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, ValueError) as exc:
            raise _ledger_refusal(self.path, number, f'not JSON: {exc}'[:160]) from None
        if not isinstance(use, dict) or use.get('schema') != LEDGER_SCHEMA:
            raise _ledger_refusal(self.path, number, f'not a {LEDGER_SCHEMA} record')
        if not isinstance(use.get('procedure_id'), str) or \
                not isinstance(use.get('calibration_ref'), str):
            raise _ledger_refusal(self.path, number, 'no procedure_id or calibration_ref')
        membership = use.get('membership_sha256')
        if membership is not None and not isinstance(membership, str):
            raise _ledger_refusal(self.path, number, 'membership_sha256 is not a digest')
        try:
            if membership is None:
                self.membership(use['calibration_ref'])
        except ContractError:
            raise _ledger_refusal(self.path, number, 'calibration_ref is not <id>@<sha256>') \
                from None
        digests = use.get('row_digests')
        if digests is not None and (not isinstance(digests, list)
                                    or not all(isinstance(d, str) for d in digests)):
            raise _ledger_refusal(self.path, number, 'row_digests is not a list of digests')
        return use

    def uses(self) -> list[dict]:
        """The recorded uses; a torn last line is ignored (the next claim repairs it)."""
        return self._read()[0]

    def _repair(self, torn: Mapping) -> None:
        """Rewrite the ledger atomically without its torn last line (under the lock): every
        complete line is kept byte for byte."""
        current = self.path.read_bytes()
        data = current[:len(current) - int(torn['size_bytes'])]
        if canonical.sha256_hex(current[len(data):]) != torn['sha256'] or \
                (data and not data.endswith(b'\n')):
            raise _ledger_refusal(self.path, int(torn['line']), 'changed while it was repaired')
        fd, tmp = tempfile.mkstemp(prefix=f'.{self.path.name}.', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'wb') as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp)
            raise
        dirfd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
        self.repairs.append(dict(torn))
        warnings.warn(LedgerRepaired(
            f'The calibration ledger {self.path.name} ended with a torn line {torn["line"]} '
            f'({torn["size_bytes"]} bytes, an interrupted append); it was removed before this '
            'claim. The recorded uses are unchanged.', torn), stacklevel=3)

    @staticmethod
    def procedure_id(procedure: Mapping) -> str:
        return canonical.scientific_id(dict(procedure))

    @staticmethod
    def membership(calibration_ref: str) -> str:
        """The row-membership digest of ``<id>@<membership>`` (the name is not the rows)."""
        name, sep, membership = str(calibration_ref).rpartition('@')
        if not sep or len(membership) != 64 or not all(c in '0123456789abcdef'
                                                       for c in membership):
            raise ContractError('contract_invalid', 'A calibration reference is '
                                '<partition id>@<membership sha256>.', path='calibration_ref',
                                remediation='Pass the calibration_ref of eligibility().')
        return membership

    @staticmethod
    def row_digests(keys: Iterable[str]) -> list[str]:
        return sorted({canonical.sha256_hex(str(k).encode()) for k in keys})

    @contextlib.contextmanager
    def _locked(self):
        """An exclusive ``flock`` on the ledger's lock file for one read-check-append."""
        if os.name == 'nt':
            raise ContractError('capability_not_supported', 'The calibration ledger needs '
                                'POSIX file locking (fcntl.flock).',
                                remediation='Use Linux, macOS or WSL.')
        import fcntl
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path.with_name(self.path.name + '.lock'), os.O_CREAT | os.O_RDWR,
                     0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def claim(self, calibration_ref: str, procedure: Mapping, *,
              keys: Iterable[str]) -> dict:
        """Record the use before computing; the same procedure on the same rows may be
        reproduced; anything else on rows already used is refused
        (``calibration_not_eligible``). ``keys`` are the rows of ``calibration_ref``
        (mandatory, ``contract_invalid`` otherwise): rows are recognised by their membership
        digest whatever the partition is called, and by each row, so a superset or an
        overlap is refused. A recorded use without row digests (written before keys were
        mandatory) cannot be shown disjoint: it blocks every other membership."""
        pid = self.procedure_id(procedure)
        membership = self.membership(calibration_ref)
        if keys is None or isinstance(keys, (str, bytes)):
            raise ContractError('contract_invalid', 'A calibration claim names its rows: pass '
                                'the row keys of the calibration reference.', path='keys',
                                remediation='Pass the keys the eligibility was computed on.')
        keys = sorted({str(k) for k in keys})
        if not keys or canonical.sha256_hex('\n'.join(keys).encode()) != membership:
            raise ContractError('contract_invalid', 'The row keys are not the rows of this '
                                'calibration reference.', path='keys',
                                remediation='Pass the keys the eligibility was computed '
                                            'on.')
        digests = self.row_digests(keys)
        with self._locked():
            uses, torn, terminated = self._read()
            if torn is not None:
                self._repair(torn)
                terminated = True
            for use in uses:
                used = use.get('membership_sha256') or self.membership(use['calibration_ref'])
                same_rows = used == membership
                recorded = use.get('row_digests')
                overlap = same_rows or recorded is None \
                    or not set(digests).isdisjoint(recorded)
                if not overlap:
                    continue
                if same_rows and use['procedure_id'] == pid:
                    return use
                raise ContractError(
                    'calibration_not_eligible',
                    'These calibration rows (or some of them) already calibrated a procedure; '
                    'reusing them adaptively, under any partition name or inside a larger '
                    'set, is outside this version.', path='calibration',
                    remediation='Reserve new calibration rows for the new model, rule or '
                                'objective.',
                    details={'bound_procedure': use['procedure_id'], 'requested': pid,
                             'bound_calibration_ref': use['calibration_ref'],
                             'reason': 'same_rows' if same_rows else
                             'overlapping_rows' if recorded is not None
                             else 'recorded_rows_unknown'})
            use = {'schema': LEDGER_SCHEMA, 'calibration_ref': calibration_ref,
                   'membership_sha256': membership, 'procedure_id': pid,
                   'procedure': dict(procedure), 'row_digests': digests}
            with open(self.path, 'a', encoding='utf-8') as fh:
                # A complete last use written without its newline is kept, and closed first.
                fh.write(('' if terminated else '\n') + canonical.dumps(use).decode() + '\n')
                fh.flush()
                os.fsync(fh.fileno())
            return use


def is_current(procedure: Mapping, *, predictor_id: str, recipe_sha256: str,
               positive_label, rule_family: str, objective: str) -> bool:
    """A calibrated object holds only for the model, recipe, class, rule family and objective
    it was computed for."""
    return (procedure.get('predictor_id'), procedure.get('recipe_sha256'),
            procedure.get('positive_label'), procedure.get('rule_family'),
            procedure.get('objective')) == (predictor_id, recipe_sha256, positive_label,
                                            rule_family, objective)


# --- results ---------------------------------------------------------------------------------

def _result(*, status, reason, backend, method, target_quantity, assumptions, eligibility_,
            calibration_ref, predictor_id, warnings=(), **fields) -> UncertaintyResult:
    doc = {'schema_version': 'hypotrail.uncertainty_result/1', 'result_id': '0' * 64,
           'status': status, 'reason': reason, 'context': None, 'backend': backend,
           'method': method, 'warnings': list(warnings), 'artifact_refs': [],
           'target_quantity': target_quantity, 'assumptions': list(assumptions),
           'eligibility': eligibility_, 'calibration_ref': calibration_ref,
           'predictor_id': predictor_id, 'confidence_level': None, 'coverage_level': None,
           'risk_target': None, 'selection_rule': None, 'valid_thresholds': None,
           'selected_threshold': None, 'interval_bounds': None, 'undefined_replicates': None,
           'extensions': {}}
    doc.update(fields)
    doc['result_id'] = canonical.artifact_id(doc, exclude=('result_id',))
    return parse(UncertaintyResult, doc)


def _check_precision_risk(precision) -> None:
    """The installed MAPIE's ``precision`` must be 1 − precision over predicted positives,
    with an empty selection never controlled."""
    import numpy as np
    value, n = precision.get_value_and_effective_sample_size(np.array([1, 0, 1, 1]),
                                                             np.array([1, 1, 0, 1]))
    empty = precision.get_value_and_effective_sample_size(np.array([1, 0]), np.array([0, 0]))
    if not (precision.higher_is_better and math.isclose(value, 1 / 3) and n == 3
            and empty[1] < 1):
        raise ContractError('environment_unqualified', 'The installed MAPIE precision risk does '
                            'not match the contract (1 - precision over predicted positives).',
                            remediation='Pin a qualified MAPIE version.')


RISK_ASSUMPTIONS = (
    'Calibration rows and future rows are exchangeable (same population, independent rows).',
    'The model, its scores and the threshold grid were fixed before the calibration rows were '
    'read; the calibration rows were never explored.',
    'The guarantee bounds the probability that the procedure certifies a threshold whose '
    'precision is below the target; it is not a precision promised on every future batch.',
    'A precision floor is not a gain over a reference.')


def control_precision(scores, y, *, thresholds: Sequence[float], target_precision: float,
                      confidence_level: float, rule: str = 'threshold',
                      selection_rule: str = 'max_recall', predictor_id: str | None,
                      calibration: Mapping, empty_selection: str = 'not_certifiable'
                      ) -> UncertaintyResult:
    """Certify thresholds of ``threshold:t`` whose precision is at least ``target_precision``
    with confidence ``confidence_level``. ``scores``: the fixed model's positive-class scores
    on the calibration rows; ``y``: 1 for the positive label (the caller maps it);
    ``calibration``: :func:`eligibility`'s result."""
    kind = str(rule).split(':', 1)[0]
    if kind in REFUSED_RULES or kind not in RULES:
        raise ContractError('capability_not_supported', f'Risk control of a {kind} rule is not in '
                            'this first scope; only threshold:t is.', path='rule',
                            remediation='Use a fixed threshold grid, or keep the development '
                                        'evaluation of the share rule.', details={'rule': rule})
    if selection_rule not in SELECTION_RULES:
        raise ContractError('contract_invalid', 'The choice among admissible thresholds is '
                            'pre-specified: max_recall or max_selected_fraction.',
                            path='selection_rule', remediation='Declare it before calibrating.')
    if empty_selection != 'not_certifiable':
        raise ContractError('contract_invalid', 'An empty selection is never certified.',
                            path='empty_selection', remediation='Keep not_certifiable.')
    backend = _backend()
    method = {'name': 'learn_then_test.precision', 'version': '1',
              'parameters': {'risk': 'precision', 'p_value': 'hoeffding_bentkus',
                             'fwer': FWER, 'thresholds': [float(t) for t in thresholds],
                             'target_precision': float(target_precision),
                             'confidence_level': float(confidence_level), 'rule': 'threshold',
                             'selection_rule': selection_rule,
                             'empty_selection': empty_selection}}
    common = dict(backend=backend, method=method, target_quantity='precision_floor',
                  assumptions=RISK_ASSUMPTIONS, eligibility_=dict(calibration),
                  calibration_ref=calibration.get('calibration_ref'), predictor_id=predictor_id,
                  confidence_level=float(confidence_level), risk_target=float(target_precision),
                  selection_rule=selection_rule)
    if not calibration.get('eligible'):
        return _result(status='not_applicable',
                       reason='calibration_not_eligible: ' + '; '.join(calibration['reasons']),
                       **common)
    import numpy as np
    s = np.asarray(scores, dtype=float)
    labels = np.asarray(y)
    if s.shape != labels.shape or not len(s):
        raise ContractError('contract_invalid', 'Scores and labels align, one per calibration '
                            'row.', path='scores', remediation='Pass the aligned arrays.')
    if not np.isfinite(s).all() or not set(np.unique(labels)) <= {0, 1}:
        raise ContractError('contract_invalid', 'Scores are finite; labels are 0/1 for the named '
                            'positive class.', path='y', remediation='Map the positive label.')
    if len(set(np.unique(labels))) < 2:
        return _result(status='insufficient_data',
                       reason='the calibration rows hold one class only', **common)
    try:
        from mapie.risk_control import BinaryClassificationController, precision
    except ImportError as exc:
        raise ContractError('optional_dependency_missing', 'MAPIE is installed without its '
                            'risk-control module.', remediation='Reinstall the uncertainty '
                                                                'extra.',
                            details={'error': str(exc)}) from None
    _check_precision_risk(precision)
    try:
        controller = BinaryClassificationController(
            predict_function=lambda X: np.c_[1 - np.asarray(X)[:, 0], np.asarray(X)[:, 0]],
            risk=precision, target_level=float(target_precision),
            confidence_level=float(confidence_level),
            best_predict_param_choice=SELECTION_RULES[selection_rule],
            list_predict_params=np.asarray(thresholds, dtype=float), fwer_method=FWER)
        controller.calibrate(s.reshape(-1, 1), labels.astype(int))
    except Exception as exc:          # noqa: BLE001 - a backend failure is named
        return _result(status='failed', reason=f'backend_failed: {type(exc).__name__}: {exc}',
                       **common)
    valid = [float(t) for t in np.asarray(controller.valid_predict_params).ravel()]
    p_values = [None if not math.isfinite(float(p)) else float(p)
                for p in np.asarray(controller.p_values)[:, 0]]
    ext = {'hypotrail.p_values': p_values, 'hypotrail.n_calibration': int(len(s))}
    if not valid:
        return _result(status='insufficient_data', reason='no_admissible_threshold',
                       valid_thresholds=[], extensions=ext, **common)
    return _result(status='ok', reason=None, valid_thresholds=valid,
                   selected_threshold=float(controller.best_predict_param),
                   extensions=ext, **common)


INTERVAL_ASSUMPTIONS = (
    'Calibration rows and future rows are exchangeable; the model was fixed before the '
    'calibration rows were read.',
    'Coverage is marginal (on average over rows), not conditional on any subgroup: subgroup '
    'figures are descriptive.',
    'An interval for one prediction is not an interval for a gain over a reference.')


class _Fixed:
    """A fixed regression model for MAPIE's prefit mode (no fit ever happens)."""

    def __init__(self, predict: Callable):
        from sklearn.base import BaseEstimator, RegressorMixin

        class Fixed(RegressorMixin, BaseEstimator):
            fitted_ = True

            def fit(self, X, y=None):
                raise RuntimeError('a fixed model is never refitted')

            def predict(self, X):
                return predict(X)

            def __sklearn_is_fitted__(self):
                return True
        self.estimator = Fixed()


def finite_sample_rank(n: int, confidence_level: float) -> int:
    """The rank ⌈(n+1)·level⌉ of the conformal quantile among n sorted residuals."""
    return int(math.ceil((n + 1) * confidence_level - 1e-12))


def _mapie_refuses(n: int, confidence_level: float) -> bool:
    """MAPIE 1.x's own size check (``mapie.utils``): ``n < max(1/α, 1/(1 − α))``."""
    alpha = 1 - float(confidence_level)
    return n < max(1 / alpha, 1 / (1 - alpha))


def split_conformal(predict: Callable, X_cal, y_cal, X_new, *, confidence_level: float,
                    predictor_id: str | None, calibration: Mapping,
                    y_new=None, groups=None) -> UncertaintyResult:
    """Split-conformal intervals of ``predict`` (a fixed model) for ``X_new``."""
    backend = _backend()
    import numpy as np
    method = {'name': 'split_conformal.absolute_residual', 'version': '1',
              'parameters': {'confidence_level': float(confidence_level),
                             'conformity_score': 'absolute', 'prefit': True}}
    common = dict(backend=backend, method=method, target_quantity='prediction_interval',
                  assumptions=INTERVAL_ASSUMPTIONS, eligibility_=dict(calibration),
                  calibration_ref=calibration.get('calibration_ref'), predictor_id=predictor_id,
                  coverage_level=float(confidence_level))
    if not calibration.get('eligible'):
        return _result(status='not_applicable',
                       reason='calibration_not_eligible: ' + '; '.join(calibration['reasons']),
                       **common)
    y_cal = np.asarray(y_cal, dtype=float)
    n = len(y_cal)
    rank = finite_sample_rank(n, confidence_level)
    if n < 1 or rank > n:
        return _result(status='insufficient_data',
                       reason=f'{n} calibration rows cannot give a finite {confidence_level:g} '
                              'interval (the conformal rank exceeds n)', **common)
    try:
        from mapie.regression import SplitConformalRegressor
    except ImportError as exc:
        raise ContractError('optional_dependency_missing', 'MAPIE is installed without its '
                            'regression module.', remediation='Reinstall the uncertainty '
                                                              'extra.',
                            details={'error': str(exc)}) from None
    ext_quantile, warnings = 'mapie', []
    try:
        if _mapie_refuses(n, confidence_level):
            # MAPIE refuses this size; the adapter's rule (rank <= n) gives a finite bound.
            residuals = np.sort(np.abs(y_cal - np.asarray(predict(X_cal), dtype=float)))
            half = float(residuals[rank - 1])
            point = np.asarray(predict(X_new), dtype=float)
            low, high = point - half, point + half
            ext_quantile = 'adapter_rank_rule'
            warnings.append(f'MAPIE {backend["version"]} refuses {n} calibration rows at this '
                            f'level; the conformal rank {rank} is at most {n}, so the adapter '
                            'computed the same finite-sample quantile itself (the residual of '
                            'that rank).')
        else:
            model = SplitConformalRegressor(estimator=_Fixed(predict).estimator,
                                            confidence_level=float(confidence_level),
                                            prefit=True)
            model.conformalize(X_cal, y_cal)
            point, bounds = model.predict_interval(X_new)
            low, high = np.asarray(bounds)[:, 0, 0], np.asarray(bounds)[:, 1, 0]
    except ValueError as exc:
        return _result(status='insufficient_data', reason=f'mapie refused: {exc}', **common)
    except Exception as exc:          # noqa: BLE001
        return _result(status='failed', reason=f'backend_failed: {type(exc).__name__}: {exc}',
                       **common)
    if not (np.isfinite(low).all() and np.isfinite(high).all()):
        return _result(status='insufficient_data', reason='an interval bound is not finite',
                       **common)
    ext = {'hypotrail.n_calibration': n, 'hypotrail.quantile': ext_quantile,
           'hypotrail.mean_width': float(np.mean(high - low)) if len(low) else None}
    if y_new is not None:
        y_new = np.asarray(y_new, dtype=float)
        inside = (y_new >= low) & (y_new <= high)
        ext['hypotrail.empirical_coverage'] = float(inside.mean()) if len(inside) else None
        if groups is not None:
            groups = np.asarray(groups)
            ext['hypotrail.subgroup_coverage_descriptive'] = {
                str(g): {'n': int((groups == g).sum()),
                         'coverage': float(inside[groups == g].mean())}
                for g in sorted(set(groups.tolist()), key=str)}
    rows = [{'row': i, 'low': float(a), 'high': float(b)} for i, (a, b) in enumerate(zip(low, high))]
    return _result(status='ok', reason=None, interval_bounds=rows, extensions=ext,
                   warnings=warnings, **common)


def require_exportable(capability: str) -> None:
    """A calibrated capability is not exported until its packaging is qualified."""
    if not EXPORT_QUALIFIED:
        raise ContractError('capability_not_supported',
                            f'Exporting the calibrated capability {capability!r} is not '
                            'qualified (MAPIE parity, environment and signature in the exported '
                            'project are untested); it is refused, not dropped.',
                            path='capabilities', remediation='Export the base predictor; keep '
                                                             'the calibration in the study.',
                            details={'capability': capability})
