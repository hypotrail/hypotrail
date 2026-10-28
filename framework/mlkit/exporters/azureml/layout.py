"""The versioned template team-azureml-v1 and the structure check AZ-STRUCT-02.

``templates/team-azureml-v1/`` holds the cleaned skeleton of the team's archive: its
``template.json`` manifest, the store of files (a path component starting with ``.`` is
stored as ``dot-...`` so that no stored ``.gitignore`` acts on this repository),
``layout.json`` (TEMPLATE-LAYOUT-v1.json, byte-identical to the shared contract) and
``transport.json`` (the SHA-256 of every file kept from the original archive). The
archive itself is never executed or extracted at export time.

:func:`check_tree` compares a generated folder with the layout: every preserved path
exists, the business data are removed, every addition is in the allowlist, no forbidden
root, no macOS or git metadata, no active code of the template's example (shuttles,
companies, reviews), the Azure expressions and graph are intact, and the effective code
upload (``.amlignore`` applied) holds only code.

The example-code check reads the template's own files (:meth:`Template.example_code`),
before any rendering: the case id, title, feature or target names a study writes into the
project are never matched, so a case about reviews or companies exports (review round 4,
R4-B2). Every shipped byte that is not a value of the study comes from those files.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from . import azure_yaml, canonical as cj, transfer
from .errors import ExportError

TEMPLATES = Path(__file__).resolve().parent / 'templates'
KNOWN = ('team-azureml-v1',)
# The shared contracts, as received with the work package (docs/specs/azureml-export/).
LAYOUT_SHA256 = 'a184c33b3a1f2d457092b47cdce49633011c28b8bee0c4e599ba3cc938aaad56'
TRANSPORT_SHA256 = '81bcb664a2eacfa442b06f3695a3bd49e13b61e1ace654e9fc632a7aeca1d710'
EXAMPLE_CODE = re.compile(r'shuttle|companies|reviews|space ?shuttle', re.IGNORECASE)
CODE_ROOTS = ('src/', 'tests/', 'aml/', '.vscode/', '.ci/', 'notebooks/')
CODE_SUFFIXES = ('.py', '.yml', '.yaml', '.json', '.ipynb')
STORED_KINDS = ('preserved', 'adapted', 'rendered', 'added')
UPLOAD_ALLOWED = re.compile(r'(src/.+|\.amlignore|\.gitignore|\.pre-commit-config\.yaml|'
                            r'README\.md|environment\.yml|pyproject\.toml)')
METADATA = re.compile(r'(^|/)(\.git|__MACOSX)(/|\Z)|(^|/)\.DS_Store\Z|(^|/)\._[^/]*\Z')


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Template:
    id: str
    root: Path

    @cached_property
    def document(self) -> dict:
        return json.loads((self.root / 'template.json').read_text(encoding='utf-8'))

    @property
    def version(self) -> str:
        return self.document['version']

    @property
    def files(self) -> list[dict]:
        return self.document['files']

    def read(self, relative: str) -> bytes:
        path = (self.root / relative).resolve()
        if self.root.resolve() not in path.parents or path.is_symlink():
            raise ExportError('template_layout_mismatch', 'A template entry leaves the store.',
                              path=relative, remediation='Fix the template manifest.')
        return path.read_bytes()

    @cached_property
    def layout(self) -> dict:
        return json.loads(self.read(self.document['layout']))

    @cached_property
    def transport(self) -> dict:
        return json.loads(self.read(self.document['transport']))

    @cached_property
    def sha256(self) -> str:
        """The identity of the template store: every stored file and its SHA-256."""
        items = sorted((p.relative_to(self.root).as_posix(), _sha(p.read_bytes()))
                       for p in self.root.rglob('*') if p.is_file()
                       and '__pycache__' not in p.parts)
        return cj.canonical_sha256([list(i) for i in items])

    def verify(self) -> None:
        """The store matches the shared layout and the transport inventory."""
        if _sha(self.read(self.document['layout'])) != LAYOUT_SHA256:
            raise ExportError('template_layout_mismatch', 'layout.json is not TEMPLATE-LAYOUT-v1.',
                              path='layout.json', remediation='Restore the shared contract.')
        if _sha(self.read(self.document['transport'])) != TRANSPORT_SHA256:
            raise ExportError('template_layout_mismatch', 'transport.json is not the transport '
                              'inventory.', path='transport.json',
                              remediation='Restore the shared inventory.')
        kept = {f['path']: f['sha256'] for f in self.transport['unchanged_files']}
        prefix = self.document['transport_prefix']
        for entry in self.files:
            if entry['kind'] != 'preserved':
                continue
            expected = kept.get(prefix + entry['path'])
            if expected is None or _sha(self.read(entry['source'])) != expected:
                raise ExportError('template_layout_mismatch', 'A preserved file differs from '
                                  'the team template.', path=entry['path'],
                                  remediation='Restore it byte for byte from the archive.')
        paths = [e['path'] for e in self.files]
        if len(paths) != len(set(paths)):
            raise ExportError('template_layout_mismatch', 'The template lists a path twice.',
                              path='template.json', remediation='Fix the template manifest.')
        problems = check_paths(self.layout, paths, require_preserved=True)
        if problems:
            raise ExportError('template_layout_mismatch', 'The template manifest does not fit '
                              'the layout.', path='template.json',
                              remediation='Fix the template manifest.',
                              details={'problems': problems})
        problems = self.example_code()
        if problems:
            raise ExportError('template_layout_mismatch', 'The template still holds code of its '
                              'example.', path='template.json',
                              remediation='Remove the example code from the template store.',
                              details={'problems': problems})

    def example_code(self) -> list[str]:
        """The code files of the project whose template source (the stored file, before its
        markers are replaced, or the shared generator module) holds code of the template's
        example. A value of the study is never read here."""
        problems = []
        for entry in self.files:
            path = entry['path']
            if not (path.startswith(CODE_ROOTS) and path.endswith(CODE_SUFFIXES)):
                continue
            if entry['kind'] in STORED_KINDS:
                data = self.read(entry['source'])
            elif entry['kind'] == 'shared':
                data = Path(importlib.util.find_spec(entry['module']).origin).read_bytes()
            else:   # generated by the generator from the study, or copied from the capture
                continue
            if EXAMPLE_CODE.search(data.decode('utf-8')):
                problems.append(f'example business code left: {path}')
        return problems


def load(template_id: str) -> Template:
    if template_id not in KNOWN:
        raise ExportError('template_unsupported', f'Template {template_id!r} is not supported.',
                          path='template', remediation=f'Use one of {", ".join(KNOWN)}; a new '
                          'team template needs its own reviewed version.')
    template = Template(template_id, TEMPLATES / template_id)
    template.verify()
    return template


def _allowed(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if pattern.endswith('/**'):
            if path.startswith(pattern[:-2]):
                return True
        elif path == pattern:
            return True
    return False


def check_paths(layout: dict, paths: list[str], *, require_preserved: bool) -> list[str]:
    """The layout problems of a list of file paths (the template's or a folder's)."""
    problems = []
    present = set(paths)
    removed = set(layout['removed_business_data'])
    original = set(layout['original_files']) - removed
    for required in layout['required_preserved_paths']:
        if require_preserved and required not in present:
            problems.append(f'missing preserved path {required}')
    for path in sorted(present):
        root = path.split('/', 1)[0]
        if root in layout['forbidden_new_roots']:
            problems.append(f'forbidden root {root}/ ({path})')
        if path in removed:
            problems.append(f'business example data kept: {path}')
        if METADATA.search(path):
            problems.append(f'metadata kept: {path}')
        if path not in original and path not in layout['additional_root_files_allowed'] \
                and not _allowed(path, layout['allowed_additions']):
            problems.append(f'addition outside the allowlist: {path}')
    return problems


def tree_paths(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob('*')
                  if p.is_file() or p.is_symlink())


def check_tree(root, template: Template) -> list[str]:
    """Every AZ-STRUCT-02 problem of a generated project folder (empty when conform)."""
    root = Path(root)
    problems = []
    for path in root.rglob('*'):
        if path.is_symlink():
            problems.append(f'symbolic link: {path.relative_to(root).as_posix()}')
    paths = tree_paths(root)
    problems += check_paths(template.layout, paths, require_preserved=True)
    for directory in template.layout['preserved_directory_skeleton']:
        if not (root / directory).is_dir():
            problems.append(f'missing directory {directory}/')
    # The template's sources, never the rendered values of the study (R4-B2).
    problems += template.example_code()
    yaml_problems, _ = azure_yaml.check(root)
    problems += yaml_problems
    for path in transfer.transferable(root):
        if not UPLOAD_ALLOWED.fullmatch(path):
            problems.append(f'code upload would include {path}')
    return problems
