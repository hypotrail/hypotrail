"""Understanding review tests (ADR 0008). Studies, repositories and banks live in tmp_path.

Every "human" in these tests is a simulated declaration of a test fixture (``simulated:
true``); no test establishes that a real person understood anything.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(autouse=True, scope='module')
def neutral_git_config(tmp_path_factory):
    """Every Git call of these tests (theirs and the engine's) reads a neutral user config.

    Git for Windows sets ``core.autocrlf=true`` system-wide, so a test repository there converts
    end of lines and the engine rightly refuses it (``git_index_conflict``, R9CD-2). The user
    config, read after the system one, sets it back to false; a test that studies a conversion
    sets it in the repository itself. The engine strips every inherited ``GIT_*`` variable
    (``verify.git_env``), so the config goes through ``HOME`` (and ``XDG_CONFIG_HOME``), for
    one test module at a time: the rest of the suite keeps its own home (the uv cache)."""
    home = tmp_path_factory.mktemp('git-home')
    (home / '.gitconfig').write_text('[core]\n\tautocrlf = false\n', encoding='utf-8')
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv('HOME', str(home))
        mp.setenv('XDG_CONFIG_HOME', str(home / '.config'))
        yield home
