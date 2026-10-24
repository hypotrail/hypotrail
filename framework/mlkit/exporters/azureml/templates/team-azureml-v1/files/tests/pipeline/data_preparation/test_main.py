"""Test suite for the data preparation module (Hypotrail export).

The team template's example test was replaced: these tests check the declared conversions of
the study's data contract on rows built here (in this project's row format: a missing value is
``contracts.MISSING_TEXT``, an empty text is an empty text), without the runtime.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.pipeline.utils.hypotrail import contracts
from src.pipeline.utils.hypotrail.errors import ProjectError

CONTRACT = json.loads((Path(__file__).parents[3] / "data/hypotrail/contracts/data-contract.json").read_text())


def _frame(rows: list[list[str]]) -> pd.DataFrame:
    names = [contracts.KEY_COLUMN] + [c["name"] for c in CONTRACT["columns"]]
    return pd.DataFrame(rows, columns=names)


def _row(key: str, overrides: dict | None = None) -> list[str]:
    values = [key]
    for column in CONTRACT["columns"]:
        kind = column["physical_type"]
        value = "1" if kind.startswith("int") else "1.5" if kind.startswith("float") else "a"
        if column.get("allowed_values"):
            value = str(column["allowed_values"][0])
        values.append((overrides or {}).get(column["name"], value))
    return values


def test_declared_conversion_keeps_rows_and_order() -> None:
    """Two valid rows stay two rows, in their order."""
    typed = contracts.typed_frame(_frame([_row("L2"), _row("L1")]), CONTRACT)
    assert typed[contracts.KEY_COLUMN].tolist() == ["L2", "L1"]


def test_missing_value_in_a_required_column_is_refused() -> None:
    """A required column with a missing value is refused, never imputed."""
    required = next((c for c in CONTRACT["columns"] if not c.get("nullable")), None)
    if required is None:
        pytest.skip("every column of this contract is nullable")
    with pytest.raises(ProjectError) as error:
        contracts.typed_frame(_frame([_row("L1", {required["name"]: contracts.MISSING_TEXT})]), CONTRACT)
    assert error.value.code == "contract_invalid"


def test_an_empty_text_is_a_value_not_a_missing_one() -> None:
    """An empty cell of a text column is the empty text the study read, never a missing value."""
    text = next((c for c in CONTRACT["columns"] if c["physical_type"] == "string"), None)
    if text is None:
        pytest.skip("this contract has no text column")
    typed = contracts.typed_frame(_frame([_row("L1", {text["name"]: ""})]), CONTRACT)
    assert typed[text["name"]].tolist() == [""]


def test_columns_out_of_order_are_refused() -> None:
    """A permuted column order is a different table."""
    frame = _frame([_row("L1")])
    with pytest.raises(ProjectError) as error:
        contracts.typed_frame(frame[list(reversed(frame.columns))], CONTRACT)
    assert error.value.code == "data_identity_mismatch"
