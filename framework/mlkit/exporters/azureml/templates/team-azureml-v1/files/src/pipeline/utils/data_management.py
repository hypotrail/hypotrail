"""Data management utilities for the ML pipeline (adapted by the Hypotrail export).

Kept from the team template: ``load_data``, ``write_data`` and ``save_scores``. Removed:
the recursive directory removal (no step deletes a folder), the Excel reader (openpyxl is
not in this environment) and pickle reading (a pickle from an unknown source runs code).
"""

import json
import logging
from pathlib import Path
from typing import Optional, Union

from pandas import DataFrame, read_csv, read_parquet

from .enums import CsvSeparator, FileSuffix, ParquetEngine


def create_path(path: Union[str, Path], *, exist_ok: bool = True) -> Path:
    """Create a directory path.

    Args:
    ----
        path: The path to create.
        exist_ok: Whether to ignore if the directory already exists. Defaults to True.

    Returns:
    -------
        The created directory path.

    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=exist_ok)
    return path


def load_data(
    file_path: Union[str, Path],
    columns: Optional[list] = None,
    parquet_engine: ParquetEngine = ParquetEngine.PYARROW,
    csv_sep: CsvSeparator = CsvSeparator.COMMA,
) -> DataFrame:
    """Load a CSV or Parquet file as a pandas DataFrame.

    Args:
    ----
        file_path (Union[str, Path]): The file path of the data file to be loaded.
        columns (Optional[list], optional): A list of column names to keep in the DataFrame.
        parquet_engine (ParquetEngine, optional): Parquet engine to use.
        csv_sep (CsvSeparator, optional): Separator to use for CSV files.

    Returns:
    -------
        DataFrame: The loaded data as a pandas DataFrame.

    Raises:
    ------
        ValueError: If the file type is not supported.

    """
    file_path = Path(file_path)
    suffix = FileSuffix(file_path.suffix)
    match suffix:
        case FileSuffix.CSV:
            data = read_csv(file_path, sep=csv_sep.value)
        case FileSuffix.PARQUET:
            data = read_parquet(file_path, engine=parquet_engine.value)
        case _:
            error_msg = f"Unsupported file type: {file_path.suffix}"
            raise ValueError(error_msg)
    if columns:
        data = data.filter(columns)
    logging.info("Data loaded successfully from %s", file_path)
    return data


def write_data(
    data: DataFrame,
    file_path: Union[str, Path],
    file_name: str,
    *,
    index: bool = False,
) -> Path:
    """Write a DataFrame to a CSV or JSON file.

    Args:
    ----
        data (DataFrame): DataFrame to write to file.
        file_path (Union[str, Path]): Folder to save the DataFrame in.
        file_name (str): File name to save the DataFrame.
        index (bool, optional): Whether to include the index in the output file.

    Returns:
    -------
        Path: The full path of the written file.

    """
    file_path = create_path(file_path) / file_name
    suffix = FileSuffix(file_path.suffix)
    match suffix:
        case FileSuffix.CSV:
            data.to_csv(file_path, index=index)
        case FileSuffix.JSON:
            data.to_json(file_path, orient="records", index=index)
        case _:
            error_msg = f"Unsupported file type: {file_path.suffix}"
            raise ValueError(error_msg)
    logging.info("Data written successfully to %s", file_path)
    return file_path


def save_scores(scores: dict, reports_path: str, filename: str = "metrics.json") -> None:
    """Save technical scores to a JSON file.

    Args:
    ----
        scores: A dictionary containing the scores.
        reports_path: The directory path to save the scores file.
        filename: Name of the file to save to.

    """
    reports_path = create_path(reports_path)
    with (reports_path / filename).open("w", encoding="utf-8") as fp:
        json.dump(obj=scores, fp=fp, indent=4, sort_keys=True)
    logging.info("Scores saved to %s", reports_path)
