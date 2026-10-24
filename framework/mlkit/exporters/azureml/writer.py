"""Atomic publication of an export folder (export spec §16 I-03, I-04).

The project is written into a temporary sibling folder, checked there (inventory,
AZ-STRUCT-02), then published by one rename. A failure removes the temporary folder and
leaves the destination as it was; an existing non-empty destination, a symbolic link, or a
folder inside the study's own folders is refused before anything is written.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from . import layout
from .errors import ExportError

FORBIDDEN = ('.hypotrail', 'reports', 'notebooks')
READ_MODE = 0o644


def target(out, study_dir: Path) -> Path:
    """The destination folder, refused when unsafe (nothing is written)."""
    if out is None:
        raise ExportError('invalid_arguments', '--out is required to write an export.',
                          path='out', remediation='Pass a new or empty folder, or --plan.')
    path = Path(out)
    if not path.is_absolute():
        path = Path.cwd() / path
    if path.is_symlink():
        raise ExportError('invalid_arguments', '--out may not be a symbolic link.', path='out',
                          remediation='Choose a real folder.')
    real = Path(os.path.realpath(path))
    study = Path(os.path.realpath(study_dir))
    for name in FORBIDDEN:
        folder = study / name
        if real == folder or folder in real.parents:
            raise ExportError('invalid_arguments', f'--out may not be inside the study folder '
                              f'{name}/.', path='out',
                              remediation='Choose a folder outside the engine files and '
                                          'deliverables.')
    if real == study or real in study.parents:
        raise ExportError('invalid_arguments', '--out may not be the study folder or contain it.',
                          path='out', remediation='Choose a new folder.')
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ExportError('destination_not_empty', 'The export folder exists and is not empty; '
                          'nothing was written.', path='out',
                          remediation='Choose a new folder; an export never overwrites one.',
                          details={'out': str(path)})
    return path


def _umask() -> int:
    mask = os.umask(0o022)
    os.umask(mask)
    return mask


def publish(files, directories: list[str], destination: Path,
            template: layout.Template) -> None:
    """Write ``files`` (``render.File``) and the empty ``directories``, check, publish."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f'.{destination.name}.export-', dir=destination.parent))
    try:
        for directory in directories:
            (staging / directory).mkdir(parents=True, exist_ok=True)
        for item in files:
            path = staging / item.path
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'xb') as handle:
                handle.write(item.data)
            os.chmod(path, READ_MODE)
        for item in files:
            if (staging / item.path).read_bytes() != item.data:
                raise ExportError('artifact_integrity_failed', 'A written file differs from its '
                                  'rendering.', path=item.path, remediation='Retry the export.')
        problems = layout.check_tree(staging, template)
        if problems:
            raise ExportError('template_layout_mismatch', 'The generated folder does not fit the '
                              'team template layout; nothing was published.', path='out',
                              remediation='Report this generator defect.',
                              details={'problems': problems})
        if destination.exists():
            if any(destination.iterdir()):
                raise ExportError('destination_not_empty', 'The export folder was filled '
                                  'meanwhile; nothing was published.', path='out',
                                  remediation='Choose a new folder.')
            destination.rmdir()
        # mkdtemp made the staging folder 0700 (private while it is written); the published
        # root follows the umask, as every folder inside it does.
        os.chmod(staging, 0o777 & ~_umask())
        os.rename(staging, destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
