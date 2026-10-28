"""R69: init writes a README saying where the data are, and a ``data`` link (never a copy)."""
import os
from pathlib import Path

from mlkit.study import commands

CASE = Path(__file__).resolve().parents[3] / 'use-cases' / 'auto-mpg'


def test_init_writes_the_readme_and_the_data_link(tmp_path):
    study = tmp_path / 'study'
    commands.init(CASE, study, language='fr')
    link = study / 'data'
    assert link.is_symlink() and not os.path.isabs(os.readlink(link))
    assert (link / 'auto-mpg.data').resolve() == (CASE / 'data' / 'auto-mpg.data').resolve()
    text = (study / 'README.md').read_text(encoding='utf-8')
    assert str((CASE / 'data' / 'auto-mpg.data').resolve()) in text
    assert 'test final' in text and 'notebooks/' in text
