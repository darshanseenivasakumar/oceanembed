"""Measure what an export actually costs, so the number can be quoted. (Unit A / Arjhun.)

    PYTHONPATH=src python scripts/phase2/measure_export_timing.py

WHY
`field.py` said "seconds on the GPU, under a minute on CPU" -- an estimate sitting where a reader
takes it for a cost figure. Under this project's own evidence rule that is [INFERRED] presented as
fact, and it is the kind of number a jury asks about directly. No inference runtime was recorded
anywhere in the repo before this.

WHAT IS MEASURED SEPARATELY, AND WHY IT MATTERS
  predictor_load  paid ONCE at server start (the bundle npz is ~485 MB). Blending it into a
                  per-request figure would misrepresent the API's latency by an order of magnitude.
  predict_field   the per-request cost. Reported as median/min/max over several runs, with run 1
                  called out separately -- the first call pays lazy imports and allocation, and
                  averaging it in reports a cost no subsequent user experiences.
  build + write   turning the field into a Dataset and a file.

A TIMING WITHOUT A MACHINE IS NOT A MEASUREMENT, so the host, device, torch version and batch size
are recorded beside the numbers. `perf_counter` rather than the repo's usual `time.time()`: it is
monotonic, which is the correct clock for a duration.
"""
from __future__ import annotations

import json
import os
import platform
import statistics as st
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config as base                  # noqa: E402
from phase2.export import netcdf as X                  # noqa: E402
from phase2.tscast_nio import provenance as P          # noqa: E402

OUT = base.art("export_timing.json")
DATE = "2026-05-15"
N_RUNS = 4


def main() -> int:
    import torch
    from phase2.tscast_nio.field import predict_field
    from phase2.tscast_nio.inference import TSCastPredictor

    print(f"measuring on {DATE}, {N_RUNS} runs\n")

    t0 = time.perf_counter()
    predictor = TSCastPredictor()
    load_s = time.perf_counter() - t0
    print(f"  predictor load        {load_s:7.2f}s   (paid once, at server start)")

    runs = []
    field = None
    for i in range(N_RUNS):
        t0 = time.perf_counter()
        field = predict_field(predictor, DATE)
        dt = time.perf_counter() - t0
        runs.append(dt)
        print(f"  predict_field run {i + 1}   {dt:7.2f}s" + ("   <- cold" if i == 0 else ""))

    warm = runs[1:] or runs
    t0 = time.perf_counter()
    ds = X.field_to_xarray(field)
    build_s = time.perf_counter() - t0

    tmp = base.art("_timing_probe.nc")
    t0 = time.perf_counter()
    X.write_netcdf(ds, tmp)
    write_s = time.perf_counter() - t0
    nbytes = os.path.getsize(tmp)
    os.remove(tmp)

    dev = next(predictor.model.parameters()).device
    out = {
        "what": "measured cost of one whole-field reconstruction and its NetCDF export",
        "date": DATE,
        "n_cells": field["provenance"].get("n_cells"),
        "batch_size": 512,
        "predictor_load_seconds": round(load_s, 2),
        "predict_field": {
            "cold_seconds": round(runs[0], 2),
            "warm_median_seconds": round(st.median(warm), 2),
            "warm_min_seconds": round(min(warm), 2),
            "warm_max_seconds": round(max(warm), 2),
            "n_runs": len(runs),
            "note": ("run 1 is reported separately, not averaged in: it pays lazy imports and "
                     "allocation costs no later request experiences."),
        },
        "build_dataset_seconds": round(build_s, 2),
        "write_netcdf_seconds": round(write_s, 2),
        "file_bytes": nbytes,
        "total_cold_seconds": round(load_s + runs[0] + build_s + write_s, 2),
        "total_warm_seconds": round(st.median(warm) + build_s + write_s, 2),
        # A timing without a machine is not a measurement.
        "host": {
            "processor": platform.processor() or "unknown",
            "platform": platform.platform(),
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda_available": bool(torch.cuda.is_available()),
            "device_used": str(dev),
            "gpu": (torch.cuda.get_device_name(0) if torch.cuda.is_available() else None),
        },
        "code_commit": P.code_commit(),
        "code_dirty": P.code_dirty(),
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, allow_nan=False)

    print(f"\n  build dataset         {build_s:7.2f}s")
    print(f"  write netcdf          {write_s:7.2f}s   ({nbytes / 1e6:.2f} MB)")
    print(f"\n  TOTAL cold (script)   {out['total_cold_seconds']:7.2f}s")
    print(f"  TOTAL warm (API)      {out['total_warm_seconds']:7.2f}s")
    print(f"\n  wrote {os.path.relpath(OUT, base.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
