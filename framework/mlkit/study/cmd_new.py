"""``hypotrail new NAME --case PATH``: a ready-to-open study on an existing case (Lot 1).

Onboarding spec (docs/plans/ONBOARDING-SPEC.md, Lot 1). In Python, what
``scripts/workshop/new-mpg-study.sh`` did in bash, for any case:

1. ``init`` on the case, into ``PARENT/NAME`` (``--dir``, default the current folder), with
   ``--lang``, ``--automation`` and, for a PDF ``--brief``, the PO brief import of
   ``init --brief-pdf``; **without** the ``data`` link of R69 (spec §2.6: the raw file stays
   outside the chat workspace; :func:`mlkit.study.launch.without_data_link`);
2. the study panel's flag and stage in the study's ``.vscode/settings.json`` (keys added
   only when absent; the panel itself stays off by default everywhere else);
3. the chat agent's PreToolUse hook, ``.github/hooks/hypotrail.json``, running
   ``hypotrail hook pretool`` with the study's own invocation (:mod:`mlkit.study.cmd_hook`);
4. in a VS Code integrated terminal, the panel installed if missing (``hypotrail setup
   vscode``; best effort, never fatal), and with ``--open`` the study opened in VS Code.

Nothing that exists is overwritten: an existing study folder is refused before any write.

``--data FILE`` (Lot 2) starts from one raw data file instead: :func:`mlkit.study.cmd_prepare.start`
makes the case folder ``NAME.case/`` and the study folder ``NAME/`` in a preparing state,
sealed later by ``hypotrail seal``; the workspace steps 2 to 4 then apply to it as well.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from . import state as st
from .errors import StudyError

SCHEMA = 'hypotrail.new/1'
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
SETTINGS = '.vscode/settings.json'
PANEL_STAGE = 'v3'
STUDY_OPTIONAL = ('*',)


def validate_name(name: str) -> str:
    if not isinstance(name, str) or not NAME.match(name):
        raise StudyError('invalid_arguments', f'Invalid study name {name!r}: letters, digits, '
                         '".", "_" and "-", starting with a letter or a digit, 64 at most.',
                         details={'name': name})
    return name


def study_path(name: str, parent=None) -> Path:
    """``PARENT/NAME`` (absolute), refused when it exists."""
    validate_name(name)
    study = (Path(parent).expanduser() if parent else Path.cwd()).resolve() / name
    if os.path.lexists(study):
        raise StudyError('state_exists', f'{study} already exists; choose another name.',
                         details={'study': str(study)})
    return study


def write_panel_settings(study: Path, stage: str = PANEL_STAGE) -> dict:
    """Add the panel's flag and stage to the study's ``.vscode/settings.json`` (only keys
    that are absent). ``{path, added, notice}``; a file that is not plain JSON is left as
    it is, with the lines to add in ``notice``."""
    path = study / SETTINGS
    wanted = {'hypotrail.companion.enabled': True, 'hypotrail.companion.stage': stage}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        data = {}
    except (OSError, ValueError):
        return {'path': SETTINGS, 'added': [],
                'notice': f'{SETTINGS} is not plain JSON; add by hand: '
                          + json.dumps(wanted)[1:-1]}
    if not isinstance(data, dict):
        return {'path': SETTINGS, 'added': [], 'notice': f'{SETTINGS} is not a JSON object.'}
    missing = {k: v for k, v in wanted.items() if k not in data}
    if missing:
        data.update(missing)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + '.tmp')
        tmp.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
        os.replace(tmp, path)
    return {'path': SETTINGS, 'added': sorted(missing), 'notice': None}


def recorded_cli(study: Path) -> dict:
    """The ``cli`` record of ``.hypotrail/agent.json`` (``{argv, shell, how}``)."""
    from .agent_files import AGENT_FILE
    record = json.loads((study / '.hypotrail' / AGENT_FILE).read_text(encoding='utf-8'))
    return record['cli']


def install_hook(study: Path) -> str | None:
    """Write ``.github/hooks/hypotrail.json`` when absent; its relative path, else None."""
    from . import cmd_hook
    path = study / cmd_hook.HOOK_FILE
    if path.exists():
        return None
    config = cmd_hook.hook_config(recorded_cli(study)['argv'], study)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'x', encoding='utf-8') as handle:
        json.dump(config, handle, indent=2)
        handle.write('\n')
    return cmd_hook.HOOK_FILE


def in_vscode_terminal() -> bool:
    return bool(os.environ.get('VSCODE_IPC_HOOK_CLI')) or \
        os.environ.get('TERM_PROGRAM') == 'vscode'


def ensure_panel() -> dict | None:
    """In a VS Code integrated terminal, install the panel when missing; never raises."""
    if not in_vscode_terminal():
        return None
    from . import cmd_setup
    try:
        out = cmd_setup.install()
        return {'status': out['status'], 'message': out['message']}
    except StudyError as exc:
        return {'status': 'not_installed', 'message': exc.message}
    except Exception as exc:   # noqa: BLE001 - best effort
        return {'status': 'not_installed', 'message': str(exc)}


def open_in_vscode(study: Path) -> dict:
    """``code -r STUDY`` (reuse the window); ``{opened, message}``, never raises."""
    from . import cmd_setup
    code, how = cmd_setup.find_code()
    if code is None or (how == 'code_server' and not os.environ.get('VSCODE_IPC_HOOK_CLI')):
        return {'opened': False, 'message': 'No "code" command here: open the folder by hand '
                                            '(File > Open Folder...).'}
    try:
        subprocess.run([code, '-r', str(study)], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return {'opened': False, 'message': f'{code} -r failed: {exc}'}
    return {'opened': True, 'message': f'Opened with {code} -r'}


def finish_workspace(study: Path, *, stage: str = PANEL_STAGE, open_editor: bool = False
                     ) -> dict:
    """Steps 2 to 4 on a study whose ``.hypotrail/agent.json`` exists."""
    out = {'settings': write_panel_settings(study, stage), 'hook': install_hook(study),
           'panel': ensure_panel()}
    out['open'] = open_in_vscode(study) if open_editor else None
    return out


def _init(case, study: Path, language: str, automation: str | None, brief: Path | None):
    """``hypotrail init`` (with ``--brief-pdf`` for a PDF brief), through the CLI's own
    dispatch so ``new`` and ``init`` stay one code path."""
    from . import cli, launch
    args = argparse.Namespace(command='init', case=str(case), study=str(study), lang=language,
                              reliability_profile=None, automation=automation,
                              brief_pdf=str(brief) if brief else None)
    with launch.without_data_link():
        return cli.dispatch(args)


def create_study(name: str, *, case, parent=None, language: str = st.DEFAULT_LANGUAGE,
                 brief=None, automation: str | None = None, open_editor: bool = False,
                 stage: str = PANEL_STAGE):
    """Create ``PARENT/NAME`` on the existing case ``case`` (``case.yaml`` or its folder)
    and prepare it for VS Code. Returns a :class:`mlkit.study.commands.Outcome`: the init
    refusal as is when ``init`` refuses, else a ``hypotrail.new/1`` payload. Raises
    :class:`StudyError` for an invalid name, an existing folder or an unsupported brief."""
    from .commands import Outcome
    study = study_path(name, parent)
    if language not in st.LANGUAGES:
        raise StudyError('invalid_arguments', f'language is one of {", ".join(st.LANGUAGES)}.')
    brief_path = None
    if brief is not None:
        brief_path = Path(brief).expanduser().resolve()
        if not brief_path.is_file():
            raise StudyError('invalid_arguments', f'No brief at {brief_path}.')
        if brief_path.suffix.lower() != '.pdf':
            raise StudyError('unsupported_capability', 'Only a PDF brief is supported for now '
                             '(Word and Markdown arrive with the preparation lot).',
                             details={'brief': str(brief_path)})
    study.parent.mkdir(parents=True, exist_ok=True)
    init = _init(case, study, language, automation, brief_path)
    if init.exit_code != 0:
        return init
    workspace = finish_workspace(study, stage=stage, open_editor=open_editor)
    cli = recorded_cli(study)
    p = init.payload
    payload = {'schema': SCHEMA, 'ok': True, 'study': str(study), 'name': name,
               'case': p.get('case'), 'revision': p.get('revision'), 'language': language,
               'automation': automation, 'cli': cli['shell'],
               'brief': p.get('brief'), 'data_link': False,
               'next_action': p.get('next_action'), 'notices': p.get('notices') or [],
               'deliverables': p.get('deliverables'), **workspace}
    payload['next_steps'] = next_steps(payload)
    return Outcome(payload)


def next_steps(payload: dict) -> list[str]:
    study, lang = payload['study'], payload.get('language')
    pdf = (payload.get('brief') or {}).get('result', {}) or {}
    fr = lang == 'fr'
    first = ('On commence' if not pdf else
             ("Prépare l'étude à partir de la fiche du PO" if fr else
              "Prepare the study from the PO's brief"))
    if fr:
        return [f'Ouvrir le dossier de l\'étude dans VS Code : code -r "{study}" (ou File > Open '
                'Folder..., et faire confiance au dossier)',
                'Palette (Ctrl+Shift+P) : « Hypotrail: open the study panel »',
                'Chat Copilot (Ctrl+Alt+I) : choisir l\'agent « Hypotrail » ; dans « Configure '
                'Tools », cocher vscode/askQuestions',
                f'Écrire : {first}',
                f'CLI directe : {payload["cli"]} status --summary --study "{study}" --format text']
    return [f'Open the study folder in VS Code: code -r "{study}" (or File > Open Folder..., '
            'and trust the folder)',
            'Command palette (Ctrl+Shift+P): "Hypotrail: open the study panel"',
            'Copilot chat (Ctrl+Alt+I): pick the "Hypotrail" agent; in "Configure Tools", '
            'enable vscode/askQuestions',
            f'Type: {first}',
            f'Direct CLI: {payload["cli"]} status --summary --study "{study}" --format text']


# --- CLI ----------------------------------------------------------------------------------

def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('name', help='the study folder name (letters, digits, . _ -)')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--case', default=None, metavar='PATH',
                        help='an existing case: case.yaml or its folder')
    source.add_argument('--data', default=None, metavar='FILE',
                        help='one data file (CSV, UTF-8): prepared with the six questions, '
                             'then sealed (hypotrail seal)')
    parser.add_argument('--dir', default=None, metavar='PARENT',
                        help='where to create the study folder (default: the current folder)')
    parser.add_argument('--lang', choices=st.LANGUAGES, default=st.DEFAULT_LANGUAGE,
                        help='the study language')
    parser.add_argument('--brief', default=None, metavar='FILE',
                        help="the product owner's brief (PDF; with --data also Word .docx, "
                             'Markdown .md or .txt)')
    parser.add_argument('--context', default=None,
                        help='with --data: a short free-text context, instead of a brief')
    parser.add_argument('--context-file', default=None, metavar='FILE',
                        help='with --data: a UTF-8 file holding that context')
    parser.add_argument('--automation', choices=st.AUTOMATION_MODES, default=None,
                        help='the automatic mode, chosen at launch only')
    parser.add_argument('--open', action='store_true', dest='open_editor',
                        help='open the study in VS Code when done (code -r)')


def main(args: argparse.Namespace):
    if args.study:
        raise StudyError('invalid_arguments', 'new takes NAME and --dir, not --study.')
    if args.data:
        return start_from_data(args)
    if args.context or args.context_file:
        raise StudyError('invalid_arguments', '--context goes with --data.')
    if not args.case:
        raise StudyError('invalid_arguments', '--case PATH or --data FILE is required.')
    return create_study(args.name, case=args.case, parent=args.dir, language=args.lang,
                        brief=args.brief, automation=args.automation,
                        open_editor=args.open_editor)


def start_from_data(args: argparse.Namespace):
    """``new NAME --data FILE``: the preparing study (Lot 2), then the workspace steps."""
    from . import cmd_prepare
    if args.automation:
        raise StudyError('invalid_arguments', '--automation is not available with --data yet: '
                         'a prepared study is sealed by hypotrail seal, without automatic mode.')
    study = study_path(args.name, args.dir)
    study.parent.mkdir(parents=True, exist_ok=True)
    out = cmd_prepare.start(str(study), args.data, brief=args.brief, context=args.context,
                            context_file=args.context_file, language=args.lang)
    if out.exit_code != 0:
        return out
    out.payload.update(finish_workspace(study, open_editor=args.open_editor))
    return out


def text(payload: dict) -> str:
    fr = payload.get('language') == 'fr'
    if str(payload.get('schema', '')).startswith('hypotrail.prepare'):
        lines = [(f'Étude en préparation : {payload["study"]} (cas : {payload.get("case")})' if fr
                  else f'Study being prepared: {payload["study"]} (case: {payload.get("case")})'),
                 ("Dans le chat : « Prépare l'étude », puis hypotrail seal" if fr else
                  'In the chat: "Prepare the study", then hypotrail seal')]
        if (payload.get('settings') or {}).get('notice'):
            lines.append('note: ' + payload['settings']['notice'])
        return '\n'.join(lines)
    lines = [(f'Étude prête : {payload["study"]} (révision {payload["revision"]})' if fr else
              f'Study ready: {payload["study"]} (revision {payload["revision"]})')]
    if payload.get('automation'):
        lines.append(('Mode automatique : ' if fr else 'Automatic mode: ') + payload['automation'])
    for n in payload.get('notices') or []:
        lines.append(f'notice: {n.get("junior_message") or n.get("message")}')
    if (payload.get('settings') or {}).get('notice'):
        lines.append('note: ' + payload['settings']['notice'])
    if payload.get('panel'):
        lines.append(('panneau : ' if fr else 'panel: ') + payload['panel']['message'])
    if payload.get('open'):
        lines.append(payload['open']['message'])
    lines.append('')
    lines.append('Ensuite, dans l\'ordre :' if fr else 'Next, in order:')
    lines += [f'  {i}. {s}' for i, s in enumerate(payload['next_steps'], 1)]
    return '\n'.join(lines)
