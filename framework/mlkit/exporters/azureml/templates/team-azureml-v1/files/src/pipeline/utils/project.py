"""Local commands of this exported project (Hypotrail export, team-azureml-v1).

Run from the project folder::

    python -m src.pipeline.utils.project validate [--offline]
    python -m src.pipeline.utils.project predict (--input FILE | --parity) [--model DIR] --output FILE
    python -m src.pipeline.utils.project materialize --source FILE
    python -m src.pipeline.utils.project run-local --mode rebuild_final_candidate [--run-dir DIR]
    python -m src.pipeline.utils.project preflight [--execute]
    python -m src.pipeline.utils.project submit [--execute] [--wait] [--new-submission]

``validate`` never uses the network (``--offline`` is accepted for clarity); a check whose
dependency is absent is ``not_run``, never ``passed``. ``predict`` loads a model and never
fits. ``run-local`` fits a new candidate and is never called by ``validate``. ``preflight``
and ``submit`` print the Azure CLI commands; they run them only with ``--execute``:
``preflight`` reads Azure, ``submit`` writes to it (assets, then one pipeline job). Nothing
here deploys an endpoint or registers a model. Each command prints one JSON document; a
refusal exits with code 2 (including a refusal of ``hypotrail_runtime``, an unreadable or
malformed input file and a configuration Hydra cannot compose), a failed check with code 1,
and an unexpected exception is reported as ``internal_error`` with code 1. ``validate``
writes ``outputs/validation.json`` whatever its checks found.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .hypotrail import azure_yaml, canonical, contracts, runtime_bridge, transfer
from .hypotrail.errors import ProjectError, from_exception, internal_error

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = contracts.ROOT
DATA_DIR = ROOT / "data" / "hypotrail"
CONF_DIR = ROOT / "src" / "conf"
OUTPUTS = ROOT / "outputs"
TARGET = CONF_DIR / "azure" / "target.yaml"
MISSING = "MISSING-"
STEPS = ("data_preparation", "data_splitting", "training", "evaluation")
UPLOAD_ALLOWED = re.compile(
    r"(src/.+|\.amlignore|\.gitignore|\.pre-commit-config\.yaml|README\.md|environment\.yml|pyproject\.toml)",
)
# Credential shapes, written in pieces so that this file does not match itself.
SECRET = re.compile(
    "("
    + "|".join(
        [
            "Account" + "Key=",
            "SharedAccess" + "Signature=",
            "-----BEGIN [A-Z ]*PRIVATE" + " KEY",
            r"client_" + r"secret\s*[:=]\s*\S",
        ],
    )
    + ")",
)
TEXT_SUFFIXES = {".py", ".yml", ".yaml", ".json", ".md", ".txt", ".toml", ".sh", ".lock", ".csv", ""}


def _emit(document: dict, code: int = 0) -> int:
    sys.stdout.write(json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return code


def _readiness() -> dict:
    return contracts.load_json(DATA_DIR / "contracts" / "readiness.json")


def _target() -> dict:
    import yaml

    return yaml.safe_load(TARGET.read_text(encoding="utf-8"))


def _check(checks: list, check_id: str, function: Callable[[], object]) -> None:
    try:
        result = function()
    except Exception as error:  # noqa: BLE001 - every failure of a check is reported, never raised
        refusal = from_exception(error)
        found = refusal.to_dict() if refusal is not None else internal_error(error)["error"]
        checks.append({"id": check_id, "status": "failed", "error": found})
        return
    status, detail = result if isinstance(result, tuple) else (result, None)
    item = {"id": check_id, "status": status}
    if detail is not None:
        item["detail"] = detail
    checks.append(item)


# --- validate --------------------------------------------------------------------------


def _hydra_config() -> tuple[str, str | None]:
    if not (runtime_bridge.available("hydra") and runtime_bridge.available("omegaconf")):
        return "not_run", "Hydra is not installed."
    from hydra import compose, initialize_config_dir

    from .hypotrail.config import freeze

    with initialize_config_dir(config_dir=str(CONF_DIR), version_base=None):
        cfg = compose(config_name="config")
    frozen = freeze(cfg)
    # The configuration's own expected identity can be edited with it: the authority is the
    # checksummed projection of the data folder, which every step also verifies.
    reference = contracts.load_json(DATA_DIR / contracts.FILES["projection"])
    if canonical.canonical_sha256(reference) != frozen["scientific_sha256"]:
        from .hypotrail import projection

        actual = projection.from_config(frozen["config"])
        raise ProjectError(
            "scientific_config_changed",
            "The scientific configuration differs from the study's exported projection.",
            path="src/conf",
            remediation="Restore the exported configuration files; a new experiment is a new activity of the study.",
            details={"differences": projection.differences(reference, actual)[:20]},
        )
    return "passed", frozen["scientific_sha256"]


def _azure_yaml() -> tuple[str, object]:
    if not runtime_bridge.available("yaml"):
        return "not_run", "PyYAML is not installed."
    problems, graph = azure_yaml.check(ROOT)
    if problems:
        raise ProjectError(
            "contract_invalid", "The Azure ML YAML has problems.", path="aml", details={"problems": problems[:20]},
        )
    return "passed", graph


def _markers() -> tuple[str, object]:
    readiness = _readiness()
    paths = [*sorted((ROOT / "aml").rglob("*.yml")), TARGET, ROOT / ".ci" / "deploy-pipeline.yml"]
    found = [p.relative_to(ROOT).as_posix() for p in paths if MISSING in p.read_text(encoding="utf-8")]
    if readiness["configuration"] == "configured" and found:
        raise ProjectError(
            "contract_invalid", "A configured export still holds a missing-value marker.", details={"files": found},
        )
    if readiness["configuration"] == "draft":
        return "draft", {"missing_fields": readiness.get("missing_fields", []), "files": found}
    return "passed", None


def _upload() -> tuple[str, object]:
    files = transfer.transferable(ROOT)
    outside = [f for f in files if not UPLOAD_ALLOWED.fullmatch(f)]
    if outside:
        raise ProjectError(
            "contract_invalid",
            "The code upload would include files outside src/ and the project metadata.",
            path=".amlignore",
            details={"files": outside[:20]},
        )
    return "passed", {"files": len(files)}


def _secrets() -> tuple[str, None]:
    hits = []
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT).as_posix()
        if not path.is_file() or rel.startswith(("outputs/", ".git/", ".venv/")) or path.suffix not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if SECRET.search(text):
            hits.append(rel)
    if hits:
        raise ProjectError("contract_invalid", "A file looks like it holds a credential.", details={"files": hits[:20]})
    return "passed", None


def _evaluated() -> tuple[str, object]:
    from .hypotrail import mlflow_packaging as mp

    folder = DATA_DIR / "models" / "evaluated"
    if not (folder / "predictor_bundle.json").is_file():
        return "missing", "No captured model: this export carries the recipe only."
    if not runtime_bridge.available("hypotrail_runtime"):
        return "not_run", "hypotrail_runtime is not installed."
    rt = runtime_bridge.runtime()
    rt.verify_bundle(folder)
    bundle = contracts.load_json(folder / "predictor_bundle.json")
    spec = mp.ParitySpec.from_bundle(bundle)
    features = mp.read_table(mp.inside(folder, spec.features_path, "parity.features_path"))
    expected = mp.read_table(mp.inside(folder, spec.expected_outputs_path, "parity.expected_outputs_path"))
    result = mp.compare(
        mp.batch_frame(rt.load_predictor(folder, trusted_roots=[folder]).predict(features.copy())),
        expected,
        spec.rtol,
        spec.atol,
    )
    if not result["equal"]:
        raise ProjectError(
            "artifact_integrity_failed", "The evaluated model does not reproduce its parity outputs.", details=result,
        )
    return "passed", {
        "rows": len(features),
        "max_abs_diff": result["max_abs_diff"],
        "rtol": spec.rtol,
        "atol": spec.atol,
    }


def _mlflow_package() -> tuple[str, object]:
    from .hypotrail import mlflow_packaging as mp

    folder = DATA_DIR / "models" / "evaluated"
    if not (folder / "predictor_bundle.json").is_file():
        return "missing", None
    bundle = contracts.load_json(folder / "predictor_bundle.json")
    packages = [p for p in bundle.get("optional_packages") or [] if p.get("format") == mp.FORMAT]
    if not packages:
        return "missing", "The evaluated model has no MLflow package."
    if not (runtime_bridge.available("hypotrail_runtime") and runtime_bridge.available("mlflow")):
        return "not_run", "hypotrail_runtime or MLflow is not installed."
    result = mp.ArtifactPackager(runtime_bridge.runtime()).verify(folder, folder / packages[0]["relative_path"])
    if result.status != "passed":
        raise ProjectError(
            "artifact_integrity_failed",
            "The MLflow package does not match the native model.",
            details=result.to_dict(),
        )
    return "passed", {"rows": result.n_rows}


def _development_rows() -> tuple[str, object]:
    manifest = DATA_DIR / "development" / contracts.DEVELOPMENT_MANIFEST
    if not manifest.is_file():
        return "missing", "Run materialize before run-local or submit."
    return "passed", contracts.load_json(manifest).get("materialization_sha256")


def validate(_args: argparse.Namespace) -> int:
    """Offline checks of the export; write outputs/validation.json."""
    checks: list = []
    _check(checks, "data_checksums", lambda: ("passed", len(contracts.verify_data_dir(DATA_DIR))))
    _check(checks, "code_contract_copies", _code_copies)
    _check(checks, "hydra_config_frozen", _hydra_config)
    _check(checks, "azure_yaml_graph", _azure_yaml)
    _check(checks, "configuration_markers", _markers)
    _check(checks, "code_upload_content", _upload)
    _check(checks, "no_credentials", _secrets)
    _check(checks, "evaluated_model_parity", _evaluated)
    _check(checks, "evaluated_model_mlflow_package", _mlflow_package)
    _check(checks, "development_rows", _development_rows)
    failed = [c["id"] for c in checks if c["status"] == "failed"]
    try:
        manifest_sha = contracts.sha256_file(DATA_DIR / contracts.FILES["manifest"])
    except OSError:
        manifest_sha = None
    document = {
        "schema_version": "hypotrail.local_validation/1",
        "status": "failed" if failed else "passed",
        "export_manifest_sha256": manifest_sha,
        "checks": checks,
        "network_used": False,
        "meaning": "Local checks of this folder; not an Azure run and not a deployment.",
    }
    OUTPUTS.mkdir(exist_ok=True)
    (OUTPUTS / "validation.json").write_bytes(canonical.pretty_bytes(document))
    return _emit(document, 1 if failed else 0)


def _code_copies() -> str:
    sums = contracts.read_sums(DATA_DIR)
    for key, name in contracts.CODE_COPIES.items():
        if contracts.sha256_file(contracts.CODE_CONTRACTS / name) != sums.get(contracts.FILES[key]):
            raise ProjectError("artifact_integrity_failed", "A contract copy differs.", path=name)
    return "passed"


# --- predict ---------------------------------------------------------------------------


def bundle_contract(folder: Path) -> dict:
    """Return the data contract the captured model was fitted with."""
    bundle = contracts.load_json(folder / "predictor_bundle.json")
    return contracts.load_json(folder / bundle["data_contract_path"])


def predict(args: argparse.Namespace) -> int:
    """Predict with a captured model (default: the evaluated one); never fits."""
    from .hypotrail import mlflow_packaging as mp

    folder = Path(args.model) if args.model else DATA_DIR / "models" / "evaluated"
    if not (folder / "predictor_bundle.json").is_file():
        raise ProjectError(
            "model_not_captured",
            "No captured model in this folder.",
            path=str(folder),
            remediation="The study exported its recipe only; run-local builds a new candidate.",
        )
    rt = runtime_bridge.runtime()
    rt.verify_bundle(folder)
    bundle = contracts.load_json(folder / "predictor_bundle.json")
    manifest = contracts.load_json(folder / bundle["predictor_manifest_path"])
    if args.parity:
        spec = mp.ParitySpec.from_bundle(bundle)
        source = mp.inside(folder, spec.features_path, "parity.features_path")
    elif args.input:
        source = Path(args.input)
    else:
        raise ProjectError("contract_invalid", "Give --input FILE or --parity.", path="input")
    # Rows given by a user are typed as the data contract declares (never by inference); a
    # runtime parity frame (hypotrail.parity_frame/1, such as the model's own parity features)
    # carries its declared types and is read by the runtime.
    if args.parity:
        features = mp.read_table(source)
    elif _is_parity_frame(source):
        features = _parity_frame(source)
    else:
        features = contracts.typed_features(source, bundle_contract(folder))
    contracts.refuse_non_finite(features, bundle_contract(folder))
    predictor = rt.load_predictor(folder, trusted_roots=[folder])
    frame = mp.batch_frame(predictor.predict(features))
    document = {
        "schema_version": "hypotrail.predictions/1",
        "predictor_id": manifest.get("predictor_id"),
        "role": (manifest.get("training_scope") or {}).get("role"),
        "output_contract": manifest.get("output_contract"),
        "columns": list(frame.columns),
        "rows": json.loads(frame.to_json(orient="records")),
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(canonical.pretty_bytes(document))
    return _emit({"ok": True, "output": str(out), "rows": len(frame), "predictor_id": document["predictor_id"]})


def _is_parity_frame(path: Path) -> bool:
    """Return whether ``path`` is a JSON parity frame of the runtime (not a CSV of rows)."""
    if path.suffix.lower() != ".json" or not path.is_file():
        return False
    try:
        document = canonical.loads_strict(path.read_text(encoding="utf-8"))
    except ValueError:
        return False
    return isinstance(document, dict) and document.get("schema_version") == "hypotrail.parity_frame/1"


def _parity_frame(path: Path) -> object:
    """Read a runtime parity frame given as input; a malformed one is a refusal."""
    from .hypotrail import mlflow_packaging as mp

    try:
        return mp.read_table(path)
    except Exception as error:  # a structured refusal is kept; any other failure is the input's
        if from_exception(error) is not None:
            raise
        raise ProjectError(
            "contract_invalid",
            "The input is not a valid hypotrail.parity_frame/1 document.",
            path=str(path),
            remediation="Give a parity frame written by the runtime, or a CSV of feature values with a header.",
            details={"error": f"{type(error).__name__}: {error}"[:300]},
        ) from error


# --- materialize -----------------------------------------------------------------------


# The engine's record reader (``mlkit.study.data.row_index`` and ``_field_splitter``), copied
# here because this project never imports the engine; it gives the row keys (the values are
# read by the engine's pandas call, ``contracts.read_source``): records are split on "\n" only (never
# on U+2028, form feed, NEL or a lone "\r", which ``str.splitlines`` would split on), a final
# empty line is dropped, a trailing "\r" is removed, and fields are split by ``csv.reader``
# on one line, or, for ``whitespace``, by the engine's tokenizer (a quoted field with doubled
# quotes, or a run of non-space characters; no shell rules for backslashes or apostrophes).
# The keys are physical line numbers: ``L2`` is the first data line of a file with a header.
MAX_LISTED = 20


def _whitespace_tokenizer(quotechar: str) -> Callable[[str], list[str]]:
    """Return the engine's whitespace field splitter for ``quotechar``."""
    q = re.escape(quotechar)
    pattern = re.compile(rf"{q}((?:[^{q}]|{q}{q})*){q}|(\S+)")

    def split(line: str) -> list[str]:
        return [bare or quoted.replace(quotechar * 2, quotechar) for quoted, bare in pattern.findall(line)]

    return split


