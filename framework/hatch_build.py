"""Hatch build hook: ship the study panel's sources inside the ``hypotrail`` wheel.

Onboarding Lot 1 (docs/plans/ONBOARDING-SPEC.md): ``hypotrail setup vscode`` builds the
panel's VSIX in pure Python from sources shipped as package data, so a user needs no Node.
The panel lives outside this project (``clients/vscode-companion/``), so:

* a wheel built from the repository (``uv build``, ``uv tool install`` from Git or a local
  path, ``pip install framework/``) takes the files from ``../clients/vscode-companion``;
* an sdist carries them under ``vscode-panel/`` so that a wheel built from the sdist finds
  them there;
* an editable install takes nothing: ``mlkit.study.cmd_setup`` reads the checkout directly.

The selection is :data:`PANEL_FILES` and :data:`PANEL_DIRS` (the files a VSIX holds); the
same rule is in ``mlkit.study.cmd_setup`` and a test compares them. A missing source fails
the build rather than shipping a package without its panel.
"""
from __future__ import annotations

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

PANEL_FILES = ('package.json', 'extension.js', 'README.md')
PANEL_DIRS = ('lib', 'media')
WHEEL_PREFIX = 'mlkit/study/panel'
SDIST_PREFIX = 'vscode-panel'


def panel_sources(root: Path) -> dict[str, Path]:
    """``{relative POSIX path: source file}`` of the panel, from the checkout or the sdist."""
    for src in (root.parent / 'clients' / 'vscode-companion', root / SDIST_PREFIX):
        if (src / 'package.json').is_file():
            break
    else:
        raise RuntimeError('the study panel sources are missing: expected '
                           f'{root.parent / "clients" / "vscode-companion"} or '
                           f'{root / SDIST_PREFIX}')
    files = {name: src / name for name in PANEL_FILES}
    for d in PANEL_DIRS:
        for p in sorted((src / d).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:
                files[p.relative_to(src).as_posix()] = p
    missing = [n for n, p in files.items() if not p.is_file()]
    if missing:
        raise RuntimeError(f'the study panel sources are incomplete: {", ".join(missing)}')
    return files


class PanelHook(BuildHookInterface):
    PLUGIN_NAME = 'custom'

    def initialize(self, version: str, build_data: dict) -> None:
        if self.target_name == 'wheel' and version == 'editable':
            return
        prefix = WHEEL_PREFIX if self.target_name == 'wheel' else SDIST_PREFIX
        for rel, path in panel_sources(Path(self.root)).items():
            build_data['force_include'][str(path)] = f'{prefix}/{rel}'
