"""Contract tests of this export (Hypotrail, team-azureml-v1).

They check the folder as exported: checksums, contract copies, Azure YAML graph, effective
code upload, and the Hydra freeze (a scientific override is refused, an operational one
keeps the identity). A test whose dependency is missing is skipped with its reason: a
skipped check is not a passed check.
"""

import importlib.util
import json
from pathlib import Path

import pytest

from src.pipeline.utils.hypotrail import azure_yaml, canonical, contracts, transfer
from src.pipeline.utils.hypotrail.errors import ProjectError

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "hypotrail"
MANIFEST = json.loads((DATA / "contracts" / "export-manifest.json").read_text(encoding="utf-8"))
HAS_HYDRA = importlib.util.find_spec("hydra") is not None
HAS_YAML = importlib.util.find_spec("yaml") is not None


def test_data_checksums_hold() -> None:
    """Every contract and model file matches data/hypotrail/SHA256SUMS."""
    assert contracts.verify_data_dir(DATA)


def test_manifest_files_are_unchanged() -> None:
    """Every file the export manifest lists still has its exported bytes."""
    changed = [f["path"] for f in MANIFEST["files"] if contracts.sha256_file(ROOT / f["path"]) != f["sha256"]]
    assert not changed, f"changed since the export (re-run its checks): {changed}"


def test_no_forbidden_root() -> None:
    """The project adds no azure/, deployment/, model/ or scripts/ root."""
    assert not [p.name for p in ROOT.iterdir() if p.name in ("azure", "deployment", "model", "scripts")]


@pytest.mark.skipif(not HAS_YAML, reason="PyYAML is not installed")
def test_azure_yaml_graph_is_consistent() -> None:
    """Every Azure expression names an existing port; no asset uses latest."""
    problems, graph = azure_yaml.check(ROOT)
    assert problems == []
    assert graph["jobs"] == ["evaluate_job", "prep_job", "split_job", "train_job"]


def test_code_upload_holds_only_code() -> None:
    """With .amlignore, the code upload holds src/ and project metadata only."""
    files = transfer.transferable(ROOT)
    assert files and all(f.startswith("src/") or "/" not in f for f in files)
    assert not [f for f in files if f.startswith(("data/", "tests/", "notebooks/"))]


def _compose(overrides: list[str]) -> dict:
    from hydra import compose, initialize_config_dir

    from src.pipeline.utils.hypotrail.config import freeze

    with initialize_config_dir(config_dir=str(ROOT / "src" / "conf"), version_base=None):
        return freeze(compose(config_name="config", overrides=overrides))


@pytest.mark.skipif(not HAS_HYDRA, reason="Hydra is not installed")
def test_default_configuration_freezes_to_the_exported_identity() -> None:
    """The composed configuration projects to the exported scientific identity."""
    frozen = _compose([])
    assert frozen["scientific_sha256"] == canonical.canonical_sha256(
        json.loads((DATA / "contracts" / "scientific-projection.json").read_text(encoding="utf-8"))
    )


@pytest.mark.skipif(not HAS_HYDRA, reason="Hydra is not installed")
def test_operational_override_keeps_the_identity() -> None:
    """Changing paths or logs keeps the scientific identity."""
    assert _compose(["models.path=/tmp/elsewhere", "debug=true"])["scientific_sha256"] == _compose([])["scientific_sha256"]


@pytest.mark.skipif(not HAS_HYDRA, reason="Hydra is not installed")
@pytest.mark.parametrize(
    ("override", "code"),
    [
        ("components/training=random_forest", "scientific_config_changed"),
        ("components.evaluation.metrics=[accuracy]", "scientific_config_changed"),
        ("+components.training.model.params.extra=1", "scientific_config_changed"),
        ("+surprise=1", "contract_invalid"),
        ("+components.training._target_=os.system", "contract_invalid"),
        ("hypotrail.execution.allow_scientific_override=true", "capability_not_supported"),
    ],
)
def test_scientific_or_unknown_override_is_refused(override: str, code: str) -> None:
    """A scientific override, an unknown key or a _target_ is refused."""
    with pytest.raises(ProjectError) as error:
        _compose([override])
    assert error.value.code == code
