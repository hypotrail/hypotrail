"""Configure pytest and shared fixtures.

This file is used to add the project's root directory to sys.path,
allowing tests to import modules from the src directory.
"""

import sys
from pathlib import Path

import pytest

# Get the root directory of the project
root_dir = Path(__file__).parent.parent.resolve()

# Add the root directory to sys.path
sys.path.append(str(root_dir))


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with custom settings."""
    config.addinivalue_line("filterwarnings", "ignore:pkg_resources is deprecated as an API:DeprecationWarning")
