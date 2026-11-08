"""Onboarding Lots 0-1 (docs/plans/ONBOARDING-SPEC.md, agent P): the portable CLI command
in ``agent.json``, the panel's VSIX built in pure Python, ``hypotrail hook pretool``,
``hypotrail new --case`` end to end on Auto MPG, and ``hypotrail doctor``."""
from __future__ import annotations

import ast
import json
import os
import shlex
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

import pytest

import flowkit as fk
from mlkit.study import agent_files as af
from mlkit.study import cli, cmd_doctor, cmd_hook, cmd_new, cmd_setup, launch

REPO = Path(__file__).resolve().parents[3]
PANEL = REPO / 'clients' / 'vscode-companion'
MPG = REPO / 'use-cases' / 'auto-mpg'
PROTOTYPE = REPO / 'docs' / 'plans' / 'onboarding' / 'mkvsix-prototype.py'


# --- Lot 0: the CLI command an agent runs ------------------------------------------------

def test_cli_command_is_an_argument_list_never_env(monkeypatch, tmp_path):
    """Every ``how`` is an argument list run without a shell; none starts with ``env``."""
    monkeypatch.delenv(af.CLI_ENV, raising=False)
    uv = af.cli_command()
    if uv['how'] == 'uv_project':
        assert uv['argv'][:3] == ['uv', 'run', '--project'] and uv['argv'][-1] == 'hypotrail'
    # an installed tool: the executable next to the interpreter, by absolute path
    bindir = tmp_path / 'tool' / ('Scripts' if os.name == 'nt' else 'bin')
    bindir.mkdir(parents=True)
    exe = bindir / ('hypotrail.exe' if os.name == 'nt' else 'hypotrail')
    exe.write_text('')
    monkeypatch.setattr(af.shutil, 'which', lambda name: None)
    monkeypatch.setattr(af.sys, 'executable', str(bindir / 'python'))
    installed = af.cli_command()
    assert installed == {'argv': [str(exe)], 'shell': af.display_command([str(exe)]),
                         'how': 'installed'}
    exe.unlink()
    fallback = af.cli_command()
    assert fallback['how'] in ('python_module', 'python_path')
    assert fallback['argv'][0] == str(bindir / 'python')
    for record in (installed, fallback):
        assert record['argv'][0] != 'env' and 'PYTHONPATH=' not in record['shell']


def test_python_path_fallback_runs_the_cli(tmp_path, monkeypatch):
    """The last resort puts the engine on sys.path itself (no ``env``, any platform)."""
    monkeypatch.delenv(af.CLI_ENV, raising=False)
    monkeypatch.setattr(af.shutil, 'which', lambda name: None)
    monkeypatch.setattr(af, '_installed_executable', lambda: None)
    monkeypatch.setattr(af, '_importable_without_help', lambda framework: False)
    record = af.cli_command()
    assert record['how'] == 'python_path' and record['argv'][1] == '-c'
    env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
    proc = subprocess.run([*record['argv'], '--help'], capture_output=True, text=True,
                          cwd=tmp_path, env=env, timeout=120)
    assert proc.returncode == 0 and 'doctor' in proc.stdout, proc.stderr


def test_display_command_quotes_for_powershell_on_windows():
    exe = r'C:\Users\Jo Doe\AppData\Roaming\uv\tools\hypotrail\Scripts\hypotrail.exe'
    assert af.display_command([exe, 'status', '--study', r"C:\s\l'étude"], windows=True) == \
        "& '" + exe + "' status --study 'C:\\s\\l''étude'"
    assert af.display_command([r'C:\uv\hypotrail.exe', 'status', '--study', r'C:\s\one'],
                              windows=True) == r'C:\uv\hypotrail.exe status --study C:\s\one'
    argv = ['/opt/my tools/hypotrail', 'status', '--study', "/s/l'étude"]
    assert af.display_command(argv, windows=False) == shlex.join(argv)
    # a comma is an array separator in PowerShell: quoted
    assert af.quote_arg('a,b', windows=True) == "'a,b'"


def test_deliverables_shell_matches_their_argv(tmp_path, synthetic_case_dir, monkeypatch):
    monkeypatch.delenv(af.CLI_ENV, raising=False)
    from mlkit.study import commands as cmd
    payload = cmd.init(synthetic_case_dir, tmp_path / 'study').payload
    for launch_ in payload['deliverables']['launch'].values():
        assert launch_['shell'] == af.display_command(launch_['argv'])


