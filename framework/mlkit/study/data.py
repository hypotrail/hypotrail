"""Dataset loading with stable row keys (plan WP1.2, ``docs/specs/CASE-CONTRACT.md``).

The dataset is read exactly as the case declares it: separator (one character, or
``whitespace``), quote character, ``na_values``, decimal mark, encoding, and header.
Nothing else is read as missing (``keep_default_na=False``), so a category such as
``unknown`` stays a value.

Every record gets the key ``L<line>``: its physical 1-based line number in the file,
anchored to the file sha256 that is verified first. The ``source_line`` rule needs one
physical line per record, which is checked field by field. Each record also gets a
content hash: the sha256 of its parsed fields, independent of quoting and spacing.

The ``source_line`` rule is insufficient when two records have the same content:
they get different keys, but nothing says whether they are one entity recorded twice.
A split could then put copies on both sides, and exposure tracking could not tell
them apart. Such a dataset is refused (``unsupported_capability``) rather than
deduplicated silently, unless the case declares ``duplicates: {policy: group}``
(v0.2b, WP-B3): identical records are then one **entity group** (:func:`entity_groups`),
kept whole on one side of the final test, the split, and the folds. Every record keeps its
own row key, and exposure still counts rows.

:func:`row_index` uses the standard library only. :func:`load_dataset` imports pandas
when it is called, never at module import time.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from .case import WHITESPACE_SEP, Case, CaseError, require_supported, verify_dataset

CAPABILITY_DUPLICATES = 'duplicate records (v0.2)'
ROW_KEY_NAME = 'row_key'
MAX_LISTED = 20


@dataclass(frozen=True)
class RowIndex:
    """Row keys and content hashes of a verified dataset file, in file order."""

    dataset_sha256: str
    keys: tuple[str, ...]
    content_hashes: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.keys)

    def hash_of(self) -> dict[str, str]:
        return dict(zip(self.keys, self.content_hashes))


@dataclass(frozen=True)
class Dataset:
    """A loaded dataset: a pandas DataFrame indexed by row key, and its row index."""

    case: Case
    index: RowIndex
    frame: Any   # pandas.DataFrame; typed loosely so pandas is not imported here

    @property
    def sha256(self) -> str:
        return self.index.dataset_sha256


def _whitespace_tokenizer(quotechar: str):
    q = re.escape(quotechar)
    pattern = re.compile(rf'{q}((?:[^{q}]|{q}{q})*){q}|(\S+)')

    def split(line: str) -> list[str]:
        out = []
        for quoted, bare in pattern.findall(line):
            out.append(quoted.replace(quotechar * 2, quotechar) if not bare else bare)
        return out
    return split


def _field_splitter(case: Case):
    d = case.dataset
    quotechar = d.get('quotechar', '"')
    if d['sep'] == WHITESPACE_SEP:
        return _whitespace_tokenizer(quotechar)
    sep = d['sep']
    return lambda line: next(csv.reader([line], delimiter=sep, quotechar=quotechar), [])


def content_hash(fields: list[str]) -> str:
    """sha256 of the parsed fields of one record (canonical JSON list)."""
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False).encode('utf-8')).hexdigest()


def row_index(case: Case, *, verify: bool = True) -> RowIndex:
    """Verify the dataset and compute its row keys and content hashes.

    Refusals: ``dataset_missing`` and ``dataset_changed`` (from the case), ``invalid_case``
    when a line does not hold exactly one record, and ``unsupported_capability`` when
    records repeat (see the module docstring).
    """
    if verify:
        verify_dataset(case)
    d = case.dataset
    text = case.dataset_path.read_bytes().decode(d['encoding'])
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    first = 2 if d['header'] else 1
    body = lines[1:] if d['header'] else lines
    split = _field_splitter(case)
    width = len(case.column_names)
    keys, hashes, problems = [], [], []
    for offset, raw in enumerate(body):
        line = first + offset
        fields = split(raw.rstrip('\r'))
        if len(fields) != width:
            problems.append({'path': f'L{line}',
                             'problem': f'{len(fields)} fields, expected {width}'})
            if len(problems) >= MAX_LISTED:
                break
            continue
        keys.append(f'L{line}')
        hashes.append(content_hash(fields))
    if problems:
        raise CaseError('invalid_case', 'The row_key rule source_line needs exactly one record '
                                        'per physical line.', problems=problems)
    index = RowIndex(d['sha256'], tuple(keys), tuple(hashes))
    if case.duplicates_policy != DUPLICATES_GROUP:
        _refuse_duplicates(index)
    return index


def content_duplicates(index: RowIndex) -> list[list[str]]:
    """Groups of row keys whose records have identical content, in file order."""
    groups: dict[str, list[str]] = {}
    for key, digest in zip(index.keys, index.content_hashes):
        groups.setdefault(digest, []).append(key)
    return [keys for keys in groups.values() if len(keys) > 1]


DUPLICATES_GROUP = 'group'


def entity_groups(index: RowIndex) -> dict[str, str]:
    """The entity group of every record (``duplicates: {policy: group}``): the row key of
    the first record, in file order, with the same content. A record without a copy is its
    own group."""
    first: dict[str, str] = {}
    out = {}
    for key, digest in zip(index.keys, index.content_hashes):
        out[key] = first.setdefault(digest, key)
    return out


def duplicate_summary(case: Case, index: RowIndex) -> dict:
    """``{policy, n_groups, n_rows, n_extra_rows, definition}``: the groups of identical
    records among the rows of ``index`` (every column, the target included), counted
    structurally. ``policy`` is the case's (``group``) or None."""
    groups = content_duplicates(index)
    return {'policy': case.duplicates_policy, 'n_groups': len(groups),
            'n_rows': sum(len(g) for g in groups),
            'n_extra_rows': sum(len(g) - 1 for g in groups),
            'definition': 'records identical on every column, the target included'}


