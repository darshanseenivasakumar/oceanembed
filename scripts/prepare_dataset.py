"""One command to (re)build the full training artifacts.

- If real GLORYS NetCDF exists in data/raw/, uses it.
- Otherwise generates a SYNTHETIC GLORYS file (fake values, real shapes) so A and C can develop on
  full-size, correctly-shaped X_train/y_train/... without CMEMS credentials.

Run:  python scripts/prepare_dataset.py            # synthetic if no real data
      python scripts/prepare_dataset.py --real     # require real GLORYS in data/raw/
Owner: Unit B (Darshan).
"""
from __future__ import annotations
import glob, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from oceanembed import config  # noqa: E402
from oceanembed.data import preprocess  # noqa: E402
from oceanembed.features import build_samples  # noqa: E402


def main(require_real: bool = False) -> None:
    real = glob.glob(os.path.join(config.DATA_RAW, "glorys_*.nc"))
    if real:
        print(f"[prepare] using {len(real)} REAL GLORYS file(s)")
    elif require_real:
        raise SystemExit("--real given but no glorys_*.nc in data/raw/ (run download_glorys first)")
    else:
        print("[prepare] no real data -> generating synthetic GLORYS (fake values, real shapes)")
        from make_synthetic_glorys import main as make_syn  # type: ignore
        sys.path.insert(0, os.path.dirname(__file__))
        make_syn()

    processed = preprocess.run()
    build_samples.run(processed)
    print("[prepare] done -> artifacts/X_train,y_train,X_test,y_test,meta_*,norm_stats.json,land_mask.npy")


if __name__ == "__main__":
    main(require_real="--real" in sys.argv)