def _field_splitter(parser: dict) -> Callable[[str], list[str]]:
    """Return the engine's field splitter of the data contract's parser."""
    import csv

    quotechar = parser.get("quotechar", '"')
    delimiter = parser.get("delimiter", ",")
    if delimiter == "whitespace":
        return _whitespace_tokenizer(quotechar)
    return lambda line: next(csv.reader([line], delimiter=delimiter, quotechar=quotechar), [])


def _records(source: Path, contract: dict) -> list[tuple[str, list[str]]]:
    """Return every record of a positional source with its engine row key, in file order.

    A line that does not hold exactly one record of the contract's width is refused, as the
    engine refuses it: such a file cannot be the one the study read.
    """
    parser = contract["parser"]
    identity = contract["row_identity"]
    if identity.get("kind") != "source_position":
        raise ProjectError(
            "capability_not_supported",
            "Only source_position row keys are materialised by this version.",
            path="row_identity.kind",
        )
    encoding = parser.get("encoding", "utf-8")
    try:
        text = source.read_bytes().decode(encoding)
    except UnicodeDecodeError as error:
        raise ProjectError(
            "data_identity_mismatch",
            f"The source file is not {encoding} text.",
            path=str(source),
            remediation="Use the file the study was made on.",
        ) from error
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    first = 2 if parser.get("header") else 1
    body = lines[1:] if parser.get("header") else lines
    prefix = identity.get("prefix", "L")
    split = _field_splitter(parser)
    width = len(contract["columns"])
    records, problems = [], []
    for offset, raw in enumerate(body):
        key = f"{prefix}{first + offset}"
        fields = split(raw.rstrip("\r"))
        if len(fields) != width:
            problems.append({"row_key": key, "expected": width, "found": len(fields)})
            continue
        records.append((key, fields))
    if problems:
        raise ProjectError(
            "data_identity_mismatch",
            "A source line does not hold exactly one record of the contract's columns.",
            path=problems[0]["row_key"],
            remediation="Use the file the study was made on; the engine reads one record per line.",
            details={"problems": problems[:MAX_LISTED], "count": len(problems)},
        )
    return records


