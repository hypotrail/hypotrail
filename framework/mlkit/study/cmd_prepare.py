"""``hypotrail prepare``: the six questions before a study is sealed (onboarding Lot 2,
``docs/plans/ONBOARDING-SPEC.md`` §2 and §3; CLI-CONTRACT §20).

    hypotrail new NAME --data FILE [--brief FILE] [--context TEXT | --context-file FILE]
                  [--lang en|fr]                                        (:func:`start`)
    hypotrail prepare status --study DIR
    hypotrail prepare answer QUESTION --value-json JSON
                  (--user-words TEXT | --user-words-file FILE) [--basis known|assumed|unknown]
                  --expected-revision REV --study DIR
    hypotrail prepare answer QUESTION --propose --source TEXT --value-json JSON
                  [--basis ...] --expected-revision REV --study DIR
    hypotrail prepare derive-clock --column DATE --date-format FMT [--name NAME]
                  [--user-words TEXT | --user-words-file FILE] --expected-revision REV
                  --study DIR                                           (:func:`derive_clock`)

:func:`start` creates two sibling folders. ``NAME.case/`` holds the copied data
(``data/FILE``, its sha256), the structural profile of every row (``profile.json``), the
draft (``case.draft.yaml`` with its ``todo``), the preparation record (``prepare.json``) and,
after ``seal``, ``case.yaml``. ``NAME/`` is the study folder the chat opens, in a
**preparing** state: ``.hypotrail/preparing.json`` names its case, the preparation agent
instructions are installed (``prepare_agent/``: a short ``CLAUDE.md`` and the on-demand skill
``hypotrail-prepare``), the brief's text is in ``brief/source.json``; there is no study state,
no partition and no case yet. The data never enter the study folder (no ``data`` link).

``prepare answer`` records one answer in the user's words, or with ``--propose`` a proposal
with its source (a brief page, the context, the column names). A proposal is never an
answer. ``exposure`` is answered first. ``final_test`` is the acceptance of the deduced final
test, shown in words and counts by ``prepare status``; it names the plan digest it accepts,
and any later change of an answer drops it. Writes reread ``prepare.json`` under the study
writer lock and refuse a stale ``--expected-revision``.

``prepare derive-clock`` is the way forward of a date offered as a clock (ADR 0006, the
derived-copy option; owner decision 2026-11-06): it writes ``data/<stem>.derived<suffix>``,
the current data file with one integer column appended, the day number since 1970-01-01 of
each date read with the explicit ``--date-format``, and records how it was derived. The copy of
the user's file is never changed; the row keys (physical lines) are unchanged. The case then
reads the derived file, and ``case.yaml`` documents the derived column and its source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from . import agent_files as af
from . import case_draft as cd
from . import commands as cmd
from .errors import StudyError

SCHEMA = 'hypotrail.prepare/1'
STATE_FILE = 'prepare.json'
STATE_SCHEMA = 'hypotrail.prepare-state/1'
MARKER = 'preparing.json'
MARKER_SCHEMA = 'hypotrail.preparing/1'
CASE_SUFFIX = '.case'
PREPARING, SEALING, SEALED = 'preparing', 'sealing', 'sealed'
AGENT_SOURCE = Path(__file__).resolve().parent / 'prepare_agent'
CLAUDE, COPILOT = 'claude', 'copilot'
AGENT_TARGETS = {
    'CLAUDE.md.in': (('CLAUDE.md', CLAUDE), ('.github/copilot-instructions.md', COPILOT)),
    'dot-claude/skills/hypotrail-prepare/SKILL.md': (
        ('.claude/skills/hypotrail-prepare/SKILL.md', CLAUDE),
        ('.github/skills/hypotrail-prepare/SKILL.md', COPILOT)),
}
SKILL_PATHS = {CLAUDE: '.claude/skills/hypotrail-prepare/SKILL.md',
               COPILOT: '.github/skills/hypotrail-prepare/SKILL.md'}
TITLES = {
    'exposure': {'en': 'Have you already explored this file?',
                 'fr': 'Avez-vous déjà exploré ce fichier ?'},
    'target': {'en': 'What is the target (and its positive label)?',
               'fr': 'Quelle est la cible (et sa valeur positive) ?'},
    'row_unit': {'en': 'What does one row represent?',
                 'fr': 'Que représente une ligne ?'},
    'timing': {'en': 'When is the prediction made, and is the use about the future?',
               'fr': 'Quand la prédiction est-elle faite, et l\'usage porte-t-il sur le futur ?'},
    'entities': {'en': 'Do entities recur (a customer, a vehicle, a patient)?',
                 'fr': 'Des entités reviennent-elles (un client, un véhicule, un patient) ?'},
    'final_test': {'en': 'Do you accept this final test?',
                   'fr': 'Acceptez-vous ce test final ?'},
}


# --- locating a preparation ---------------------------------------------------------------

def case_dir_for(study: Path) -> Path:
    return study.parent / f'{study.name}{CASE_SUFFIX}'


def _marker(study: Path) -> Path:
    from .lock import home_of
    return home_of(study) / MARKER


def locate(study) -> tuple[Path, Path]:
    """``(study, case_dir)`` of a study in preparation (or being sealed), else a refusal."""
    study = Path(study).resolve()
    marker = _marker(study)
    if not marker.is_file():
        from .store import StudyStore
        if StudyStore(study).exists():
            raise StudyError('precondition_missing', 'This study is sealed: preparation is '
                                                     'over. Use status and the study steps.',
                             details={'reason': 'already_sealed', 'study': str(study)})
        raise StudyError('study_missing', f'No study in preparation at {study}: start one '
                                          'with hypotrail new NAME --data FILE.',
                         details={'study': str(study)})
    record = json.loads(marker.read_text(encoding='utf-8'))
    return study, Path(record['case']).resolve()


def load(case_dir: Path) -> dict:
    return json.loads((case_dir / STATE_FILE).read_text(encoding='utf-8'))


def load_profile(case_dir: Path) -> dict:
    return json.loads((case_dir / cd.PROFILE_FILE).read_text(encoding='utf-8'))


def _write(case_dir: Path, record: Mapping) -> None:
    from .store import atomic_write_json
    atomic_write_json(case_dir / STATE_FILE, dict(record))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- the preparation agent instructions ---------------------------------------------------

def _agent_values(study: Path) -> dict:
    cli = af.cli_command()
    return {'HYPOTRAIL': cli['shell'], 'STUDY': af.quote_arg(str(study))}, cli


def install_agent(study: Path) -> dict:
    """Write the preparation instructions (never over an existing file) and
    ``.hypotrail/agent.json``; ``{target: sha256}`` of the files written."""
    from .store import atomic_write_json
    values, cli = _agent_values(study)
    written = {}
    for rel, targets in AGENT_TARGETS.items():
        text = (AGENT_SOURCE / rel).read_text(encoding='utf-8')
        for target, flavour in targets:
            dest = study / target
            if dest.exists():
                continue
            out = text
            for key, value in dict(values, SKILL=SKILL_PATHS[flavour],
                                   CHOICE_TOOL=af.CHOICE_TOOLS[flavour]).items():
                out = out.replace('{{' + key + '}}', value)
            if flavour == COPILOT:
                header = af.COPILOT_HEADER.format(source=f'mlkit/study/prepare_agent/{rel}')
                if out.startswith('---\n'):
                    end = out.index('\n---\n', 4) + len('\n---\n')
                    out = out[:end] + header + '\n' + out[end:]
                else:
                    out = header + '\n\n' + out
            dest.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(out)
            written[target] = _sha(dest)
    agent_file = study / '.hypotrail' / af.AGENT_FILE
    if not agent_file.exists():
        atomic_write_json(agent_file, {
            'schema': af.SCHEMA, 'study': str(study), 'cli': cli,
            'invocation': f'{cli["shell"]} <command> ... --study {af.quote_arg(str(study))}',
            'phase': PREPARING,
            'note': 'A study in preparation: run every hypotrail command with this invocation. '
                    'Replaced by the study record when hypotrail seal creates the study.'})
        written['.hypotrail/' + af.AGENT_FILE] = _sha(agent_file)
    return written


def remove_agent(study: Path, written: Mapping[str, str]) -> dict:
    """Remove the preparation instructions that are unchanged (an edited one is kept and
    reported), so ``init`` installs the study's own."""
    removed, kept = [], []
    for target, sha in written.items():
        path = study / target
        if path.is_file() and _sha(path) == sha:
            path.unlink()
            removed.append(target)
        elif path.exists():
            kept.append(target)
    for target in removed:
        parent = (study / target).parent
        while parent != study and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    return {'removed': sorted(removed), 'kept_edited': sorted(kept)}


