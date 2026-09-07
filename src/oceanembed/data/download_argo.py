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
from phase2.data.argo_depth import depth_from_pressure


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


def _profiles_to_rows(ds, with_salinity: bool = False) -> list[tuple]:
    """argopy N_POINTS dataset -> long rows [lat, lon, date, depth_idx, temp], QC-filtered + interpolated.

    with_salinity=True appends a `psal` column (PSS-78) for TS-Cast stage 2. It is OFF by default
    so the table underwriting every published temperature number keeps its exact schema.

    Salinity is added WITHOUT disturbing a single temperature row. PSAL QC is applied by masking
    the salinity VALUE, never by dropping the row, and salinity is interpolated on its own finite
    samples. A float that reported good temperature and bad salinity therefore still contributes
    its temperature, exactly as before, and simply carries NaN salinity.
    """
    df = ds.to_dataframe().reset_index()
    df = df.rename(columns={"LATITUDE": "lat", "LONGITUDE": "lon", "TIME": "date",
                            "PRES": "pres", "TEMP": "temp", "PSAL": "psal"})
    # keep only good-QC temperature/pressure measurements
    for qc in ("TEMP_QC", "PRES_QC", "POSITION_QC"):
        if qc in df.columns:
            df = df[df[qc].isin(GOOD_QC)]
    if with_salinity:
        if "psal" not in df.columns:
            raise KeyError("PSAL is absent from this argopy dataset; cannot build a salinity "
                           "table. Do not substitute reanalysis salinity for an observation.")
        if "PSAL_QC" in df.columns:                    # mask the value, never drop the row
            df.loc[~df["PSAL_QC"].isin(GOOD_QC), "psal"] = np.nan
    df = df.dropna(subset=["pres", "temp", "lat", "lon", "date"])

    keys = [k for k in ["PLATFORM_NUMBER", "CYCLE_NUMBER"] if k in df.columns]
    groups = df.groupby(keys) if keys else [(0, df)]

    rows: list[tuple] = []
    max_d = float(max(config.DEPTHS))
    for _, prof in groups:
        prof = prof.sort_values("pres")
        lat, lon = float(prof["lat"].iloc[0]), float(prof["lon"].iloc[0])
        # Argo reports PRESSURE in dbar. config.DEPTHS is METRES. Until 2026-09-07 the two were
        # interpolated against each other directly, which sampled every float ~1% too shallow --
        # 0.6 m at 100 m, 8 m at 1000 m -- and in a thermocline that is a tenth of a degree
        # charged to the model. Convert first (UNESCO 1983; see phase2.data.argo_depth).
        p = depth_from_pressure(prof["pres"].to_numpy(float), lat)
        t = prof["temp"].to_numpy(float)
        if len(p) < 3 or p.min() > 20.0:      # need a real profile that reaches near-surface
            continue
        # only interpolate within the profile's own sampled range (no extrapolation)
        temps = np.interp(config.DEPTHS, p, t, left=np.nan, right=np.nan)
        temps[np.asarray(config.DEPTHS, float) > p.max()] = np.nan
        if np.isnan(temps).all():
            continue
        date = pd.to_datetime(prof["date"].iloc[0])

        if not with_salinity:
            for di, v in enumerate(temps):
                if not np.isnan(v):
                    rows.append((lat, lon, date, di, float(v)))
            continue

        # Salinity on its OWN finite samples and its own sampled range -- a float whose salinity
        # sensor stopped shallower than its thermistor must not have salinity extrapolated down
        # to match the temperature profile's depth.
        sp = prof["psal"].to_numpy(float)
        ok = np.isfinite(sp) & np.isfinite(p)
        if ok.sum() >= 3:
            sals = np.interp(config.DEPTHS, p[ok], sp[ok], left=np.nan, right=np.nan)
            sals[np.asarray(config.DEPTHS, float) > p[ok].max()] = np.nan
        else:
            sals = np.full(len(config.DEPTHS), np.nan)
        for di, (v, sv) in enumerate(zip(temps, sals)):
            if not np.isnan(v):
                rows.append((lat, lon, date, di, float(v), float(sv)))
    return rows


def _dedupe_rows(out: pd.DataFrame, key=("lat", "lon", "date", "depth_idx")) -> pd.DataFrame:
    """Drop rows ERDDAP returned twice, and refuse to hide a real conflict.

    At least one Arabian Sea float comes back duplicated for every one of its ~10-day cycles:
    40 profiles, 559 (lat, lon, date, depth_idx) keys, byte-identical in temp AND psal. The
    scoring path pivots with aggfunc="mean", so mean(x, x) = x and no published number was ever
    affected -- but the profile count is inflated, and any future consumer that does not pivot
    would double-weight that float.

    Only EXACT duplicates are dropped, so nothing is chosen between. If two rows share the key
    but disagree on a value, that is a different and worse problem -- the pivot would silently
    average two distinct measurements into one -- so it is reported rather than swallowed.
    """
    key = list(key)
    before = len(out)
    out = out.drop_duplicates()
    dropped = before - len(out)

    conflicts = out.duplicated(subset=key, keep=False)
    if conflicts.any():
        n_keys = out.loc[conflicts, key].drop_duplicates().shape[0]
        print(f"[argo] WARNING: {int(conflicts.sum())} rows across {n_keys} keys share "
              f"(lat, lon, date, depth_idx) but DISAGREE on their values. These are not "
              f"redundant records and are NOT removed; pivot_profiles will average them. "
              f"Inspect before quoting any number that rests on them.")
    if dropped:
        print(f"[argo] removed {dropped} exactly-duplicated rows returned by the source")
    return out


def download(year: int = config.TEST_YEARS[0], out_noext: str | None = None, src: str = "erddap",
             with_salinity: bool = False) -> str:
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
            got = _profiles_to_rows(ds, with_salinity=with_salinity)
            rows.extend(got)
            print(f"[argo] {m:%Y-%m}: {len(got):6d} rows  (total {len(rows)})")
        except Exception as e:  # a bad month must not kill the year
            print(f"[argo] {m:%Y-%m}: FAILED ({type(e).__name__}: {str(e)[:80]})")

    cols = ["lat", "lon", "date", "depth_idx", "temp"] + (["psal"] if with_salinity else [])
    out = _dedupe_rows(pd.DataFrame(rows, columns=cols))
    path = io.save_table(out, out_noext or config.art("argo_test"))
    n_prof = out.groupby(["lat", "lon", "date"]).ngroups if len(out) else 0
    print(f"[argo] wrote {len(out)} rows from ~{n_prof} profiles to {path}")
    return path


if __name__ == "__main__":
    download()