def _source_lines(source: Path, contract: dict, wanted: set[str]) -> tuple[list[str], list[list[str]]]:
    """Return the development rows of a positional source (keys and fields), in file order."""
    pairs = [(key, fields) for key, fields in _records(source, contract) if key in wanted]
    return [key for key, _ in pairs], [fields for _, fields in pairs]


def _pandas_version() -> str:
    import pandas as pd

    return pd.__version__


def materialize(args: argparse.Namespace) -> int:
    """Extract the development rows of the original file into data/hypotrail/development.

    The row keys are the engine's (its record splitter); the values are read by the
    engine's own ``pandas.read_csv`` call on the whole file (``contracts.read_source``) and
    converted as the engine converts them (``contracts.engine_values``).
    """
    from .hypotrail.steps import development_keys

    contracts.verify_data_dir(DATA_DIR)
    contract = contracts.load_json(DATA_DIR / "contracts" / "data-contract.json")
    plan = contracts.load_json(DATA_DIR / "contracts" / "development-plan.json")
    source = Path(args.source)
    if contracts.sha256_file(source) != contract["source_sha256"]:
        raise ProjectError(
            "data_identity_mismatch",
            "The source file is not the study's dataset (sha256 differs).",
            path=str(source),
            remediation="Use the file the study was made on; a modified file is a new source.",
        )
    wanted = development_keys(plan)
    records = _records(source, contract)
    # The study recorded how many records the file holds: a reader that split records
    # differently would shift every key after the difference.
    expected = plan.get("n_source_records")
    if isinstance(expected, int) and len(records) != expected:
        raise ProjectError(
            "data_identity_mismatch",
            "The source does not split into the records the study counted.",
            path=str(source),
            remediation="Use the file the study was made on, unmodified.",
            details={"records_found": len(records), "records_expected": expected},
        )
    keys = [key for key, _ in records]
    if not set(wanted) <= set(keys):
        raise ProjectError(
            "data_identity_mismatch", "The source does not hold every development row.", path=str(source),
        )
    # The values are the engine's: the same pandas.read_csv call on the whole file, the rows
    # restricted to the development rows (file order), the engine's numeric conversion.
    frame = contracts.read_source(source, contract, keys)
    wanted_set = set(wanted)
    development = frame.loc[[key for key in keys if key in wanted_set]]
    development = contracts.engine_values(development, contract, str(source)).loc[wanted]
    folder = DATA_DIR / "development"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "development.csv"
    contracts.write_rows(development.reset_index(), target)
    manifest = {
        "schema_version": contracts.MATERIALIZATION_SCHEMA,
        "source_sha256": contract["source_sha256"],
        "materialization_sha256": contracts.sha256_file(target),
        "row_key_column": contracts.KEY_COLUMN,
        "n_rows": len(development),
        "development_keys_sha256": canonical.canonical_sha256(wanted),
        "final_test_rows_included": False,
        "values": "read as the engine read them: pandas.read_csv with the data contract's parser",
        "pandas_version": _pandas_version(),
    }
    (folder / contracts.DEVELOPMENT_MANIFEST).write_bytes(canonical.pretty_bytes(manifest))
    return _emit({"ok": True, **manifest})


