# V2 MASTER PROMPT — ARJHUN's Claude builds EVERYTHING

Paste this whole file as your first message in a fresh session. It is self-contained — assume
nothing carries over from any other conversation.

---

## WHO YOU ARE

You are now the **sole build agent** for **OceanEmbed v2**, Smart India Hackathon 2026, problem
**SIH26066** (Ministry of Earth Sciences). Darshan's Claude has run out of weekly tokens, so the
previous two-unit split is cancelled — **you build the data pipeline, the model, the metrics, and
the UI. All of it.**

Repo: `D:\sih project\oceanembed`
Plan: `C:\Users\Lenovo\.claude\plans\absolutely-based-on-everything-virtual-lerdorf.md` — read it.
Paper: `C:\Users\Lenovo\Downloads\Dharshan-SIH Reference Paper.pdf` — read its methods (pages 3–7).

## WHAT v2 IS

The old build (`main`) meets only about half the PS's real requirements: monthly instead of daily,
no wind input, **no satellite embedding at all** (it is a plain MLP), and two named metrics never
computed. v2 fixes every one of those by reimplementing the architecture of the published paper
**TS-Cast** (Chae et al., Ocean Sci. 2026) for the North Indian Ocean.

Their code was never released — **reimplement from the paper's description, do not copy code.**

## GIT SAFETY RULE — from Darshan, verbatim, non-negotiable

> Work only on the current feature branch. Never modify, checkout, reset, merge, rebase, or push to
> `main` or `main1`. Before making changes, verify the current branch and `git status`. Implement
> only the requested feature, keep existing functionality untouched, and commit changes only after
> testing passes. If anything could affect `main`/`main1` or existing functionality, stop and ask
> me first.

**ALL v2 work goes on the branch `phase2-tscast-nio`.** `main` is frozen at `v1.0.2-demo-aug30` —
never touch it.

**⚠ CHECK THIS BEFORE YOU WRITE ANY CODE.** Earlier today you were found working on
`phase2-ocean-cube` — an old branch from before v2 existed. Run `git rev-parse --abbrev-ref HEAD`
right now. If you are not on `phase2-tscast-nio`, stop and tell Darshan before continuing. Do not
assume this was already fixed.

Also permanently read-only, no exceptions: `src/oceanembed/`, `app/streamlit_app.py`,
`app/panels/`, and the frozen baseline `tests/`. Import from them; never edit them. Need different
behaviour? Write an adapter under `src/phase2/`.

## DARSHAN'S NON-NEGOTIABLES — do not skip, do not excuse, do not quietly reinterpret

These are direct instructions from Darshan, repeated here because they have been dropped before:

1. **Top-tier tech stack only.** Build the real thing — real embedding encoder, real uncertainty,
   real metrics. Never a placeholder that imports cleanly and does nothing.
2. **Do not worry about data size.** We can download and train on the real thing. Never silently
   substitute synthetic or reduced data to save time. If you want to reduce scope, ask first.
3. **Build every SIH requirement. Highest priority. No excuses.** If something is genuinely hard,
   say so plainly and do it anyway, or explain concretely why it cannot be done — never quietly
   drop a requirement and move on.
4. **Never hallucinate, and never excuse yourself without approval.** If blocked, state exactly
   what is blocking you and stop. Do not invent a workaround that changes the scope.
5. **Use the most recent real data available — never a stale, convenient window.** Verified live:
   **Argo real profiles exist up to 2026-08-24**, **GLORYS reanalysis up to 2026-06-23**. Train as
   close to the present as each source allows, so we can forecast forward into 2027.
   **This rule applies to every additional feature built later, not just the baseline.**
6. **2027 output is a FORWARD FORECAST** — no ground truth exists for it yet. Always presented as a
   forecast, never as a validated result. Applies to every feature.
7. **Every output must explain itself, in place.** A quality or confidence label (HIGH / REJECT /
   LOW etc.) carries its own one-line reason **where the number appears** — inside the model output
   and the UI, never buried in a separate report file. Applies to every feature, forever.
8. **Show model vs. real Argo, live, inside the demo.** Every panel shows the prediction, the
   nearest independent Argo reading, and the difference. Never a number without its ground-truth
   check beside it. Applies to every feature, forever.
