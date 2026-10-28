"""``hypotrail brief``: start a study from the product owner's PDF (owner remark R68, minimal
version decided on 2026-10-28; CLI-CONTRACT §19).

    hypotrail brief import --study DIR --pdf FILE --expected-revision REV [--request-id ID]
    hypotrail brief set --study DIR --file DRAFT.yaml --user-words TEXT
                        --expected-revision REV [--request-id ID]

``import`` extracts the text of the PDF page by page (``pypdf``, deterministic, no language
model), records the PDF (name, SHA-256, page count) in ``state.brief.source`` through the
normal store path (a stale revision is refused), then writes ``brief/source.json``
(``{schema, pdf, sha256, pages [{n, text}]}``) and a copy of the PDF in the study's
``brief/`` folder. It decides nothing and renders nothing.

``set`` validates a draft written by the chat agent (the fields of ``case-brief.yaml`` plus
``citations`` and ``open_questions``, :func:`case_brief.validate_draft`) against the pages
of the imported PDF, and records it in ``state.brief.confirmed`` with the junior's words.
From then the study's brief replaces the use case's own one (digest, report, panel). It is
the only thing taken from the PDF: target, prediction moment and availability stay the
study's own steps.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
from pathlib import Path

import yaml

from mlkit.reliability import CommandRefused, Handler

from . import case_brief as cb
from . import commands as cmd
from . import confirm as cf
from . import read
from . import state as st
from .errors import StudyError
from .store import atomic_write_json

ACTION_IMPORT = 'brief.import'
ACTION_SET = 'brief.set'
IMPORT_PARAMS = frozenset({'pdf', 'sha256', 'pages'})
SET_PARAMS = frozenset({'document', 'citations', 'open_questions', 'user_words',
                        'source_sha256'})
FOLDER = 'brief'
SOURCE_FILE = 'source.json'
SOURCE_SCHEMA = 'hypotrail.brief-source/1'
PDF_MAGIC = b'%PDF-'
DRAFT = f'{FOLDER}/draft.yaml'
# The closed question after the draft (R68): adopt, correct, or explain first.
OPTIONS = {'fr': ("J'adopte la fiche", 'Corriger quelque chose', "Expliquer d'abord"),
           'en': ('I adopt the brief', 'Correct something', 'Explain first')}
THEN_KEYS = ('text', 'source', 'draft', 'options', 'command')
THEN_TEXT = (
    'Read the source (the PDF\'s text, page by page). Write the draft: YAML with schema '
    'hypotrail.case-brief/1, source {fictitious, text}, problem, decision, objective, '
    'production, data_provenance {real, scenario}, users_and_cost_of_error {users, cost}, '
    'out_of_scope_and_risks {out_of_scope, risks}, links {prediction_moment, error_measure, '
    'conclusion}, current_method_error and target_error ({value, unit, measure: mae or rmse} '
    'from the PDF, or null). A text is one quoted string in the study language. Under '
    'citations, give each field the pages it comes from; under open_questions ({about: field, '
    'text}), list what the PDF does not say: never invent it. Show the junior a short summary '
    '(the fields, their pages, the open questions), then ask one closed question with the '
    'picker, these options in this order. On adoption, run the command with the label '
    'verbatim; on a correction, change the draft as the junior says and ask again. Nothing '
    'else is decided from the PDF: the target, the prediction moment and the availability '
    'stay the study\'s own steps.')


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('verb', choices=('import', 'set'),
                        help="import: extract the text of the product owner's PDF into the "
                             "study; set: record the drafted brief with the junior's words")
    parser.add_argument('--pdf', default=None, help='with import: the PDF file')
    parser.add_argument('--file', default=None,
                        help='with set: the draft (YAML), the fields of case-brief.yaml plus '
                             'citations and open_questions')
    parser.add_argument('--user-words', default=None,
                        help="with set: the junior's verbatim words adopting the brief")
    parser.add_argument('--request-id', default=None,
                        help='optional; derived from the content and the revision when absent')
    parser.add_argument('--expected-revision', required=True, type=int,
                        help='the revision you read with status')


def _invalid(message: str, **details) -> StudyError:
    return StudyError('invalid_value', message, details=details)


def extract(path: Path) -> tuple[bytes, list[dict]]:
    """The bytes of the PDF at ``path`` and its pages ``[{n, text}]`` (refused when it is not
    a PDF, cannot be read, or holds no text)."""
    if not path.is_file():
        raise _invalid(f'No file at {path}.', field='pdf', reason='missing_file')
    data = path.read_bytes()
    if not data.startswith(PDF_MAGIC):
        raise _invalid(f'{path.name} is not a PDF (it does not start with %PDF-).',
                       field='pdf', reason='not_a_pdf')
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [{'n': i, 'text': (page.extract_text() or '').strip()}
                 for i, page in enumerate(reader.pages, start=1)]
    except Exception as exc:              # noqa: BLE001 - any parser failure is a refusal
        raise _invalid(f'{path.name} cannot be read as a PDF: {exc}', field='pdf',
                       reason='unreadable_pdf') from exc
    if not any(p['text'] for p in pages):
        raise _invalid(f'No text could be extracted from {path.name} (a scanned PDF?). Ask '
                       'the product owner for a PDF with text, or copy its text.',
                       field='pdf', reason='empty_extraction', pages=len(pages))
    return data, pages


def _import(ctx: cmd.Context) -> Handler:
    def run(state, params):
        revision = state['revision'] + 1
        record = state.setdefault('brief', {'source': None, 'confirmed': None})
        record['source'] = {'pdf': params['pdf'], 'sha256': params['sha256'],
                            'pages': params['pages'], 'path': f'{FOLDER}/{params["pdf"]}',
                            'revision': revision, 'time': st.now(),
                            'request_id': ctx.request_id}
        return {'pdf': params['pdf'], 'sha256': params['sha256'], 'pages': params['pages'],
                'source': f'{FOLDER}/{SOURCE_FILE}', 'copy': f'{FOLDER}/{params["pdf"]}',
                'confirmed': record.get('confirmed') is not None}
    return Handler(IMPORT_PARAMS, run)


def _set(ctx: cmd.Context) -> Handler:
    def check(params):
        words = params['user_words']
        if not isinstance(words, str) or not words.strip():
            raise CommandRefused('ambiguous_confirmation', "Recording the brief needs the "
                                 "junior's own words adopting it.",
                                 details={'reason': 'missing_user_words'})
        if cf.is_question(words):
            raise CommandRefused('ambiguous_confirmation', 'These words are a question: '
                                 'answer it, then ask again whether the junior adopts the '
                                 'brief.', details={'reason': 'question_reply',
                                                    'user_words': words})

    def run(state, params):
        source = (state.get('brief') or {}).get('source')
        if not source or source['sha256'] != params['source_sha256']:
            raise CommandRefused('precondition_missing', 'The brief is drafted from the PDF '
                                 'imported in this study: run `brief import` again, reread '
                                 f'{FOLDER}/{SOURCE_FILE} and redraft.',
                                 details={'missing': [{'requirement': 'brief_imported',
                                                       'detail': 'the PDF the draft cites'}]})
        revision = state['revision'] + 1
        state['brief']['confirmed'] = {
            'document': params['document'], 'citations': params['citations'],
            'open_questions': params['open_questions'], 'user_words': params['user_words'],
            'source_sha256': params['source_sha256'], 'revision': revision, 'time': st.now(),
            'request_id': ctx.request_id}
        return {'pdf': source['pdf'], 'citations': params['citations'],
                'open_questions': len(params['open_questions']),
                'user_words': params['user_words']}
    return Handler(SET_PARAMS, run, check)


cmd.register_action(ACTION_IMPORT, _import)
cmd.register_action(ACTION_SET, _set)


def _request_id(args, verb: str, content: bytes) -> str:
    if args.request_id:
        return args.request_id
    digest = hashlib.sha256(content).hexdigest()[:16]
    return f'brief-{verb}-{digest}-r{args.expected_revision}'


def _write_source(study: Path, pdf: Path, data: bytes, pages: list[dict]) -> None:
    folder = study / FOLDER
    folder.mkdir(exist_ok=True)
    atomic_write_json(folder / SOURCE_FILE,
                      {'schema': SOURCE_SCHEMA, 'pdf': pdf.name,
                       'sha256': hashlib.sha256(data).hexdigest(), 'pages': pages})
    target = folder / pdf.name
    if pdf.resolve() != target.resolve():
        shutil.copyfile(pdf, target)


def then(study: Path, revision: int) -> dict:
    """What the agent does after ``brief import`` (``then`` of its payload): draft, cite,
    ask, record (R68)."""
    import shlex
    lang = st.language_of(read.open(study).state)
    root = study.resolve()
    draft = root / DRAFT
    return {'text': THEN_TEXT, 'source': str(root / FOLDER / SOURCE_FILE), 'draft': str(draft),
            'options': list(OPTIONS.get(lang, OPTIONS['en'])),
            'command': f'hypotrail brief set --file {shlex.quote(str(draft))} --user-words '
                       f'"<the option label, verbatim>" --expected-revision {revision} '
                       f'--study {shlex.quote(str(root))}'}


def _target_unit(state) -> str | None:
    try:
        case = cmd.case_of(state)
    except Exception:                    # noqa: BLE001 - no readable case: no unit check
        return None
    return case.target_unit if case.task == 'regression' else None


def main(args: argparse.Namespace) -> cmd.Outcome:
    study = Path(args.study)
    if args.verb == 'import':
        if args.pdf is None or args.file is not None or args.user_words is not None:
            raise StudyError('invalid_arguments', 'brief import takes --pdf (and no --file or '
                                                  '--user-words).')
        pdf = Path(args.pdf)
        data, pages = extract(pdf)
        sha = hashlib.sha256(data).hexdigest()
        outcome = cmd.apply(study, action=ACTION_IMPORT,
                            params={'pdf': pdf.name, 'sha256': sha, 'pages': len(pages)},
                            request_id=_request_id(args, 'import', data),
                            expected_revision=args.expected_revision, command='brief import',
                            quiet=True)
        # The state records the import; the files follow it (again on a replay).
        _write_source(study, pdf, data, pages)
        outcome.payload['next_action'] = cmd.refreshed_next_action(study)
        outcome.payload['then'] = then(study, outcome.payload['revision'])
        return outcome
    if args.file is None or args.user_words is None or args.pdf is not None:
        raise StudyError('invalid_arguments', 'brief set takes --file and --user-words (and '
                                              'no --pdf).')
    path = Path(args.file)
    if not path.is_file():
        raise _invalid(f'No file at {path}.', field='file', reason='missing_file')
    text = path.read_text(encoding='utf-8')
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise _invalid(f'{path.name} is not valid YAML: {exc}', field='file',
                       reason='invalid_yaml') from exc
    state = read.open(study).state
    source = (state.get('brief') or {}).get('source')
    if not source:
        raise StudyError('precondition_missing', 'No PDF imported in this study: run '
                                                 '`brief import --pdf FILE` first.',
                         details={'missing': [{'requirement': 'brief_imported',
                                               'detail': 'the PDF the draft cites'}]})
    try:
        brief, citations, questions = cb.validate_draft(document, source['pages'],
                                                        _target_unit(state))
    except cb.BriefError as exc:
        raise _invalid(f'The draft is refused: {exc}', field='file',
                       reason='invalid_draft') from exc
    params = {'document': brief, 'citations': citations, 'open_questions': questions,
              'user_words': args.user_words, 'source_sha256': source['sha256']}
    content = json.dumps(params, sort_keys=True, ensure_ascii=False).encode('utf-8')
    return cmd.apply(study, action=ACTION_SET, params=params,
                     request_id=_request_id(args, 'set', content),
                     expected_revision=args.expected_revision, command='brief set')