# --- run-local -------------------------------------------------------------------------


def run_local(args: argparse.Namespace) -> int:
    """Run the four steps in order as separate processes, as Azure ML would."""
    if args.mode != "rebuild_final_candidate":
        raise ProjectError(
            "capability_not_supported", f"Mode {args.mode!r} is not available in this version.", path="mode",
        )
    base = Path(args.run_dir) if args.run_dir else OUTPUTS / "local-run"
    if base.exists() and any(base.iterdir()):
        raise ProjectError(
            "destination_not_empty",
            "The run folder is not empty.",
            path=str(base),
            remediation="Pass a new --run-dir; runs never overwrite each other.",
        )
    overrides = [
        f"preprocessed_data.path={base / '02_processed'}",
        f"train_data.path={base / '03_partitions'}",
        f"models.path={base / '04_model'}",
        f"reports.path={base / '05_reports'}",
        f"hydra.run.dir={base / 'hydra'}",
    ]
    for step in STEPS:
        # The steps' logs go to stderr, so this command still prints one JSON document.
        # This interpreter and this project's own modules only.
        result = subprocess.run(
            [sys.executable, "-m", f"src.pipeline.{step}.main", *overrides],  # noqa: S603
            cwd=ROOT,
            check=False,
            stdout=sys.stderr,
        )
        if result.returncode != 0:
            return _emit({"ok": False, "failed_step": step, "run_dir": str(base)}, 2)
    report = contracts.load_json(base / "05_reports" / "technical-report.json")
    return _emit(
        {
            "ok": True,
            "run_dir": str(base),
            "role": "rebuilt_candidate",
            "technical_status": report["status"],
            "scientific_verdict": report["scientific_verdict"],
        },
    )


