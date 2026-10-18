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
deduplicated silently.

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
    _refuse_duplicates(index)
    return index


def content_duplicates(index: RowIndex) -> list[list[str]]:
    """Groups of row keys whose records have identical content, in file order."""
    groups: dict[str, list[str]] = {}
    for key, digest in zip(index.keys, index.content_hashes):
        groups.setdefault(digest, []).append(key)
    return [keys for keys in groups.values() if len(keys) > 1]


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
                        f'deduplicates nor groups them silently.'}
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


def load_dataset(case: Case, *, supported_only: bool = True) -> Dataset:
    """Load the dataset as a DataFrame indexed by ``row_key``.

    With ``supported_only`` (the default), an unsupported case is refused first
    (``unsupported_capability``), before the data are read.
    """
    if supported_only:
        require_supported(case)
    index = row_index(case)
    import pandas as pd

    frame = pd.read_csv(case.dataset_path, **read_kwargs(case))
    if list(frame.columns) != case.column_names or len(frame) != len(index):
        raise CaseError('invalid_case', 'The parsed dataset does not match the case.',
                        problems=[{'path': 'dataset',
                                   'problem': f'parsed {len(frame)} rows and columns '
                                              f'{list(frame.columns)}; expected {len(index)} '
                                              f'rows and {case.column_names}'}])
    frame.index = pd.Index(index.keys, name=ROW_KEY_NAME)
    return Dataset(case=case, index=index, frame=frame)