# --- Lot 1: the panel's VSIX in pure Python ----------------------------------------------

def _panel_sources() -> set[str]:
    """The panel's shipped files, enumerated independently of cmd_setup: everything but the
    tests, the two developer documents and hidden local folders (``.local/`` baselines)."""
    out = set()
    for p in PANEL.rglob('*'):
        rel = p.relative_to(PANEL).as_posix()
        if p.is_file() and not rel.startswith(('test/', '.')) and rel not in (
                'ARCHITECTURE.md', 'MANUAL-TEST.md'):
            out.add(rel)
    return out


def test_vsix_holds_exactly_the_panel_sources_byte_for_byte(tmp_path):
    out = cmd_setup.build_vsix(PANEL, tmp_path / 'panel.vsix')
    with zipfile.ZipFile(out['path']) as z:
        names = z.namelist()
        assert names[:2] == ['extension.vsixmanifest', '[Content_Types].xml']
        members = {n[len('extension/'):] for n in names[2:]}
        expected = {('readme.md' if r == 'README.md' else r) for r in _panel_sources()}
        assert members == expected and len(names) == len(expected) + 2
        for rel in _panel_sources():
            name = 'extension/' + ('readme.md' if rel == 'README.md' else rel)
            assert z.read(name) == (PANEL / rel).read_bytes(), rel
        pkg = json.loads((PANEL / 'package.json').read_text(encoding='utf-8'))
        manifest = z.read('extension.vsixmanifest').decode()
        assert f'Id="{pkg["name"]}" Version="{pkg["version"]}" Publisher="{pkg["publisher"]}"' \
            in manifest
        types = z.read('[Content_Types].xml').decode()
        for ext in {Path(n).suffix for n in names[2:]}:
            assert f'Extension="{ext}"' in types, ext
    assert out['extension'] == f'{pkg["publisher"]}.{pkg["name"]}'
    again = cmd_setup.build_vsix(PANEL, tmp_path / 'again.vsix')
    assert Path(again['path']).read_bytes() == Path(out['path']).read_bytes()   # reproducible


def test_vsix_is_identical_to_the_prototype_checked_against_vsce(tmp_path):
    """The prototype (docs/plans/onboarding) was verified against @vscode/vsce 3.9.2 (review
    B §7: same entries, same content types, extension/* byte for byte)."""
    proto = tmp_path / 'proto.vsix'
    subprocess.run([sys.executable, str(PROTOTYPE), str(PANEL), str(proto)], check=True,
                   timeout=120)
    ours = Path(cmd_setup.build_vsix(PANEL, tmp_path / 'ours.vsix')['path'])
    assert ours.read_bytes() == proto.read_bytes()


def test_the_wheel_hook_ships_the_same_panel_files_as_setup():
    """framework/hatch_build.py (wheel package data) and cmd_setup select the same files."""
    tree = ast.parse((REPO / 'framework' / 'hatch_build.py').read_text(encoding='utf-8'))
    consts = {t.id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
              for t in n.targets if isinstance(t, ast.Name) and t.id.startswith('PANEL_')}
    assert consts == {'PANEL_FILES': cmd_setup.PANEL_FILES, 'PANEL_DIRS': cmd_setup.PANEL_DIRS}
    assert set(cmd_setup.panel_files(PANEL)) == _panel_sources()


def test_setup_vscode_installs_with_the_code_command(tmp_path, monkeypatch):
    """A fake ``code`` records its arguments: list, then install of a real VSIX; a second
    run with the same version installed does nothing."""
    if os.name == 'nt':
        pytest.skip('the fake code command is a POSIX script')
    log = tmp_path / 'calls.jsonl'
    installed = tmp_path / 'installed.txt'
    fake = tmp_path / 'code'
    fake.write_text(f'#!{sys.executable}\n' + textwrap.dedent(f"""\
        import json, os, re, sys, zipfile
        with open({str(log)!r}, 'a') as h:
            h.write(json.dumps(sys.argv[1:]) + '\\n')
        if sys.argv[1] == '--list-extensions':
            if os.path.exists({str(installed)!r}):
                print(open({str(installed)!r}).read())
        elif sys.argv[1] == '--install-extension':
            with zipfile.ZipFile(sys.argv[2]) as z:
                assert z.testzip() is None
                m = re.search(r'<Identity [^>]*Version="([^"]+)"',
                              z.read('extension.vsixmanifest').decode())
            open({str(installed)!r}, 'w').write('hypotrail-local.hypotrail-companion@' + m.group(1))
        """))
    fake.chmod(0o755)
    monkeypatch.setenv('HYPOTRAIL_CODE', str(fake))
    first = cli.run(['setup', 'vscode'])
    assert first.exit_code == 0 and first.payload['status'] == 'installed', first.payload
    second = cli.run(['setup', 'vscode'])
    assert second.payload['status'] == 'already_installed'
    calls = [json.loads(x) for x in log.read_text().splitlines()]
    assert [c[0] for c in calls] == ['--list-extensions', '--install-extension',
                                     '--list-extensions']
    assert calls[1][-1] == '--force' and calls[1][1].endswith('.vsix')


