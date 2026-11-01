"""``hypotrail setup vscode``: install the study panel into VS Code, without Node (Lot 1).

The study panel (``clients/vscode-companion/``, plain JavaScript, no build step) ships inside
the Python package as package data (``mlkit/study/panel/``, added to the wheel by
``framework/hatch_build.py``); a source checkout reads ``clients/vscode-companion/``
directly. The VSIX is built here in pure Python (:func:`build_vsix`: a zip with
``extension.vsixmanifest``, ``[Content_Types].xml`` and ``extension/...``, verified byte for
byte against ``@vscode/vsce`` 3.9.2 on the ``extension/`` members, see
``docs/plans/onboarding/mkvsix-prototype.py``), then installed with the VS Code command line
(:func:`find_code`): ``code`` (``code.cmd`` on Windows), else the VS Code server's own
``code-server`` (Codespaces, remote containers).

``--vsix-out PATH`` only writes the file (to install by hand: Extensions view, "...",
"Install from VSIX..."). The panel stays behind its feature flag, off by default: installing
it changes no setting (``hypotrail new`` writes the study's flag and stage).
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from .errors import StudyError

SCHEMA = 'hypotrail.setup/1'
# The same selection rule as framework/hatch_build.py (a test compares them).
PANEL_FILES = ('package.json', 'extension.js', 'README.md')
PANEL_DIRS = ('lib', 'media')
PACKAGED = Path(__file__).resolve().parent / 'panel'
CHECKOUT = Path(__file__).resolve().parents[3] / 'clients' / 'vscode-companion'
_EPOCH = (2020, 1, 1, 0, 0, 0)
CONTENT_TYPES = {'.vsixmanifest': 'text/xml', '.json': 'application/json',
                 '.js': 'application/javascript', '.md': 'text/markdown', '.css': 'text/css',
                 '.svg': 'image/svg+xml', '.png': 'image/png', '.html': 'text/html'}
TIMEOUT = 180


def SetupError(code: str, message: str, **details) -> StudyError:   # noqa: N802
    """A refusal without effect (``hypotrail.error/1``, exit 2)."""
    return StudyError(code, message, details=details or None)


def panel_source() -> Path:
    """The panel's sources: the package data of an installed engine, else the checkout."""
    for src in (PACKAGED, CHECKOUT):
        if (src / 'package.json').is_file():
            return src
    raise SetupError('panel_missing', 'The study panel sources are not in this installation '
                     f'(looked in {PACKAGED} and {CHECKOUT}).')


