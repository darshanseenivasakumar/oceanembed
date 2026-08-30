#!/bin/sh
# Phase 4: the final stage-1 model, plus the matched 5-channel leg that makes the wind
# comparison mean something. Same T_SEQ, same samples, same epochs, same seed -- the ONLY
# difference between the two runs is whether channels 6-7 exist.
set -x
COMMON="--data daily --t-seq 11 --decoder simple --loss nll --epochs 25 --train-samples 60000 --test-samples 12000 --patience 5"
echo "===== RUN A: 7 CHANNELS (wind included) ====="
PYTHONPATH=src python -m phase2.tscast_nio.train.train_stage1 $COMMON --tag 7ch
echo "===== RUN B: 5 CHANNELS (matched, wind absent) ====="
PYTHONPATH=src python -m phase2.tscast_nio.train.train_stage1 $COMMON --tag 5ch --daily-dir data/processed/daily_5ch
echo "===== PHASE 4 COMPLETE ====="
