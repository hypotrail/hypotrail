"""The contracts of this export, verified before any step uses them.

``data/hypotrail/SHA256SUMS`` lists the SHA-256 of every contract and of every file of the
evaluated model, relative to ``data/hypotrail``. The copies of the recipe and data contract
in ``src/conf/hypotrail/contracts/`` (they travel with the code) must be byte-identical to
the ones in the data asset: they are never a second authority. The recipe and data
contract must also hash, canonically, to the identities frozen in the configuration.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

from . import canonical
from .errors import ProjectError

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
            raise ProjectError("artifact_integrity_failed", "A checksum names a path outside the data folder.", path=name)
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
    """Verify the data folder and the code copies, then return the contracts."""
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
            "artifact_integrity_failed", "The data contract does not match its identity.", path=FILES["data_contract"]
        )
    if canonical.canonical_sha256(docs["projection"]) != hyp["expected_scientific_sha256"]:
        raise ProjectError(
            "artifact_integrity_failed", "The scientific projection does not match its identity.", path=FILES["projection"]
        )
    return Contracts(
        data_dir, docs["recipe"], docs["data_contract"], docs["plan"], docs["snapshot"], docs["projection"], docs["manifest"]
    )


# --- typed rows ------------------------------------------------------------------------


def _na_tokens(contract: dict) -> set[str]:
    parser = contract.get("parser") or {}
    return {str(v) for v in parser.get("na_values") or []}


def _convert(value: str, column: dict, na: set[str]) -> object:
    """Declared conversion of one text value; ``None`` for a declared NA token."""
    if value in na or value == "":
        return None
    kind = str(column.get("physical_type"))
    if kind in ("int64", "int32"):
        text = value.strip()
        if text.endswith(".0"):
            text = text[:-2]
        if not text.lstrip("-").isdigit():
            raise ValueError(value)
        return int(text)
    if kind in ("float64", "float32"):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(value)
        return number
    if kind in ("bool", "boolean"):
        lowered = value.strip().lower()
        if lowered not in ("true", "false"):
            raise ValueError(value)
        return lowered == "true"
    return value


def typed_frame(frame, contract: dict):
    """The rows of ``frame`` (text values, key column first) converted per the data
    contract: declared NA tokens become missing, every other value must convert, a
    non-nullable column may not be missing, ``allowed_values`` are enforced. No row is
    dropped and no value is imputed; the row order is kept."""
    import pandas as pd

    columns = [c for c in contract["columns"] if isinstance(c, dict)]
    expected = [KEY_COLUMN] + [c["name"] for c in columns]
    if list(frame.columns) != expected:
        raise ProjectError(
            "data_identity_mismatch",
            "The development rows do not have the contract's columns in its order.",
            path="columns",
            details={"expected": expected, "found": list(frame.columns)[:50]},
        )
    na = _na_tokens(contract)
    out = {KEY_COLUMN: frame[KEY_COLUMN].astype(str).tolist()}
    problems = []
    for column in columns:
        name = column["name"]
        values = []
        for key, raw in zip(out[KEY_COLUMN], frame[name].astype(str).tolist()):
            try:
                value = _convert(raw, column, na)
            except ValueError:
                problems.append({"row_key": key, "column": name, "problem": "not_convertible"})
                value = None
            if value is None and not column.get("nullable"):
                problems.append({"row_key": key, "column": name, "problem": "missing_not_allowed"})
            allowed = column.get("allowed_values")
            if value is not None and allowed is not None and value not in allowed:
                problems.append({"row_key": key, "column": name, "problem": "value_not_allowed"})
            values.append(value)
        out[name] = values
    if problems:
        raise ProjectError(
            "contract_invalid",
            f"{len(problems)} values do not satisfy the data contract; nothing was corrected.",
            path="development rows",
            remediation="Check the source file against the data contract; the export never repairs data.",
            details={"examples": problems[:MAX_EXAMPLES], "count": len(problems)},
        )
    typed = pd.DataFrame(out)
    for column in columns:
        kind = str(column.get("physical_type"))
        if kind in ("int64", "int32"):
            typed[column["name"]] = typed[column["name"]].astype("Int64" if column.get("nullable") else "int64")
        elif kind in ("float64", "float32"):
            typed[column["name"]] = typed[column["name"]].astype("float64")
    return typed


def read_rows(path: Path, contract: dict):
    """Read a CSV of text values written by this project and type it."""
    import pandas as pd

    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    return typed_frame(frame, contract)


def write_rows(frame, path: Path) -> None:
    """Write typed rows as text CSV (missing values empty), creating the folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = frame.astype(object).where(frame.notna(), "")
    text.to_csv(path, index=False)