# --- new --data ---------------------------------------------------------------------------

def start(name, data, *, brief=None, context: str | None = None,
          context_file=None, language: str = 'en') -> cmd.Outcome:
    """``hypotrail new NAME --data FILE``: the case folder ``NAME.case/`` and the study folder
    ``NAME/`` in a preparing state. Every refusal comes before the first write."""
    from . import cmd_brief, partition
    from . import state as st
    from .guard import assert_writable
    assert_writable()
    if language not in st.LANGUAGES:
        raise StudyError('invalid_arguments', f'language is one of {", ".join(st.LANGUAGES)}.')
    study = Path(name).resolve()
    case_dir = case_dir_for(study)
    if (study / '.hypotrail').exists() or (study.exists() and any(study.iterdir())):
        raise StudyError('state_exists', f'{study} already exists and is not empty; a study '
                                         'is never created over another folder.',
                         details={'study': str(study)})
    if case_dir.exists():
        raise StudyError('state_exists', f'{case_dir} already exists; it is never overwritten.',
                         details={'case': str(case_dir)})
    if context is not None and context_file is not None:
        raise StudyError('invalid_arguments', '--context and --context-file are exclusive.')
    if context_file is not None:
        context = Path(context_file).read_text(encoding='utf-8')
    if context is not None and not context.strip():
        raise StudyError('invalid_arguments', 'The context is empty.')
    if brief is not None and context is not None:
        raise StudyError('invalid_arguments', 'Give a brief or a context, not both: the brief '
                                              'is the source the answers cite.')
    data = Path(data)
    table = cd.read_table(data)
    rows = len(table['rows'])
    lowest = int(-(-partition.MIN_FINAL_ROWS // partition.FRACTION_RANGE[1]))
    if rows < lowest:
        raise cd.refused('unsupported_capability',
                         f'{data.name} holds {rows} rows. A final test needs at least '
                         f'{partition.MIN_FINAL_ROWS} rows and at most '
                         f'{partition.FRACTION_RANGE[1]:.0%} of the file, so no final test '
                         f'can be set aside from fewer than {lowest} rows. Gather more rows '
                         'before starting a study.', 'too_few_rows', rows=rows,
                         minimum=lowest)
    extracted = cmd_brief.extract_document(Path(brief)) if brief is not None else None
    case_id = cd.slug(study.name)
    data_path = f'{cd.DATA_DIR}/{data.name}'
    (case_dir / cd.DATA_DIR).mkdir(parents=True)
    copy = case_dir / data_path
    copy.write_bytes(data.read_bytes())
    if _sha(copy) != table['sha256']:
        raise StudyError('integrity_error', 'The data copy differs from the file read.')
    prof = cd.profile(table, data_path)
    from .store import atomic_write_json
    atomic_write_json(case_dir / cd.PROFILE_FILE, prof)
    import yaml
    (case_dir / cd.DRAFT_FILE).write_text(
        yaml.safe_dump(cd.draft(prof, case_id, data_path), sort_keys=False,
                       allow_unicode=True, width=100), encoding='utf-8')
    study.mkdir(parents=True, exist_ok=True)
    (study / '.hypotrail').mkdir()
    brief_record = None
    if extracted is not None:
        raw, pages, kind = extracted
        cmd_brief.write_source(study, Path(brief), raw, pages, kind)
        brief_record = {'kind': kind, 'file': f'{cmd_brief.FOLDER}/{Path(brief).name}',
                        'units': len(pages), 'sha256': hashlib.sha256(raw).hexdigest()}
    elif context is not None:
        folder = study / cmd_brief.FOLDER
        folder.mkdir()
        path = folder / cmd_brief.CONTEXT_FILE
        path.write_text(context.strip() + '\n', encoding='utf-8')
        raw = path.read_bytes()
        pages = cmd_brief.text_pages(raw.decode('utf-8'))
        cmd_brief.write_source(study, path, raw, pages, cmd_brief.CONTEXT_KIND)
        brief_record = {'kind': cmd_brief.CONTEXT_KIND,
                        'file': f'{cmd_brief.FOLDER}/{cmd_brief.CONTEXT_FILE}',
                        'units': len(pages), 'sha256': hashlib.sha256(raw).hexdigest()}
    written = install_agent(study)
    atomic_write_json(_marker(study), {'schema': MARKER_SCHEMA, 'case': str(case_dir),
                                       'created': st.now(), 'agent_files': written})
    record = {'schema': STATE_SCHEMA, 'status': PREPARING, 'revision': 1, 'case_id': case_id,
              'title': study.name, 'language': language, 'study': str(study),
              'created': st.now(),
              'data': {'original': str(data.resolve()), 'path': data_path,
                       'sha256': table['sha256']},
              'profile_sha256': _sha(case_dir / cd.PROFILE_FILE), 'brief': brief_record,
              'answers': {}, 'proposals': {}, 'history': [], 'sealed': None}
    _write(case_dir, record)
    out = status_payload(study, case_dir, command='new')
    out['created'] = {'study': str(study), 'case': str(case_dir), 'data': str(copy),
                      'agent_files': sorted(written)}
    return cmd.Outcome(out)


# --- status ---------------------------------------------------------------------------------

def _answered(record: Mapping) -> dict:
    return {q: a for q, a in record['answers'].items()}


def status_payload(study: Path, case_dir: Path, *, command: str = 'prepare status',
                   feasibility: bool = True) -> dict:
    from . import cmd_case
    record = load(case_dir)
    prof = load_profile(case_dir)
    lang = record['language']
    answers = _answered(record)
    target = ((answers.get('target') or {}).get('value') or {}).get('column')
    questions = []
    for q in cd.QUESTIONS:
        answer, proposal = answers.get(q), record['proposals'].get(q)
        questions.append({
            'id': q, 'title': TITLES[q][lang],
            'status': 'answered' if answer else ('proposed' if proposal else 'missing'),
            'value': (answer or proposal or {}).get('value'),
            'basis': (answer or proposal or {}).get('basis'),
            'source': (proposal or {}).get('source') if not answer else
                      answer.get('proposed_from'),
            'user_words': (answer or {}).get('user_words')})
    pending = [q['id'] for q in questions if q['status'] != 'answered']
    final = None
    if feasibility and all(q in answers for q in cd.QUESTIONS[:-1]):
        final = cmd_case.feasibility(case_dir, record, prof)
    brief = record.get('brief')
    if brief:
        brief = dict(brief, source=str(study / 'brief' / 'source.json'))
    hyp = _hyp(study)
    out = {'schema': SCHEMA, 'ok': True, 'command': command, 'study': str(study),
           'case': str(case_dir), 'state': record['status'], 'revision': record['revision'],
           'language': lang, 'rows': prof['rows'], 'columns': cd.column_view(prof, target),
           'duplicates': prof['duplicates'], 'suspicious': cd.suspicious(prof, target),
           'brief': brief, 'questions': questions,
           'next_question': pending[0] if pending else None,
           'final_test': final, 'sealed': record.get('sealed'),
           'reveals': prof['reveals']}
    if record['status'] != PREPARING:
        out['next'] = None
    elif not pending:
        out['next'] = f'{hyp} seal --expected-revision {record["revision"]} --study ' \
                      f'{af.quote_arg(str(study))}'
    else:
        out['next'] = (f'{hyp} prepare answer {pending[0]} --value-json \'...\' --user-words '
                       f'"<the user\'s words>" --expected-revision {record["revision"]} '
                       f'--study {af.quote_arg(str(study))}')
    return out


def _hyp(study: Path) -> str:
    try:
        record = json.loads((study / '.hypotrail' / 'agent.json').read_text(encoding='utf-8'))
        return record['cli']['shell']
    except (OSError, ValueError, KeyError, TypeError):
        return 'hypotrail'


# --- answer -----------------------------------------------------------------------------------

def _words(args) -> str | None:
    if args.user_words is not None and args.user_words_file is not None:
        raise StudyError('invalid_arguments', '--user-words and --user-words-file are '
                                              'exclusive.')
    if args.user_words_file is not None:
        return Path(args.user_words_file).read_text(encoding='utf-8').strip()
    return args.user_words


def answer(study, question: str, value: Any, *, user_words: str | None, propose: bool,
           source: str | None, basis: str | None, expected_revision: int) -> cmd.Outcome:
    from . import confirm as cf
    from . import lock
    from . import state as st
    from .guard import assert_writable
    assert_writable()
    study, case_dir = locate(study)
    if question not in cd.QUESTIONS:
        raise StudyError('invalid_arguments', f'QUESTION is one of {", ".join(cd.QUESTIONS)}.')
    if basis is not None and basis not in cd.BASES:
        raise StudyError('invalid_arguments', f'--basis is one of {", ".join(cd.BASES)}.')
    if propose:
        if user_words is not None:
            raise StudyError('invalid_arguments', 'A proposal has no user words: it is the '
                                                  "agent's, with its source.")
        if not source or not source.strip():
            raise StudyError('invalid_arguments', 'A proposal names its source (--source: a '
                                                  'brief page, "context", or "column names '
                                                  'and structural profile").')
        if question == 'final_test':
            raise StudyError('invalid_arguments', 'The final test is accepted in the user\'s '
                                                  'words; it is never proposed.')
    else:
        if source is not None:
            raise StudyError('invalid_arguments', '--source goes with --propose.')
        if not isinstance(user_words, str) or not user_words.strip():
            raise StudyError('ambiguous_confirmation', "An answer is recorded with the user's "
                                                       'own words (--user-words).',
                             details={'reason': 'missing_user_words'})
        if cf.is_question(user_words):
            raise StudyError('ambiguous_confirmation', 'These words are a question: answer '
                                                       'it, then ask again.',
                             details={'reason': 'question_reply', 'user_words': user_words})
    with lock.writer_lock(study):
        record = load(case_dir)
        if record['status'] != PREPARING:
            raise StudyError('precondition_missing', f'The preparation is {record["status"]}.',
                             details={'reason': record['status']})
        if expected_revision != record['revision']:
            raise StudyError('stale_revision', 'The preparation changed since you read it: '
                                               'read prepare status again.',
                             details={'expected_revision': expected_revision,
                                      'current_revision': record['revision']})
        prof = load_profile(case_dir)
        answers = record['answers']
        if not propose and question != 'exposure' and 'exposure' not in answers:
            raise StudyError('precondition_missing', 'Ask first whether the user has already '
                                                     'explored this file (exposure).',
                             details={'reason': 'exposure_first',
                                      'missing': [{'requirement': 'exposure_answered'}]})
        normalised = cd.check_answer(question, value, prof, answers)
        revision = record['revision'] + 1
        time = st.now()
        if question == 'final_test':
            missing = [q for q in cd.QUESTIONS[:-1] if q not in answers]
            if missing:
                raise StudyError('precondition_missing', 'The final test is shown once the '
                                                         'other five questions are answered.',
                                 details={'reason': 'questions_missing', 'missing': missing})
            from . import cmd_case
            final = cmd_case.feasibility(case_dir, record, prof)
            if final['status'] != 'pass':
                raise StudyError('precondition_missing', 'This final test cannot be accepted: '
                                                         + '; '.join(final['problems']),
                                 details={'reason': 'feasibility_failed', 'feasibility': final})
            if normalised['plan'] != final['plan']:
                raise StudyError('stale_revision', 'The plan accepted is not the current one: '
                                                   'show prepare status again.',
                                 details={'reason': 'plan_changed', 'plan': final['plan']})
        if propose:
            record['proposals'][question] = {'value': normalised, 'source': source.strip(),
                                             'basis': basis or 'assumed', 'revision': revision,
                                             'time': time}
            action = 'propose'
        else:
            proposal = record['proposals'].pop(question, None)
            entry = {'value': normalised, 'basis': basis or 'assumed',
                     'user_words': user_words.strip(), 'revision': revision, 'time': time,
                     'proposed_from': (proposal['source'] if proposal
                                       and proposal['value'] == normalised else None)}
            previous = answers.get(question)
            answers[question] = entry
            action = 'answer'
            if question != 'final_test' and 'final_test' in answers and (
                    previous is None or previous['value'] != normalised
                    or previous['basis'] != entry['basis']):
                answers.pop('final_test')
                record['history'].append({'revision': revision, 'question': 'final_test',
                                          'action': 'dropped', 'because': question})
        record['history'].append({'revision': revision, 'question': question,
                                  'action': action, 'time': time})
        record['revision'] = revision
        _write(case_dir, record)
    out = status_payload(study, case_dir, command='prepare answer')
    out['recorded'] = {'question': question, 'action': action, 'value': normalised}
    return cmd.Outcome(out)


# --- derive-clock -----------------------------------------------------------------------------

EPOCH = 'days since 1970-01-01'
DERIVED_INFIX = '.derived'
_NAME = __import__('re').compile(r'[A-Za-z_][A-Za-z0-9_]*')
_DIRECTIVES = __import__('re').compile(r'%(.)')
_ALLOWED_DIRECTIVES = set('YmdHMS%')


def _check_format(fmt: str) -> None:
    used = _DIRECTIVES.findall(fmt)
    unknown = sorted(set(used) - _ALLOWED_DIRECTIVES)
    missing = [d for d in 'Ymd' if d not in used]
    if unknown or missing or any(used.count(d) > 1 for d in 'YmdHMS'):
        raise cd.refused('invalid_value',
                         f'--date-format {fmt!r}: a date format names the year, the month and the '
                         'day once each (%Y, %m, %d), and may add a time of day (%H, %M, %S); '
                         'other directives (such as %y, a two-digit year, or a month name) '
                         'are not read.', 'clock_format', format=fmt, unknown=unknown,
                         missing=missing)


def _days(cells: list[str], fmt: str) -> tuple[list[str], list[int]]:
    """The day numbers of ``cells`` (empty stays empty) and the 2-based lines that do not
    match ``fmt``."""
    from datetime import datetime
    epoch = datetime(1970, 1, 1)
    out, bad = [], []
    for i, cell in enumerate(cells):
        if cell == '':
            out.append('')
            continue
        try:
            moment = datetime.strptime(cell, fmt)
        except ValueError:
            bad.append(i + 2)
            out.append('')
            continue
        out.append(str((moment.replace(hour=0, minute=0, second=0) - epoch).days))
    return out, bad


def _append_column(raw: bytes, sep: str, name: str, values: list[str]) -> bytes:
    """``raw`` with ``name`` and ``values`` appended to its physical lines (header first);
    every other byte is kept (a byte-order mark, the line ends, the quoting)."""
    import codecs
    bom = codecs.BOM_UTF8 if raw.startswith(codecs.BOM_UTF8) else b''
    text = raw[len(bom):].decode('utf-8')
    lines = text.split('\n')
    trailing = lines and lines[-1] == ''
    if trailing:
        lines.pop()
    if len(lines) != len(values) + 1:
        raise StudyError('integrity_error', 'The data file changed while it was read.')
    out = []
    for line, value in zip(lines, [name, *values]):
        end = '\r' if line.endswith('\r') else ''
        out.append((line[:-1] if end else line) + sep + value + end)
    return bom + ('\n'.join(out) + ('\n' if trailing else '')).encode('utf-8')


def derive_clock(study, column: str, fmt: str, *, name: str | None, user_words: str | None,
                 expected_revision: int) -> cmd.Outcome:
    """Append to a derived copy of the data the day number of a date column (ADR 0006: an
    integer column derived from the date in a documented copy), so it can be a clock."""
    from . import confirm as cf
    from . import lock
    from . import state as st
    from .guard import assert_writable
    from .store import atomic_write, atomic_write_json
    assert_writable()
    study, case_dir = locate(study)
    _check_format(fmt)
    name = name or f'{column}_day'
    if not _NAME.fullmatch(name):
        raise cd.refused('invalid_value', f'--name {name!r}: a derived column name is letters, '
                                          'digits and underscores, starting with a letter.',
                         'clock_name', name=name)
    if user_words is not None:
        if not user_words.strip():
            raise StudyError('invalid_arguments', 'The user words are empty.')
        if cf.is_question(user_words):
            raise StudyError('ambiguous_confirmation', 'These words are a question: answer '
                                                       'it, then ask again.',
                             details={'reason': 'question_reply', 'user_words': user_words})
    with lock.writer_lock(study):
        record = load(case_dir)
        if record['status'] != PREPARING:
            raise StudyError('precondition_missing', f'The preparation is {record["status"]}.',
                             details={'reason': record['status']})
        if expected_revision != record['revision']:
            raise StudyError('stale_revision', 'The preparation changed since you read it: '
                                               'read prepare status again.',
                             details={'expected_revision': expected_revision,
                                      'current_revision': record['revision']})
        prof = load_profile(case_dir)
        by_name = {c['name']: c for c in prof['variables']}
        if column not in by_name:
            raise cd.refused('invalid_value', f'{column!r} is not a column of the file.',
                             'unknown_column', column=column)
        if name in by_name:
            raise cd.refused('invalid_value', f'{name!r} is already a column of the file: name '
                                              'the derived column with --name.',
                             'clock_name_taken', name=name)
        target = ((record['answers'].get('target') or {}).get('value') or {}).get('column')
        if column == target:
            raise cd.refused('invalid_value', 'The target cannot date the rows.',
                             'clock_is_target', column=column)
        current = case_dir / record['data']['path']
        if _sha(current) != record['data']['sha256']:
            raise StudyError('integrity_error', f'{record["data"]["path"]} differs from the '
                                                'file the preparation recorded.')
        table = cd.read_table(current)
        cells = [row[table['header'].index(column)] for row in table['rows']]
        values, bad = _days(cells, fmt)
        if bad:
            examples = [cells[line - 2] for line in bad[:MAX_SHOWN]]
            raise cd.refused('invalid_value',
                             f'{len(bad)} cells of {column!r} do not match --date-format {fmt!r} '
                             f'(lines {", ".join(map(str, bad[:MAX_SHOWN]))}: '
                             f'{", ".join(map(repr, examples))}). Nothing was written.',
                             'clock_unparsed', column=column, format=fmt, count=len(bad),
                             lines=bad[:MAX_SHOWN])
        swapped = fmt.replace('%d', '\0').replace('%m', '%d').replace('\0', '%m')
        other, other_bad = _days(cells, swapped)
        if not other_bad and other != values and user_words is None:
            raise StudyError('ambiguous_confirmation',
                             f'Every cell of {column!r} also reads with {swapped!r}, with other '
                             'dates: the day and the month cannot be told apart from the '
                             'values. Ask the user which comes first and record their words '
                             '(--user-words).',
                             details={'reason': 'ambiguous_format', 'format': fmt,
                                      'also': swapped, 'column': column})
        original = Path(record['data']['path'])
        stem = original.name.split(DERIVED_INFIX, 1)[0] if DERIVED_INFIX in original.name \
            else original.stem
        derived_path = f'{cd.DATA_DIR}/{stem}{DERIVED_INFIX}{original.suffix}'
        raw = _append_column(current.read_bytes(), table['sep'], name, values)
        target_file = case_dir / derived_path
        atomic_write(target_file, raw)
        new_table = cd.read_table(target_file)
        if new_table['rows'] and [r[:-1] for r in new_table['rows']] != table['rows']:
            raise StudyError('integrity_error', 'The derived copy does not keep the rows.')
        new_prof = cd.profile(new_table, derived_path)
        atomic_write_json(case_dir / cd.PROFILE_FILE, new_prof)
        import yaml
        (case_dir / cd.DRAFT_FILE).write_text(
            yaml.safe_dump(cd.draft(new_prof, record['case_id'], derived_path),
                           sort_keys=False, allow_unicode=True, width=100), encoding='utf-8')
        revision = record['revision'] + 1
        time = st.now()
        entry = {'column': name, 'from': column, 'format': fmt, 'rule': EPOCH,
                 'empty': sum(1 for v in values if v == ''),
                 'from_file': record['data']['path'], 'from_sha256': record['data']['sha256'],
                 'file': derived_path, 'sha256': new_table['sha256'],
                 'user_words': user_words.strip() if user_words else None,
                 'revision': revision, 'time': time}
        record.setdefault('derived', []).append(entry)
        record['data'] = dict(record['data'], path=derived_path, sha256=new_table['sha256'])
        record['profile_sha256'] = _sha(case_dir / cd.PROFILE_FILE)
        if 'final_test' in record['answers']:
            record['answers'].pop('final_test')
            record['history'].append({'revision': revision, 'question': 'final_test',
                                      'action': 'dropped', 'because': 'derive-clock'})
        record['history'].append({'revision': revision, 'action': 'derive-clock',
                                  'column': name, 'from': column, 'time': time})
        record['revision'] = revision
        _write(case_dir, record)
    out = status_payload(study, case_dir, command='prepare derive-clock')
    out['derived'] = entry
    return cmd.Outcome(out)


MAX_SHOWN = 5


# --- CLI ------------------------------------------------------------------------------------

def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('verb', choices=('status', 'answer', 'derive-clock'),
                        help='status: what is answered, proposed and missing; answer: record '
                             "one answer in the user's words, or a proposal with its source; "
                             'derive-clock: add the day number of a date column to a derived '
                             'copy of the data, so it can be a clock')
    parser.add_argument('question', nargs='?', default=None, choices=cd.QUESTIONS,
                        help='with answer: the question')
    parser.add_argument('--value-json', default=None, help='with answer: the value (JSON)')
    parser.add_argument('--user-words', default=None,
                        help="with answer: the user's words, verbatim")
    parser.add_argument('--user-words-file', default=None,
                        help="with answer: a UTF-8 file holding the user's words, verbatim")
    parser.add_argument('--propose', action='store_true',
                        help='with answer: record a proposal (with --source), not an answer')
    parser.add_argument('--source', default=None,
                        help='with --propose: where it comes from (a brief page, "context", '
                             '"column names and structural profile")')
    parser.add_argument('--basis', choices=cd.BASES, default=None,
                        help='how the user knows it: known (a fact they state), assumed (the '
                             'default), unknown')
    parser.add_argument('--expected-revision', type=int, default=None,
                        help='with answer and derive-clock: the revision prepare status gave')
    parser.add_argument('--column', default=None,
                        help='with derive-clock: the date column')
    parser.add_argument('--date-format', dest='date_format', default=None,
                        help='with derive-clock: how its dates are written, e.g. %%Y-%%m-%%d or '
                             '%%d/%%m/%%Y (%%Y, %%m and %%d required; %%H, %%M, %%S allowed)')
    parser.add_argument('--name', default=None,
                        help='with derive-clock: the derived column (default COLUMN_day)')


def main(args: argparse.Namespace) -> cmd.Outcome:
    clock_args = (args.column, args.date_format, args.name)
    if args.verb == 'status':
        if args.question or args.value_json or args.expected_revision is not None \
                or any(a is not None for a in clock_args):
            raise StudyError('invalid_arguments', 'prepare status takes only --study.')
        study, case_dir = locate(args.study)
        return cmd.Outcome(status_payload(study, case_dir))
    if args.verb == 'derive-clock':
        if args.question or args.value_json or args.propose or args.source or args.basis:
            raise StudyError('invalid_arguments', 'prepare derive-clock takes --column, '
                                                  '--date-format, [--name], [--user-words] and '
                                                  '--expected-revision.')
        if args.column is None or args.date_format is None or args.expected_revision is None:
            raise StudyError('invalid_arguments', 'prepare derive-clock takes --column, '
                                                  '--date-format and --expected-revision.')
        return derive_clock(args.study, args.column, args.date_format, name=args.name,
                            user_words=_words(args), expected_revision=args.expected_revision)
    if any(a is not None for a in clock_args):
        raise StudyError('invalid_arguments', '--column, --date-format and --name go with '
                                              'derive-clock.')
    if args.question is None or args.value_json is None or args.expected_revision is None:
        raise StudyError('invalid_arguments', 'prepare answer takes QUESTION, --value-json and '
                                              '--expected-revision.')
    try:
        value = json.loads(args.value_json)
    except ValueError as exc:
        raise StudyError('invalid_arguments', f'--value-json is not valid JSON: {exc}') from exc
    return answer(args.study, args.question, value, user_words=_words(args),
                  propose=args.propose, source=args.source, basis=args.basis,
                  expected_revision=args.expected_revision)
