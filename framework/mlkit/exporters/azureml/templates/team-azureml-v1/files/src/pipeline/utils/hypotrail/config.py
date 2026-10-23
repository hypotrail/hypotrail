"""Freezing of the Hydra configuration (Hypotrail export, spec L-18).

:func:`freeze` is the first call of every step. It

1. resolves the composed configuration, refusing a missing value (``???``);
2. converts it to plain JSON types and refuses NaN or infinite numbers;
3. refuses any key outside the closed shape of ``projection.CONFIG_SHAPE`` (a typo, a key
   added with ``+key=value``) and any ``_target_`` (no object is built from configuration);
4. compares its scientific projection with ``hypotrail.expected_scientific_sha256``: a
   difference is ``scientific_config_changed``, with the paths that differ;
5. returns the frozen configuration; the step reads only this frozen copy, so nothing
   (an environment variable, a resolver) can change the run after this point.

Operational overrides (paths, logs, tracking) keep the scientific identity. The Azure
expressions ``${{...}}`` are never read by OmegaConf: Azure ML replaces them in the
component command before Hydra parses the overrides.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from . import canonical, projection
from .errors import ProjectError

MAX_DIFFERENCES = 20


def _overrides() -> list[str]:
    try:
        from hydra.core.hydra_config import HydraConfig

        return list(HydraConfig.get().overrides.task)
    except (ImportError, ValueError):
        return []


def freeze_container(container: dict, overrides: list[str] | None = None) -> dict:
    """Freeze an already resolved configuration (plain containers)."""
    container = copy.deepcopy(container)
    container.pop("hydra", None)
    try:
        container = canonical.normalise(container, "config")
    except canonical.CanonicalError as error:
        raise ProjectError("contract_invalid", str(error), path=error.path) from error
    try:
        projection.check_shape(container)
    except projection.ProjectionError as error:
        raise ProjectError(
            "contract_invalid",
            str(error),
            path=error.path,
            remediation="Remove the key or the override; this project accepts no new configuration key.",
        ) from error
    execution = container["hypotrail"]["execution"]
    if execution.get("purpose") != projection.REPLAY_PURPOSE or execution.get("allow_scientific_override") is not False:
        raise ProjectError(
            "capability_not_supported",
            "This project replays the selected recipe only; a new experiment is a new activity of the study.",
            path="hypotrail.execution",
            remediation="Keep purpose replay_selected_recipe and allow_scientific_override false.",
        )
    try:
        actual = projection.from_config(container)
    except (KeyError, TypeError) as error:
        raise ProjectError(
            "contract_invalid",
            f"A scientific setting is missing from the configuration: {error}",
            path="components",
            remediation="Restore the exported configuration files.",
        ) from error
    sha = canonical.canonical_sha256(actual)
    expected = container["hypotrail"]["expected_scientific_sha256"]
    if sha != expected:
        reference_path = Path(container["contracts"]["path"]) / "scientific-projection.json"
        differences = ["(the exported projection could not be read)"]
        if reference_path.is_file():
            reference = canonical.loads_strict(reference_path.read_text(encoding="utf-8"))
            differences = projection.differences(reference, actual)
        raise ProjectError(
            "scientific_config_changed",
            "A scientific setting differs from the study's selected recipe; a faithful replay refuses it.",
            path="components",
            remediation="Remove the scientific override. To try another model, run a new activity in the study.",
            details={"differences": differences[:MAX_DIFFERENCES], "overrides": overrides or []},
        )
    return {
        "schema_version": "hypotrail.frozen_run_config/1",
        "config": container,
        "scientific_sha256": sha,
        "overrides": list(overrides or []),
    }


def freeze(cfg: object) -> dict:
    """Resolve, check and freeze a Hydra ``DictConfig`` (see the module docstring)."""
    from omegaconf import OmegaConf
    from omegaconf.errors import InterpolationResolutionError, MissingMandatoryValue

    try:
        container = OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)
    except MissingMandatoryValue as error:
        raise ProjectError(
            "contract_invalid",
            "A configuration value is missing (???).",
            path=str(getattr(error, "full_key", "")),
            remediation="Give the value with an operational override or in the profile.",
        ) from error
    except InterpolationResolutionError as error:
        raise ProjectError(
            "contract_invalid", f"An interpolation cannot be resolved: {error}", path="config",
        ) from error
    return freeze_container(container, _overrides())


def write_frozen(frozen: dict, folder: Path, name: str = "hypotrail-run-config.json") -> Path:
    """Write the frozen configuration and the overrides next to a step's outputs."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(json.dumps(frozen, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
