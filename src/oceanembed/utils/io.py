"""I/O helpers with graceful fallbacks (parquet -> csv, json).

Owner: Unit B (Darshan). Tables use parquet when pyarrow is installed, else csv.
Always save/load tables through save_table/load_table so the format is transparent.
"""
from __future__ import annotations
import json
import os
import numpy as np
import pandas as pd


def _has_pyarrow() -> bool:
    try:
        import pyarrow  # noqa: F401
        return True
    except Exception:
        return False


def save_table(df: pd.DataFrame, path_noext: str) -> str:
    """Save a DataFrame as parquet (preferred) or csv. Pass a path WITHOUT extension.

    Removes the other format so a stale twin can never shadow the fresh file (load_table prefers parquet).
    """
    os.makedirs(os.path.dirname(os.path.abspath(path_noext)), exist_ok=True)
    if _has_pyarrow():
        p, stale = path_noext + ".parquet", path_noext + ".csv"
        df.to_parquet(p, index=False)
    else:
        p, stale = path_noext + ".csv", path_noext + ".parquet"
        df.to_csv(p, index=False)
    if os.path.exists(stale):
        os.remove(stale)
    return p


def load_table(path_noext: str) -> pd.DataFrame:
    """Load a table saved by save_table, auto-detecting parquet vs csv."""
    pq, csv = path_noext + ".parquet", path_noext + ".csv"
    if os.path.exists(pq):
        return pd.read_parquet(pq)
    if os.path.exists(csv):
        return pd.read_csv(csv)
    raise FileNotFoundError(f"No table at {pq} or {csv}")


def save_npy(arr: np.ndarray, path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    np.save(path, arr)
    return path


def load_npy(path: str) -> np.ndarray:
    return np.load(path)


def save_json(obj: dict, path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    return path


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
