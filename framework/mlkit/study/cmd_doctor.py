"""``hypotrail doctor``: what this machine has for a Hypotrail study, and how to fix the rest.

Onboarding Lot 1 (docs/plans/ONBOARDING-SPEC.md). Read only: it writes nothing and never
fails hard. Every check is ``{id, status, detail, fix}`` with ``status`` one of ``ok``,
``warn`` (works, with a risk), ``fail`` (a study step will not work), ``info`` and ``skip``
(not relevant on this platform); ``fix`` is the command or step to run, or None. The exit
code is 0 whatever the checks find; one check that raises becomes a ``warn`` of its own.

Checks: Python, uv, the engine and how an agent runs it, the VS Code command line, the
chat agents (GitHub Copilot Chat in VS Code, Claude Code; best effort), the study panel,
the platform (Windows native is supported once the cross-platform lock lands: the check
asks the engine's lock module), PowerShell's execution policy and long paths (Windows),
a OneDrive folder, and the proxy and certificate variables.
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCHEMA = 'hypotrail.doctor/1'
STATUSES = ('ok', 'warn', 'fail', 'info', 'skip')
COPILOT_CHAT = 'github.copilot-chat'
INSTALL_FROM_GIT = ('uv tool install "git+https://github.com/hypotrail/hypotrail'
                    '#subdirectory=framework"')
UV_INSTALL = {'nt': 'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"',
              'posix': 'curl -LsSf https://astral.sh/uv/install.sh | sh'}
STUDY_OPTIONAL = ('*',)


def check(id_: str, status: str, detail: str, fix: str | None = None) -> dict:
    assert status in STATUSES
    return {'id': id_, 'status': status, 'detail': detail, 'fix': fix}


def _out(argv, timeout=30) -> str | None:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              encoding='utf-8', errors='replace')
    except (OSError, subprocess.SubprocessError):
        return None
    return (proc.stdout or '').strip() if proc.returncode == 0 else None


def check_python() -> dict:
    v = sys.version_info
    detail = f'Python {platform.python_version()} at {sys.executable}'
    if (v.major, v.minor) == (3, 13):
        return check('python', 'ok', detail)
    return check('python', 'fail', detail + ' (the engine needs Python 3.13)',
                 'uv python install 3.13, then reinstall: ' + INSTALL_FROM_GIT + ' --python 3.13')


def check_uv() -> dict:
    uv = shutil.which('uv')
    if not uv:
        return check('uv', 'warn', 'uv is not on PATH (needed to install or update the engine '
                     'and by a source checkout)', UV_INSTALL['nt' if os.name == 'nt' else 'posix'])
    return check('uv', 'ok', f'{_out([uv, "--version"]) or "uv"} at {uv}')


def check_engine() -> dict:
    from importlib.metadata import PackageNotFoundError, version
    from . import agent_files
    try:
        installed = version('hypotrail')
    except PackageNotFoundError:
        installed = None
    cli = agent_files.cli_command()
    detail = (f'hypotrail {installed or "(source checkout)"}; a new study\'s agent runs it '
              f'as: {cli["shell"]} ({cli["how"]})')
    if cli['how'] == 'python_path':
        return check('engine', 'warn', detail, INSTALL_FROM_GIT)
    return check('engine', 'ok', detail)


def check_platform() -> dict:
    from . import lock
    system = platform.system()
    detail = f'{system} {platform.release()} ({platform.machine()})'
    if os.environ.get('CODESPACES') == 'true':
        detail += ', GitHub Codespaces'
    elif 'microsoft' in platform.release().lower():
        detail += ', WSL'
    try:
        backend = lock.require_locking()
    except Exception as exc:   # noqa: BLE001 - the lock module's own refusal
        return check('platform', 'fail', f'{detail}: studies cannot be written here '
                     f'({getattr(exc, "message", exc)})',
                     'Use a Linux, macOS or Windows Python with its standard library '
                     '(fcntl or msvcrt), or a Codespace.')
    return check('platform', 'ok', f'{detail}; file locks: {backend}')


def check_code(found) -> dict:
    code, how = found
    if code is None:
        return check('vscode', 'warn', 'No VS Code command line found (code, code.cmd, '
                     'code-server)', 'Install VS Code, then in VS Code: Command Palette, "Shell '
                     'Command: Install \'code\' command in PATH" (macOS); on Windows the installer '
                     'adds it. Or write the panel with: hypotrail setup vscode --vsix-out FILE')
    return check('vscode', 'ok', f'{code} ({how})')


def _extensions(code: str | None) -> list[str] | None:
    if code is None:
        return None
    out = _out([code, '--list-extensions', '--show-versions'], timeout=60)
    return None if out is None else [x.strip() for x in out.splitlines() if x.strip()]


def check_agents(extensions) -> dict:
    found = []
    if extensions is not None and any(x.lower().startswith(COPILOT_CHAT + '@')
                                      for x in extensions):
        found.append('GitHub Copilot Chat (VS Code)')
    claude = shutil.which('claude')
    if claude:
        found.append(f'Claude Code ({claude})')
    if found:
        return check('chat_agent', 'ok', ', '.join(found))
    if extensions is None:
        return check('chat_agent', 'info', 'Could not list the VS Code extensions; Claude Code '
                     'is not on PATH', None)
    return check('chat_agent', 'warn', 'Neither GitHub Copilot Chat nor Claude Code was found',
                 'In VS Code: Extensions view, install "GitHub Copilot Chat" and sign in; or '
                 'install Claude Code')


def check_panel(code: str | None, extensions) -> dict:
    from . import cmd_setup
    try:
        pkg = cmd_setup.package_json(cmd_setup.panel_source())
    except Exception as exc:   # noqa: BLE001
        return check('panel', 'fail', f'The study panel is not in this installation: {exc}',
                     INSTALL_FROM_GIT + ' --force')
    ext, want = cmd_setup.extension_id(pkg), pkg['version']
    if extensions is None:
        return check('panel', 'info', f'Panel {ext} {want} ships with the engine; not checked in '
                     'VS Code', 'hypotrail setup vscode')
    have = next((x.partition('@')[2] for x in extensions
                 if x.lower().partition('@')[0] == ext.lower()), None)
    if have is None:
        return check('panel', 'warn', f'{ext} is not installed in VS Code ({code})',
                     'hypotrail setup vscode')
    if have != want:
        return check('panel', 'warn', f'{ext} {have} installed, the engine ships {want}',
                     'hypotrail setup vscode')
    return check('panel', 'ok', f'{ext} {have} installed')


def check_execution_policy() -> dict:
    if os.name != 'nt':
        return check('powershell_policy', 'skip', 'Not Windows')
    exe = shutil.which('powershell') or shutil.which('pwsh')
    policy = _out([exe, '-NoProfile', '-Command', 'Get-ExecutionPolicy']) if exe else None
    if policy is None:
        return check('powershell_policy', 'info', 'Could not read the execution policy')
    if policy.strip() in ('Restricted', 'AllSigned'):
        return check('powershell_policy', 'warn', f'PowerShell execution policy: {policy} '
                     '(the uv installer and venv scripts cannot run)',
                     'Set-ExecutionPolicy -Scope CurrentUser RemoteSigned')
    return check('powershell_policy', 'ok', f'PowerShell execution policy: {policy}')


def check_long_paths() -> dict:
    if os.name != 'nt':
        return check('long_paths', 'skip', 'Not Windows')
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r'SYSTEM\CurrentControlSet\Control\FileSystem') as key:
            value, _ = winreg.QueryValueEx(key, 'LongPathsEnabled')
    except OSError:
        value = 0
    if value == 1:
        return check('long_paths', 'ok', 'Long paths are enabled')
    return check('long_paths', 'warn', 'Long paths are disabled: deep study folders (over 260 '
                 'characters) fail', 'As administrator, in PowerShell: New-ItemProperty -Path '
                 '"HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FileSystem" -Name '
                 '"LongPathsEnabled" -Value 1 -PropertyType DWORD -Force; or keep studies in a '
                 'short folder such as C:\\studies')


def check_onedrive(folder: Path) -> dict:
    roots = [os.environ.get(k) for k in ('OneDrive', 'OneDriveCommercial', 'OneDriveConsumer')]
    text = str(folder)
    synced = any(r and os.path.normcase(text).startswith(os.path.normcase(r)) for r in roots) \
        or re.search(r'(^|[\\/])OneDrive( - [^\\/]+)?([\\/]|$)', text) is not None
    if synced:
        return check('onedrive', 'warn', f'{folder} is in a OneDrive folder: syncing can lock '
                     'files while the engine replaces them and copies study state between '
                     'machines', 'Create studies outside OneDrive, for example in '
                     + ('C:\\studies' if os.name == 'nt' else '~/studies'))
    return check('onedrive', 'ok', f'{folder} is not in a OneDrive folder')


def check_proxy() -> dict:
    proxy = [k for k in ('HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy')
             if os.environ.get(k)]
    certs = [k for k in ('UV_SYSTEM_CERTS', 'UV_NATIVE_TLS', 'SSL_CERT_FILE',
                         'REQUESTS_CA_BUNDLE') if os.environ.get(k)]
    if not proxy:
        return check('proxy', 'ok', 'No proxy variable set'
                     + (f'; certificates: {", ".join(certs)}' if certs else ''))
    detail = f'Proxy variables: {", ".join(proxy)}'
    if certs:
        return check('proxy', 'ok', f'{detail}; certificates: {", ".join(certs)}')
    fix = ('$env:UV_SYSTEM_CERTS = "1"   (or setx UV_SYSTEM_CERTS 1)' if os.name == 'nt'
           else 'export UV_SYSTEM_CERTS=1')
    return check('proxy', 'warn', detail + '; no certificate variable: a corporate proxy that '
                 'inspects TLS makes uv fail with a certificate error', fix)


def run_checks(folder: Path | None = None) -> list[dict]:
    from . import cmd_setup
    folder = (folder or Path.cwd()).resolve()
    out: list[dict] = []

    def guarded(id_, fn, *a):
        try:
            out.append(fn(*a))
        except Exception as exc:   # noqa: BLE001 - doctor never fails hard
            out.append(check(id_, 'warn', f'The check failed: {exc}'))

    guarded('python', check_python)
    guarded('uv', check_uv)
    guarded('engine', check_engine)
    guarded('platform', check_platform)
    try:
        found = cmd_setup.find_code()
    except Exception:   # noqa: BLE001
        found = (None, 'missing')
    guarded('vscode', check_code, found)
    extensions = _extensions(found[0])
    guarded('chat_agent', check_agents, extensions)
    guarded('panel', check_panel, found[0], extensions)
    guarded('powershell_policy', check_execution_policy)
    guarded('long_paths', check_long_paths)
    guarded('onedrive', check_onedrive, folder)
    guarded('proxy', check_proxy)
    return out


def report(folder: Path | None = None) -> dict:
    checks = run_checks(folder)
    counts = {s: sum(1 for c in checks if c['status'] == s) for s in STATUSES}
    return {'schema': SCHEMA, 'ok': True, 'platform': sys.platform, 'checks': checks,
            'counts': counts,
            'fixes': [c['fix'] for c in checks if c['fix'] and c['status'] in ('warn', 'fail')]}


# --- CLI ----------------------------------------------------------------------------------

def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--dir', default=None, metavar='FOLDER',
                        help='the folder where studies will live (default: the current one)')


def main(args: argparse.Namespace):
    from .commands import Outcome
    return Outcome(report(Path(args.dir) if args.dir else None))


MARKS = {'ok': 'ok  ', 'warn': 'WARN', 'fail': 'FAIL', 'info': 'info', 'skip': 'skip'}


def text(payload: dict) -> str:
    lines = []
    for c in payload['checks']:
        lines.append(f'[{MARKS[c["status"]]}] {c["id"]}: {c["detail"]}')
        if c['fix'] and c['status'] in ('warn', 'fail', 'info'):
            lines.append(f'       fix: {c["fix"]}')
    n = payload['counts']
    lines.append(f'{n["ok"]} ok, {n["warn"]} warning(s), {n["fail"]} failure(s)')
    return '\n'.join(lines)
