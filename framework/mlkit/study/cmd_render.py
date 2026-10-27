"""``hypotrail render`` and the automatic render after every commit (plan WP3.4).

    hypotrail render --study DIR

renders, under the writer lock and from one view (:func:`mlkit.study.view.build`):

1. ``notebooks/study_generated.py`` (regenerated, user edits archived),
   ``notebooks/study_editable.py`` (synced until its first user edit), and
   ``notebooks/workbench.py`` (created once) — :mod:`mlkit.study.render_notebook`;
2. ``reports/study.html`` — :mod:`mlkit.study.render_html`, written atomically;
3. ``.hypotrail/artifacts.json`` — :mod:`mlkit.study.manifest`.

Each artefact succeeds or fails on its own. When the HTML fails, the previous file is
kept and a stale banner is injected at ``<!--hypotrail:banner-->``; its manifest item
becomes ``failed`` with the error, and ``last_ok_revision`` keeps the last good
revision. Nothing ever claims that everything is up to date: the output lists each
artefact with its own status.

:func:`after_commit` is called by :func:`mlkit.study.commands.apply` after every
committed, non-replayed mutation. It never raises and never undoes the commit; a
``stale`` or ``failed`` artefact makes the command exit with code 3.

Fault injection for tests and acceptance scenarios: ``HYPOTRAIL_FAULT=render_html``
or ``render_notebook`` (comma-separated for both) is honoured **only** when
``HYPOTRAIL_TEST_HOOKS=1``.

Rendering modules are imported when a render runs, not when this module is imported;
Marimo only when the generated notebook text changes. No pandas, numpy, or scikit-learn.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from . import commands as cmd
from . import guard, manifest as mf
from .errors import StudyError
from .store import StudyStore

SCHEMA = 'hypotrail.render/1'
FAULT_ENV = 'HYPOTRAIL_FAULT'
HOOKS_ENV = 'HYPOTRAIL_TEST_HOOKS'
FAULTS = ('render_html', 'render_notebook')
ARTIFACT_NAMES = tuple(mf.ARTIFACTS)


class InjectedFault(RuntimeError):
    """A failure requested by ``HYPOTRAIL_FAULT`` under ``HYPOTRAIL_TEST_HOOKS=1``."""


def fault_requested(name: str) -> bool:
    if os.environ.get(HOOKS_ENV) != '1':
        return False
    return name in {f.strip() for f in os.environ.get(FAULT_ENV, '').split(',')}


def _inject(name: str) -> None:
    if fault_requested(name):
        raise InjectedFault(f'{FAULT_ENV}={name}: injected render failure (test hook)')


def _error(exc: BaseException) -> dict:
    if isinstance(exc, StudyError):
        return {'code': exc.code, 'message': exc.message}
    return {'code': 'render_failed', 'message': f'{type(exc).__name__}: {exc}'}


def _pseudo_state(view: dict) -> dict:
    """What :func:`manifest.effective_status` needs, taken from the view."""
    return {'revision': view['revision'],
            'current': {slot: r['result_id'] for slot, r in view['results'].items()},
            'stale': view['stale']}


def _variables(view: dict) -> list[dict]:
    """The case's variables for the report's dictionary; in a French study (L3, owner session
    2026-10-26, R4) with each description and group in French where the case gives them (the
    variable's ``labels.fr``, the translation sidecar recorded at ``init``: ``view.case_texts``)."""
    from . import case as c

    try:
        document = c.load_case(view['case']['path'], verify_data=False).document
        variables = list(document['variables'])
    except Exception:      # the report still renders without the variable dictionary
        return []
    if view.get('language') != 'fr':
        return variables
    groups = (view.get('case_texts') or {}).get('groups') or {}
    out = []
    for v in variables:
        french = dict(v)
        description = (v.get('labels') or {}).get('fr')
        if description:
            french['description'] = description
        group = (groups.get(v.get('group')) or {}).get('fr')
        if group:
            french['group'] = group
        out.append(french)
    return out


def sample_rows(study: Path, view: dict) -> dict | None:
    """The seeded step-1 sample of the report's data section (contract P1.9, CLI-CONTRACT
    §17.3): eight development rows drawn at random, target first, as recorded (text), with
    the seed (``{columns, rows, seed, target_shown}``).

    The same rows as ``hypotrail data`` (``partition.sample``), read with the standard library
    so that a render never imports pandas, and only those lines. Development rows only: the
    sealed final test is never read (ADR 0006). The target is shown only when the look is
    recorded (render records it first, :func:`render_all`). None when they cannot be read
    (the report then says so)."""
    from . import case as c, data as dt, exposure, read

    try:
        snapshot = read.open(study)
        entries = snapshot.exposure_records()
        drawn = exposure.current_sample(snapshot, snapshot.state, entries)
        if drawn is None:
            return None
        shown = bool(exposure.sample_records(entries, drawn['seed']))
        case = c.load_case(view['case']['path'], verify_data=False)
        lines = case.dataset_path.read_bytes().decode(case.dataset['encoding']).split('\n')
        first = 2 if case.dataset['header'] else 1
        body = lines[1:] if case.dataset['header'] else lines
        split = dt._field_splitter(case)
        names = case.column_names
        target = case.target_column
        columns = ([target] if shown else []) + [n for n in names if n != target]
        rows = []
        for key in drawn['row_keys']:
            fields = split(body[int(key[1:]) - first].rstrip('\r'))
            if len(fields) != len(names):
                return None
            record = dict(zip(names, fields))
            rows.append({'row_key': key, 'values': {col: record[col] for col in columns}})
        return {'columns': columns, 'rows': rows, 'seed': drawn['seed'],
                'target_shown': shown}
    except Exception:          # the report still renders, without the example rows
        return None


def _decision_marks(study: Path, view: dict) -> dict:
    """Contract P1.13: the decisions changed after an evaluation of the earlier value
    (``panel_digest.decision_marks``); empty when they cannot be read."""
    from . import panel_digest, read
    try:
        return panel_digest.decision_marks(read.open(study), view)
    except Exception:          # noqa: BLE001 - the report renders without the mark
        return {}


def _understanding(study: Path) -> str:
    """The understanding section (ADR 0008), empty when the study never enabled it."""
    from . import read
    state = read.load_state(study)
    if 'understanding' not in state:
        return ''
    from .understanding import render
    try:
        return render.section(study, state)
    except Exception:          # noqa: BLE001 - the report renders; status shows the review
        return ('<section class="card" id="understanding"><h2>Understanding and handover'
                '</h2><p>The review summary could not be read; run hypotrail understanding '
                'status.</p></section>')


def twin_view(study: Path, view: dict) -> dict | None:
    """v4 (R27): the study read in the other language (no write, no clock), for the second
    edition of the report: the plan, the limits and the next action in that language, the
    restatements the agent gave in it (``view.language_texts`` reads the summary's the same
    way). None when it cannot be built (the report then derives it from ``view``)."""
    from . import read, view as view_model
    try:
        snapshot = read.open(study)
        state = snapshot.state
        other = 'fr' if (view.get('language') or 'en') == 'en' else 'en'
        twin = read.Study.at_state(snapshot.study_dir, {**state, 'language': other})
        return view_model.build(twin)
    except Exception:
        return None


def _render_report(study: Path, view: dict, manifest: dict, surfaces: dict) -> dict:
    from . import render_html
    from .store import atomic_write

    item = mf.item(manifest, 'report', kind='html')
    path = study / mf.ARTIFACTS['report']
    try:
        _inject('render_html')
        with render_html.changed_after_validation_context(_decision_marks(study, view)):
            page, consumed = render_html.build(view, surfaces=surfaces,
                                               variables=_variables(view),
                                               sample=sample_rows(study, view),
                                               understanding=_understanding(study),
                                               twin=twin_view(study, view))
        data = page.encode('utf-8')
        atomic_write(path, data)
    except Exception as exc:
        error = _error(exc)
        try:
            banner = render_html.banner_html(report_revision=item.get('last_ok_revision'),
                                             failed_revision=view['revision'], error=error)
            if path.is_file():
                data = render_html.inject_banner(path.read_text(encoding='utf-8'), banner).encode('utf-8')
            else:
                data = render_html.failure_page(failed_revision=view['revision'],
                                                error=error).encode('utf-8')
            atomic_write(path, data)
            item['sha256'] = mf_sha(data)
        except Exception as inner:   # keep whatever is on disk
            error['banner_error'] = _error(inner)
        item.update(status='failed', revision=view['revision'], error=error)
        return item
    item.update(status='ok', revision=view['revision'], consumed=consumed, sha256=mf_sha(data),
                generated=True, template_version=render_html.TEMPLATE_VERSION, error=None,
                last_ok_revision=view['revision'])
    return item


def mf_sha(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _render_notebooks(study: Path, view: dict, manifest: dict) -> dict:
    try:
        _inject('render_notebook')
        from . import render_notebook

        out = render_notebook.render(study, view, manifest)
        return {'notebook': out['notebook'], 'editable': out['editable'],
                'workbench': out['workbench']}
    except Exception as exc:
        item = mf.item(manifest, 'notebook', kind='marimo_notebook')
        item.update(status='failed', revision=view['revision'], error=_error(exc))
        out = {'notebook': item}
        if manifest.get('artifacts', {}).get('workbench'):
            out['workbench'] = mf.item(manifest, 'workbench', kind='marimo_notebook',
                                       generated=False)
        if manifest.get('artifacts', {}).get('editable'):
            out['editable'] = mf.item(manifest, 'editable', kind='marimo_notebook',
                                      generated=False)
        return out


def render_all(study_dir) -> dict:
    """Render every artefact; return ``{revision, status, artifacts: {name: {...}}}``."""
    from . import lock, read, view as view_model
    from .store import StudyStore

    guard.assert_writable()
    study = Path(study_dir).resolve()
    snapshot = read.open(study)             # study_missing / integrity_error before locking
    if snapshot.source_changes():           # L1: never render from changed case bytes
        from .case import changed_sources_error
        raise changed_sources_error(snapshot.source_changes())
    # Marimo's code generator is imported by render_notebook only when the notebook text
    # changes (cached template); most commits render without importing it.
    with lock.writer_lock(study):
        # Contract P1.9: render is a write; a study created before the step-1 sample records
        # its look here when no write did, so the report shows the target it records.
        from . import exposure
        store = StudyStore(study)
        exposure.ensure_sample(store, store.load_state())
        view = view_model.build(study)
        manifest = mf.load(study)
        items = _render_notebooks(study, view, manifest)
        state = _pseudo_state(view)
        surfaces = {}
        for name, item in items.items():
            surfaces[name] = {'status': mf.effective_status(item, state),
                              'revision': item.get('revision'), 'error': item.get('error')}
            if item.get('generated') is False:
                surfaces[name]['tracked'] = False
        items['report'] = _render_report(study, view, manifest, surfaces)
        ordered = {name: items[name] for name in ARTIFACT_NAMES if name in items}
        statuses = [mf.effective_status(i, state) for i in ordered.values()]
        new = {'schema': mf.SCHEMA, 'revision': view['revision'], 'status': mf.overall(statuses),
               'artifacts': ordered}
        mf.save(study, new)
        failed = sorted(n for n, i in ordered.items() if i['status'] == 'failed')
        if failed:
            StudyStore(study).event('render_failed', revision=view['revision'], artifacts=failed,
                                    errors={n: ordered[n]['error'] for n in failed})
    return {'revision': view['revision'], 'status': new['status'],
            'artifacts': mf.summary(new, state, study)}


def _failed_everywhere(exc: BaseException, payload: dict | None = None) -> dict:
    error = _error(exc)
    revision = (payload or {}).get('revision')
    return {name: {'status': 'failed', 'path': mf.ARTIFACTS[name], 'revision': revision,
                   'last_ok_revision': None, 'error': error,
                   'message': f'Rendering failed at revision {revision} before any deliverable '
                              f'was written ({error["code"]}); whatever {mf.ARTIFACTS[name]} '
                              f'holds is not current.'}
            for name in ARTIFACT_NAMES}


def after_commit(study_dir: Path, payload: dict) -> dict:
    """Render after a committed mutation; never raises (the commit stands)."""
    try:
        return render_all(study_dir)['artifacts']
    except BaseException as exc:            # noqa: BLE001 - a render never undoes a commit
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return _failed_everywhere(exc, payload)


# --- CLI --------------------------------------------------------------------------------

def configure(parser: argparse.ArgumentParser) -> None:
    parser.description = ('Render the HTML report, the generated and editable notebooks, '
                          'and the workbench from the current study state.')
    # v0.3 (WP-J, R35): the study panel passes webview; recorded as an event, not a revision.
    parser.add_argument('--channel', default=None,
                        help='chat (the default), cli, or webview: where the render came from')


def record_channel(study_dir, action: str, channel: str | None, revision) -> None:
    """v0.3 (WP-J, R35): a render or an export started outside the chat is recorded as a
    ``channel_action`` event (``events.jsonl``), which the digest lists; a chat request
    records nothing."""
    from .executions import channel_param
    named = channel_param(channel)
    if named:
        StudyStore(Path(study_dir)).event('channel_action', action=action,
                                          channel=named['channel'], revision=revision)


def main(args: argparse.Namespace) -> cmd.Outcome:
    from .executions import channel_param
    channel_param(getattr(args, 'channel', None))      # refused before anything is written
    result = render_all(args.study)
    record_channel(args.study, 'render', getattr(args, 'channel', None), result['revision'])
    payload = {'schema': SCHEMA, 'ok': True, 'study': str(Path(args.study).resolve()),
               'revision': result['revision'], 'status': result['status'],
               'artifacts': result['artifacts']}
    bad = any(a['status'] in ('stale', 'failed') for a in result['artifacts'].values())
    return cmd.Outcome(payload, cmd.EXIT_ARTIFACT_STALE if bad else cmd.EXIT_OK)
