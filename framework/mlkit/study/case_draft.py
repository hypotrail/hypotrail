"""A case drafted from one data file, before sealing (onboarding Lot 2, ``ONBOARDING-SPEC.md``).

``hypotrail new NAME --data FILE`` copies the file into ``NAME.case/data/`` and reads it
**structurally**, on every row (§2.1): the separator, UTF-8, one physical line per record, the
header, and for each column its type, missing cells, number of distinct values and a few
example values; for the column that becomes the target, only its label set or range and its
missing count. Never a rate of the target, never the target crossed with another column,
never a model. That reading is recorded as a ``prior_exposure`` statement (``observed``):
the rows of the final test are not unseen in that structural sense.

What is inferred, and how far it is trusted (review B §5):

* **reliable** (``observed``): the sha256, the physical lines, the header, the separator (a
  constant number of fields), UTF-8, the missing cells, the cardinality, the exact duplicates;
  multi-line records are refused;
* **proposed only, never applied**: a type that could hide codes (leading zeros), a comma
  decimal mark, a date with an ambiguous day and month, a token that looks like a missing
  marker in a numeric column (never put in ``na_values``), an identifier that may encode
  time. They are listed under ``todo`` and as suspicious columns;
* **never inferred**: the target, the groups, the availability of a variable. They come from
  the six preparation questions (:data:`QUESTIONS`) answered in the user's words.

:func:`build_case` turns the profile and the answers into a ``hypotrail.case/1`` document:
``target``, ``task``, ``structure``, ``duplicates``, ``prior_exposure`` and the facts of the
``analysis_contract`` (intended use, clocks, dependencies, claim ceiling). A case never
records a decision: every statement carries an epistemic status and quotes the user's words
as its source. The final test is not chosen: it is deduced from those facts at sealing
(:func:`mlkit.study.partition.deduce`).

Pure: the standard library and PyYAML only, no pandas.
"""
from __future__ import annotations

import codecs
import csv
import hashlib
import io
import re
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from .errors import StudyError

DRAFT_FILE = 'case.draft.yaml'
DRAFT_SCHEMA = 'hypotrail.case-draft/1'
PROFILE_FILE = 'profile.json'
PROFILE_SCHEMA = 'hypotrail.case-profile/1'
DATA_DIR = 'data'
SEPARATORS = (',', ';', '\t', '|')
MAX_EXAMPLES = 3
MAX_LABELS = 10
MAX_LISTED = 5
# The six preparation questions, in the order they are asked (§2.2); ``exposure`` first.
QUESTIONS = ('exposure', 'target', 'row_unit', 'timing', 'entities', 'final_test')
EXPOSURE_VALUES = ('not_explored', 'looked_at_rows', 'analysed_with_target')
USE_VALUES = ('future', 'retrospective', 'unknown')
RECURRING_VALUES = ('yes', 'no', 'unknown')
DUPLICATE_VALUES = ('same_entity', 'distinct', 'unknown')
# How the user knows an answer: ``known`` (they state it from their own knowledge of the data
# or the business), ``assumed`` (plausible, not established), ``unknown``.
BASES = ('known', 'assumed', 'unknown')
BASIS_STATUS = {'known': 'documented_fact', 'assumed': 'scenario_assumption',
                'unknown': 'unknown'}
CLOCK_TYPES = ('integer', 'numeric')

_INT = re.compile(r'[+-]?\d+')
_LEADING_ZERO = re.compile(r'[+-]?0\d')
_FLOAT = re.compile(r'[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?')
_COMMA_DECIMAL = re.compile(r'[+-]?\d+,\d+')
_ISO_DATE = re.compile(r'\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?')
_OTHER_DATE = re.compile(r'\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}')
_TOKENS = re.compile(r'[a-z]+|\d+')
# Name tokens that suggest a column records the outcome, or something after it (§2.3).
AFTER_OUTCOME_TOKENS = ('status', 'outcome', 'result', 'cancel', 'canceled', 'cancelled',
                        'cancellation', 'churn', 'churned', 'closed', 'close', 'end', 'final',
                        'paid', 'payment', 'return', 'returned', 'resolution', 'resolved',
                        'discharge', 'death', 'default', 'settled', 'refund', 'complete',
                        'completed', 'after', 'post')
ID_TOKENS = ('id', 'key', 'uuid', 'code', 'ref', 'number', 'no', 'num')


def refused(code: str, message: str, reason: str, **details) -> StudyError:
    return StudyError(code, message, details={'reason': reason, **details})


def today() -> str:
    return date.today().isoformat()


def slug(name: str) -> str:
    out = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    return out or 'study'


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- reading the file (structural, every row) ------------------------------------------------