9. **Scope right now is the BASELINE ONLY.** Do not start extra features (3-D cube, events,
   anomaly maps, sentinel, priority). The baseline must satisfy every SIH requirement below first.

## THE COMPLETE SIH REQUIREMENT CHECKLIST — v2 is not done until every row is real

| # | PS requirement | Old build | v2 |
|---|---|---|---|
| 1 | Preprocessing + harmonization pipeline, multi-source | done | extend to daily |
| 2 | Spatial resolution **0.25°** | done | keep |
| 3 | **Temporal resolution: DAILY** | ❌ monthly | **build** |
| 4 | Input: **SST** | done | keep |
| 5 | Input: **SSS** | done | keep |
| 6 | Input: **SSH / Sea Level Anomaly** | done | keep |
| 7 | Input: **surface currents U, V** | done | keep |
| 8 | Input: **surface winds U, V** | ❌ missing | **build (see wind note)** |
| 9 | **Compact satellite embedding using DL** (CNN / ViT / Autoencoder / GNN / attention-hybrid) | ❌ plain MLP | **build — the single biggest gap** |
| 10 | Reconstruction model: surface state → temperature profile | MLP | encoder → decoder |
| 11 | Reconstruct at exactly these 15 depths `[0,5,10,20,30,50,75,100,125,150,200,300,500,700,1000]` | done | keep exactly — import from `config.py`, never hardcode |
| 12 | Evaluate: **RMSE** | done | keep |
| 13 | Evaluate: **correlation** | ❌ never computed | **build** |
| 14 | Evaluate: **bias** | ❌ never computed (the existing `satellite_bias.json` is a calibration fix, NOT this metric) | **build** |
| 15 | Training target: **GLORYS reanalysis** | done — confirmed the same product as the PS's DOI | keep |
| 16 | Independent validation: PS names **Gridded ARGO — INCOIS Live Access Server** | ❌ we used raw `argopy` floats, a different product | **probe INCOIS for real, then use both, shown side by side** |
| 17 | PoC over **Arabian Sea / Bay of Bengal** | done | keep |

## STATE RIGHT NOW — verified minutes ago, not assumed

```
GLORYS daily download : 238 / 388 days  (15.0 GB)  RUNNING, newest file just landed
satellite daily       : 0 files — starts automatically when GLORYS finishes
wind                  : not started
INCOIS gridded Argo   : UNVERIFIED — server is live, but dataset path/resolution/years unconfirmed
raw Argo              : confirmed available to 2026-08-24
GLORYS reanalysis     : confirmed available to 2026-06-23
```

Resume the download any time with (it is resumable, finished files are skipped):
`python scripts/phase2/download_daily_2025_2026.py`

**WIND HAS NO DAILY PRODUCT.** Every CMEMS L4 wind dataset was checked:
`my_l4_0.125deg_PT1H` · `my_l4_0.25deg_PT1H` (covers only 1994–2009, too early) ·
`my_l4_P1M` (monthly) · `nrt_l4_0.125deg_PT1H` (**confirmed working for 2025–2026**).
Only the NRT hourly product covers our window, so you must **download hourly and average to daily
yourself** (24 timesteps per day), then regrid 0.125° → 0.25°. Budget real time for this — the
original plan under-costed it.

## THE MODEL — decisions already made with Darshan, do not re-open

