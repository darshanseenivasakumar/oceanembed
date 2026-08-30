"""Freeze the T_SEQ ablation result into a TRACKED artifact so it survives one laptop.

All three legs ran on Arjhun's machine against the daily bundle. Every leg's checkpoint and
metrics JSON is gitignored, and each leg OVERWRITES the previous leg's pair -- so by the time the
sweep finished, the only surviving record of legs 1 and 11 was a table in AGENT_SYNC prose, and
the T_SEQ=11 checkpoint (the winner) had already been overwritten by the T_SEQ=31 run.

That is the failure this script exists to stop. It writes artifacts/tseq_ablation.json, which is
committed with `git add -f`, so the decision the other machine has to make is auditable there
rather than re-derivable only by spending 2.5 h of CPU it does not have.

PROVENANCE IS PER-LEG AND EXPLICIT. Leg 31 is read out of the metrics JSON on disk; legs 1 and 11
are DECLARED from the AGENT_SYNC table because their JSONs were overwritten. Every leg carries a
`source` field saying which it is. Nothing here is presented as measured by this script.

    PYTHONPATH=src python scripts/phase2/record_tseq_ablation.py [--check]

--check re-reads the artifact and the live metrics JSON and fails if leg 31 has drifted, so a
later retrain cannot silently invalidate the record.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from oceanembed import config  # noqa: E402

OUT = config.art("tseq_ablation.json")
LIVE = config.art("tscast_stage1_metrics.json")

# Legs 1 and 11: their metrics JSONs were overwritten by the next leg. These are the numbers as
# recorded in docs/phase2/AGENT_SYNC.md 2026-08-29 section 5, which is the only surviving record.
DECLARED = {
    1:  dict(rmse=0.9096, bias=+0.170, correlation=0.894, skill_rmse_ratio=0.258, best_epoch=7),
    11: dict(rmse=0.8529, bias=+0.036, correlation=0.889, skill_rmse_ratio=0.304, best_epoch=2),
}
DECLARED_SOURCE = "docs/phase2/AGENT_SYNC.md 2026-08-29 section 5 (leg JSON overwritten by the next leg)"

# The tie-break in scripts/phase2/pick_tseq_and_retrain.py: prefer the shorter window under this.
TIE_BREAK_DEGC = 0.02


def read_live_leg() -> dict:
    """Read the leg whose metrics JSON is still on disk. Refuse if it is not a daily leg."""
    if not os.path.exists(LIVE):
        sys.exit(f"{LIVE} is absent -- nothing to read. Run a leg first, or pass every leg as "
                 f"declared and say so.")
    d = json.load(open(LIVE, encoding="utf-8"))
    if d.get("data") != "daily":
        sys.exit(f"{LIVE} reports data={d.get('data')!r}, not 'daily'. A monthly run is not part "
                 f"of this sweep and must not be recorded as one.")
    m = d["metrics"]["overall"]
    return dict(
        t_seq=int(d["T_SEQ"]),
        rmse=round(m["rmse"], 4),
        bias=round(m["bias"], 4),
        correlation=round(m["correlation"], 4),          # per-depth mean, never the pooled figure
        skill_rmse_ratio=round(m["skill_rmse_ratio"], 4),
        skill_vs_climatology=round(m["skill_vs_climatology"], 4),
        best_epoch=d["best_epoch"],
        epochs_run=d["epochs_run"],
        train_samples=d["train_samples"],
        train_seconds=d["train_seconds"],
        argo_profiles=d["argo_profiles"],
        n_depth_comparisons=m["n"],
        calibration=d.get("calibration"),
        code_commit=d.get("code_commit"),
    )


def build() -> dict:
    live = read_live_leg()
    legs = {}
    for t, v in DECLARED.items():
        legs[str(t)] = dict(v, t_seq=t, source="declared", source_detail=DECLARED_SOURCE)
    legs[str(live["t_seq"])] = dict(live, source="measured",
                                    source_detail=f"read from {os.path.basename(LIVE)} on disk")

    ranked = sorted(legs.values(), key=lambda r: r["rmse"])
    win, second = ranked[0], ranked[1]
    margin = round(second["rmse"] - win["rmse"], 4)
    chosen = win["t_seq"]
    rule = (f"lowest independent-Argo RMSE; margin {margin:.4f} degC over T_SEQ={second['t_seq']} "
            f"exceeds the {TIE_BREAK_DEGC} tie-break, so the shorter-window preference did not "
            f"apply")
    if margin < TIE_BREAK_DEGC and win["t_seq"] > second["t_seq"]:
        chosen = second["t_seq"]
        rule = (f"margin {margin:.4f} degC is under the {TIE_BREAK_DEGC} tie-break, so the SHORTER "
                f"window T_SEQ={chosen} is taken over the nominally-lower T_SEQ={win['t_seq']}")

    return {
        "what": "T_SEQ ablation on the daily bundle: how many days of surface context the encoder "
                "sees around the target date.",
        "legs": legs,
        "chosen_t_seq": chosen,
        "selection_rule": rule,
        "ranking": [r["t_seq"] for r in ranked],
        "comparability": {
            "held_constant": "seed 42, decoder simple, loss beta-NLL 0.5, 40,000 train samples, "
                             "cnn3d encoder, same daily bundle, same 962 independent Argo profiles "
                             "at max 5 days offset",
            "channels": 5,
            "channels_note": "sst, sss, ssh, u, v. No wind -- PS requirement 8 was still at 0% when "
                             "every leg ran. A 7-channel leg would not be comparable to these.",
            "caveat": "AGENT_SYNC states legs 1 and 11 held seed/samples/decoder/loss identical but "
                      "never records their --epochs/--patience. If those differed from leg 31's "
                      "15/4, the sweep is not perfectly matched and that must be said.",
        },
        "finding": "The paper's 31-day window is the WORST of the three at our data scale -- worse "
                   "even than no window at all -- and carries the largest warm bias. TS-Cast used "
                   "+/-15 days on 1/8 deg NW Pacific data with ~155k in-situ profiles; at our "
                   "sample budget +/-5 days wins. This is a measured disagreement with the paper, "
                   "not a reimplementation failure, and it should be reported as one.",
        "warning": "artifacts/tscast_stage1.pt is the T_SEQ=31 model -- the WORST leg. Each leg "
                   "overwrote the last, so the winning T_SEQ=11 checkpoint no longer exists and "
                   "must be regenerated by the final retrain before anything ships.",
        "provenance": {
            "declared_source": DECLARED_SOURCE,
            "measured_from": os.path.basename(LIVE),
            "written_by": "scripts/phase2/record_tseq_ablation.py",
            "tracked": "committed with `git add -f` because /artifacts/* is gitignored and this "
                       "result must reach the other machine",
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify the recorded measured leg still matches the metrics JSON on disk")
    a = ap.parse_args()

    if a.check:
        if not os.path.exists(OUT):
            sys.exit(f"{OUT} does not exist yet -- run without --check first.")
        rec = json.load(open(OUT, encoding="utf-8"))
        live = read_live_leg()
        got = rec["legs"].get(str(live["t_seq"]))
        if got is None:
            sys.exit(f"the metrics JSON now describes T_SEQ={live['t_seq']}, which is not in the "
                     f"recorded ablation. A new leg ran -- re-record it deliberately.")
        if abs(got["rmse"] - live["rmse"]) > 1e-4:
            sys.exit(f"DRIFT: recorded T_SEQ={live['t_seq']} rmse={got['rmse']} but the metrics "
                     f"JSON now reads {live['rmse']}. Something retrained over it. Re-record, and "
                     f"do not quote the old number.")
        print(f"OK  T_SEQ={live['t_seq']} still reads rmse={live['rmse']:.4f} in both places.")
        return

    rec = build()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)

    print(f"wrote {OUT}\n")
    print(f"{'T_SEQ':>6} {'RMSE':>8} {'bias':>8} {'corr':>7} {'skill_r':>8}  source")
    for t in sorted(rec["legs"], key=int):
        L = rec["legs"][t]
        print(f"{L['t_seq']:6d} {L['rmse']:8.4f} {L['bias']:+8.4f} {L['correlation']:7.3f} "
              f"{L['skill_rmse_ratio']:8.4f}  {L['source']}")
    print(f"\nCHOSEN: T_SEQ={rec['chosen_t_seq']}\n  {rec['selection_rule']}")
    print(f"\n{rec['warning']}")


if __name__ == "__main__":
    main()