def test_setup_vscode_without_code_is_a_refusal_with_the_way_out(monkeypatch):
    monkeypatch.delenv('HYPOTRAIL_CODE', raising=False)
    monkeypatch.setattr(cmd_setup, 'find_code', lambda: (None, 'missing'))
    out = cli.run(['setup', 'vscode'])
    assert out.exit_code == 2 and out.payload['error']['code'] == 'vscode_missing'
    assert '--vsix-out' in out.payload['error']['message']


# --- Lot 1: the hook ------------------------------------------------------------------------

def _run(command):
    return {'tool_name': 'run_in_terminal', 'tool_input': {'command': command}}


def test_hook_decisions_follow_the_recorded_invocation():
    uv = cmd_hook.engine_prefixes(['uv', 'run', '--project', '/r/framework', 'hypotrail'])
    files = ['auto-mpg.data']
    assert cmd_hook.decide(_run('uv run --project /r/framework hypotrail status --study s'),
                           uv, files, windows=False)[0] == 'allow'
    assert cmd_hook.decide(_run('uv run --quiet --project /r/framework hypotrail run split'),
                           uv, files, windows=False)[0] == 'allow'
    for other in ('uv run --project /r/framework hypotrail status; rm -rf x',
                  'uv run --project /r/framework hypotrail status | python -c x',
                  'uv run --project /r/framework hypotrail status $(id)',
                  'uv run --project /elsewhere/framework hypotrail status',
                  'uv run --project /r/framework python -c x', 'rm -rf /', ''):
        assert cmd_hook.decide(_run(other), uv, files, windows=False) == (None, ''), other
    assert cmd_hook.decide({'tool_name': 'read_file',
                            'tool_input': {'filePath': '/c/data/auto-mpg.data'}},
                           uv, files, windows=False)[0] == 'deny'
    assert cmd_hook.decide(_run('head ../auto-mpg.data'), uv, files, windows=False)[0] == 'deny'
    # an installed executable, and its PowerShell form on Windows
    exe = r'C:\Users\Jo Doe\.local\bin\hypotrail.exe'
    win = cmd_hook.engine_prefixes([exe])
    line = af.display_command([exe, 'status', '--study', r'C:\s\one'], windows=True)
    assert cmd_hook.decide(_run(line), win, files, windows=True)[0] == 'allow'
    assert cmd_hook.decide(_run(line.replace('Jo Doe', 'jo doe')), win, files,
                           windows=True)[0] == 'allow'       # case-insensitive paths
    assert cmd_hook.decide(_run(line + '; Remove-Item x'), win, files, windows=True) == \
        (None, '')
    posix = cmd_hook.engine_prefixes(['/home/jo/.local/bin/hypotrail'])
    assert cmd_hook.decide(_run('/home/jo/.local/bin/hypotrail data --study s'), posix, files,
                           windows=False)[0] == 'allow'
    assert cmd_hook.decide(_run('/tmp/hypotrail data'), posix, files, windows=False) == (None, '')


# --- Lot 1: hypotrail new --case, end to end on Auto MPG --------------------------------------

@pytest.fixture
def mpg_study(tmp_path, monkeypatch):
    monkeypatch.delenv(af.CLI_ENV, raising=False)
    monkeypatch.delenv('VSCODE_IPC_HOOK_CLI', raising=False)
    monkeypatch.delenv('TERM_PROGRAM', raising=False)
    out = cli.run(['new', 'mpg-1', '--case', str(MPG), '--dir', str(tmp_path / 'studies'),
                   '--lang', 'fr'])
    assert out.exit_code == 0, out.payload
    return Path(out.payload['study']), out.payload


