"""Append-only data-exposure log of a study (plan §3.5).

Every activity that reads data rows records which rows it read and why, in
``.hypotrail/exposure.jsonl``. Rows are identified by their row key (``L<line>``,
anchored to the dataset sha256), so the log stays meaningful when a derived column
is added or when the split changes. The row keys of one record are a content-
addressed blob (sorted, one key per line).

Purposes (``records.EXPOSURE_PURPOSES``): ``structural_inspection``, ``train_eda``,
``train_fit``, ``validation_model_evaluation``, ``validation_policy_selection``.

Nothing is ever removed: changing the split does not make explored rows unseen.
:func:`overlap` reports, for a new split, how many rows of each new partition were
already exposed and for which purpose. The study's ``prior_exposure`` (data published
before the study) is surfaced by :func:`summary` and never subtracted.

Call :func:`record` under the writer lock (see ``registry`` for the order of calls).
This module imports neither pandas, numpy, nor scikit-learn.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Iterable, Mapping

from . import records as rec
from .errors import StudyError
from .store import StudyStore, append_jsonl, read_jsonl

EXPOSURE_FILE = 'exposure.jsonl'
PARTITIONS = ('all', 'train', 'validation')


def new_exposure_id() -> str:
    return 'x_' + uuid.uuid4().hex


def _path(store: StudyStore):
    return store.home / EXPOSURE_FILE


def record(store: StudyStore, *, exposure_id: str, revision: int, activity: str,
           result_id: str | None, purpose: str, partition: str, row_keys: Iterable[str],
           dataset_sha256: str, columns: Iterable[str], execution_id: str | None = None) -> dict:
    """Append one exposure record and return it.

    ``result_id`` may be ``None`` for rows read by an execution whose result was never
    stored (for example an interrupted one): exposure is over-reported rather than
    lost.
    """
    if purpose not in rec.EXPOSURE_PURPOSES:
        raise StudyError('invalid_exposure', f'Unknown exposure purpose {purpose!r}.',
                         details={'purposes': list(rec.EXPOSURE_PURPOSES)})
    if partition not in PARTITIONS:
        raise StudyError('invalid_exposure', f'Unknown partition {partition!r}.',
                         details={'partitions': list(PARTITIONS)})
    if not isinstance(exposure_id, str) or not exposure_id.startswith('x_'):
        raise StudyError('invalid_exposure', 'exposure_id comes from new_exposure_id().')
    if any(r.get('exposure_id') == exposure_id for r in read_jsonl(_path(store))):
        raise StudyError('invalid_exposure', f'Exposure {exposure_id} is already recorded.')
    data = rec.row_keys_bytes(row_keys)
    entry = {'schema': rec.EXPOSURE_SCHEMA, 'exposure_id': exposure_id, 'revision': revision,
             'activity': activity, 'result_id': result_id, 'execution_id': execution_id,
             'purpose': purpose, 'partition': partition,
             'n_rows': len(rec.parse_row_keys(data)), 'row_keys': store.put_blob(data),
             'dataset_sha256': dataset_sha256, 'columns': list(columns),
             'time': dt.datetime.now(dt.timezone.utc).isoformat()}
    append_jsonl(_path(store), entry)
    return entry


def records(store: StudyStore) -> list[dict]:
    return read_jsonl(_path(store))


def rows(store: StudyStore, entry: Mapping) -> list[str]:
    """Row keys of one exposure record (verified blob)."""
    return rec.parse_row_keys(store.read_blob(entry['row_keys']))


def exposed_by_purpose(store: StudyStore) -> dict[str, set]:
    out: dict[str, set] = {}
    for entry in records(store):
        out.setdefault(entry['purpose'], set()).update(rows(store, entry))
    return out


def summary(store: StudyStore, state: Mapping | None = None) -> dict:
    """Distinct exposed rows by purpose and partition, plus ``prior_exposure``."""
    entries = records(store)
    keys = {e['exposure_id']: rows(store, e) for e in entries}
    return rec.summarize(entries, keys, (state or {}).get('prior_exposure'))


def overlap(old_split: Mapping, new_split: Mapping, *, store: StudyStore | None = None) -> dict:
    """See :func:`mlkit.study.records.overlap`; with ``store``, exposure is included."""
    return rec.overlap(old_split, new_split, exposed_by_purpose(store) if store else None)
