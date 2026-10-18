"""Environment smoke test: the locked framework environment imports the engine."""
import marimo


def test_engine_modules_import():
 from mlkit import pilot, reliability
 assert callable(pilot.main) and callable(reliability.apply)


def test_marimo_version_is_pinned():
 assert marimo.__version__=='0.25.1'


def test_package_assets_are_available():
 from importlib.resources import files
 assert files('mlkit').joinpath('assets/design.css').is_file()