def panel_files(src: Path) -> dict[str, Path]:
    """``{relative POSIX path: file}``: the three top files, then ``lib/`` and ``media/``."""
    files = {name: src / name for name in PANEL_FILES}
    for d in PANEL_DIRS:
        for p in sorted((src / d).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:
                files[p.relative_to(src).as_posix()] = p
    missing = [n for n, p in files.items() if not p.is_file()]
    if missing:
        raise SetupError('panel_missing', 'The study panel sources are incomplete: '
                         + ', '.join(missing))
    return files


def package_json(src: Path) -> dict:
    return json.loads((src / 'package.json').read_text(encoding='utf-8'))


def extension_id(pkg: dict) -> str:
    return f'{pkg["publisher"]}.{pkg["name"]}'


def manifest(pkg: dict) -> str:
    """``extension.vsixmanifest`` as ``vsce`` writes it for this package."""
    return f'''<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
<Metadata>
<Identity Language="en-US" Id="{escape(pkg['name'])}" Version="{escape(pkg['version'])}" Publisher="{escape(pkg['publisher'])}" />
<DisplayName>{escape(pkg.get('displayName', pkg['name']))}</DisplayName>
<Description xml:space="preserve">{escape(pkg.get('description', ''))}</Description>
<Tags></Tags><Categories>{escape(','.join(pkg.get('categories', [])))}</Categories><GalleryFlags>Public</GalleryFlags>
<Properties>
<Property Id="Microsoft.VisualStudio.Code.Engine" Value="{escape(pkg['engines']['vscode'])}" />
<Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value="" />
<Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value="" />
<Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace" />
<Property Id="Microsoft.VisualStudio.Code.LocalizedLanguages" Value="" />
<Property Id="Microsoft.VisualStudio.Code.EnabledApiProposals" Value="" />
<Property Id="Microsoft.VisualStudio.Code.ExecutesCode" Value="true" />
<Property Id="Microsoft.VisualStudio.Services.GitHubFlavoredMarkdown" Value="true" />
<Property Id="Microsoft.VisualStudio.Services.Content.Pricing" Value="Free"/>
</Properties>
</Metadata>
<Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>
<Dependencies/>
<Assets>
<Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
<Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/readme.md" Addressable="true" />
</Assets>
</PackageManifest>
'''


def vsix_members(src: Path) -> dict[str, Path]:
    """``{member name: source file}`` of the ``extension/`` part (``README.md`` becomes
    ``extension/readme.md``, as ``vsce`` names it)."""
    return {'extension/' + ('readme.md' if rel == 'README.md' else rel): path
            for rel, path in panel_files(src).items()}


def content_types(names) -> str:
    exts = sorted({Path(n).suffix.lower() for n in names} | {'.vsixmanifest'})
    return ('<?xml version="1.0" encoding="utf-8"?>\n<Types xmlns="http://schemas.'
            'openxmlformats.org/package/2006/content-types">'
            + ''.join(f'<Default Extension="{e}" ContentType="'
                      f'{CONTENT_TYPES.get(e) or mimetypes.guess_type("x" + e)[0] or "application/octet-stream"}"/>'
                      for e in exts) + '</Types>')


def build_vsix(src: Path, out: Path) -> dict:
    """Write the VSIX of the panel at ``src`` to ``out`` (fixed timestamps, sorted members:
    the same sources give the same bytes). Returns ``{path, extension, version, members}``."""
    pkg = package_json(src)
    members = vsix_members(src)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + '.part')
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        def put(name, data):
            info = zipfile.ZipInfo(name, _EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
        put('extension.vsixmanifest', manifest(pkg))
        put('[Content_Types].xml', content_types(members))
        for name, path in members.items():
            put(name, path.read_bytes())
    os.replace(tmp, out)
    return {'path': str(out), 'extension': extension_id(pkg), 'version': pkg['version'],
            'members': len(members) + 2}


# --- the VS Code command line -------------------------------------------------------------

def _code_server() -> str | None:
    """The newest VS Code server CLI (``.../bin/code-server``) of a remote host."""
    found = []
    for root in (Path('/vscode'), Path.home() / '.vscode-remote', Path.home() / '.vscode-server'):
        if not root.is_dir():
            continue
        for path in root.glob('**/bin/code-server'):
            if path.is_file() and len(path.relative_to(root).parts) <= 7:
                try:
                    found.append((path.stat().st_mtime, str(path)))
                except OSError:
                    pass
    return max(found)[1] if found else None


def _known_locations() -> list[Path]:
    if os.name == 'nt':
        local = os.environ.get('LOCALAPPDATA', '')
        program = os.environ.get('ProgramFiles', r'C:\Program Files')
        return [Path(local) / 'Programs' / 'Microsoft VS Code' / 'bin' / 'code.cmd',
                Path(program) / 'Microsoft VS Code' / 'bin' / 'code.cmd']
    return [Path('/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code'),
            Path('/usr/share/code/bin/code'), Path('/snap/bin/code')]


def find_code() -> tuple[str | None, str]:
    """``(command, how)`` of the VS Code command line: ``HYPOTRAIL_CODE``; the ``code`` of a
    VS Code integrated terminal; the VS Code server's ``code-server`` (Codespaces); ``code``
    on PATH (``code.cmd`` on Windows, found through PATHEXT); a usual install location."""
    override = os.environ.get('HYPOTRAIL_CODE', '').strip()
    if override:
        return override, 'override'
    code = shutil.which('code')
    if code and os.environ.get('VSCODE_IPC_HOOK_CLI'):
        return code, 'integrated_terminal'
    server = _code_server()
    if server:
        return server, 'code_server'
    if code:
        return code, 'path'
    for path in _known_locations():
        if path.is_file():
            return str(path), 'known_location'
    return None, 'missing'


def _run(argv, timeout=TIMEOUT) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                          encoding='utf-8', errors='replace')