def _refuse_duplicates(index: RowIndex) -> None:
    groups = content_duplicates(index)
    if not groups:
        return
    extra = sum(len(g) - 1 for g in groups)
    reason = {'code': 'unsupported_capability', 'capability': CAPABILITY_DUPLICATES,
              'path': 'structure.duplicates', 'duplicate_groups': len(groups),
              'duplicate_rows': extra, 'examples': groups[:MAX_LISTED],
              'reason': f'{extra} records repeat the content of an earlier record. Row keys '
                        f'(source_line) cannot tell whether a copy is the same entity, so a '
                        f'split could place copies in both partitions. This version neither '
                        f'deduplicates nor groups them silently; a case may declare '
                        f'duplicates: {{policy: group}} to keep each group of copies whole.'}
    raise CaseError('unsupported_capability',
                    f'This case needs a capability that is not available yet: '
                    f'{CAPABILITY_DUPLICATES}', details={'reasons': [reason]})


def read_kwargs(case: Case) -> dict:
    """Arguments of ``pandas.read_csv`` that reproduce the case reading parameters."""
    d = case.dataset
    kwargs = {'sep': case.read_sep, 'encoding': d['encoding'], 'decimal': d['decimal'],
              'quotechar': d.get('quotechar', '"'), 'keep_default_na': False,
              'na_values': list(d.get('na_values', [])), 'skip_blank_lines': False}
    if d['header']:
        kwargs['header'] = 0
    else:
        kwargs.update(header=None, names=case.column_names)
    return kwargs


def read_frame(case: Case, index: RowIndex):
    """Every record of the verified dataset as a DataFrame indexed by ``row_key``, with no
    value check. Only :func:`load_dataset` and the final-test assignment at ``init``
    (:mod:`mlkit.study.partition`) call it."""
    import pandas as pd

    frame = pd.read_csv(case.dataset_path, **read_kwargs(case))
    if list(frame.columns) != case.column_names or len(frame) != len(index):
        raise CaseError('invalid_case', 'The parsed dataset does not match the case.',
                        problems=[{'path': 'dataset',
                                   'problem': f'parsed {len(frame)} rows and columns '
                                              f'{list(frame.columns)}; expected {len(index)} '
                                              f'rows and {case.column_names}'}])
    frame.index = pd.Index(index.keys, name=ROW_KEY_NAME)
    return frame


def restrict(index: RowIndex, rows) -> RowIndex:
    """The row index of the records ``rows`` only, in file order.

    A key that is not a record of the file is an ``integrity_error``: the recorded
    partition no longer describes this dataset."""
    wanted = set(rows)
    unknown = wanted - set(index.keys)
    if unknown:
        from .errors import StudyError
        raise StudyError('integrity_error', 'The recorded development rows are not records of '
                                            'this dataset.',
                         details={'unknown_rows': len(unknown),
                                  'dataset_sha256': index.dataset_sha256})
    pairs = [(k, h) for k, h in zip(index.keys, index.content_hashes) if k in wanted]
    return RowIndex(index.dataset_sha256, tuple(k for k, _ in pairs), tuple(h for _, h in pairs))


def load_dataset(case: Case, *, supported_only: bool = True, rows=None) -> Dataset:
    """Load the dataset as a DataFrame indexed by ``row_key``.

    With ``supported_only`` (the default), an unsupported case is refused first
    (``unsupported_capability``), before the data are read.

    ``rows`` (ADR 0006) restricts the dataset to those row keys: the frame and the row
    index hold them only, in file order, and values are checked on them only. Study
    activities never call this function directly: they go through
    :func:`load_development`, the single choke point that keeps the sealed final test
    out of every computation. ``rows=None`` reads every record (a legacy study without a
    final test, or a test of the reader itself).
    """
    if supported_only:
        require_supported(case)
    index = row_index(case)
    frame = read_frame(case, index)
    if rows is not None:
        index = restrict(index, rows)
        frame = frame.loc[list(index.keys)].copy()
    check_values(case, frame)
    return Dataset(case=case, index=index, frame=frame)


