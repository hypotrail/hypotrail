"""The four steps of the exported project (export spec §11).

1. :func:`prepare`: reads the development rows (materialised from the original file by
   ``project.py materialize``), checks their identity (source hash, row keys) and types them
   with the data contract's declared conversions. It learns no statistic and drops no row.
2. :func:`split`: writes each recorded partition of the development plan; it never draws a
   split and checks each partition's key hash against the plan.
3. :func:`train`: fits a **new candidate** (``rebuilt_candidate``) with the selected recipe
   on every authorised development row, through ``hypotrail_runtime``, and captures it with
   its MLflow package (the packager hook) before any check. Nothing is registered.
4. :func:`evaluate`: technical checks of that candidate (bundle verification, reload,
   native/MLflow parity, and for a binary score that every score is a probability) and its
   observed deviation from the evaluated model on the parity rows. It reads no final-test row
   and computes no metric (the parity rows carry no label; ROC AUC, Brier score or log loss on
   the training rows would not be generalisation): the candidate does not inherit the
   study's verdict. A binary study's decision rule is reported as metadata, never applied.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from . import canonical, contracts, runtime_bridge
from .config import write_frozen
from .errors import ProjectError

if TYPE_CHECKING:
    from types import ModuleType

    import pandas as pd

CANDIDATE_ROLE = "rebuilt_candidate"
REPORT_SCHEMA = "hypotrail.technical_report/1"
RUN_SCHEMA = "hypotrail.candidate_run/1"
PARTITIONS_FILE = "partitions.json"
PARITY_FALLBACK_ROWS = 20
BUNDLE_FOLDER = "bundle"
LOCK_PATH = "aml/pipelines/training/requirements.lock"


def _write_json(path: Path, document: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical.pretty_bytes(document))
    return path


_key_order = contracts.key_order
development_keys = contracts.development_keys


# --- 1. data preparation ---------------------------------------------------------------


def prepare(frozen: dict) -> dict:
    """Read, identify and type the development rows; write them and a validation report."""
    config = frozen["config"]
    found = contracts.load(frozen)
    raw_dir = Path(config["raw_data"]["path"])
    manifest_path = raw_dir / contracts.DEVELOPMENT_MANIFEST
    data_path = raw_dir / config["raw_data"]["file"]
    if not data_path.is_file() or not manifest_path.is_file():
        raise ProjectError(
            "data_identity_mismatch",
            "The development rows are not materialised.",
            path=str(data_path),
            remediation="python -m src.pipeline.utils.project materialize --source <original dataset file>",
        )
    manifest = contracts.load_json(manifest_path)
    if manifest.get("schema_version") != contracts.MATERIALIZATION_SCHEMA:
        raise ProjectError("schema_version_unsupported", "Unknown materialisation manifest.", path=str(manifest_path))
    if manifest.get("source_sha256") != found.data_contract["source_sha256"]:
        raise ProjectError(
            "data_identity_mismatch",
            "The development rows were extracted from another source file.",
            path="source_sha256",
            remediation="Materialise again from the study's original dataset file.",
        )
    if contracts.sha256_file(data_path) != manifest.get("materialization_sha256"):
        raise ProjectError(
            "data_identity_mismatch",
            "The development rows changed after their materialisation.",
            path=str(data_path),
            remediation="Materialise again; never edit the development rows.",
        )
    typed = contracts.read_rows(data_path, found.data_contract)
    keys = typed[contracts.KEY_COLUMN].tolist()
    expected = development_keys(found.plan)
    if len(set(keys)) != len(keys) or sorted(keys, key=_key_order) != expected:
        raise ProjectError(
            "data_identity_mismatch",
            "The development rows are not exactly the plan's development rows.",
            path="row keys",
            details={"expected_rows": len(expected), "found_rows": len(keys)},
        )
    out_dir = Path(config["preprocessed_data"]["path"])
    contracts.write_rows(typed, out_dir / config["preprocessed_data"]["file"])
    report = {
        "schema_version": "hypotrail.preparation_report/1",
        "status": "passed",
        "n_rows": len(keys),
        "source_sha256": manifest["source_sha256"],
        "materialization_sha256": manifest["materialization_sha256"],
        "development_keys_sha256": canonical.canonical_sha256(expected),
        "learnt_statistics": [],
        "dropped_rows": 0,
    }
    encoding = target_encoding(found.recipe, typed)
    if encoding is not None:
        report["target_encoding"] = encoding
    _write_json(out_dir / "validation-report.json", report)
    write_frozen(frozen, out_dir)
    logging.info("Prepared %d development rows", len(keys))
    return report


def target_encoding(recipe: dict, rows: pd.DataFrame) -> dict | None:
    """Return how a binary study's target is encoded, or None for a regression.

    The positive label is the one the study recorded (``target.positive_label``); a row is 1
    when its target is that label and 0 otherwise, by the runtime's own encoding. Rows of a
    single class are refused here, before any fit.
    """
    if recipe["task"] != "binary":
        return None
    target = recipe["target"]
    encode = runtime_bridge.positive_indicator()
    positives = int(encode(rows[target["name"]], target["positive_label"]).sum())
    negatives = len(rows) - positives
    if positives == 0 or negatives == 0:
        raise ProjectError(
            "data_identity_mismatch",
            "The development rows hold one class of the target only.",
            path=target["name"],
            remediation="Materialise the study's development rows from its original dataset file.",
            details={"positive_label": target["positive_label"], "n_positive": positives, "n_negative": negatives},
        )
    return {
        "target": target["name"],
        "positive_label": target["positive_label"],
        "rule": "1 when the target is the positive label the study recorded, else 0 (hypotrail_runtime)",
        "n_positive": positives,
        "n_negative": negatives,
    }


# --- 2. data splitting -----------------------------------------------------------------


def split(frozen: dict) -> dict:
    """Write each recorded partition; refuse a partition whose keys do not match."""
    config = frozen["config"]
    found = contracts.load(frozen)
    prepared = contracts.read_rows(
        Path(config["preprocessed_data"]["path"]) / config["preprocessed_data"]["file"],
        found.data_contract,
    )
    by_key = prepared.set_index(contracts.KEY_COLUMN, drop=False)
    out_dir = Path(config["train_data"]["path"])
    listed = []
    for part in found.plan["partitions"]:
        keys = list(part["row_keys"])
        if canonical.canonical_sha256(keys) != part["keys_sha256"]:
            raise ProjectError("data_identity_mismatch", "A partition does not match its key hash.", path=part["id"])
        missing = [k for k in keys if k not in by_key.index]
        if missing:
            raise ProjectError(
                "data_identity_mismatch",
                "A partition names rows that are not in the development rows.",
                path=part["id"],
                details={"examples": missing[:10]},
            )
        rows = by_key.loc[keys].reset_index(drop=True)
        contracts.write_rows(rows, out_dir / f"{part['id']}.csv")
        listed.append({"id": part["id"], "role": part["role"], "n_rows": len(keys), "keys_sha256": part["keys_sha256"]})
    manifest = {
        "schema_version": "hypotrail.partitions/1",
        "protocol_id": found.plan["protocol_id"],
        "keys_sha256": found.plan["keys_sha256"],
        "partitions": listed,
        "new_split_drawn": False,
    }
    _write_json(out_dir / PARTITIONS_FILE, manifest)
    write_frozen(frozen, out_dir)
    return manifest


# --- 3. training -----------------------------------------------------------------------


def _code_fingerprint() -> str:
    root = contracts.ROOT / "src"
    files = sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    return canonical.canonical_sha256([[p.relative_to(root).as_posix(), contracts.sha256_file(p)] for p in files])


def _training_rows(frozen: dict, found: contracts.Contracts) -> pd.DataFrame:
    import pandas as pd

    folder = Path(frozen["config"]["train_data"]["path"])
    manifest = contracts.load_json(folder / PARTITIONS_FILE)
    if manifest.get("keys_sha256") != found.plan["keys_sha256"]:
        raise ProjectError("data_identity_mismatch", "The partitions are not this plan's.", path=PARTITIONS_FILE)
    frames = [contracts.read_rows(folder / f"{p['id']}.csv", found.data_contract) for p in manifest["partitions"]]
    rows = pd.concat(frames, ignore_index=True).drop_duplicates(subset=[contracts.KEY_COLUMN])
    order = development_keys(found.plan)
    if sorted(rows[contracts.KEY_COLUMN], key=_key_order) != order:
        raise ProjectError(
            "data_identity_mismatch", "The partitions do not cover the development rows.", path=PARTITIONS_FILE,
        )
    rows = rows.set_index(contracts.KEY_COLUMN).loc[order]
    rows.index.name = None
    return rows


def evaluated_bundle(found: contracts.Contracts) -> Path | None:
    """Return the evaluated model's native bundle folder, when the export carries one."""
    folder = found.data_dir / "models" / "evaluated"
    return folder if (folder / "predictor_bundle.json").is_file() else None


