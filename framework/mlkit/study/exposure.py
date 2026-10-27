"""Append-only data-exposure log of a study (plan §3.5).

Every activity that reads data rows records which rows it read and why, in
``.hypotrail/exposure.jsonl``. Rows are identified by their row key (``L<line>``,
anchored to the dataset sha256), so the log stays meaningful when a derived column
is added or when the split changes. The row keys of one record are a content-
addressed blob (sorted, one key per line).

Purposes (``records.EXPOSURE_PURPOSES``): ``structural_inspection``, ``train_eda``,
``train_fit``, ``validation_model_evaluation``, ``validation_policy_selection``, and
``sealed`` (ADR 0006): the final-test rows set aside at ``init``, whose cells only a
counts-only schema check read. Sealed rows are listed, never counted as exposed
(``rows_exposed``).

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
# ``development`` and ``final_test`` (ADR 0006): a study with a sealed final test records
# its structural inspection on the development rows and its final-test rows as ``sealed``;
# ``all`` stays for a study created before it.
PARTITIONS = ('all', 'train', 'validation', 'development', 'final_test')


def new_exposure_id() -> str:
    return 'x_' + uuid.uuid4().hex


def _path(store: StudyStore):
    return store.home / EXPOSURE_FILE


def record(store: StudyStore, *, exposure_id: str, revision: int, activity: str,
           result_id: str | None, purpose: str, partition: str, row_keys: Iterable[str],
           dataset_sha256: str, columns: Iterable[str], execution_id: str | None = None,
           sample_seed: str | None = None) -> dict:
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
    if sample_seed is not None:
        # Contract P1.9: the optional key (``records.EXPOSURE_OPTIONAL_KEYS``), last.
        entry['sample_seed'] = sample_seed
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


# --- the seeded step-1 sample (CLI-CONTRACT §17.3, contract P1.9) ---------------------------

SAMPLE_PURPOSE = 'development_target_sample'
SAMPLE_ACTIVITY = 'data.sample'
STRUCTURAL_PURPOSE = 'structural_inspection'
# The ledger entry's note (``texts.*.sample_note``, ``evidence.exposure.ledger``).
SAMPLE_NOTE = {
    'en': "These eight rows' target values were shown at step 1, before the split. They stay "
          'counted as seen: with cross-validation they later fall in validation folds; with a '
          'holdout split, those in the validation rows were seen before.',
    'fr': "Les valeurs de la cible de ces huit lignes ont été montrées à l'étape 1, avant le "
          'découpage. Elles restent comptées comme vues : avec la validation croisée, elles '
          'tombent ensuite dans des blocs de validation ; avec un échantillon réservé, celles '
          'qui sont dans la validation ont été vues avant.'}


def sample_note(lang: str = 'en') -> str:
    """:data:`SAMPLE_NOTE` in ``lang`` (English for another language)."""
    return SAMPLE_NOTE.get(lang, SAMPLE_NOTE['en'])


def sample_records(entries: Iterable[Mapping], seed: str | None = None) -> list[Mapping]:
    """The ``development_target_sample`` records of ``entries`` (of ``seed`` when given)."""
    return [e for e in entries if e.get('purpose') == SAMPLE_PURPOSE
            and (seed is None or e.get('sample_seed') == seed)]


def _structural(entries: Iterable[Mapping]) -> list[Mapping]:
    return [e for e in entries if e.get('purpose') == STRUCTURAL_PURPOSE]


def current_sample(store, state: Mapping, entries: list[Mapping] | None = None) -> dict | None:
    """``{seed, row_keys}`` of the study's step-1 sample, or None when no row can be listed
    (``partition.sample``). ``store`` reads blobs (a :class:`StudyStore` or a
    ``read.Study``, whose ``blob`` reads them). Row keys only: no data value is read. A study
    without a final test draws from the rows its structural inspection recorded at ``init``."""
    from . import partition
    read_blob = getattr(store, 'read_blob', None) or store.blob
    if entries is None:
        entries = records(store) if isinstance(store, StudyStore) else store.exposure_records()

    def every_key():
        keys: set = set()
        for entry in _structural(entries):
            keys.update(rec.parse_row_keys(read_blob(entry['row_keys'])))
        return sorted(keys, key=lambda k: int(str(k)[1:])) if keys else None
    try:
        return partition.sample(state, read_blob, every_key)
    except (StudyError, KeyError, OSError, ValueError):
        return None


def ensure_sample(store: StudyStore, state: Mapping | None = None) -> dict | None:
    """Record the look at the step-1 sample's target values, once per seed (contract P1.9):
    ``init`` for every study it creates, and the first write command of a study created
    before (``decide``, ``run``, ``render``, ``mode set``, ``automation run``), before its own
    work. Call under the writer lock; ``state`` is read when not given. Returns the new
    record, or None when the seed's record exists already or no sample can be drawn. A read
    never calls it."""
    from . import partition
    if state is None:
        state = store.load_state()
    entries = records(store)
    drawn = current_sample(store, state, entries)
    if drawn is None or sample_records(entries, drawn['seed']):
        return None
    structural = _structural(entries)
    if not structural:
        return None
    # Every case column, the target included, as ``init`` recorded them.
    columns = list(structural[0].get('columns') or [])
    part = partition.DEVELOPMENT if partition.of(state) is not None else 'all'
    return record(store, exposure_id=new_exposure_id(), revision=state['revision'],
                  activity=SAMPLE_ACTIVITY, result_id=None, purpose=SAMPLE_PURPOSE,
                  partition=part, row_keys=drawn['row_keys'],
                  dataset_sha256=state['dataset']['sha256'], columns=columns,
                  sample_seed=drawn['seed'])


def ensure_sample_locked(study_dir) -> dict | None:
    """:func:`ensure_sample` under the writer lock, for a write command that takes the lock
    itself afterwards. A study that cannot be read is left to the command's own refusal."""
    store = StudyStore(study_dir)
    if not store.exists():
        return None
    with store.writing() as state:
        return ensure_sample(store, state)
