"""Enumeration classes for data management utilities."""

from enum import Enum


class ParquetEngine(Enum):
    """Enumeration for Parquet engine options."""

    PYARROW = "pyarrow"
    FASTPARQUET = "fastparquet"


class CsvSeparator(Enum):
    """Enumeration for CSV separator options."""

    COMMA = ","
    SEMICOLON = ";"
    TAB = "\t"
    PIPE = "|"


class FileSuffix(Enum):
    """Enumeration for file suffix options."""

    CSV = ".csv"
    PARQUET = ".parquet"
    XLSX = ".xlsx"
    PKL = ".pkl"
    JSON = ".json"