# --- Azure commands --------------------------------------------------------------------


def _scope(target: dict) -> list[str]:
    return [
        "--subscription",
        target["subscription_id"],
        "--resource-group",
        target["resource_group"],
        "--workspace-name",
        target["workspace"],
    ]


def _require_configured() -> dict:
    readiness = _readiness()
    if readiness["configuration"] != "configured":
        raise ProjectError(
            "contract_invalid",
            "This export is a draft: the destination profile is incomplete.",
            path="src/conf/azure/target.yaml",
            remediation="Export again with a complete --profile.",
            details={"missing_fields": readiness.get("missing_fields", [])},
        )
    return _target()


def _commands_preflight(target: dict) -> list[dict]:
    scope = _scope(target)
    return [
        {"argv": ["az", "account", "show", "--subscription", target["subscription_id"]], "scope": "network_read"},
        {
            "argv": [
                "az",
                "ml",
                "workspace",
                "show",
                "--subscription",
                target["subscription_id"],
                "--resource-group",
                target["resource_group"],
                "--name",
                target["workspace"],
            ],
            "scope": "network_read",
        },
        {"argv": ["az", "ml", "compute", "show", "--name", target["compute"], *scope], "scope": "network_read"},
        {
            "argv": [
                "az",
                "ml",
                "data",
                "show",
                "--name",
                target["data_asset"]["name"],
                "--version",
                target["data_asset"]["version"],
                *scope,
            ],
            "scope": "network_read",
            "absent_is_expected": True,
        },
        {
            "argv": [
                "az",
                "ml",
                "environment",
                "show",
                "--name",
                target["environment"]["name"],
                "--version",
                target["environment"]["version"],
                *scope,
            ],
            "scope": "network_read",
            "absent_is_expected": True,
        },
    ]