def verified_evaluated(found: contracts.Contracts, rt: ModuleType) -> Path | None:
    """Return the evaluated bundle folder once verified as the snapshot's predictor, or None.

    ``hypotrail_runtime.verify_bundle`` recomputes the predictor id from the bundle's content
    (its parity rows included), which must be the id the snapshot names (review round 9,
    R9AB-1): a folder copied from another bundle, with its checksums rewritten, is refused.
    """
    folder = evaluated_bundle(found)
    if folder is not None:
        contracts.check_evaluated(found.data_dir, found.snapshot, rt.verify_bundle(folder).predictor_id)
    return folder


def parity_features(found: contracts.Contracts, rows: pd.DataFrame, rt: ModuleType) -> tuple[pd.DataFrame, str]:
    """Return the parity rows (features only, no target) and their origin.

    They are the evaluated bundle's (authorised development rows or synthetic cases), else
    the first development rows in key order.
    """
    from . import mlflow_packaging as mp

    bundle_dir = verified_evaluated(found, rt)
    if bundle_dir is not None:
        bundle = contracts.load_json(bundle_dir / "predictor_bundle.json")
        spec = mp.ParitySpec.from_bundle(bundle)
        return mp.read_table(mp.inside(bundle_dir, spec.features_path, "parity.features_path")), "evaluated_bundle"
    features = list(found.recipe["features"])
    return rows[features].head(PARITY_FALLBACK_ROWS).reset_index(drop=True), "development_rows"