def installed_version(code: str, ext_id: str) -> str | None:
    """The version of ``ext_id`` installed in that VS Code, or None."""
    try:
        proc = _run([code, '--list-extensions', '--show-versions'], timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in proc.stdout.splitlines():
        name, _, version = line.strip().partition('@')
        if name.lower() == ext_id.lower():
            return version or ''
    return None


def install(*, vsix_out: str | None = None, force: bool = False) -> dict:
    src = panel_source()
    pkg = package_json(src)
    ext = extension_id(pkg)
    base = {'schema': SCHEMA, 'ok': True, 'target': 'vscode', 'extension': ext,
            'version': pkg['version'], 'source': str(src)}
    if vsix_out:
        built = build_vsix(src, Path(vsix_out).expanduser().resolve())
        return {**base, 'status': 'written', 'vsix': built['path'], 'code': None,
                'message': f'VSIX written to {built["path"]}. To install it by hand: VS Code, '
                           'Extensions view, "...", "Install from VSIX...".'}
    code, how = find_code()
    if code is None:
        raise SetupError('vscode_missing', 'No VS Code command line was found (code, code.cmd '
                         'or code-server). Install VS Code and its "code" command, or write the '
                         'file with --vsix-out PATH and install it from the Extensions view.')
    current = installed_version(code, ext)
    if current == pkg['version'] and not force:
        return {**base, 'status': 'already_installed', 'vsix': None, 'code': code,
                'code_how': how, 'message': f'{ext} {current} is already installed.'}
    with tempfile.TemporaryDirectory(prefix='hypotrail-panel-') as tmp:
        built = build_vsix(src, Path(tmp) / f'{pkg["name"]}-{pkg["version"]}.vsix')
        try:
            proc = _run([code, '--install-extension', built['path'], '--force'])
        except (OSError, subprocess.SubprocessError) as exc:
            raise SetupError('install_failed', f'{code} could not be run: {exc}') from exc
    if proc.returncode != 0:
        raise SetupError('install_failed', f'{code} --install-extension failed '
                         f'(exit {proc.returncode}).',
                         stderr=(proc.stderr or proc.stdout or '')[-2000:])
    return {**base, 'status': 'installed', 'vsix': None, 'code': code, 'code_how': how,
            'previous_version': current,
            'message': f'{ext} {pkg["version"]} installed. In an open VS Code window, run '
                       '"Developer: Reload Window" if its commands do not appear. The panel '
                       'stays off until a study enables it (hypotrail new does).'}


# --- CLI ----------------------------------------------------------------------------------

STUDY_OPTIONAL = ('vscode',)


def configure(parser: argparse.ArgumentParser) -> None:
    from .cli import Parser, _common

    verbs = parser.add_subparsers(dest='verb', required=True, parser_class=Parser)
    p = verbs.add_parser('vscode', parents=[_common(False)],
                         help='install the study panel into VS Code (no Node needed)')
    p.add_argument('--vsix-out', default=None, metavar='PATH',
                   help='only write the VSIX file to PATH (install it by hand)')
    p.add_argument('--force', action='store_true',
                   help='reinstall even when the same version is installed')


def main(args: argparse.Namespace):
    from .commands import Outcome

    return Outcome(install(vsix_out=args.vsix_out, force=args.force))


def text(payload: dict) -> str:
    lines = [payload.get('message', '')]
    if payload.get('code'):
        lines.append(f'VS Code command line: {payload["code"]}')
    return '\n'.join(x for x in lines if x)