def _run(argv: list[str]) -> dict:
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=False)  # noqa: S603
    return {
        "argv": argv,
        "exit_code": result.returncode,
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-2000:],
    }


def preflight(args: argparse.Namespace) -> int:
    """Print, or with --execute run, the read-only Azure checks."""
    target = _require_configured()
    commands = _commands_preflight(target)
    if not args.execute:
        return _emit(
            {
                "ok": True,
                "executed": False,
                "commands": commands,
                "meaning": "Read-only checks; a passing preflight does not guarantee a future run.",
            },
        )
    results = [{**_run(c["argv"]), "absent_is_expected": c.get("absent_is_expected", False)} for c in commands]
    failed = [r for r in results if r["exit_code"] != 0 and not r["absent_is_expected"]]
    document = {
        "schema_version": "hypotrail.azure_preflight/1",
        "status": "failed" if failed else "passed",
        "results": results,
    }
    OUTPUTS.mkdir(exist_ok=True)
    (OUTPUTS / "preflight.json").write_bytes(canonical.pretty_bytes(document))
    return _emit(document, 1 if failed else 0)


def submit(args: argparse.Namespace) -> int:
    """Print, or with --execute run, the asset creation and the one pipeline job."""
    target = _require_configured()
    scope = _scope(target)
    training = "aml/pipelines/training"
    commands = [
        {"argv": ["az", "ml", "data", "create", "--file", f"{training}/data.yml", *scope], "scope": "azure_write"},
        {
            "argv": ["az", "ml", "environment", "create", "--file", f"{training}/aml-environment.yml", *scope],
            "scope": "azure_write",
        },
        {
            "argv": [
                "az",
                "ml",
                "job",
                "create",
                "--file",
                f"{training}/pipeline-job.yml",
                "--query",
                "name",
                "-o",
                "tsv",
                *scope,
            ],
            "scope": "azure_write",
        },
    ]
    if not args.execute:
        return _emit(
            {
                "ok": True,
                "executed": False,
                "commands": commands,
                "meaning": "These commands write to Azure. Run again with --execute to submit one pipeline job.",
            },
        )
    submission = OUTPUTS / "submission.json"
    if submission.is_file() and not args.new_submission:
        raise ProjectError(
            "destination_not_empty",
            "A job was already submitted from this folder.",
            path=str(submission),
            remediation="Read its status with az ml job show, or pass --new-submission deliberately.",
        )
    validation = OUTPUTS / "validation.json"
    manifest_sha = contracts.sha256_file(DATA_DIR / "contracts" / "export-manifest.json")
    if not validation.is_file():
        raise ProjectError("contract_invalid", "Run validate before submit.", path=str(validation))
    checked = contracts.load_json(validation)
    if checked.get("status") != "passed" or checked.get("export_manifest_sha256") != manifest_sha:
        raise ProjectError("contract_invalid", "The last validation did not pass on this export.", path=str(validation))
    if _development_rows()[0] != "passed":
        raise ProjectError(
            "data_identity_mismatch",
            "Materialise the development rows before submitting.",
            path="data/hypotrail/development",
        )
    results = []
    for command in commands[:2]:
        result = _run(command["argv"])
        if result["exit_code"] != 0 and "already exists" not in (result["stderr"] + result["stdout"]).lower():
            return _emit({"ok": False, "status": "not_submitted", "results": [*results, result]}, 1)
        result["reused_existing"] = result["exit_code"] != 0
        results.append(result)
    job = _run(commands[2]["argv"])
    results.append(job)
    if job["exit_code"] != 0:
        return _emit({"ok": False, "status": "not_submitted", "results": results}, 1)
    name = job["stdout"].strip().splitlines()[-1]
    document = {
        "schema_version": "hypotrail.azure_submission/1",
        "status": "submitted",
        "job_name": name,
        "results": results,
        "meaning": "Submitted, result not observed yet; a submitted job is not a successful run.",
    }
    OUTPUTS.mkdir(exist_ok=True)
    submission.write_bytes(canonical.pretty_bytes(document))
    if args.wait:
        _run(["az", "ml", "job", "stream", "--name", name, *scope])
        state = _run(["az", "ml", "job", "show", "--name", name, "--query", "status", "-o", "tsv", *scope])
        document["status"] = state["stdout"].strip().lower() or "submitted"
        submission.write_bytes(canonical.pretty_bytes(document))
    return _emit(document)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(prog="python -m src.pipeline.utils.project")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("validate")
    p.add_argument("--offline", action="store_true")
    p.set_defaults(handler=validate)
    p = sub.add_parser("predict")
    p.add_argument("--input")
    p.add_argument("--parity", action="store_true")
    p.add_argument("--model")
    p.add_argument("--output", required=True)
    p.set_defaults(handler=predict)
    p = sub.add_parser("materialize")
    p.add_argument("--source", required=True)
    p.set_defaults(handler=materialize)
    p = sub.add_parser("run-local")
    p.add_argument("--mode", required=True)
    p.add_argument("--run-dir")
    p.set_defaults(handler=run_local)
    p = sub.add_parser("preflight")
    p.add_argument("--execute", action="store_true")
    p.set_defaults(handler=preflight)
    p = sub.add_parser("submit")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--wait", action="store_true")
    p.add_argument("--new-submission", action="store_true")
    p.set_defaults(handler=submit)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one command; a refusal prints its JSON and returns 2, an unexpected error 1."""
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except Exception as error:  # noqa: BLE001 - every outcome is one JSON document
        refusal = from_exception(error)
        if refusal is None:
            return _emit(internal_error(error), 1)
        sys.stdout.write(refusal.to_json() + "\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