def read_table(path: Path) -> dict:
    """``{encoding, sep, header, rows, sha256}`` of a delimited text file, or a refusal.

    UTF-8 strict (a byte-order mark is kept and read as ``utf-8-sig``); a separator among
    :data:`SEPARATORS` that gives every physical line the same number of fields (at least
    two); a header of unique, non-empty names that is not a row of numbers; one physical line
    per record (a quoted field spanning lines is refused, since row keys are line numbers)."""
    path = Path(path)
    if not path.is_file():
        raise refused('invalid_arguments', f'No file at {path}.', 'missing_file')
    if path.suffix.lower() not in ('.csv', '.tsv', '.txt'):
        raise refused('unsupported_capability',
                      f'{path.name}: only delimited text (CSV) is supported in this version. '
                      'Export the sheet as "CSV UTF-8" and start again.',
                      'unsupported_format', suffix=path.suffix)
    data = path.read_bytes()
    if not data.strip():
        raise refused('invalid_value', f'{path.name} is empty.', 'empty_file')
    encoding = 'utf-8'
    body = data
    if data.startswith(codecs.BOM_UTF8):
        encoding, body = 'utf-8-sig', data[len(codecs.BOM_UTF8):]
    try:
        text = body.decode('utf-8', errors='strict')
    except UnicodeDecodeError as exc:
        line = body[:exc.start].count(b'\n') + 1
        raise refused('invalid_value',
                      f'{path.name} is not UTF-8 (first invalid byte on line {line}). Save it '
                      'as UTF-8 ("CSV UTF-8" in a spreadsheet) and start again; this version '
                      'does not guess another encoding.', 'not_utf8', line=line) from exc
    if '\x00' in text:
        raise refused('invalid_value', f'{path.name} holds NUL bytes: it is not a text file.',
                      'binary_file')
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    lines = [line[:-1] if line.endswith('\r') else line for line in lines]
    best = None
    for sep in SEPARATORS:
        widths = [len(_fields(line, sep)) for line in lines]
        if widths[0] >= 2 and all(w == widths[0] for w in widths):
            if best is None or widths[0] > best[1]:
                best = (sep, widths[0])
    if best is None:
        _refuse_layout(path, text, lines)
    sep, width = best
    rows = [_fields(line, sep) for line in lines]
    header = rows[0]
    if any(not name.strip() for name in header) or len(set(header)) != len(header):
        raise refused('invalid_value', f'{path.name}: line 1 must be a header of unique, '
                                       'non-empty column names.', 'header_required',
                      header=header)
    if all(_FLOAT.fullmatch(name.strip()) for name in header):
        raise refused('invalid_value', f'{path.name}: line 1 looks like data, not a header. '
                                       'Add a line of column names and start again.',
                      'header_required')
    if len(rows) < 2:
        raise refused('invalid_value', f'{path.name} holds a header and no row.', 'no_rows')
    return {'encoding': encoding, 'sep': sep, 'width': width, 'header': header,
            'rows': rows[1:], 'sha256': sha256_bytes(data)}


def _fields(line: str, sep: str) -> list[str]:
    return next(csv.reader([line], delimiter=sep, quotechar='"'), [])


def _refuse_layout(path: Path, text: str, lines: list[str]) -> None:
    for sep in SEPARATORS:
        records = list(csv.reader(io.StringIO(text), delimiter=sep, quotechar='"'))
        widths = {len(r) for r in records if r}
        if len(widths) == 1 and widths.pop() >= 2 and len(records) < len(lines):
            raise refused('unsupported_capability',
                          f'{path.name} holds records that span several lines (a quoted field '
                          'with a line break). Rows are keyed by their line number, so each '
                          'record must fit on one line: remove the line breaks inside the '
                          'fields (or export again without them) and start again.',
                          'multi_line_records', records=len(records) - 1,
                          physical_lines=len(lines) - 1)
    counts = [len(_fields(line, ',')) for line in lines]
    width = counts[0]
    bad = [i + 1 for i, n in enumerate(counts) if n != width][:MAX_LISTED]
    raise refused('invalid_value',
                  f'{path.name}: no separator among comma, semicolon, tab and bar gives every '
                  'line the same number of fields (lines '
                  + ', '.join(map(str, bad)) + ' differ from the header). Check for blank '
                  'lines or stray separators.', 'inconsistent_fields', lines=bad)


# --- the structural profile ------------------------------------------------------------------