def load_development(case: Case, development) -> Dataset:
    """The development rows of a study (ADR 0006): the one function through which every
    activity reads the dataset.

    ``development`` is the list of development row keys of the study's sealed final-test
    partition, or ``None`` for a legacy study created before the partition existed (every
    row is then a development row: the study has no final test). The sealed final-test
    rows are dropped right after parsing; no caller receives them."""
    return load_dataset(case, rows=development)


def load_final_test(case: Case, final_test) -> Dataset:
    """The final-test rows of a study (WP-B1), read by one activity only:
    ``final_test.evaluation``, once, after the junior opened the final test in their words.
    Every other read goes through :func:`load_development`."""
    if final_test is None:
        from .errors import StudyError
        raise StudyError('integrity_error', 'This study has no final test to read.')
    return load_dataset(case, rows=final_test)


NUMBER_TYPES = ('numeric', 'integer')
CAPABILITY_MISSING_TARGET = 'missing target values (v0.2)'
MAX_EXAMPLES = 5


def _keys(mask) -> list[str]:
    return sorted(mask[mask].index, key=lambda k: int(k[1:]))


def check_values(case: Case, frame) -> None:
    """Refuse values that would silently change meaning (structural inspection).

    * A ``numeric`` or ``integer`` variable whose cells are not all numbers, once the case
      ``na_values`` are read as missing, is refused (``invalid_case``): pandas would read
      the column as text, and the models would one-hot encode it as a category.
    * A binary target holding a label other than the case labels (``positive_label`` and,
      when declared, ``negative_label``; otherwise at most one other label) is refused
      (``invalid_case``): every unexpected label would silently count as negative.
    * A missing target value (a cell matching ``na_values``) is refused
      (``unsupported_capability``, ``missing target values (v0.2)``): rows are neither
      dropped nor imputed silently.

    Only the structure is read: which cells parse and which labels occur, never a rate."""
    import pandas as pd
    from pandas.api.types import is_numeric_dtype

    problems = []
    for i, v in enumerate(case.document['variables']):
        column = frame[v['name']]
        if v['type'] in NUMBER_TYPES and not is_numeric_dtype(column):
            bad = column.notna() & pd.to_numeric(column, errors='coerce').isna()
            if not bad.any():
                # The non-number cells were in rows left out (the sealed final test, whose
                # own check counts them): these rows parse, so they are read as numbers.
                frame[v['name']] = pd.to_numeric(column)
                continue
            tokens = sorted({str(x) for x in column[bad]})
            problems.append({
                'path': f'variables[{i}].type',
                'problem': f'{v["name"]!r} is declared {v["type"]} but {int(bad.sum())} cells '
                           f'are not numbers: {", ".join(map(repr, tokens[:MAX_EXAMPLES]))} '
                           f'(first rows {", ".join(_keys(bad)[:MAX_EXAMPLES])}). Declare how '
                           f'such a cell is read (dataset.na_values, with a special value) or '
                           f'change the type; it is never read as a category silently.'})
    target = frame[case.target_column]
    if case.task == 'binary':
        labels = target.dropna().astype(str)
        positive_label = str(case.positive_label)
        negative = case.document['target'].get('negative_label')
        expected = {positive_label} | ({str(negative)} if negative is not None else set())
        others = sorted(set(labels) - expected)
        if negative is None and len(others) == 1:
            others = []
        if others or positive_label not in set(labels):
            counts = {label: int((labels == label).sum()) for label in others}
            problems.append({
                'path': 'target',
                'problem': (f'The target {case.target_column!r} holds labels other than '
                            f'{" and ".join(map(repr, sorted(expected)))}: '
                            + ', '.join(f'{label!r} ({n} rows)' for label, n in counts.items())
                            + '. Each would silently count as negative.') if others else
                           f'The positive label {positive_label!r} never occurs in '
                           f'{case.target_column!r}.'})
    if problems:
        raise CaseError('invalid_case', 'Some values would silently change meaning.',
                        problems=problems)
    missing = target.isna()
    if missing.any():
        keys = _keys(missing)
        reason = {'code': 'unsupported_capability', 'capability': CAPABILITY_MISSING_TARGET,
                  'path': 'target.column', 'column': case.target_column,
                  'rows': len(keys), 'examples': keys[:MAX_LISTED],
                  'reason': f'{len(keys)} rows have no value of the target '
                            f'{case.target_column!r}. This version neither drops nor imputes '
                            f'target rows silently.'}
        raise CaseError('unsupported_capability',
                        f'This case needs a capability that is not available yet: '
                        f'{CAPABILITY_MISSING_TARGET}', details={'reasons': [reason]})