def _output_fields(found: contracts.Contracts) -> dict:
    """Return the output kind and, for a binary study, its decision rule (never applied)."""
    out = {"output_kind": found.recipe["output_contract"]["kind"]}
    rule = contracts.decision_rule(found.snapshot)
    if rule is not None:
        out["decision_rule"] = rule
    return out


def train(frozen: dict) -> dict:
    """Fit and capture a rebuilt candidate; write ``hypotrail-run.json`` next to it."""
    config = frozen["config"]
    training = config["components"]["training"]
    if training["mode"] != "rebuild_final_candidate":
        raise ProjectError(
            "capability_not_supported",
            f"Training mode {training['mode']!r} is not available in this template version.",
            path="components.training.mode",
            remediation="Use rebuild_final_candidate; development_evaluation is a later version.",
        )
    packaging = config["packaging"]
    rt = runtime_bridge.runtime()
    packager = None
    if packaging["format"] == "mlflow_pyfunc" and (packaging["required"] or runtime_bridge.available("mlflow")):
        runtime_bridge.mlflow()
        from . import mlflow_packaging

        packager = mlflow_packaging.ArtifactPackager(rt)
    found = contracts.load(frozen)
    rows = _training_rows(frozen, found)
    recipe = rt.validate_recipe(found.recipe)
    data_contract = rt.validate_data_contract(found.data_contract)
    scope = {
        "role": CANDIDATE_ROLE,
        "dataset_id": found.data_contract["dataset_id"],
        "membership_sha256": found.plan["development_keys_sha256"],
        "protocol_id": found.plan["protocol_id"],
    }
    fitted = rt.fit_predictor(recipe, data_contract, rows, scope)
    snapshot = found.snapshot
    # The code upload excludes aml/: the lock's identity comes from the export manifest.
    lock_sha = next((f["sha256"] for f in found.manifest["files"] if f["path"] == LOCK_PATH), None)
    context = {
        "schema_version": "hypotrail.computation_context/1",
        "activity_id": f"azureml-rebuild-{frozen['scientific_sha256'][:16]}",
        "study_id": snapshot["study_id"],
        "expected_revision": snapshot["study_revision"],
        "protocol_id": found.plan["protocol_id"],
        "decision_refs": [snapshot["selected"]["decision_id"]],
        "input_refs": [
            {"id": "development_rows", "sha256": found.plan["development_keys_sha256"], "role": "development"},
        ],
        "partition_refs": [
            {
                "id": p["id"],
                "membership_sha256": p["keys_sha256"],
                # Contract v1 roles: a cross-validation fold is a fold's validation rows.
                "role": p["role"] if p["role"] in ("train", "validation", "development") else "fold_validation",
                "exposure_status": "exposed",
            }
            for p in found.plan["partitions"]
        ],
        "code_fingerprint": _code_fingerprint(),
        "runtime_version": rt.RUNTIME_API_VERSION,
        "backend": {"distribution": rt.DISTRIBUTION, "version": rt.__version__},
        "method_contract_version": found.recipe["method_contract_version"],
        "semantic_dependencies": [],
        "environment_lock_sha256": lock_sha,
    }
    features, parity_origin = parity_features(found, rows, rt)
    models = Path(config["models"]["path"])
    destination = models / BUNDLE_FOLDER
    rt.capture_predictor(fitted, context, features, destination, packager=packager)
    rt.verify_bundle(destination)
    manifest_doc = contracts.load_json(destination / "predictor_bundle.json")
    predictor = contracts.load_json(destination / manifest_doc["predictor_manifest_path"])
    evaluated = (found.snapshot.get("predictor") or {}).get("predictor_id")
    if predictor.get("predictor_id") == evaluated:
        raise ProjectError(
            "artifact_integrity_failed",
            "A rebuilt candidate must have a new identity.",
            path="predictor_id",
        )
    record = {
        "schema_version": RUN_SCHEMA,
        "role": CANDIDATE_ROLE,
        "predictor_id": predictor.get("predictor_id"),
        "evaluated_predictor_id": evaluated,
        "verdict": "not_inherited",
        "scientific_sha256": frozen["scientific_sha256"],
        "n_training_rows": len(rows),
        "parity_origin": parity_origin,
        "mlflow_package": bool(manifest_doc.get("optional_packages")),
        "registered": False,
        **_output_fields(found),
    }
    _write_json(models / "hypotrail-run.json", record)
    write_frozen(frozen, models)
    return record