def test_new_creates_a_study_ready_for_vscode_without_a_data_link(mpg_study):
    study, payload = mpg_study
    assert payload['schema'] == cmd_new.SCHEMA and payload['revision'] >= 1
    assert payload['case']['id'] and payload['data_link'] is False
    assert (study / '.hypotrail' / 'state.json').is_file()
    assert not os.path.lexists(study / launch.DATA_LINK)          # spec §2.6
    readme = (study / 'README.md').read_text(encoding='utf-8')
    assert "pas de lien" in readme and 'auto-mpg.data' in readme
    settings = json.loads((study / '.vscode' / 'settings.json').read_text(encoding='utf-8'))
    assert settings['hypotrail.companion.enabled'] is True
    assert settings['hypotrail.companion.stage'] == 'v3'
    assert launch.INTERPRETER_KEY in settings                       # init's line kept
    record = json.loads((study / '.hypotrail' / 'agent.json').read_text(encoding='utf-8'))
    assert record['cli']['argv'][0] != 'env'
    hook = json.loads((study / cmd_hook.HOOK_FILE).read_text(encoding='utf-8'))
    command = hook['hooks']['PreToolUse'][0]['command']
    assert command == af.display_command(cmd_hook.hook_command(
        record['cli']['argv'], study, study / cmd_hook.LOG_FILE))
    assert payload['next_steps'] and payload['cli'] == record['cli']['shell']
    assert 'Étude prête' in cli._text(payload)


def test_new_hook_command_decides_on_real_calls(mpg_study):
    """The installed hook command, run as VS Code runs it: allow the study's own engine
    command, deny the raw data file, no decision otherwise; every call is logged."""
    study, _ = mpg_study
    record = json.loads((study / '.hypotrail' / 'agent.json').read_text(encoding='utf-8'))
    argv = cmd_hook.hook_command(record['cli']['argv'], study, study / cmd_hook.LOG_FILE)

    def decide(event):
        proc = subprocess.run(argv, input=json.dumps(event), capture_output=True, text=True,
                              cwd=study, env=fk.env(), timeout=300)
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout).get('hookSpecificOutput', {})

    engine = f'{record["cli"]["shell"]} status --summary --study {af.quote_arg(str(study))}'
    allowed = decide(_run(engine))
    assert allowed['permissionDecision'] == 'allow'
    assert 'autorisée' in allowed['permissionDecisionReason']   # the study's language (fr)
    assert decide(_run(engine + ' && cat x')) == {}
    assert decide({'tool_name': 'read_file', 'tool_input': {
        'filePath': str(MPG / 'data' / 'auto-mpg.data')}})['permissionDecision'] == 'deny'
    assert decide(_run('ls')) == {}
    lines = [json.loads(x) for x in
             (study / cmd_hook.LOG_FILE).read_text(encoding='utf-8').splitlines()]
    assert [x['decision'] for x in lines] == ['allow', 'ask', 'deny', 'ask']


def test_hook_without_a_study_or_with_garbage_gives_no_decision(tmp_path):
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'hook', 'pretool',
                           '--study', str(tmp_path)], input='{not json', capture_output=True,
                          text=True, env=fk.env(), timeout=120)
    assert proc.returncode == 0 and json.loads(proc.stdout) == {}


def test_new_refuses_an_existing_folder_and_a_non_pdf_brief(tmp_path, mpg_study):
    study, _ = mpg_study
    again = cli.run(['new', study.name, '--case', str(MPG), '--dir', str(study.parent)])
    assert again.exit_code == 2 and again.payload['error']['code'] == 'state_exists'
    brief = tmp_path / 'brief.md'
    brief.write_text('# brief\n')
    out = cli.run(['new', 'other', '--case', str(MPG), '--dir', str(tmp_path / 'x'),
                   '--brief', str(brief)])
    assert out.exit_code == 2 and out.payload['error']['code'] == 'unsupported_capability'
    assert not (tmp_path / 'x' / 'other').exists()
    bad = cli.run(['new', '../escape', '--case', str(MPG), '--dir', str(tmp_path)])
    assert bad.exit_code == 2 and bad.payload['error']['code'] == 'invalid_arguments'


