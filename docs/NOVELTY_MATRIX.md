# NOVELTY_MATRIX.md  (Owner: Unit C — Mitun+Niru)

Brutally honest. Never say "nobody has done this" without evidence (`docs/LITERATURE_MATRIX.md`).

**Provenance:** every citation below is `[ABSTRACT-ONLY]` — compiled from published abstracts and
landing pages fetched online. No methods section has been read (the PDFs are not on the build
machine). Enough to position ourselves; **not** enough to assert what a paper did *not* do.

---

## The matrix

| Idea | Bucket | Evidence |
|---|---|---|
| AI reconstructs subsurface temperature from surface | **NOT NOVEL** | Meng 2021; DORS 2022; FFPG-net 2025; TS-Cast 2026; NeSPReSO 2025 |
| 3D reconstruction at 0.25° with anomalies | **ALREADY DONE** | Meng 2021 (1° and 1/4°, 26 levels to 2000 m) |
| Uncertainty-aware reconstruction | **ALREADY DONE, and better than ours** | TS-Cast 2026 predicts depth-dependent log error **variances** for T, S and density — parametric and calibrated. Ours is MC-dropout, and D-016 measured it as overconfident at depth. |
| Physics-guided reconstruction | **ALREADY DONE** | FFPG-net 2025 (EOF vertical modes); TS-Cast 2026 (seawater equation of state) |
| ConvLSTM / spatiotemporal | **ALREADY DONE** | DORS 2022 (global, 0–2000 m, 1993–2020) |
| Anomaly product from reconstruction | **ALREADY DONE** | Meng 2021 targets subsurface **anomalies** directly |
| Benchmarking against classical baselines | **ALREADY DONE** | NeSPReSO 2025 beats GEM, MLR, ISOP — a stronger bar than our climatology + LightGBM |
| **Observation-priority / where-to-measure-next** | **⚠ ALREADY DONE — see correction below** | Optimizing BGC Argo distribution to minimise objective mapping uncertainty (JTECH 2023); optimal sensor placement via differentiable Gumbel-Softmax (arXiv); adaptive float sampling / FloatCast (2026) |
| North-Indian-Ocean–focused validated system | **UNDEREXPLORED (weakly)** | No NIO-specific paper surfaced — but global methods already cover NIO. See caveat. |
| Integrated tool: reconstruct → uncertainty → anomaly → priority, for NIO, validated on independent Argo | **SYSTEM-LEVEL INTEGRATION, not method novelty** | The combination; none of the parts |

---

## ⚠ Correction to the seeded matrix — our strongest claim does not survive

The seed put observation-priority in **"UNDEREXPLORED / POTENTIALLY NOVEL (system-level)"**. A
targeted search says otherwise. Uncertainty-guided observation targeting is an **established
research area** with dedicated methods:

- **Optimizing the Biogeochemical Argo Float Distribution** (J. Atmos. Ocean. Tech. 40(11), 2023) —
  sequentially identifies the best **deployment locations** to minimise objective mapping
  uncertainty. That is our idea, done rigorously, for Argo specifically.
- **Optimal sensor placement for reconstruction of ocean states** (differentiable Gumbel-Softmax
  sampling) — optimised patterns that "consistently target energetic regions such as eddies and
  fronts", under explicit sensor-budget constraints.
- **Adaptive sampling in the Philippine Sea using autonomous profiling floats / FloatCast** (2026).

**So `anomaly × uncertainty × sparsity` is not a novel idea.** It is a **simple heuristic**
version of a problem that has objective-mapping-theoretic and optimisation-based treatments. Ours
has no cost model, no float drift physics, no budget constraint, and a σ term we have measured as
overconfident at depth (D-016).

**Say this before a judge does.** Claiming novelty here in front of anyone who knows the observing-
system literature would cost us the room. Framing it as *"a lightweight, interpretable heuristic
that surfaces candidate regions, complementary to formal observing-system design"* is both true
and still interesting.

## Caveat on the NIO claim

"No NIO-specific paper surfaced" is **weak evidence**. One search failing to find something is not
proof of absence, the search was English-language and abstract-level, and — decisively — the global
methods (DORS 2022 covers the whole ocean) **already include the North Indian Ocean**. So:

- ✗ "First to reconstruct subsurface temperature in the NIO" — **not defensible**
- ✓ "A NIO-focused system, validated against independent NIO Argo, with the limitations stated" —
  defensible

Indian-language and regional-journal literature (INCOIS, NIO Goa, IITM) has **not** been searched.
Given the sponsor is INCOIS, they will know that literature far better than we do.

---

## Our honest claim, final form

> A North-Indian-Ocean–focused, independently-validated reconstruction **system** — surface →
> subsurface temperature with uncertainty, anomaly and an observation-priority layer — built and
> verified end to end. We are **not** proposing a new reconstruction method, and we do **not**
> claim novelty for uncertainty-guided observation targeting; both are established fields whose
> state of the art exceeds our MVP.

**What actually makes it worth showing:** it runs end to end, every number traces to a logged run,
it is validated against a genuinely independent source, and it states where it is weak — including
the deep-layer overconfidence we found in our own uncertainty (D-016). Judges have seen plenty of
demos that claim novelty. Fewer arrive with their own failure modes documented.

## Open literature gaps  `[UNKNOWN]`
- INCOIS / NIO Goa / IITM regional literature — unsearched, and the sponsor knows it best.
- Wang 2021 and Chen 2022 from the TEAM_PLAN list were not located; DOIs needed.
- No methods section read for any cited paper.

---

## Added 2026-09-14 (Unit B) — the Bay of Bengal winter inversion as an explicit, held-out target

| Idea | Bucket | Evidence |
|---|---|---|
| Making **winter temperature-inversion fidelity in the Bay of Bengal** an explicit, pre-registered, **held-out-winter** evaluation target (and, if it fails, a targeted fix) of a **satellite-only** DL subsurface reconstruction over the NIO | **UNDEREXPLORED — to our knowledge** (searches 2026-09-14, record below) | The inversion itself is thoroughly documented from observations (Thadathil 2002/2016, Nagura 2015) and reanalysis (Pramanik 2025) — `LITERATURE_MATRIX.md` §"Barrier layer & temperature inversion". Nearest ML neighbours: Jia et al. 2025 (CNN → **MLD** in the Bay, not the profile, not inversions); a variational NIO T/S reconstruction seen only as a search snippet; global DL reconstructions (Su 2022, Meng 2021, TS-Cast 2026) that report basin-aggregate RMSE and do not, in their abstracts, evaluate inversion sign or amplitude. |

**Search record** (WebSearch, 2026-09-14): (1) `deep learning reconstruction subsurface temperature satellite "Bay of Bengal" "temperature inversion" OR "barrier layer" neural network Argo`; (2) `machine learning subsurface temperature salinity reconstruction "Bay of Bengal" from satellite SST SSS SSH 2023 2024 2025`; plus DOI-level Crossref / Semantic Scholar lookups listed in the literature matrix. **Absence from two searches is not absence from the literature**, and INCOIS / NIO / IITM regional work remains unsearched (existing gap above).

**Wording we may use:** "To our knowledge, no published satellite-only reconstruction reports inversion-detection skill on a held-out Bay of Bengal winter; we do, and we wrote the pass/fail rule down before running (E-INV-00)." **Wording we may not use:** "nobody has done this", "first ever", or any claim about what Jia 2025 or the global papers did *not* do inside methods we have not read.

**What would falsify the claim:** any paper whose methods evaluate predicted-vs-observed inversion presence or amplitude for a satellite-driven reconstruction in the Bay. If found, the row moves to ALREADY DONE and we cite it.