# --- 4. evaluation ---------------------------------------------------------------------


def _load_bundle(rt: ModuleType, bundle_dir: Path) -> object:
    """Load the predictor of a bundle, trusted by its absolute folder (a relative root is refused)."""
    return rt.load_predictor(bundle_dir, trusted_roots=[bundle_dir.resolve()])


def output_checks(recipe: dict, outputs: pd.DataFrame) -> list[dict]:
    """Return the checks of the model output: for a binary score, every score is a probability.

    A score is a probability when it is finite and between 0 and 1; a regression prediction
    has no such check.
    """
    if recipe["output_contract"]["kind"] != "binary_score":
        return []
    values = outputs.to_numpy(dtype=float).ravel()
    outside = int(sum(1 for v in values if not 0.0 <= v <= 1.0))
    return [
        {
            "id": "candidate_scores_are_probabilities",
            "status": "passed" if outside == 0 else "failed",
            "rows": len(values),
            "outside_unit_interval": outside,
        },
    ]


def evaluate(frozen: dict) -> dict:
    """Technical checks of the run's candidate; never a generalisation claim."""
    from . import mlflow_packaging as mp

    config = frozen["config"]
    found = contracts.load(frozen)
    rt = runtime_bridge.runtime()
    models = Path(config["models"]["path"])
    bundle_dir = models / BUNDLE_FOLDER
    run = contracts.load_json(models / "hypotrail-run.json")
    checks = []
    rt.verify_bundle(bundle_dir)
    checks.append({"id": "candidate_bundle_verified", "status": "passed"})
    bundle = contracts.load_json(bundle_dir / "predictor_bundle.json")
    manifest = contracts.load_json(bundle_dir / bundle["predictor_manifest_path"])
    role = (manifest.get("training_scope") or {}).get("role")
    checks.append({"id": "candidate_role", "status": "passed" if role == CANDIDATE_ROLE else "failed", "detail": role})
    checks.append(
        {
            "id": "no_inherited_evidence",
            "status": "passed" if not bundle.get("evidence_binding_path") else "failed",
        },
    )
    spec = mp.ParitySpec.from_bundle(bundle)
    features = mp.read_table(mp.inside(bundle_dir, spec.features_path, "parity.features_path"))
    native = mp.batch_frame(_load_bundle(rt, bundle_dir).predict(features.copy()))
    expected = mp.read_table(mp.inside(bundle_dir, spec.expected_outputs_path, "parity.expected_outputs_path"))
    reload = mp.compare(native, expected, spec.rtol, spec.atol)
    checks += [
        {"id": "candidate_reload_parity", "status": "passed" if reload["equal"] else "failed", **reload},
        *output_checks(found.recipe, native),
    ]
    packages = [p for p in bundle.get("optional_packages") or [] if p.get("format") == mp.FORMAT]
    if packages:
        result = mp.ArtifactPackager(rt).verify(bundle_dir, bundle_dir / packages[0]["relative_path"])
        checks.append({"id": "mlflow_package_parity", "status": result.status, "reason": result.reason})
    else:
        status = "failed" if config["packaging"]["required"] else "not_run"
        checks.append({"id": "mlflow_package_parity", "status": status, "reason": "no_package"})
    deviation = None
    evaluated_dir = verified_evaluated(found, rt)
    if evaluated_dir is not None:
        evaluated = contracts.load_json(evaluated_dir / "predictor_bundle.json")
        espec = mp.ParitySpec.from_bundle(evaluated)
        efeatures = mp.read_table(mp.inside(evaluated_dir, espec.features_path, "parity.features_path"))
        eexpected = mp.read_table(mp.inside(evaluated_dir, espec.expected_outputs_path, "parity.expected_outputs_path"))
        candidate = mp.batch_frame(_load_bundle(rt, bundle_dir).predict(efeatures.copy()))
        observed = mp.compare(candidate, eexpected, espec.rtol, espec.atol)
        deviation = {
            "rows": len(efeatures),
            "max_abs_diff": observed["max_abs_diff"],
            "within_evaluated_tolerance": observed["equal"],
            "meaning": "Observed difference on a few parity rows; it does not transfer the evaluated model's verdict.",
        }
        # The same recipe fitted on the same rows reproduces the evaluated model within its
        # declared tolerance; a rebuild outside it is not a faithful replay and never passes.
        checks.append(
            {
                "id": "candidate_within_evaluated_tolerance",
                "status": "passed" if observed["equal"] else "failed",
                "max_abs_diff": observed["max_abs_diff"],
            },
        )
    else:
        checks.append(
            {"id": "candidate_within_evaluated_tolerance", "status": "not_run", "reason": "no_evaluated_model"},
        )
    status = "passed" if all(c["status"] in ("passed", "not_run") for c in checks) else "failed"
    report = {
        "schema_version": REPORT_SCHEMA,
        "status": status,
        "candidate_predictor_id": run["predictor_id"],
        "evaluated_predictor_id": run["evaluated_predictor_id"],
        "role": CANDIDATE_ROLE,
        "scientific_verdict": "not_inherited",
        "generalisation_metrics": None,
        "generalisation_metrics_reason": "No final-test row is read here; training-row metrics are not generalisation.",
        **_output_fields(found),
        "checks": checks,
        "deviation_from_evaluated_model": deviation,
        "registered": False,
    }
    reports = Path(config["reports"]["path"])
    _write_json(reports / "technical-report.json", report)
    write_frozen(frozen, reports)
    if status != "passed":
        raise ProjectError(
            "artifact_integrity_failed",
            "A technical check of the candidate failed; see technical-report.json.",
            path=str(reports / "technical-report.json"),
            details={"failed": [c["id"] for c in checks if c["status"] == "failed"]},
        )
    return report


def log_json(document: dict) -> None:
    """Log a step's result as one JSON line."""
    logging.info("%s", json.dumps(document, sort_keys=True, ensure_ascii=False))