def test_init_alone_keeps_the_data_link(tmp_path, synthetic_case_dir, monkeypatch):
    """R69 is unchanged for ``init``: only ``new`` leaves the link out."""
    monkeypatch.delenv(af.CLI_ENV, raising=False)
    from mlkit.study import commands as cmd
    cmd.init(synthetic_case_dir, tmp_path / 'study')
    assert (tmp_path / 'study' / launch.DATA_LINK).is_symlink()


# --- Lot 1: doctor --------------------------------------------------------------------------

def test_doctor_reports_every_check_and_never_fails(tmp_path, monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY', 'http://proxy.example:3128')
    for key in ('UV_SYSTEM_CERTS', 'UV_NATIVE_TLS', 'SSL_CERT_FILE', 'REQUESTS_CA_BUNDLE'):
        monkeypatch.delenv(key, raising=False)
    onedrive = tmp_path / 'OneDrive - Contoso' / 'studies'
    onedrive.mkdir(parents=True)
    out = cli.run(['doctor', '--dir', str(onedrive)])
    assert out.exit_code == 0
    checks = {c['id']: c for c in out.payload['checks']}
    assert set(checks) == {'python', 'uv', 'engine', 'platform', 'vscode', 'chat_agent',
                           'panel', 'powershell_policy', 'long_paths', 'onedrive', 'proxy'}
    assert all(c['status'] in cmd_doctor.STATUSES for c in checks.values())
    assert checks['python']['status'] == 'ok'
    assert checks['onedrive']['status'] == 'warn' and checks['onedrive']['fix']
    assert checks['proxy']['status'] == 'warn' and 'UV_SYSTEM_CERTS' in checks['proxy']['fix']
    assert out.payload['fixes'] and 'fix:' in cli._text(out.payload)


def test_doctor_survives_a_check_that_raises(monkeypatch):
    def boom():
        raise RuntimeError('broken probe')
    monkeypatch.setattr(cmd_doctor, 'check_uv', boom)
    checks = {c['id']: c for c in cmd_doctor.run_checks()}
    assert checks['uv']['status'] == 'warn' and 'broken probe' in checks['uv']['detail']


# --- Lot 0: the dependency lock of an installed engine --------------------------------------

def test_absent_dependency_lock_is_recorded_not_silent(monkeypatch, tmp_path):
    from mlkit.study.understanding import snapshot as snap
    monkeypatch.setattr(snap, 'LOCK_FILE', tmp_path / 'uv.lock')
    out = snap.capture_context({'case': {}}, policy_digest=None, taskset_doc=None, repo=None,
                               sources=[], salt='s')
    keys = [e['logical_key'] for e in out['local']['entries']]
    assert 'engine:dependency_lock' not in keys
    assert {'logical_key': 'engine:dependency_lock', 'role': 'dependency_lock'} in \
        out['local']['unreadable_sources']


def test_the_vendored_runtime_reports_its_version_and_closure(monkeypatch):
    """Lot 0: with the runtime vendored (no `hypotrail-runtime` metadata), the engine still
    finds its version and the predictor's dependency closure still holds its requirements."""
    import importlib.metadata as md
    import hypotrail_runtime
    from hypotrail_runtime import predictor
    from mlkit.contracts import context
    real = md.distribution

    def no_runtime(name):
        if name.lower().replace('_', '-') == 'hypotrail-runtime':
            raise md.PackageNotFoundError(name)
        return real(name)
    monkeypatch.setattr(md, 'distribution', no_runtime)
    monkeypatch.setattr(context, 'version', lambda n: no_runtime(n).version)
    assert context.installed_version('hypotrail-runtime') == hypotrail_runtime.__version__
    closure = predictor.runtime_closure()
    assert closure['hypotrail-runtime'] == hypotrail_runtime.__version__
    assert {'numpy', 'pandas', 'scikit-learn', 'pydantic'} <= set(closure)


@pytest.mark.parametrize('language, brief, first', [
    ('en', None, "Type: Let's start"),
    ('fr', None, 'Écrire : On commence'),
    ('en', {'result': {'pages': 2}}, "Type: Prepare the study from the PO's brief"),
    ('fr', {'result': {'pages': 2}}, "Écrire : Prépare l'étude à partir de la fiche du PO"),
])
def test_new_first_message_is_in_the_study_language(language, brief, first):
    """The first chat message `new` suggests is in the study language, with or without a
    PO brief (an English study without a brief used to be told "On commence")."""
    steps = cmd_new.next_steps({'study': '/s', 'language': language, 'brief': brief,
                                'cli': 'hypotrail'})
    assert first in steps
