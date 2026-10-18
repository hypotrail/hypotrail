"""Static case contract ``hypotrail.case/1``: load, validate, and check capabilities.

A case file (``use-cases/<id>/case.yaml``) is a static adapter: it says where the
dataset is, how to read it, how rows are keyed, what each variable means, and what
is known about it. It never records a human decision. Decisions live in study state.
The contract is specified in ``docs/specs/CASE-CONTRACT.md``.

Every refusal is a :class:`CaseError` with a stable ``code``:

* ``invalid_case``: the document does not follow the schema;
* ``confirmed_status_forbidden``: the document claims a confirmation;
* ``dataset_missing``: the dataset file is absent or outside the case directory;
* ``dataset_changed``: the dataset bytes no longer match the declared sha256;
* ``unsupported_capability``: the case is valid but needs a capability that this
  version does not have. Nothing falls back silently to a supported mode.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SCHEMA = 'hypotrail.case/1'
CASE_FILE = 'case.yaml'

EPISTEMIC_STATUSES = ('documented_fact', 'scenario_assumption', 'observed', 'unknown')
AVAILABILITY_VALUES = ('available_at_prediction', 'not_available', 'uncertain', 'unknown')
TASKS = ('binary', 'regression')
SUPPORTED_TASKS = ('binary', 'regression')
# A regression target is a number with a declared unit (errors are reported in it).
REGRESSION_TARGET_TYPES = ('numeric', 'integer')
# A time column this version can split on: integer values ordered as written (a year coded
# with two digits). It is never converted to a date: pandas would read an integer as
# nanoseconds since 1970.
ORDINAL_TIME_TYPES = ('integer',)
ROLES = ('feature', 'target', 'identifier', 'group_id', 'time')
VARIABLE_TYPES = ('numeric', 'integer', 'binary', 'category', 'ordinal', 'string', 'date')
ROW_KEY_RULE = 'source_line'
ROW_KEY_FORMAT = 'L<line>'
WHITESPACE_SEP = 'whitespace'
# A case states facts and assumptions; confirmation is a human act recorded in study
# state. These words are refused as a key or as a whole string value anywhere.
FORBIDDEN_WORDS = ('confirmed', 'confirmation')

CAPABILITY_TIME_SPLIT = 'temporal split on a date or non-integer time column (v0.2)'
# Not a refusal: a declared group column is accepted, and every split reports how many group
# values its partitions share (``limitations``). The capability is named, never assumed.
CAPABILITY_GROUPED_SPLIT = 'grouped split (v0.2)'

TOP_REQUIRED = ('schema', 'id', 'title', 'description', 'provenance', 'dataset', 'target',
                'row_key', 'facts', 'variables', 'special_values', 'structure', 'task')
TOP_OPTIONAL = ('prior_exposure', 'migration')
DATASET_REQUIRED = ('path', 'format', 'sep', 'encoding', 'decimal', 'header', 'sha256', 'rows',
                    'columns')
DATASET_OPTIONAL = ('quotechar', 'na_values')
VARIABLE_REQUIRED = ('name', 'type', 'role', 'description', 'status', 'source', 'availability',
                     'special_values')
VARIABLE_OPTIONAL = ('unit', 'format')
STATEMENT_KEYS = ('value', 'status', 'source')
SPECIAL_VALUE_KEYS = ('value', 'meaning', 'status', 'source')
STRUCTURE_KEYS = ('row_unit', 'group_column', 'time_column', 'duplicates')
MIGRATION_REQUIRED = ('from', 'from_schema', 'from_sha256', 'tool', 'tool_version')
MIGRATION_OPTIONAL = ('supplement', 'supplement_sha256', 'rules', 'notes')
SHA256 = re.compile(r'[0-9a-f]{64}')


class CaseError(ValueError):
    """A structured refusal. ``to_dict()`` is the machine-readable form."""

    def __init__(self, code: str, message: str, *, problems: list[dict] | None = None,
                 details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.problems = problems or []
        self.details = details or {}

    def to_dict(self) -> dict:
        out = {'code': self.code, 'message': self.message}
        if self.problems:
            out['problems'] = self.problems
        if self.details:
            out['details'] = self.details
        return out


@dataclass(frozen=True)
class Case:
    """A validated case. ``document`` is a private copy; do not mutate it."""

    path: Path
    document: dict

    @property
    def root(self) -> Path:
        return self.path.parent

    @property
    def id(self) -> str:
        return self.document['id']

    @property
    def task(self) -> str:
        return self.document['task']

    @property
    def dataset(self) -> dict:
        return self.document['dataset']

    @property
    def dataset_path(self) -> Path:
        return self.root / self.dataset['path']

    @property
    def read_sep(self) -> str:
        """Separator in the form ``pandas.read_csv`` expects."""
        sep = self.dataset['sep']
        return r'\s+' if sep == WHITESPACE_SEP else sep

    @property
    def column_names(self) -> list[str]:
        return [v['name'] for v in self.document['variables']]

    @property
    def variables(self) -> dict[str, dict]:
        return {v['name']: v for v in self.document['variables']}

    @property
    def target_column(self) -> str:
        return self.document['target']['column']

    @property
    def positive_label(self) -> Any:
        return self.document['target'].get('positive_label')

    @property
    def target_unit(self) -> str | None:
        """The unit of the target variable (required for a regression target)."""
        return self.variables[self.target_column].get('unit')

    @property
    def time_column(self) -> str | None:
        return self.document['structure']['time_column']['value']

    @property
    def group_column(self) -> str | None:
        return self.document['structure']['group_column']['value']

    def row_key(self, line: int) -> str:
        """Row key of the record on 1-based physical ``line`` (the header is line 1)."""
        first = 2 if self.dataset['header'] else 1
        if type(line) is not int or line < first:
            raise ValueError(f'line must be an integer >= {first}')
        return f'L{line}'


# --- validation -------------------------------------------------------------------------

def _walk(node: Any, path: str):
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f'{path}.{key}' if path else str(key))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _walk(item, f'{path}[{i}]')


def confirmation_claims(document: Any) -> list[dict]:
    """Every place where ``document`` claims a confirmation."""
    found = []
    for path, node in _walk(document, ''):
        if isinstance(node, dict):
            for key in node:
                if isinstance(key, str) and key.strip().lower() in FORBIDDEN_WORDS:
                    found.append({'path': f'{path}.{key}' if path else key,
                                  'problem': f'key "{key}" is not allowed in a case'})
        elif isinstance(node, str) and node.strip().lower() in FORBIDDEN_WORDS:
            found.append({'path': path, 'problem': f'value "{node}" is not allowed in a case'})
    return found


class _Problems:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, path: str, problem: str) -> None:
        self.items.append({'path': path, 'problem': problem})

    def keys(self, node: Any, path: str, required, optional=()) -> bool:
        if not isinstance(node, dict):
            self.add(path, 'must be a mapping')
            return False
        missing = [k for k in required if k not in node]
        unknown = [k for k in node if k not in required and k not in optional]
        for k in missing:
            self.add(f'{path}.{k}' if path else k, 'is required')
        for k in unknown:
            self.add(f'{path}.{k}' if path else str(k), 'is not part of the schema')
        return not missing

    def text(self, node: Any, path: str) -> None:
        if not isinstance(node, str) or not node.strip():
            self.add(path, 'must be a non-empty string')

    def status(self, node: Any, path: str) -> None:
        if node not in EPISTEMIC_STATUSES:
            self.add(path, f'must be one of {", ".join(EPISTEMIC_STATUSES)}')

    def statement(self, node: Any, path: str) -> None:
        if self.keys(node, path, STATEMENT_KEYS):
            self.status(node['status'], f'{path}.status')
            self.text(node['source'], f'{path}.source')


def _validate_dataset(d: Any, p: _Problems) -> None:
    if not p.keys(d, 'dataset', DATASET_REQUIRED, DATASET_OPTIONAL):
        return
    p.text(d['path'], 'dataset.path')
    if isinstance(d['path'], str) and (Path(d['path']).is_absolute() or '..' in Path(d['path']).parts):
        p.add('dataset.path', 'must be a relative path inside the case directory')
    if d['format'] != 'csv':
        p.add('dataset.format', 'must be "csv" (delimited text)')
    if not isinstance(d['sep'], str) or not d['sep']:
        p.add('dataset.sep', f'must be a non-empty string or "{WHITESPACE_SEP}"')
    elif d['sep'] != WHITESPACE_SEP and len(d['sep']) != 1:
        p.add('dataset.sep', f'must be a single character or "{WHITESPACE_SEP}"')
    p.text(d['encoding'], 'dataset.encoding')
    if not isinstance(d['decimal'], str) or len(d['decimal']) != 1:
        p.add('dataset.decimal', 'must be a single character')
    if type(d['header']) is not bool:
        p.add('dataset.header', 'must be true or false')
    if not isinstance(d['sha256'], str) or not SHA256.fullmatch(d['sha256']):
        p.add('dataset.sha256', 'must be 64 lowercase hexadecimal characters')
    for key in ('rows', 'columns'):
        if type(d[key]) is not int or d[key] < 1:
            p.add(f'dataset.{key}', 'must be a positive integer')
    if 'quotechar' in d and (not isinstance(d['quotechar'], str) or len(d['quotechar']) != 1):
        p.add('dataset.quotechar', 'must be a single character')
    if 'na_values' in d and (not isinstance(d['na_values'], list)
                             or not all(isinstance(v, str) for v in d['na_values'])):
        p.add('dataset.na_values', 'must be a list of strings')


def _validate_variables(variables: Any, p: _Problems) -> list[dict]:
    if not isinstance(variables, list) or not variables:
        p.add('variables', 'must be a non-empty list')
        return []
    seen, valid = set(), []
    for i, v in enumerate(variables):
        path = f'variables[{i}]'
        if not p.keys(v, path, VARIABLE_REQUIRED, VARIABLE_OPTIONAL):
            continue
        p.text(v['name'], f'{path}.name')
        if v['name'] in seen:
            p.add(f'{path}.name', f'duplicate variable "{v["name"]}"')
        seen.add(v['name'])
        if v['type'] not in VARIABLE_TYPES:
            p.add(f'{path}.type', f'must be one of {", ".join(VARIABLE_TYPES)}')
        if v['role'] not in ROLES:
            p.add(f'{path}.role', f'must be one of {", ".join(ROLES)}')
        p.text(v['description'], f'{path}.description')
        p.status(v['status'], f'{path}.status')
        p.text(v['source'], f'{path}.source')
        a = v['availability']
        if p.keys(a, f'{path}.availability', STATEMENT_KEYS):
            if a['value'] not in AVAILABILITY_VALUES:
                p.add(f'{path}.availability.value',
                      f'must be one of {", ".join(AVAILABILITY_VALUES)}')
            p.status(a['status'], f'{path}.availability.status')
            p.text(a['source'], f'{path}.availability.source')
            if (a['value'] == 'unknown') != (a['status'] == 'unknown'):
                p.add(f'{path}.availability',
                      'value "unknown" and status "unknown" go together')
        if not isinstance(v['special_values'], list):
            p.add(f'{path}.special_values', 'must be a list')
        else:
            for j, sv in enumerate(v['special_values']):
                sp = f'{path}.special_values[{j}]'
                if p.keys(sv, sp, SPECIAL_VALUE_KEYS):
                    p.text(sv['meaning'], f'{sp}.meaning')
                    p.status(sv['status'], f'{sp}.status')
                    p.text(sv['source'], f'{sp}.source')
        valid.append(v)
    return valid


def validate(document: Any) -> list[dict]:
    """Return every schema problem of ``document`` (empty when it is valid).

    Confirmation claims are reported by :func:`confirmation_claims`, not here.
    """
    p = _Problems()
    if not p.keys(document, '', TOP_REQUIRED, TOP_OPTIONAL):
        return p.items
    if document['schema'] != SCHEMA:
        p.add('schema', f'must be "{SCHEMA}"')
    p.text(document['id'], 'id')
    p.text(document['title'], 'title')
    p.text(document['description'], 'description')
    if not isinstance(document['provenance'], dict) or 'kind' not in document['provenance']:
        p.add('provenance', 'must be a mapping with a "kind"')
    if document['task'] not in TASKS:
        p.add('task', f'must be one of {", ".join(TASKS)}')
    _validate_dataset(document['dataset'], p)
    variables = _validate_variables(document['variables'], p)
    names = [v['name'] for v in variables]
    roles = {}
    for v in variables:
        roles.setdefault(v['role'], []).append(v['name'])

    d = document['dataset']
    if isinstance(d, dict) and type(d.get('columns')) is int and d['columns'] != len(document['variables'] or []):
        p.add('dataset.columns', 'must equal the number of variables')

    t = document['target']
    if p.keys(t, 'target', ('column', 'positive_label'), ('negative_label',)):
        if t['column'] not in names:
            p.add('target.column', 'must name a variable')
        elif roles.get('target', []) != [t['column']]:
            p.add('target.column', 'exactly one variable has role "target" and it is this column')
        if document['task'] == 'binary' and (t['positive_label'] is None or t['positive_label'] == ''):
            p.add('target.positive_label', 'is required for a binary task')
        if document['task'] == 'regression' and t['positive_label'] is not None:
            p.add('target.positive_label', 'must be null for a regression task')
        if document['task'] == 'regression' and t['column'] in names:
            target = next(v for v in variables if v['name'] == t['column'])
            if target['type'] not in REGRESSION_TARGET_TYPES:
                p.add('target.column', 'a regression target has type '
                      + ' or '.join(REGRESSION_TARGET_TYPES))
            unit = target.get('unit')
            if not isinstance(unit, str) or not unit.strip():
                p.add('target.column', 'a regression target declares its unit (variable unit): '
                                       'errors are reported in it')

    rk = document['row_key']
    if p.keys(rk, 'row_key', ('rule', 'format', 'description')):
        if rk['rule'] != ROW_KEY_RULE:
            p.add('row_key.rule', f'must be "{ROW_KEY_RULE}"')
        if rk['format'] != ROW_KEY_FORMAT:
            p.add('row_key.format', f'must be "{ROW_KEY_FORMAT}"')
        p.text(rk['description'], 'row_key.description')

    facts = document['facts']
    if not isinstance(facts, list):
        p.add('facts', 'must be a list')
    else:
        ids = set()
        for i, f in enumerate(facts):
            if p.keys(f, f'facts[{i}]', ('id',) + STATEMENT_KEYS):
                p.text(f['id'], f'facts[{i}].id')
                if f['id'] in ids:
                    p.add(f'facts[{i}].id', f'duplicate fact "{f["id"]}"')
                ids.add(f['id'])
                p.status(f['status'], f'facts[{i}].status')
                p.text(f['source'], f'facts[{i}].source')

    expected = [{'column': v['name'], **sv} for v in variables
                if isinstance(v['special_values'], list) for sv in v['special_values']]
    if document['special_values'] != expected:
        p.add('special_values', 'must list every variable special value, in variable order, '
                                'as {column, value, meaning, status, source}')

    s = document['structure']
    if p.keys(s, 'structure', STRUCTURE_KEYS):
        for key in STRUCTURE_KEYS:
            p.statement(s[key], f'structure.{key}')
        for key, role in (('time_column', 'time'), ('group_column', 'group_id')):
            value = s[key].get('value') if isinstance(s[key], dict) else None
            if value is not None and value not in names:
                p.add(f'structure.{key}.value', 'must name a variable or be null')
            if roles.get(role, []) != ([value] if value is not None else []):
                p.add(f'structure.{key}', f'variables with role "{role}" must be exactly this column')
        dup = s['duplicates'].get('value') if isinstance(s['duplicates'], dict) else None
        if dup is not None and (type(dup) is not int or dup < 0):
            p.add('structure.duplicates.value', 'must be a count of exact duplicate rows or null')

    if 'prior_exposure' in document:
        pe = document['prior_exposure']
        if not isinstance(pe, list):
            p.add('prior_exposure', 'must be a list')
        else:
            for i, item in enumerate(pe):
                p.statement(item, f'prior_exposure[{i}]')
    if 'migration' in document:
        m = document['migration']
        if p.keys(m, 'migration', MIGRATION_REQUIRED, MIGRATION_OPTIONAL):
            for key in ('from_sha256', 'supplement_sha256'):
                if key in m and (not isinstance(m[key], str) or not SHA256.fullmatch(m[key])):
                    p.add(f'migration.{key}', 'must be 64 lowercase hexadecimal characters')
    return p.items


# --- dataset ----------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def case_of(state, *, verify_data: bool = False) -> Case:
    """The case recorded in a study ``state`` (its file is read again; the dataset bytes
    are verified only with ``verify_data``). The one definition, used by the commands and
    the activities."""
    return load_case(state['case']['path'], verify_data=verify_data)


def source_changes(state) -> list[dict]:
    """The case and dataset files whose bytes differ from the digests recorded in
    ``state`` (plan §3.7 row 12): ``[{label, path, expected_sha256, actual_sha256}]``,
    empty when both match. ``actual_sha256`` is None for a missing file."""
    out = []
    for label in ('case', 'dataset'):
        path, expected = Path(state[label]['path']), state[label]['sha256']
        actual = sha256_file(path) if path.is_file() else None
        if actual != expected:
            out.append({'label': label, 'path': str(path), 'expected_sha256': expected,
                        'actual_sha256': actual})
    return out


def changed_sources_error(changes: list[dict]):
    """The ``dataset_changed`` refusal of :func:`source_changes` (first change in details)."""
    from .errors import StudyError

    first = changes[0]
    return StudyError('dataset_changed',
                      f'The {first["label"]} file changed since the study started; decisions and '
                      f'results refer to the original bytes. Start a new study on the new data.',
                      details={**{k: first[k] for k in ('path', 'expected_sha256',
                                                         'actual_sha256')},
                               'changes': changes})


def _header_fields(first_line: str, d: dict) -> list[str]:
    if d['sep'] == WHITESPACE_SEP:
        return first_line.split()
    return next(csv.reader([first_line], delimiter=d['sep'], quotechar=d.get('quotechar', '"')))


def verify_dataset(case: Case) -> None:
    """Check that the dataset is the declared file: location, sha256, rows, header."""
    d = case.dataset
    root = case.root.resolve()
    path = case.dataset_path.resolve()
    if not path.is_relative_to(root):
        raise CaseError('dataset_missing', 'The dataset is outside the case directory.',
                        details={'path': d['path']})
    if not path.is_file():
        raise CaseError('dataset_missing', f'Dataset not found: {d["path"]}',
                        details={'path': d['path']})
    actual = sha256_file(path)
    if actual != d['sha256']:
        raise CaseError('dataset_changed',
                        'The dataset bytes differ from the sha256 declared in the case. '
                        'Row keys and every recorded result are anchored to that sha256.',
                        details={'path': d['path'], 'declared_sha256': d['sha256'],
                                 'actual_sha256': actual})
    data = path.read_bytes()
    lines = data.count(b'\n') + (0 if not data or data.endswith(b'\n') else 1)
    rows = lines - (1 if d['header'] else 0)
    if rows != d['rows']:
        raise CaseError('invalid_case', 'dataset.rows does not match the physical lines of the file',
                        problems=[{'path': 'dataset.rows',
                                   'problem': f'declared {d["rows"]}, file has {rows} data lines'}])
    if d['header']:
        first = data.split(b'\n', 1)[0].decode(d['encoding']).rstrip('\r')
        fields = _header_fields(first, d)
        if fields != case.column_names:
            raise CaseError('invalid_case', 'The header does not match the variable names',
                            problems=[{'path': 'variables',
                                       'problem': f'header {fields} differs from {case.column_names}'}])


# --- loading and capabilities -----------------------------------------------------------

def check_document(document: Any) -> None:
    """Raise a :class:`CaseError` unless ``document`` is a valid, claim-free case."""
    claims = confirmation_claims(document)
    if claims:
        raise CaseError('confirmed_status_forbidden',
                        'A case states facts and assumptions; it never records a confirmation. '
                        'Confirmations are human decisions recorded in study state.',
                        problems=claims)
    problems = validate(document)
    if problems:
        raise CaseError('invalid_case', f'The case does not follow {SCHEMA}', problems=problems)


def load_case(path, *, verify_data: bool = True) -> Case:
    """Load ``path`` (a case.yaml or its directory), validate it, and verify the dataset."""
    path = Path(path)
    if path.is_dir():
        path = path / CASE_FILE
    if not path.is_file():
        raise CaseError('invalid_case', f'Case file not found: {path}')
    try:
        document = yaml.safe_load(path.read_text(encoding='utf-8'))
    except yaml.YAMLError as exc:
        raise CaseError('invalid_case', f'Case file is not valid YAML: {exc}') from exc
    check_document(document)
    case = Case(path=path.resolve(), document=copy.deepcopy(document))
    if verify_data:
        verify_dataset(case)
    return case


def _variable(doc: dict, name: str) -> dict:
    return next((v for v in doc['variables'] if v['name'] == name), {})


def unsupported_capabilities(case: Case | dict) -> list[dict]:
    """Structured reasons why this version cannot run a study on ``case``.

    Supported: a ``binary`` or a ``regression`` task, and a declared time column whose
    variable type is ``integer`` (split by an ordinal cutoff, ``ordinal_cutoff``). A time
    column of another type (a date, a decimal number) is refused: it is never handled by a
    random split, and it is never converted silently. A declared group column is not
    refused; see :func:`limitations`.
    """
    doc = case.document if isinstance(case, Case) else case
    reasons = []
    column = doc['structure']['time_column']['value']
    if column is not None:
        kind = _variable(doc, column).get('type')
        if kind not in ORDINAL_TIME_TYPES:
            reasons.append({
                'code': 'unsupported_capability', 'capability': CAPABILITY_TIME_SPLIT,
                'path': 'structure.time_column', 'column': column,
                'reason': f'The case declares time column "{column}" of type {kind}; this '
                          f'version splits on an integer time column only (an ordinal cutoff). '
                          f'A random split would mix earlier and later rows across partitions, '
                          f'so it does not fall back to a random split.'})
    return reasons


def limitations(case: Case | dict) -> list[dict]:
    """Named capabilities a supported case lacks, without being refused.

    A declared group column (rows that describe the same entity) cannot be kept on one
    side of the split: this version has no grouped split. The study is not refused, but
    the capability is named, and every split reports the group values its partitions
    share (``split.values.groups``), so independence is never claimed silently.
    """
    doc = case.document if isinstance(case, Case) else case
    out = []
    column = doc['structure']['group_column']['value']
    if column is not None:
        out.append({'capability': CAPABILITY_GROUPED_SPLIT, 'path': 'structure.group_column',
                    'column': column,
                    'consequence': f'Rows sharing a value of "{column}" may fall in both '
                                   f'partitions; each split reports the shared group values.'})
    return out



def require_supported(case: Case) -> Case:
    """Return ``case`` if this version supports it; otherwise refuse with every reason."""
    reasons = unsupported_capabilities(case)
    if reasons:
        names = sorted({r['capability'] for r in reasons})
        raise CaseError('unsupported_capability',
                        'This case needs a capability that is not available yet: '
                        + '; '.join(names),
                        details={'reasons': reasons})
    return case
