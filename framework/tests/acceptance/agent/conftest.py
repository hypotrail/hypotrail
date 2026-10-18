"""Agent acceptance tests are excluded from default pytest runs.

They launch real `claude -p` sessions (cost, non-determinism). Opt in with
``HYPOTRAIL_AGENT_ACCEPTANCE=1`` and select them with ``-m agent_acceptance``.
"""
import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get('HYPOTRAIL_AGENT_ACCEPTANCE') == '1':
        return
    skip = pytest.mark.skip(reason='agent acceptance runs real Claude Code sessions; '
                                   'set HYPOTRAIL_AGENT_ACCEPTANCE=1 to run')
    for item in items:
        if 'agent_acceptance' in item.keywords:
            item.add_marker(skip)
