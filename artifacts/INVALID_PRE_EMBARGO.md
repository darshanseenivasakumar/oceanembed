# INVALID — produced before the temporal embargo fix

Commit `1d3c135` (2026-09-02) fixed `dataset._window()`, which clamped the input window to the
array ends instead of to the train/test split. At T_SEQ=11, **5 of 304 train days
(2026-03-27..31, 1.64%) read test-period surface fields.**

Everything in this list predates that fix and is **INVALID. Do not quote, do not ship, do not
compare against.** Kept as historical evidence — never delete.

    tscast_stage1_withUV_s42.pt          rmse 0.8611  (7 ch, T_SEQ=11, seed 42)
    tscast_stage1_withUV_s42_metrics.json
    tscast_stage1_noUV_s42.pt            rmse 0.9024  (5 ch matched control)
    tscast_stage1_noUV_s42_metrics.json
    tscast_stage1_tseq31.pt              (T_SEQ=31, 5 ch)
    tscast_stage1_metrics_tseq31.json    rmse 0.9267
    _stale_pre401e67b/tscast_stage1.pt   (also self-contradictory metadata)
    _stale_pre401e67b/tscast_stage1_metrics.json

The wind result derived from the first two (−0.0149 °C) is **not established**: both legs are
leaky, and the effect already flipped sign under one retrain. Re-measure across >=3 seeds.

Replacement runs carry the tag `embargo_*`.
