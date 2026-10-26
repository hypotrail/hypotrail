"""The contracts of this export, verified before any step uses them.

``data/hypotrail/SHA256SUMS`` lists the SHA-256 of every contract and of every file of the
evaluated model, relative to ``data/hypotrail``. The copies of the recipe and data contract
in ``src/conf/hypotrail/contracts/`` (they travel with the code) must be byte-identical to
the ones in the data asset: they are never a second authority. The recipe and data
contract must also hash, canonically, to the identities frozen in the configuration.

SHA256SUMS is written with the data folder, so it proves that nothing changed by accident,
not where the files come from (review round 9, R9AB-1). Every contract a step reads is
therefore bound to the configuration that travels with the code, and a mismatch is refused
as ``artifact_integrity_failed`` before anything is read from it:

* the development plan (:func:`check_plan`): its partition key digests, its ``keys_sha256``
  and ``protocol_id`` recomputed and compared with ``components.data_splitting`` (part of
  the scientific projection), its development key digest and row count recomputed, its
  roles, final-test summary and excluded rows equal to the snapshot's evaluation plan;
* the deployment snapshot (:func:`check_snapshot`): its canonical SHA-256 is
  ``hypotrail.snapshot_id``, and its study, recipe, data contract and plan identities are
  the configuration's; an override of an identity of ``hypotrail`` is refused;
* the evaluated model (:func:`check_evaluated`): ``models/evaluated`` is present exactly
  when the snapshot names a predictor, and its bundle is that predictor (the steps and
  ``validate`` also compare the id ``hypotrail_runtime.verify_bundle`` recomputes).
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from . import canonical
from .errors import ProjectError

if TYPE_CHECKING:
    import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
CODE_CONTRACTS = ROOT / "src" / "conf" / "hypotrail" / "contracts"
SUMS = "SHA256SUMS"
KEY_COLUMN = "hypotrail_row_key"
DEVELOPMENT_MANIFEST = "development.manifest.json"
MATERIALIZATION_SCHEMA = "hypotrail.development_materialization/1"
FILES = {
    "recipe": "contracts/model-recipe.json",
    "data_contract": "contracts/data-contract.json",
    "plan": "contracts/development-plan.json",
    "snapshot": "contracts/deployment-snapshot.json",
    "projection": "contracts/scientific-projection.json",
    "manifest": "contracts/export-manifest.json",
    "readiness": "contracts/readiness.json",
}
CODE_COPIES = {"recipe": "model-recipe.json", "data_contract": "data-contract.json"}
MAX_EXAMPLES = 10


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a file's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_sums(data_dir: Path) -> dict[str, str]:
    """Return ``{relative path: sha256}`` of ``data/hypotrail/SHA256SUMS``."""
    path = data_dir / SUMS
    if not path.is_file():
        raise ProjectError(
            "artifact_integrity_failed",
            "data/hypotrail/SHA256SUMS is missing.",
            path=str(path),
            remediation="Export the study again; never edit the export's data folder.",
        )
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, _, name = line.partition("  ")
            out[name] = digest
    return out


def verify_data_dir(data_dir: Path) -> dict[str, str]:
    """Check every file listed in SHA256SUMS; refuse a missing or altered one."""
    sums = read_sums(data_dir)
    for name, digest in sums.items():
        path = data_dir / name
        if ".." in Path(name).parts or Path(name).is_absolute():
            raise ProjectError(
                "artifact_integrity_failed", "A checksum names a path outside the data folder.", path=name,
            )
        if not path.is_file() or path.is_symlink():
            raise ProjectError(
                "artifact_integrity_failed",
                "A file of the export is missing.",
                path=name,
                remediation="Export the study again.",
            )
        if sha256_file(path) != digest:
            raise ProjectError(
                "artifact_integrity_failed",
                "A file of the export was changed after the export.",
                path=name,
                remediation="Restore the exported file or export again; a changed contract is a new study activity.",
            )
    return sums


def load_json(path: Path) -> dict:
    """Read a strict JSON object (no NaN or Infinity)."""
    try:
        data = canonical.loads_strict(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProjectError("contract_invalid", "A contract file is not readable JSON.", path=str(path)) from error
    if not isinstance(data, dict):
        raise ProjectError("contract_invalid", "A contract file is not a JSON object.", path=str(path))
    return data


# --- the identities of the plan, the snapshot and the evaluated model (R9AB-1) -----------

IDENTITY_OVERRIDES = ("hypotrail.snapshot_id", "hypotrail.study_id", "hypotrail.study_revision")
EVALUATED = "models/evaluated"
BUNDLE_DOCUMENT = "predictor_bundle.json"
RESTORE = "Restore the exported data folder and configuration, or export the study again; never edit them."


def key_order(key: str) -> tuple:
    """Return the sort key of a row key (the engine's ``L<n>`` keys in numeric order)."""
    digits = key[1:] if key[:1].isalpha() else key
    return (0, int(digits), key) if digits.isdigit() else (1, 0, key)


def development_keys(plan: dict) -> list[str]:
    """Return every development row key of the plan, in key order."""
    return sorted({k for part in plan["partitions"] for k in part["row_keys"]}, key=key_order)


def _identity_refused(message: str, path: str, details: dict) -> ProjectError:
    return ProjectError("artifact_integrity_failed", message, path=path, remediation=RESTORE, details=details)


def _compare(found: object, expected: object, message: str, path: str) -> None:
    if found != expected:
        raise _identity_refused(message, path, {"expected": expected, "found": found})


def check_plan(plan: dict, protocol_id: str, keys_sha256: str, snapshot: dict) -> None:
    """Refuse a development plan that is not the one the configuration and snapshot name.

    Every digest is recomputed from the row keys the steps will read: a partition's
    ``keys_sha256``, the plan's ``keys_sha256`` (equal to ``keys_sha256``, the
    configuration's), its development key digest and row count; ``protocol_id`` is the
    configuration's, and the roles, final-test summary and excluded rows are the snapshot's.
    """
    where = FILES["plan"]
    try:
        partitions = plan["partitions"]
        rows = {part["id"]: list(part["row_keys"]) for part in partitions}
        if len(rows) != len(partitions):
            raise ValueError("two partitions have the same id")
        for part in partitions:
            _compare(part["keys_sha256"], canonical.canonical_sha256(list(part["row_keys"])),
                     "A partition of the development plan does not match its key hash.", f"{where}#{part['id']}")
        development = development_keys(plan)
    except (KeyError, TypeError, ValueError) as error:
        raise _identity_refused("The development plan is malformed.", where, {"error": str(error)}) from error
    recomputed = canonical.canonical_sha256(rows)
    _compare(recomputed, keys_sha256, "The development plan is not the study's: its row keys do not hash to the "
             "configuration's components.data_splitting.keys_sha256.", where)
    _compare(plan.get("keys_sha256"), recomputed,
             "The development plan's keys_sha256 is not its row keys' hash.", where)
    _compare(plan.get("protocol_id"), protocol_id, "The development plan names another protocol than the "
             "configuration's components.data_splitting.protocol_id.", where)
    _compare(plan.get("development_keys_sha256"), canonical.canonical_sha256(development),
             "The development plan's development_keys_sha256 is not its development rows' hash.", where)
    _compare(plan.get("n_development_rows"), len(development),
             "The development plan's n_development_rows is not its number of development rows.", where)
    recorded = snapshot.get("evaluation_plan") or {}
    found = {
        "protocol_id": plan.get("protocol_id"),
        "keys_sha256": recomputed,
        "roles": [part.get("role") for part in partitions],
        "n_development_rows": len(development),
        "final_test": plan.get("final_test"),
        "excluded_rows": plan.get("excluded_rows"),
    }
    expected = {key: recorded.get(key) for key in found}
    differing = sorted(key for key in found if found[key] != expected[key])
    if differing:
        raise _identity_refused(
            "The development plan differs from the snapshot's evaluation plan.", where, {"differing": differing},
        )


def check_snapshot(snapshot: dict, config: dict, overrides: list[str]) -> None:
    """Refuse a deployment snapshot that is not the one the configuration names.

    Its canonical SHA-256 is ``hypotrail.snapshot_id``; its study, recipe, data contract and
    plan identities are the configuration's. An override of ``hypotrail.snapshot_id``,
    ``study_id`` or ``study_revision`` (generated identities, never operational) is refused.
    """
    where = FILES["snapshot"]
    for override in overrides:
        key = override.split("=", 1)[0].lstrip("+~")
        if key in IDENTITY_OVERRIDES:
            raise ProjectError(
                "scientific_config_changed",
                "An identity of the export cannot be overridden.",
                path=key,
                remediation="Remove the override; the identities are generated with the export.",
                details={"override": override},
            )
    hyp, split = config["hypotrail"], config["components"]["data_splitting"]
    _compare(canonical.canonical_sha256(snapshot), hyp["snapshot_id"],
             "The deployment snapshot does not match the configuration's hypotrail.snapshot_id.", where)
    plan = snapshot.get("evaluation_plan") or {}
    found = {
        "study_id": snapshot.get("study_id"),
        "study_revision": snapshot.get("study_revision"),
        "recipe_sha256": snapshot.get("recipe_sha256"),
        "data_contract_sha256": snapshot.get("data_contract_sha256"),
        "protocol_id": plan.get("protocol_id"),
        "keys_sha256": plan.get("keys_sha256"),
    }
    expected = {
        "study_id": hyp["study_id"],
        "study_revision": hyp["study_revision"],
        "recipe_sha256": hyp["recipe_sha256"],
        "data_contract_sha256": hyp["data_contract_sha256"],
        "protocol_id": split["protocol_id"],
        "keys_sha256": split["keys_sha256"],
    }
    differing = sorted(key for key in found if found[key] != expected[key])
    if differing:
        raise _identity_refused(
            "The deployment snapshot names other identities than the configuration.", where, {"differing": differing},
        )


def evaluated_predictor_id(snapshot: dict) -> str | None:
    """Return the predictor id of the evaluated model the snapshot names, or None."""
    predictor = snapshot.get("predictor")
    return predictor.get("predictor_id") if isinstance(predictor, dict) else None


def check_evaluated(data_dir: Path, snapshot: dict, predictor_id: str | None = None) -> None:
    """Refuse an evaluated model folder that is not the snapshot's predictor.

    ``models/evaluated`` holds a bundle exactly when the snapshot names a predictor, and the
    bundle document names that predictor. ``predictor_id``, when given, is the id that
    ``hypotrail_runtime.verify_bundle`` recomputed from the bundle's content, compared too.
    """
    expected = evaluated_predictor_id(snapshot)
    document = data_dir / EVALUATED / BUNDLE_DOCUMENT
    if not document.is_file():
        if expected is not None:
            raise _identity_refused(
                "The snapshot names an evaluated model that the export does not hold.",
                f"{EVALUATED}/{BUNDLE_DOCUMENT}",
                {"expected": expected},
            )
        return
    if expected is None:
        raise _identity_refused(
            "The export holds an evaluated model that its snapshot does not name.",
            EVALUATED,
            {"expected": None},
        )
    _compare(load_json(document).get("predictor_id"), expected,
             "The evaluated model is not the predictor the snapshot names.", EVALUATED)
    if predictor_id is not None:
        _compare(predictor_id, expected, "The evaluated model is not the predictor the snapshot names.", EVALUATED)


def decision_rule(snapshot: dict) -> dict | None:
    """Return the binary study's adopted decision rule, as metadata, or None (regression).

    The rule is carried by the snapshot (bound by ``hypotrail.snapshot_id``) and never applied:
    the model output is the positive-class score; a capacity or share rule needs a whole batch
    ranked, which a row-wise endpoint cannot do.
    """
    rule = snapshot.get("decision_rule")
    if not isinstance(rule, dict):
        return None
    return {
        "rule": rule.get("rule"),
        "kind": rule.get("kind"),
        "applied_in_model_output": False,
        "needs_batch_ranking": bool(rule.get("needs_batch_ranking")),
    }


@dataclass(frozen=True)
class Contracts:
    """The verified contracts of the export."""

    data_dir: Path
    recipe: dict
    data_contract: dict
    plan: dict
    snapshot: dict
    projection: dict
    manifest: dict


def load(frozen: dict) -> Contracts:
    """Verify the data folder, the code copies and every identity, then return the contracts."""
    config = frozen["config"]
    data_dir = Path(config["data_dir"])
    sums = verify_data_dir(data_dir)
    docs = {key: load_json(data_dir / rel) for key, rel in FILES.items()}
    for key, name in CODE_COPIES.items():
        copy = CODE_CONTRACTS / name
        if not copy.is_file() or sha256_file(copy) != sums.get(FILES[key]):
            raise ProjectError(
                "artifact_integrity_failed",
                "The contract copy shipped with the code differs from the exported one.",
                path=f"src/conf/hypotrail/contracts/{name}",
                remediation="Restore the exported copy; it is never a second authority.",
            )
    hyp = config["hypotrail"]
    if canonical.canonical_sha256(docs["recipe"]) != hyp["recipe_sha256"]:
        raise ProjectError("artifact_integrity_failed", "The recipe does not match its identity.", path=FILES["recipe"])
    if canonical.canonical_sha256(docs["data_contract"]) != hyp["data_contract_sha256"]:
        raise ProjectError(
            "artifact_integrity_failed",
            "The data contract does not match its identity.",
            path=FILES["data_contract"],
        )
    if canonical.canonical_sha256(docs["projection"]) != hyp["expected_scientific_sha256"]:
        raise ProjectError(
            "artifact_integrity_failed",
            "The scientific projection does not match its identity.",
            path=FILES["projection"],
        )
    split = config["components"]["data_splitting"]
    check_snapshot(docs["snapshot"], config, frozen.get("overrides") or [])
    check_plan(docs["plan"], split["protocol_id"], split["keys_sha256"], docs["snapshot"])
    check_evaluated(data_dir, docs["snapshot"])
    return Contracts(
        data_dir,
        docs["recipe"],
        docs["data_contract"],
        docs["plan"],
        docs["snapshot"],
        docs["projection"],
        docs["manifest"],
    )


# --- the values the engine read --------------------------------------------------------
#
# The study's engine reads its dataset with one ``pandas.read_csv`` call
# (``mlkit.study.data.read_kwargs`` and ``read_frame``): the separator (``whitespace`` is
# ``\s+``), encoding, decimal mark, quote character and header of the case, only the case's
# ``na_values`` as missing (``keep_default_na=False``, so an empty cell is an empty text
# value), and blank lines kept. A numeric variable that pandas read as text, every cell of
# which is a number once the rows are restricted, is converted with ``pandas.to_numeric``
# (``mlkit.study.data.check_values``). This project repeats that call and that conversion,
# without importing the engine, so the rows it trains and predicts on hold the values the
# study's model was fitted on. Only the row keys come from the engine's record splitter
# (``project.py``).

MISSING_TEXT = "\\N"
ESCAPE = "\\"
NUMERIC = "numeric"


def _columns(contract: dict) -> list[dict]:
    return [c for c in contract["columns"] if isinstance(c, dict)]


def read_kwargs(contract: dict) -> dict:
    """Return the ``pandas.read_csv`` arguments of the engine's reading of the dataset."""
    parser = contract.get("parser") or {}
    delimiter = parser.get("delimiter", ",")
    kwargs = {
        "sep": r"\s+" if delimiter == "whitespace" else delimiter,
        "encoding": parser.get("encoding", "utf-8"),
        "decimal": parser.get("decimal") or ".",
        "quotechar": parser.get("quotechar", '"'),
        "keep_default_na": False,
        "na_values": [str(v) for v in parser.get("na_values") or []],
        "skip_blank_lines": False,
    }
    if parser.get("header"):
        kwargs["header"] = 0
    else:
        kwargs.update(header=None, names=[c["name"] for c in _columns(contract)])
    return kwargs


def _text_auxiliary(contract: dict) -> list[str]:
    """Return the auxiliary columns the contract declares as text.

    The predictor never reads an auxiliary column. One whose pandas type the contract cannot
    declare (an integer above the int64 range read as ``uint64``, booleans with a missing
    token read as an ``object`` column; listed under the extension
    ``hypotrail.auxiliary_as_text``) is declared ``string``: its cells are read as their text,
    never converted, so the export and this project describe the same values.
    """
    return [
        c["name"] for c in _columns(contract) if c.get("role") == "auxiliary" and c.get("physical_type") == "string"
    ]


def read_source(path: Path, contract: dict, keys: list[str]) -> pd.DataFrame:
    """Read every record of the study's dataset file as the engine does, indexed by its keys.

    ``keys`` are the engine's row keys of the file's records, in file order; the parsed file
    must have exactly the contract's columns and one row per key, as the engine requires.
    """
    import pandas as pd

    kwargs = read_kwargs(contract)
    kwargs["dtype"] = dict.fromkeys(_text_auxiliary(contract), str)
    frame = pd.read_csv(path, **kwargs)
    names = [c["name"] for c in _columns(contract)]
    if list(frame.columns) != names or len(frame) != len(keys):
        raise ProjectError(
            "data_identity_mismatch",
            "The source file does not parse into the records and columns the study read.",
            path=str(path),
            remediation="Use the file the study was made on, unmodified.",
            details={"rows": len(frame), "records": len(keys), "columns": [str(c) for c in frame.columns][:50]},
        )
    frame.index = pd.Index(keys, name=KEY_COLUMN)
    return frame


def _physical_type(series: pd.Series) -> str | None:
    """Return the contract physical type a column holds (``hypotrail_runtime.inference``)."""
    from pandas.api.types import is_bool_dtype, is_float_dtype, is_integer_dtype, is_object_dtype, is_string_dtype

    dtype = series.dtype
    if is_bool_dtype(dtype):
        return "bool"
    if is_integer_dtype(dtype) and str(dtype) == "int64":
        return "int64"
    if is_float_dtype(dtype) and str(dtype) == "float64":
        return "float64"
    if (is_string_dtype(dtype) or is_object_dtype(dtype)) and all(isinstance(v, str) for v in series.dropna()):
        return "string"
    return None


def _numbers(series: pd.Series) -> tuple[pd.Series, list]:
    """Convert a numeric column that pandas read as text, as the engine does.

    Return the converted column and the positions of the cells that are not numbers (the
    column is returned unchanged when there is one).
    """
    import pandas as pd
    from pandas.api.types import is_numeric_dtype

    if is_numeric_dtype(series.dtype):
        return series, []
    bad = series.notna() & pd.to_numeric(series, errors="coerce").isna()
    if bad.any():
        return series, [i for i, flag in enumerate(bad.tolist()) if flag]
    return pd.to_numeric(series), []


def engine_values(frame: pd.DataFrame, contract: dict, where: str) -> pd.DataFrame:
    """Return the development rows as the engine holds them, checked against the contract.

    A numeric column read as text is converted as the engine converts it; every column must
    then hold the contract's physical type, its missing values must be allowed and its
    values must be allowed ones. Nothing is imputed, dropped or reordered.
    """
    out = frame.copy()
    keys = [str(k) for k in out.index]
    problems: list = []
    as_text = set(_text_auxiliary(contract))
    for column in _columns(contract):
        name = column["name"]
        if column.get("semantic_type") == NUMERIC and name not in as_text:
            out[name], bad = _numbers(out[name])
            problems += [{"row_key": keys[i], "column": name, "problem": "not_convertible"} for i in bad]
        found = _physical_type(out[name])
        if found != column.get("physical_type"):
            problems.append({"column": name, "problem": "physical_type", "expected": column.get("physical_type"),
                             "found": found})
    problems += _contract_problems(out, contract, keys)
    _refuse(problems, where)
    return out


def _contract_problems(frame: pd.DataFrame, contract: dict, keys: list[str]) -> list:
    """Return the missing values a column does not allow and the values it does not list."""
    problems = []
    for column in _columns(contract):
        if column["name"] not in frame.columns:
            continue
        allowed = column.get("allowed_values")
        missing = frame[column["name"]].isna().tolist()
        for key, value, absent in zip(keys, frame[column["name"]].tolist(), missing, strict=True):
            if absent and not column.get("nullable"):
                problems.append({"row_key": key, "column": column["name"], "problem": "missing_not_allowed"})
            elif not absent and allowed is not None and value not in allowed:
                problems.append({"row_key": key, "column": column["name"], "problem": "value_not_allowed"})
    return problems


def _refuse(problems: list, where: str) -> None:
    if problems:
        raise ProjectError(
            "contract_invalid",
            f"{len(problems)} values do not satisfy the data contract; nothing was corrected.",
            path=where,
            remediation="Check the file against the data contract; the export never repairs data.",
            details={"examples": problems[:MAX_EXAMPLES], "count": len(problems)},
        )


# --- prediction input ----------------------------------------------------------------------


def typed_features(path: Path, contract: dict) -> pd.DataFrame:
    """Read a CSV of feature values with the dataset's reading rules and type it as declared.

    The file is comma-separated (semicolon-separated when the dataset's decimal mark is a
    comma) with a header, in any column order and without the target. It is read like the
    study's dataset: its encoding, quote character and decimal mark, only its ``na_values`` as
    missing, so an empty cell is an empty text value. A declared text column keeps its text;
    a declared number column holds what pandas reads as a number (as the engine read it), an
    empty cell of it being a missing value; an undeclared column is kept as read so the
    predictor can refuse it. Nothing is imputed, dropped or reordered.
    """
    import pandas as pd

    declared = {c["name"]: c for c in _columns(contract)}
    kwargs = read_kwargs(contract)
    kwargs.update(sep=";" if kwargs["decimal"] == "," else ",", header=0)
    kwargs.pop("names", None)
    kwargs["dtype"] = {name: str for name, c in declared.items() if c.get("physical_type") == "string"}
    frame = pd.read_csv(path, **kwargs)
    keys = [f"row{i}" for i in range(len(frame))]
    problems: list = []
    for name in frame.columns:
        column = declared.get(name)
        if column is not None:
            frame[name], found = _as_declared(frame[name], column)
            problems += [{"row_key": keys[i], "column": name, "problem": "not_convertible"} for i in found]
    problems += _contract_problems(frame, contract, keys)
    _refuse(problems, str(path))
    return frame


def refuse_non_finite(frame: pd.DataFrame, contract: dict) -> None:
    """Refuse a feature value that is not a finite number before any prediction.

    pandas reads ``inf`` and ``Infinity`` as numbers (the input is read as the engine reads
    its dataset), but no fitted model takes them: the refusal is ``contract_invalid`` with
    one issue per column, in the shape of the runtime's input check (``code``, ``path``
    ``input/<column>``, ``kind``, ``n_rows`` and the positions of a few rows).
    """
    import numpy as np
    from pandas.api.types import is_bool_dtype, is_numeric_dtype

    issues = []
    for column in _columns(contract):
        name = column["name"]
        if column.get("role", "feature") != "feature" or name not in frame.columns:
            continue
        series = frame[name]
        if not is_numeric_dtype(series.dtype) or is_bool_dtype(series.dtype):
            continue
        values = series.to_numpy(dtype="float64", na_value=np.nan)
        bad = np.isinf(values)
        if bad.any():
            issues.append(
                {
                    "code": "contract_invalid",
                    "path": f"input/{name}",
                    "kind": "non_finite_values",
                    "n_rows": int(bad.sum()),
                    "rows": [int(i) for i in np.flatnonzero(bad)[:MAX_EXAMPLES]],
                },
            )
    if issues:
        first = issues[0]
        more = f" (and {len(issues) - 1} more)" if len(issues) > 1 else ""
        raise ProjectError(
            "contract_invalid",
            f"The inference rows do not satisfy the data contract: {first['kind']} at {first['path']}{more}",
            path=first["path"],
            remediation="Send finite numbers (or an empty cell for a missing value); an infinity is never predicted.",
            details={"issues": issues},
        )


def _as_declared(series: pd.Series, column: dict) -> tuple[pd.Series, list]:
    """Type one input column as declared; return it and the positions that do not convert."""
    import pandas as pd
    from pandas.api.types import is_bool_dtype, is_numeric_dtype

    kind = column.get("physical_type")
    if kind == "bool":
        return series, [i for i, v in enumerate(series.tolist()) if not pd.isna(v) and not isinstance(v, bool)]
    if kind not in ("float64", "int64"):
        return series, []
    if is_bool_dtype(series.dtype):
        return series, list(range(len(series)))
    # An empty cell of a number column can only be a missing value (``DataFrame.to_csv``
    # writes one so); in a text column it stays the empty text the engine reads.
    if not is_numeric_dtype(series.dtype):
        series = series.mask(series == "")
    series, bad = _numbers(series)
    if bad or (kind == "int64" and str(series.dtype) == "int64"):
        return series, bad
    series = series.astype("float64")
    if kind == "int64":
        bad = [i for i, v in enumerate(series.tolist()) if not math.isnan(v) and not v.is_integer()]
        if not bad and not series.isna().any():
            return series.astype("int64"), []
    return series, bad


# --- the rows this project writes ------------------------------------------------------------
#
# The development rows, the prepared rows and the partitions are CSV files (UTF-8, header
# ``hypotrail_row_key`` then the contract's columns) whose cells hold exactly the typed
# values: a missing value is ``\N``, a text value starting with a backslash gets one more
# backslash in front (so an empty text, ``\N`` or any other text is read back as itself),
# a number is written so it reads back to the same float or integer. Written and read with
# the standard ``csv`` module, these files hold no value pandas would reinterpret.


def _cell(value: object) -> str:
    """Return the text of one typed value."""
    import numpy as np
    import pandas as pd

    if value is None or value is pd.NA or (isinstance(value, float) and math.isnan(value)):
        return MISSING_TEXT
    if isinstance(value, str):
        return ESCAPE + value if value.startswith(ESCAPE) else value
    if isinstance(value, bool | np.bool_):
        return "True" if value else "False"
    if isinstance(value, float | np.floating):
        return repr(float(value))
    if isinstance(value, int | np.integer):
        return str(int(value))
    raise ProjectError("contract_invalid", f"A value of type {type(value).__name__} cannot be written.", path="rows")


def _value(text: str, kind: str | None) -> object:
    """Return the typed value of one cell; raise ``ValueError`` when it does not convert."""
    if text == MISSING_TEXT:
        return None
    if text.startswith(ESCAPE):
        text = text[1:]
    if kind == "float64":
        return float(text)
    if kind == "int64":
        return int(text)
    if kind == "bool":
        if text not in ("True", "False"):
            raise ValueError(text)
        return text == "True"
    return text


def typed_frame(frame: pd.DataFrame, contract: dict) -> pd.DataFrame:
    """Convert rows read from this project's files (key column first) to typed values.

    The cells hold the texts :func:`write_rows` writes; every value must convert to its
    declared type, a non-nullable column may not be missing, and ``allowed_values`` are
    enforced. No row is dropped and no value is imputed; the row order is kept.
    """
    import numpy as np
    import pandas as pd

    columns = _columns(contract)
    expected = [KEY_COLUMN] + [c["name"] for c in columns]
    if list(frame.columns) != expected:
        raise ProjectError(
            "data_identity_mismatch",
            "The development rows do not have the contract's columns in its order.",
            path="columns",
            details={"expected": expected, "found": list(frame.columns)[:50]},
        )
    keys = [str(_value(str(k), None)) for k in frame[KEY_COLUMN].tolist()]
    problems: list = []
    out = {KEY_COLUMN: keys}
    for column in columns:
        values = []
        for key, text in zip(keys, frame[column["name"]].tolist(), strict=True):
            try:
                values.append(_value(str(text), column.get("physical_type")))
            except ValueError:
                problems.append({"row_key": key, "column": column["name"], "problem": "not_convertible"})
                values.append(None)
        out[column["name"]] = values
    typed = pd.DataFrame(out)
    for column in columns:
        name, kind = column["name"], column.get("physical_type")
        missing = typed[name].isna().any()
        if kind == "int64":
            typed[name] = typed[name].astype("Int64" if missing else "int64")
        elif kind == "float64":
            typed[name] = typed[name].astype("float64")
        elif kind == "bool" and not missing:
            typed[name] = typed[name].astype("bool")
        elif kind == "string":
            typed[name] = typed[name].where(typed[name].notna(), np.nan)
    problems += _contract_problems(typed, contract, keys)
    _refuse(problems, "development rows")
    return typed


def read_rows(path: Path, contract: dict) -> pd.DataFrame:
    """Read a CSV of rows written by this project (:func:`write_rows`) and type it."""
    import csv

    import pandas as pd

    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise ProjectError("data_identity_mismatch", "The rows file is empty.", path=str(path))
    header, body = rows[0], rows[1:]
    if any(len(row) != len(header) for row in body):
        raise ProjectError("data_identity_mismatch", "A row of the file has another width.", path=str(path))
    return typed_frame(pd.DataFrame(body, columns=header, dtype=object), contract)


def write_rows(frame: pd.DataFrame, path: Path) -> None:
    """Write typed rows (key column first) as this project's CSV, creating the folder."""
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow([str(c) for c in frame.columns])
        writer.writerows([_cell(v) for v in row] for row in frame.itertuples(index=False, name=None))
