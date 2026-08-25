"""Download real Argo temperature profiles for the NIO, 2022 — INDEPENDENT validation only.

OWNER: Unit B (Darshan).
API VERIFIED via Context7 (euroargodev/argopy). Runtime NOT verified here: needs `pip install argopy` + network.

Region box format (argopy): [lon_min, lon_max, lat_min, lat_max, pres_min, pres_max, date_start, date_end].
Output xarray has PRES, TEMP, PSAL, LATITUDE, LONGITUDE, TIME over dims (N_PROF, N_LEVELS).

Run:  python -m oceanembed.data.download_argo
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd
from oceanembed import config
from oceanembed.utils import io


def _fix_ssl() -> None:
    """Point Python's SSL at certifi's CA bundle.

    [VERIFIED 2026-08-25] On Windows the default SSL context often cannot find a CA bundle, so the Argo
    ERDDAP server fails with CERTIFICATE_VERIFY_FAILED. Setting these env vars fixes it for every teammate.
    """
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except Exception:
        pass


_fix_ssl()


GOOD_QC = {1, 2}  # Argo QC: 1=good, 2=probably good


def _profiles_to_rows(ds) -> list[tuple]:
    """argopy N_POINTS dataset -> long rows [lat, lon, date, depth_idx, temp], QC-filtered + interpolated."""
    df = ds.to_dataframe().reset_index()
    df = df.rename(columns={"LATITUDE": "lat", "LONGITUDE": "lon", "TIME": "date",
                            "PRES": "pres", "TEMP": "temp"})
    # keep only good-QC temperature/pressure measurements
    for qc in ("TEMP_QC", "PRES_QC", "POSITION_QC"):
        if qc in df.columns:
            df = df[df[qc].isin(GOOD_QC)]
    df = df.dropna(subset=["pres", "temp", "lat", "lon", "date"])

    keys = [k for k in ["PLATFORM_NUMBER", "CYCLE_NUMBER"] if k in df.columns]
    groups = df.groupby(keys) if keys else [(0, df)]

    rows: list[tuple] = []
    max_d = float(max(config.DEPTHS))
    for _, prof in groups:
        prof = prof.sort_values("pres")
        p, t = prof["pres"].to_numpy(float), prof["temp"].to_numpy(float)
        if len(p) < 3 or p.min() > 20.0:      # need a real profile that reaches near-surface
            continue
        # only interpolate within the profile's own sampled range (no extrapolation)
        temps = np.interp(config.DEPTHS, p, t, left=np.nan, right=np.nan)
        temps[np.asarray(config.DEPTHS, float) > p.max()] = np.nan
        if np.isnan(temps).all():
            continue
        lat, lon = float(prof["lat"].iloc[0]), float(prof["lon"].iloc[0])
        date = pd.to_datetime(prof["date"].iloc[0])
        for di, v in enumerate(temps):
            if not np.isnan(v):
                rows.append((lat, lon, date, di, float(v)))
    return rows


def download(year: int = config.TEST_YEARS[0], out_noext: str | None = None, src: str = "erddap") -> str:
    """Fetch REAL Argo profiles in the NIO box for `year`, interpolate to config.DEPTHS, and write
    a long table [lat, lon, date, depth_idx, temp] to artifacts/argo_test.{parquet|csv}.

    Downloads month-by-month so one slow request cannot kill the whole job.
    """
    from argopy import DataFetcher  # imported here so the repo imports without argopy installed
    r = config.REGION
    rows: list[tuple] = []
    months = pd.date_range(f"{year}-01-01", f"{year}-12-01", freq="MS")
    for m in months:
        nxt = m + pd.offsets.MonthBegin(1)
        box = [r["lon_min"], r["lon_max"], r["lat_min"], r["lat_max"],
               0.0, max(config.DEPTHS) + 50.0, m.strftime("%Y-%m"), nxt.strftime("%Y-%m")]
        try:
            ds = DataFetcher(src=src, ds="phy").region(box).load().data
            got = _profiles_to_rows(ds)
            rows.extend(got)
            print(f"[argo] {m:%Y-%m}: {len(got):6d} rows  (total {len(rows)})")
        except Exception as e:  # a bad month must not kill the year
            print(f"[argo] {m:%Y-%m}: FAILED ({type(e).__name__}: {str(e)[:80]})")

    out = pd.DataFrame(rows, columns=["lat", "lon", "date", "depth_idx", "temp"])
    path = io.save_table(out, out_noext or config.art("argo_test"))
    n_prof = out.groupby(["lat", "lon", "date"]).ngroups if len(out) else 0
    print(f"[argo] wrote {len(out)} rows from ~{n_prof} profiles to {path}")
    return path


if __name__ == "__main__":
    download()