def _column_type(values: list[str]) -> tuple[str, list[str]]:
    """The type of a column from its non-empty cells, and the flags of what it may hide."""
    flags: list[str] = []
    if not values:
        return 'string', ['empty_column']
    distinct = set(values)
    if all(_INT.fullmatch(v) for v in values):
        if any(_LEADING_ZERO.match(v) for v in values):
            return 'string', ['leading_zeros']
        return 'integer', flags
    if all(_FLOAT.fullmatch(v) for v in values):
        return 'numeric', flags
    if all(_COMMA_DECIMAL.fullmatch(v) or _INT.fullmatch(v) for v in values):
        return 'string', ['comma_decimal']
    if all(_ISO_DATE.fullmatch(v) for v in values):
        return 'date', ['date']
    if all(_OTHER_DATE.fullmatch(v) for v in values):
        return 'string', ['ambiguous_date']
    numeric = [v for v in values if _FLOAT.fullmatch(v)]
    if numeric and len(numeric) >= 0.9 * len(values):
        flags.append('numeric_with_tokens')
    if len(distinct) == 2:
        return 'binary', flags
    return ('category' if len(distinct) <= max(20, len(values) // 20) else 'string'), flags


def _number(v: str):
    return int(v) if _INT.fullmatch(v) else float(v)


def profile(table: Mapping, file_name: str) -> dict:
    """The structural profile of every row (``hypotrail.case-profile/1``): per column its
    type, missing cells, distinct values, a few examples, and, for a column with at most
    :data:`MAX_LABELS` values, its label set (or, numeric, its range). No count per value."""
    header, rows = table['header'], table['rows']
    columns = []
    for j, name in enumerate(header):
        cells = [r[j] for r in rows]
        present = [v for v in cells if v != '']
        kind, flags = _column_type(present)
        distinct = sorted(set(present))
        examples = []
        for v in present:
            if v not in examples:
                examples.append(v)
            if len(examples) == MAX_EXAMPLES:
                break
        item = {'name': name, 'type': kind, 'missing': len(cells) - len(present),
                'distinct': len(distinct), 'examples': examples,
                'labels': distinct if len(distinct) <= MAX_LABELS else None,
                'range': None, 'unique': len(distinct) == len(cells), 'flags': flags}
        if kind in ('integer', 'numeric') and present:
            numbers = [_number(v) for v in present]
            item['range'] = [min(numbers), max(numbers)]
        columns.append(item)
    content: dict[tuple, int] = {}
    for r in rows:
        content[tuple(r)] = content.get(tuple(r), 0) + 1
    repeated = [n for n in content.values() if n > 1]
    return {'schema': PROFILE_SCHEMA, 'file': file_name, 'sha256': table['sha256'],
            'encoding': table['encoding'], 'sep': table['sep'], 'rows': len(rows),
            'columns': len(header), 'missing_cells': sum(c['missing'] for c in columns),
            'duplicates': {'groups': len(repeated), 'extra_rows': sum(n - 1 for n in repeated),
                           'definition': 'records identical on every column'},
            'variables': columns, 'created': today(),
            'reveals': 'structure only: types, counts, missing cells, cardinality, a few '
                       'example values; no rate of any value and no relation between columns'}


def _tokens(name: str) -> list[str]:
    spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    return _TOKENS.findall(spaced.lower())


def suspicious(prof: Mapping, target: str | None = None) -> list[dict]:
    """Columns to check before sealing, from their names and the structure only (§2.3):
    an identifier that may encode time, a date that may come after the outcome, a name that
    suggests the outcome, a near-copy of the target (same name stem or same label set), and
    what the reading could not settle (codes, decimal comma, ambiguous dates, tokens in a
    numeric column). Never a relation computed between a column and the target."""
    out = []
    by_name = {c['name']: c for c in prof['variables']}
    tgt = by_name.get(target) if target else None
    target_tokens = {t for t in _tokens(target) if len(t) >= 3} if target else set()
    for c in prof['variables']:
        name = c['name']
        if name == target:
            continue
        tokens = set(_tokens(name))
        why = []
        if c['unique'] and (tokens & set(ID_TOKENS) or c['type'] in ('string', 'integer')):
            why.append('identifier: one value per row; an identifier that grows over time '
                       'encodes time, and it never generalises as a predictor')
        if c['type'] == 'date' or 'date' in tokens or 'time' in tokens:
            why.append('a date or a time: check that it is known when the prediction is made '
                       '(a date after the outcome reveals it)')
        if tokens & set(AFTER_OUTCOME_TOKENS):
            why.append('its name suggests the outcome or an event after it: check when its '
                       'value becomes known')
        if target_tokens and tokens & target_tokens:
            why.append(f'its name shares a word with the target {target!r}: it may be a '
                       f'near-copy of it')
        if tgt is not None and c['labels'] is not None and tgt.get('labels') is not None \
                and len(c['labels']) == len(tgt['labels']) == 2 \
                and set(c['labels']) == set(tgt['labels']):
            why.append(f'it holds the same two values as the target {target!r}: it may be a '
                       f'near-copy of it')
        for flag, text in (('leading_zeros', 'values with leading zeros: read as codes '
                                             '(text), never converted to numbers'),
                           ('comma_decimal', 'numbers with a decimal comma: kept as text; '
                                             'export with a decimal point to read them as '
                                             'numbers'),
                           ('ambiguous_date', 'dates whose day and month order is not '
                                              'stated: kept as text'),
                           ('numeric_with_tokens', 'mostly numbers with a few other tokens '
                                                   '(a missing marker?): kept as text; no '
                                                   'token is read as missing silently'),
                           ('empty_column', 'every cell is empty')):
            if flag in c['flags']:
                why.append(text)
        if c['missing'] and c['missing'] * 2 > prof['rows']:
            why.append('more than half of its cells are empty')
        if why:
            out.append({'column': name, 'why': why})
    return out


def column_view(prof: Mapping, target: str | None = None) -> list[dict]:
    """The profile's columns as shown to the user: the target (once named) by its label set
    or range and its missing count only, the other columns with their examples."""
    out = []
    for c in prof['variables']:
        item = {'name': c['name'], 'type': c['type'], 'missing': c['missing'],
                'distinct': c['distinct']}
        if c['name'] == target:
            item['role'] = 'target'
            item['labels' if c['labels'] is not None else 'range'] = (
                c['labels'] if c['labels'] is not None else c['range'])
        else:
            item['examples'] = c['examples']
        out.append(item)
    return out


# --- the draft ---------------------------------------------------------------------------

def draft(prof: Mapping, case_id: str, data_path: str) -> dict:
    """``case.draft.yaml``: what the reading established, what it could not, and the
    ``todo`` list of what the six questions must settle before ``hypotrail seal``."""
    todo = [
        {'question': 'exposure', 'text': 'Has the user already explored this file (rows, '
                                         'target rates, models)? Asked first.'},
        {'question': 'target', 'text': 'Which column is the target, and for a binary target '
                                       'which value is the positive one? (never inferred)'},
        {'question': 'row_unit', 'text': 'What does one row represent?'
                                         + (f' {prof["duplicates"]["extra_rows"]} rows repeat '
                                            'an earlier row: are they the same entity?'
                                            if prof['duplicates']['extra_rows'] else '')},
        {'question': 'timing', 'text': 'When is the prediction made, and is the use about the '
                                       'future? Which column dates the prediction, and which '
                                       'one the moment the outcome is known?'},
        {'question': 'entities', 'text': 'Do entities recur (a customer, a vehicle, a '
                                         'patient)? Which column names them? (never inferred)'},
        {'question': 'final_test', 'text': 'Does the user accept the final test, shown in '
                                           'words and counts?'},
    ]
    for item in suspicious(prof):
        todo.append({'column': item['column'], 'text': '; '.join(item['why'])})
    return {'schema': DRAFT_SCHEMA, 'id': case_id,
            'note': 'Drafted by hypotrail new from a structural reading of every row. Not a '
                    'case yet: hypotrail seal writes case.yaml from the answers to the six '
                    'questions. Do not edit by hand; answer with hypotrail prepare answer.',
            'dataset': {'path': data_path, 'format': 'csv', 'sep': prof['sep'],
                        'encoding': prof['encoding'], 'decimal': '.', 'header': True,
                        'sha256': prof['sha256'], 'rows': prof['rows'],
                        'columns': prof['columns']},
            'variables': [{'name': c['name'], 'type': c['type'], 'missing': c['missing'],
                           'distinct': c['distinct'], 'status': 'observed'}
                          for c in prof['variables']],
            'duplicates': prof['duplicates'],
            'todo': todo}


# --- the answers, checked against the profile -------------------------------------------

def _invalid(message: str, reason: str, **details) -> StudyError:
    return refused('invalid_value', message, reason, **details)


def check_answer(question: str, value: Any, prof: Mapping, answers: Mapping) -> dict:
    """``value`` normalised for ``question``, or a refusal saying why. Reads the profile
    only (types, counts, label sets), never a value of the data file."""
    by_name = {c['name']: c for c in prof['variables']}
    if not isinstance(value, Mapping):
        raise _invalid(f'The value of {question} is a JSON object.', 'value_not_object')

    def keys(required, optional=()):
        missing = [k for k in required if k not in value]
        extra = [k for k in value if k not in required and k not in optional]
        if missing or extra:
            raise _invalid(f'{question} takes {{{", ".join(required + tuple(optional))}}}'
                           + (f'; missing: {", ".join(missing)}' if missing else '')
                           + (f'; unknown: {", ".join(extra)}' if extra else ''),
                           'value_keys', missing=missing, unknown=extra)

    def column(name, what):
        if name not in by_name:
            raise _invalid(f'{what}: {name!r} is not a column of the file.', 'unknown_column',
                           column=name)
        return by_name[name]

    target = ((answers.get('target') or {}).get('value') or {}).get('column')
    if question == 'exposure':
        keys(('explored',))
        if value['explored'] not in EXPOSURE_VALUES:
            raise _invalid(f'explored is one of {", ".join(EXPOSURE_VALUES)}.', 'bad_choice')
        return {'explored': value['explored']}
    if question == 'target':
        keys(('column',), ('positive_label', 'unit'))
        col = column(value['column'], 'target')
        if col['missing']:
            raise refused(
                'unsupported_capability',
                f'{col["missing"]} rows have no value of {col["name"]!r}. This version neither '
                'drops nor imputes target rows silently. If those rows are out of scope, '
                'make a copy of the file without them, write down how (which rows, why), and '
                'start again with hypotrail new on that copy; the rows left out are then '
                'stated in your words.', 'missing_target', capability='missing target values '
                '(v0.2)', rows=col['missing'])
        if col['distinct'] == 2:
            labels = col['labels']
            positive = value.get('positive_label')
            if positive is None or str(positive) not in labels:
                raise _invalid(f'A binary target names its positive label, one of '
                               f'{", ".join(map(repr, labels))}.', 'positive_label',
                               labels=labels)
            if value.get('unit') is not None:
                raise _invalid('A binary target has no unit.', 'unit_not_allowed')
            negative = next(label for label in labels if label != str(positive))
            return {'column': col['name'], 'task': 'binary', 'positive_label': str(positive),
                    'negative_label': negative, 'unit': None}
        if col['type'] in ('integer', 'numeric') and col['distinct'] > 2:
            unit = value.get('unit')
            if not isinstance(unit, str) or not unit.strip():
                raise _invalid('A numeric target (regression) declares its unit: errors are '
                               'reported in it.', 'unit_required')
            if value.get('positive_label') is not None:
                raise _invalid('A numeric target has no positive label.',
                               'positive_label_not_allowed')
            return {'column': col['name'], 'task': 'regression', 'positive_label': None,
                    'negative_label': None, 'unit': unit.strip()}
        raise refused('unsupported_capability',
                      f'{col["name"]!r} holds {col["distinct"]} distinct values of type '
                      f'{col["type"]}: this version studies a binary target (two values) or a '
                      'numeric one (regression), not a target with several categories or '
                      'text.', 'unsupported_task', column=col['name'],
                      distinct=col['distinct'], type=col['type'])
    if question == 'row_unit':
        keys(('row_unit',), ('duplicates',))
        unit = value['row_unit']
        if not isinstance(unit, str) or not unit.strip():
            raise _invalid('row_unit is what one row represents, in words.', 'row_unit_text')
        dup = value.get('duplicates')
        if prof['duplicates']['extra_rows'] and dup not in DUPLICATE_VALUES:
            raise _invalid(f'{prof["duplicates"]["extra_rows"]} rows repeat an earlier row: '
                           f'say whether they are the same entity (duplicates: one of '
                           f'{", ".join(DUPLICATE_VALUES)}). Either way they are kept together '
                           'on one side of the final test.', 'duplicates_required')
        if not prof['duplicates']['extra_rows'] and dup is not None:
            raise _invalid('No row repeats another: duplicates takes no value.',
                           'duplicates_not_allowed')
        return {'row_unit': ' '.join(unit.split()), 'duplicates': dup}
    if question == 'timing':
        keys(('use', 'statement'), ('prediction_clock', 'outcome_clock'))
        if value['use'] not in USE_VALUES:
            raise _invalid(f'use is one of {", ".join(USE_VALUES)}.', 'bad_choice')
        statement = value['statement']
        if not isinstance(statement, str) or not statement.strip():
            raise _invalid('statement says when the prediction is made, in words.',
                           'statement_text')
        clocks = {}
        for key in ('prediction_clock', 'outcome_clock'):
            name = value.get(key)
            if name is None:
                clocks[key] = None
                continue
            col = column(name, key)
            if name == target:
                raise _invalid(f'{key}: the target cannot date the rows.', 'clock_is_target')
            if col['type'] == 'date' or 'ambiguous_date' in col['flags']:
                raise refused(
                    'unsupported_capability',
                    f'{name!r} holds dates; this version reads a clock as a number only and '
                    'never converts a date silently. The way forward: add an integer column '
                    'derived from the date, the day number since 1970-01-01, with '
                    f'hypotrail prepare derive-clock --column {name} --date-format FORMAT (the '
                    'format the dates are written in, such as %Y-%m-%d), then name the new '
                    'column here. Otherwise sort a copy of the file by the date, state the '
                    'order and start again with hypotrail new on it (a retrospective study '
                    'only).', 'date_clock', column=name,
                    derive=f'prepare derive-clock --column {name} --date-format FORMAT',
                    capability='temporal split on a date or non-integer time column (v0.2)')
            if col['type'] not in CLOCK_TYPES:
                raise _invalid(f'{key}: {name!r} is of type {col["type"]}; a clock is a '
                               'column of numbers on one ascending scale.', 'clock_type')
            if col['missing']:
                raise _invalid(f'{key}: {col["missing"]} rows of {name!r} are empty, so they '
                               'cannot be placed in time.', 'clock_missing')
            clocks[key] = name
        if clocks['outcome_clock'] and not clocks['prediction_clock']:
            raise _invalid('An outcome clock needs a prediction clock on the same scale.',
                           'outcome_without_prediction')
        if value['use'] == 'future' and not clocks['prediction_clock']:
            raise _invalid(
                'A use about the future needs the column that dates each prediction: without '
                'it the final test would mix every period. If the file has no such column, '
                'the study can only be retrospective (use: retrospective or unknown).',
                'future_without_clock')
        if clocks['prediction_clock'] and clocks['prediction_clock'] == clocks['outcome_clock']:
            raise _invalid('The prediction clock and the outcome clock are two columns.',
                           'same_clock')
        return {'use': value['use'], 'statement': ' '.join(statement.split()), **clocks}
    if question == 'entities':
        keys(('recurring',), ('column',))
        if value['recurring'] not in RECURRING_VALUES:
            raise _invalid(f'recurring is one of {", ".join(RECURRING_VALUES)}.', 'bad_choice')
        name = value.get('column')
        if value['recurring'] == 'yes':
            if name is None:
                raise _invalid('Recurring entities need the column that names them.',
                               'group_column_required')
            col = column(name, 'entities')
            if name == target:
                raise _invalid('The target cannot name the entities.', 'group_is_target')
            if col['missing']:
                raise _invalid(f'{col["missing"]} rows of {name!r} are empty: they would form '
                               'one entity together.', 'group_missing')
            if col['unique']:
                raise _invalid(f'Every value of {name!r} occurs once: no entity recurs in it.',
                               'group_unique')
            return {'recurring': 'yes', 'column': name}
        if name is not None:
            raise _invalid('A column is named only when entities recur.', 'column_not_allowed')
        return {'recurring': value['recurring'], 'column': None}
    if question == 'final_test':
        keys(('accept', 'plan'))
        if value['accept'] is not True:
            raise _invalid('The final test is accepted (accept: true) with the plan shown by '
                           'prepare status; to change it, change the answers it rests on.',
                           'not_accepted')
        if not isinstance(value['plan'], str) or not value['plan']:
            raise _invalid('plan is the plan digest shown by prepare status.', 'plan_digest')
        return {'accept': True, 'plan': value['plan']}
    raise _invalid(f'Unknown question {question!r}; the questions are '
                   f'{", ".join(QUESTIONS)}.', 'unknown_question')


# --- the case document -------------------------------------------------------------------

def _quote(words: str) -> str:
    return '«' + ' '.join(str(words).split()) + '»'


def _source(answer: Mapping) -> str:
    text = f"Preparation answer in the user's words ({answer['time'][:10]}): " \
           f"{_quote(answer['user_words'])}"
    if answer.get('proposed_from'):
        text += f'; proposed from {answer["proposed_from"]}'
    return text


def _status(answer: Mapping) -> str:
    return BASIS_STATUS[answer.get('basis') or 'assumed']


def contract(answers: Mapping, case_id: str, prof: Mapping, file_name: str) -> dict:
    """The ``analysis_contract`` facts from the answers, by the rules of §2.4: a future use
    with documented clocks is a future prediction; a prediction clock otherwise is an assumed
    time dependence; recurring entities are grouped dependencies (grouped and temporal with a
    clock); unknown entities without a clock stay unknown, with capped claims."""
    timing, entities = answers['timing'], answers['entities']
    exposure = answers['exposure']['value']['explored']
    t, g = timing['value'], entities['value']
    t_status, g_status = _status(timing), _status(entities)
    t_source, g_source = _source(timing), _source(entities)

    def clock(name):
        return None if name is None else {'by': name, 'status': t_status, 'source': t_source}

    future = (t['use'] == 'future' and t['prediction_clock'] and t['outcome_clock']
              and t_status == 'documented_fact')
    if g['recurring'] == 'yes':
        kind = 'grouped_temporal' if t['prediction_clock'] else 'grouped'
        dep = {'kind': kind, 'group_column': g['column'], 'group_goal': 'unseen_groups',
               'status': g_status, 'source': g_source}
    elif t['prediction_clock']:
        dep = {'kind': 'temporal', 'group_column': None, 'group_goal': None,
               'status': t_status, 'source': t_source}
    elif g['recurring'] == 'no' and t['use'] != 'unknown':
        dep = {'kind': 'independent', 'group_column': None, 'group_goal': None,
               'status': g_status, 'source': g_source}
    else:
        dep = {'kind': 'unknown', 'group_column': None, 'group_goal': None,
               'status': 'unknown', 'source': g_source}
    claims = ['retrospective_association']
    if future and exposure != 'analysed_with_target' and dep['kind'] != 'unknown':
        claims.append('future_predictive_performance')
    return {'schema': 'hypotrail.analysis/1', 'scenario_id': f'{case_id}-prepared-v1',
            'intended_use': 'future_prediction' if future else 'retrospective_comparison',
            'row_unit': answers['row_unit']['value']['row_unit'],
            'population': f'The {prof["rows"]} rows of {file_name}, as provided',
            'prediction_statement': t['statement'],
            'timing': {'prediction_order': clock(t['prediction_clock']),
                       'outcome_available_order': clock(t['outcome_clock']) if future or
                       t['outcome_clock'] else None,
                       'scale': 'ordinal'},
            'dependencies': dep, 'permitted_claims': claims}


EXPOSURE_TEXTS = {
    'not_explored': 'The user states that they had not explored this file before the '
                    'preparation.',
    'looked_at_rows': 'The user had looked at rows of this file before the preparation, '
                      'without target rates or models: the final test may hold rows they saw.',
    'analysed_with_target': 'The user had analysed this file with its target (rates, charts '
                            'or models) before the preparation: the final test is not unseen, '
                            'it is no independent evidence, and the claims are capped (no '
                            'future performance).',
}


def build_case(prof: Mapping, answers: Mapping, *, case_id: str, title: str,
               data_path: str, profile_sha256: str, original_name: str,
               derived=()) -> dict:
    """The ``hypotrail.case/1`` document from the profile and the answers (every question
    but ``final_test`` answered). Never a decision: statuses come from how the user knows
    each answer (:data:`BASIS_STATUS`), sources quote their words. ``derived`` lists the
    columns ``prepare derive-clock`` appended (documented in the variable and the
    provenance)."""
    derived_by = {d['column']: d for d in derived}
    file_name = Path(data_path).name
    tgt = answers['target']['value']
    unit = answers['row_unit']
    timing, entities = answers['timing']['value'], answers['entities']['value']
    the_contract = contract(answers, case_id, prof, file_name)
    clock = timing['prediction_clock']
    by_name = {c['name']: c for c in prof['variables']}
    time_column = clock if clock and by_name[clock]['type'] == 'integer' else None
    group_column = entities['column']
    inspected = f'Structural inspection of {data_path} (hypotrail new)'
    variables = []
    for c in prof['variables']:
        name = c['name']
        kind = c['type']
        role = 'feature'
        availability = {'value': 'unknown', 'status': 'unknown',
                        'source': 'Not documented at preparation; whether it is known at '
                                  'prediction time is a decision of the study.'}
        if name == tgt['column']:
            role = 'target'
            kind = 'binary' if tgt['task'] == 'binary' else kind
            availability = {'value': 'not_available', 'status': 'documented_fact',
                            'source': 'The outcome to predict (the target named at '
                                      'preparation).'}
        elif name == time_column:
            role = 'time'
        elif name == group_column:
            role = 'group_id'
        elif c['unique'] and kind in ('string', 'binary', 'category'):
            role = 'identifier'
        if name == timing['outcome_clock']:
            availability = {'value': 'not_available', 'status': _status(answers['timing']),
                            'source': 'The moment the outcome becomes known (the outcome '
                                      'clock): it comes after the prediction. '
                                      + _source(answers['timing'])}
        entry = {'name': name, 'type': kind, 'role': role}
        if role == 'target' and tgt['unit']:
            entry['unit'] = tgt['unit']
        made = derived_by.get(name)
        entry.update({
            'description': (f'The target named at preparation: {_quote(answers["target"]["user_words"])}.'
                            if role == 'target' else _derived_text(made) if made else
                            f'Column {name} of {file_name}; no description yet.'),
            'status': _status(answers['target']) if role == 'target' else
                      'observed' if made else 'unknown',
            'source': _source(answers['target']) if role == 'target' else
                      _derived_source(made) if made else 'Not documented at preparation.',
            'availability': availability,
            'special_values': ([{'value': '', 'meaning': 'An empty cell, read as missing.',
                                 'status': 'observed', 'source': inspected}]
                               if c['missing'] else [])})
        variables.append(entry)
    dataset = {'path': data_path, 'format': 'csv', 'sep': prof['sep'],
               'encoding': prof['encoding'], 'decimal': '.', 'header': True,
               'sha256': prof['sha256'], 'rows': prof['rows'], 'columns': prof['columns']}
    if prof['missing_cells']:
        dataset['na_values'] = ['']
    task = tgt['task']
    target_words = (f'{tgt["column"]}, positive label {tgt["positive_label"]!r}'
                    if task == 'binary' else f'{tgt["column"]}, in {tgt["unit"]}')
    exposure = answers['exposure']
    facts = [
        {'id': 'observation_unit', 'value': unit['value']['row_unit'],
         'status': _status(unit), 'source': _source(unit)},
        {'id': 'target', 'value': target_words, 'status': _status(answers['target']),
         'source': _source(answers['target'])},
        {'id': 'prediction_time', 'value': timing['statement'],
         'status': _status(answers['timing']), 'source': _source(answers['timing'])},
        {'id': 'intended_use',
         'value': {'future': 'Predict outcomes that are not known yet.',
                   'retrospective': 'Compare and explain on rows whose outcome is known '
                                    '(retrospective).',
                   'unknown': 'Not stated: whether the use is about the future is unknown.'}
         [timing['use']],
         'status': 'unknown' if timing['use'] == 'unknown' else _status(answers['timing']),
         'source': _source(answers['timing'])},
    ]
    doc = {
        'schema': 'hypotrail.case/1', 'id': case_id, 'title': title,
        'description': (f'Predict {tgt["column"]} for each row ({unit["value"]["row_unit"]}).'
                        if task == 'binary' else
                        f'Estimate {tgt["column"]} for each row ({unit["value"]["row_unit"]}).'),
        'provenance': {'kind': 'unspecified', 'copied_from': original_name,
                       'copied_by': 'hypotrail new --data'
                                    + (', then hypotrail prepare derive-clock' if derived
                                       else ''),
                       'profile_sha256': profile_sha256}
        | ({'derived_columns': [
            {k: d[k] for k in ('column', 'from', 'format', 'rule', 'empty', 'from_file',
                               'from_sha256', 'file', 'sha256')}
            | ({'user_words': d['user_words']} if d.get('user_words') else {})
            for d in derived]} if derived else {}),
        'dataset': dataset,
        'target': {'column': tgt['column'], 'positive_label': tgt['positive_label']}
        | ({'negative_label': tgt['negative_label']} if task == 'binary' else {}),
        'row_key': {'rule': 'source_line', 'format': 'L<line>',
                    'description': f'Physical 1-based line number in {file_name}; the header '
                                   'is line 1, so the first data row is L2. The key is '
                                   'anchored to the dataset sha256.'},
        'facts': facts,
        'variables': variables,
        'special_values': [{'column': v['name'], **sv} for v in variables
                           for sv in v['special_values']],
        'structure': {
            'row_unit': {'value': unit['value']['row_unit'], 'status': _status(unit),
                         'source': _source(unit)},
            'group_column': {'value': group_column, 'status': _status(answers['entities']),
                             'source': _source(answers['entities'])},
            'time_column': {'value': time_column, 'status': _status(answers['timing']),
                            'source': _source(answers['timing'])},
            'duplicates': {'value': prof['duplicates']['extra_rows'], 'status': 'observed',
                           'source': inspected}},
        'task': task,
        'prior_exposure': [
            {'value': 'Structural inspection of every row before sealing (hypotrail new): '
                      'column types, counts, missing cells, cardinality and a few example '
                      'values of each column; for the target, its label set or range and its '
                      'missing count. No rate of the target and no relation between columns '
                      'was read. The final-test rows are not unseen in that structural sense.',
             'status': 'observed', 'source': f'{PROFILE_FILE} (sha256 {profile_sha256})'},
            {'value': EXPOSURE_TEXTS[exposure['value']['explored']],
             'status': _status(exposure), 'source': _source(exposure)}],
    }
    if prof['duplicates']['extra_rows']:
        doc['duplicates'] = {'policy': 'group', 'status': _status(unit),
                             'source': f'{prof["duplicates"]["extra_rows"]} rows repeat an '
                                       'earlier row; kept together as one entity. '
                                       + _source(unit)}
    doc['analysis_contract'] = the_contract
    return doc


def _derived_text(made: Mapping) -> str:
    return (f'The day number ({made["rule"]}) of the date in {made["from"]}, read with the '
            f'format {made["format"]}; a time of day is dropped'
            + (f', and {made["empty"]} empty dates stay empty' if made['empty'] else '')
            + '. Derived by hypotrail prepare derive-clock, so the date can serve as a clock.')


def _derived_source(made: Mapping) -> str:
    text = (f'hypotrail prepare derive-clock ({made["time"][:10]}): appended to '
            f'{made["from_file"]} (sha256 {made["from_sha256"]}), giving {made["file"]} '
            f'(sha256 {made["sha256"]}); every other byte is unchanged')
    if made.get('user_words'):
        text += f'; the order of day and month in the user\'s words: {_quote(made["user_words"])}'
    return text


HEADER = ('# Generated by hypotrail seal from the structural profile and the answers to the six\n'
          '# preparation questions (hypotrail prepare answer). Do not edit by hand: every\n'
          '# change of these bytes makes the study report sources_changed.\n'
          '# A case states facts and assumptions; human decisions live in study state.\n')


def render(document: Mapping) -> str:
    import yaml
    return HEADER + yaml.safe_dump(dict(document), sort_keys=False, allow_unicode=True,
                                   width=100)