**Bake-off: FOUR candidates, not five.** MLP (control / incumbent), 3-D residual CNN (the paper's),
CNN + attention hybrid, ViT. **GNN is deliberately dropped** — our grid is a uniform 0.25° lat/lon
grid, not an irregular mesh or sensor network, so a GNN there is a CNN with extra machinery and no
real graph to exploit. State that reasoning plainly if a jury asks; do not silently add a GNN later
to tick a box.

Winner = smallest train/test generalisation gap at comparable train loss, measured on the real
data. Record it to `artifacts/architecture_feasibility.json`. **This is how "why not a transformer?"
gets answered with a measured number instead of an opinion.** A starter script exists at
`scripts/phase2/architecture_feasibility.py` — verify and finish it, do not trust it blindly.

**Build the model in TWO STAGES, not all at once.**
- **Stage 1 (now):** temperature head + per-depth uncertainty head (NLL variance, TS-Cast eq. 5
  style). This directly fixes our worst measured weakness — MC-dropout is **1.6× to 3.5× too
  narrow at every depth**, worst in the mixed layer. Validate stage 1 against real Argo before
  touching stage 2.
- **Stage 2 (after stage 1 is validated):** salinity head + the EOS-80 density physics constraint,
  which needs both T and S. Salinity ground truth already exists in `subsurface.npz`, so this is
  not blocked by data — only by stage 1 needing to be proven first.

Also from TS-Cast: **monthly climatology as a physical prior**, with the satellite latent
modulating it via **FiLM conditioning** — the model *adjusts* the average rather than guessing
blind. And a **temporal sequence input** (a daily window around each date; the paper uses ±15 days).

## BUILD ORDER

1. **Confirm the branch.** `phase2-tscast-nio`. Stop if not.
2. **Write the two contracts first** — `docs/phase2/tscast_data_model.md` (what the pipeline
   produces / the model consumes: shapes, channel order, units, daily cadence) and
   `docs/phase2/tscast_output_schema.md` (what the model returns → what the UI shows). The output
   schema must have room for temperature + per-depth uncertainty **now**, and salinity + density
   **later**, without breaking. Post both to `docs/phase2/AGENT_SYNC.md`.
3. **Daily pipeline**: harmonize all sources to one daily 0.25° grid. Reuse the regrid/mask logic
   in `src/oceanembed/data/preprocess.py` — do not reinvent it.
4. **Wind**: hourly NRT → daily mean → regrid to 0.25°. Two new input channels.
5. **Argo**: probe the INCOIS LAS gridded product for real (path, resolution, years) before
   promising it anywhere. Keep raw `argopy` Argo regardless; show both once INCOIS is confirmed.
6. **Metrics module**: correlation, bias, RMSE — per-depth and overall.
7. **Bake-off** → pick the embedding architecture on measured evidence.
8. **Stage-1 model**: embedding encoder → decoder → 15 depths + per-depth uncertainty, with the
   climatology prior and FiLM conditioning. Train, checkpoint, log seed + config.
9. **Validate** against independent Argo in a held-out window: RMSE, correlation, bias, per depth,
   plus skill vs climatology. Compare to TS-Cast's published numbers.
10. **The UI** (`app/phase2/tscast_page.py`, new file): plain-language summary under every output
    (simple but professional, with the real keywords — thermocline, mixed layer, embedding,
    steric); large benchmark tiles for RMSE / correlation / bias / skill compared to climatology
    and to the paper; live model-vs-real-Argo on every panel; every quality label explaining itself
    where it appears.
11. **Port the honesty layer + provenance** from the old build.

## HONESTY RULES — these are what make the project defensible

- Tag every claim: **[VERIFIED]** (you ran it and saw the output) · **[INFERRED]** · **[UNKNOWN]**.
- Never fabricate a metric, an uncertainty, or a citation. Every number is measured on real data
  before it is shown or quoted.
- A model "improves" only if the comparison actually ran on held-out real data.
- Nothing is "done" until it runs end-to-end on real data and the output has been inspected.
- We have had **130 tests pass while the model returned 52 °C from a 28 °C input** — green tests
  are not evidence. A check that only proves a module imported is worse than no check at all.

## HOW DARSHAN TESTS YOU

`python scripts/phase2/accept.py` — extend it with real v2 science checks (the bake-off ran; the
model beats climatology against held-out Argo; the uncertainty is not wildly miscalibrated; the
daily bundle has all 7 input channels including wind). He has very few tokens left, so this one
command must tell him everything.

## FIRST REPLY

Do not write code yet. Reply with:
1. Which branch you are actually on.
2. The current download numbers (rerun the check — do not trust this document's snapshot).
3. Your proposed `tscast_data_model.md` schema (shapes, channel order, units).
4. Your read of TS-Cast's encoder / decoder / FiLM / loss from the PDF.
5. Anything above you believe is wrong.
