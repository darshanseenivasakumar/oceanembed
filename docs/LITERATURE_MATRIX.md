# LITERATURE_MATRIX.md  (Owner: Unit C — Mitun+Niru)

## ⚠ Provenance of this matrix — read before citing anything here
Every row is **`[ABSTRACT-ONLY]`**: compiled from the papers' published abstracts and landing
pages, fetched online. The PDFs in `all research papers/` are **not on the build machine**
(gitignored, and they live on Mitun's/Niru's machines), so **nobody has read these methods
sections**.

That is enough to position our work honestly. It is **not** enough to:
- quote a methods detail, hyperparameter, or ablation,
- claim a paper did *not* do something (absence from an abstract is not absence from the paper),
- assert a numerical comparison against our results.

Whoever holds the PDFs should upgrade rows to `[VERIFIED]` after reading. Until then, cite these
papers for **existence and general approach only**.

Sources are linked per row. Nothing below is paraphrased from memory.

---

## Core papers — surface → subsurface reconstruction

### 1. Meng et al. 2021 — CNN reconstruction of 3D T/S from satellite  `[ABSTRACT-ONLY]`
*Reconstruction of Three-Dimensional Temperature and Salinity Fields From Satellite Observations*,
JGR: Oceans. [doi:10.1029/2021JC017605](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2021JC017605)

| | |
|---|---|
| Region | Central Pacific, 160°E–120°W, 30°S–30°N |
| Inputs | SLA, SST, SSS, zonal + meridional wind stress |
| Target | Subsurface temperature **and** salinity anomalies |
| Depth | 26 levels, 5 m → **2000 m** |
| Resolution | 1° and 1/4°, **monthly** |
| Model | CNN, 15 hidden layers (conv / pooling / fully connected) |
| Physics | Dynamic height + geostrophic velocity derived from the estimated fields |
| Uncertainty | None — RMSE / R² / correlation reported as skill, not predictive uncertainty |
| Validation | Gridded Argo (1°), ISAS Argo (1/2°), EN4 individual profiles; 5°×5° box verification |
| Headline | Temp RMSE 0.022 °C, salinity 0.0028 psu (averaged across depths) |
| Stated limits | Monthly only; daily scale left to future work; demonstrated mainly for 2012 central Pacific |
| **Overlap with us** | **High on approach** — same surface→depth framing, similar input set. Differs in region (Pacific vs North Indian Ocean), cadence (monthly vs our daily target), and depth (2000 m vs our 500 m). |

### 2. TS-Cast 2026 — uncertainty-aware U-Net + FiLM  `[ABSTRACT-ONLY]`
*TS-Cast: Deep Learning for Subsurface Ocean Reconstruction from Satellite Observations in the
Northwestern Pacific*, Ocean Science 22, 2161.
[os.copernicus.org/articles/22/2161/2026](https://os.copernicus.org/articles/22/2161/2026/)

| | |
|---|---|
| Region | Northwestern Pacific — Kuroshio Extension, East/Japan Sea |
| Inputs | SST, SSS, ADT **plus the satellite error fields** |
| Target | Vertical T and S profiles |
| Depth | 10–700 dbar |
| Resolution | 1/8°, daily inputs over 31-day sequences |
| Model | U-Net backbone + **FiLM** conditioning, satellite encoder, parallel prediction/uncertainty heads |
| Physics | **Yes** — seawater equation of state enforced for plausible T/S combinations |
| Uncertainty | **Yes** — predicts depth-dependent log error variances for T, S and density |
| Validation | ~155,000 Argo + CTD profiles; independent KEO/EC1 moorings and PIES arrays; spectral coherence |
| Headline | RMSE < 1 °C (T), < 0.1 psu (S) in the upper 500 m |
| Stated limits | Degrades at periods < 20 days — bounded by altimetry's 10-day repeat and inability to separate barotropic from baroclinic signal |
| **Overlap with us** | **Highest of any paper here.** Uncertainty-aware, physics-constrained, daily, and it uses FiLM conditioning — which is what Unit A's decoder design also reaches for. **This is the paper to compare ourselves against honestly.** Its stated limit (surface data bounds deep/high-frequency skill) is the same one we must report. |

### 3. DORS 2022 — ConvLSTM global reconstruction  `[ABSTRACT-ONLY]`
*Subsurface Temperature Reconstruction for the Global Ocean from 1993 to 2020 Using Satellite
Observations and Deep Learning*, Remote Sensing 14(13), 3198.
[doi:10.3390/rs14133198](https://doi.org/10.3390/rs14133198)
*(MDPI returns HTTP 403 to automated fetches; row compiled from the indexed abstract.)*

| | |
|---|---|
| Region | **Global** |
| Inputs | Multisource remote sensing + gridded Argo |
| Target | Subsurface temperature |
| Depth | Upper **2000 m** |
| Period | 1993–2020 |
| Model | **ConvLSTM** — explicitly temporal, unlike a per-column model |
| Physics | Not stated in the abstract |
| Uncertainty | Not stated in the abstract |
| **Overlap with us** | Same target, far larger scope. Its existence is why a global-novelty claim is unavailable to us. Our defensible ground is regional focus + the decision layer, not the reconstruction itself. |

### 4. FFPG-net 2025 — feature fusion + physical guidance  `[ABSTRACT-ONLY]`
*Reconstruction of the Subsurface Temperature and Salinity in the South China Sea Using
Deep-Learning Techniques with a Physical Guidance*, Remote Sensing 17(17), 2954.
[doi:10.3390/rs17172954](https://doi.org/10.3390/rs17172954)

| | |
|---|---|
| Region | South China Sea |
| Target | Subsurface T and S |
| Model | Residual + channel-attention deep network |
| Physics | **Yes** — vertical T/S modes from **EOF** decomposition act as the physical constraint |
| Uncertainty | Not stated in the abstract |
| Headline | Monthly-mean RMSE 0.31 °C (winter) / 0.35 °C (summer) for T; 0.06 / 0.07 psu for S |
| **Overlap with us** | Regional-basin framing closest to ours. Its EOF-mode constraint is a cheaper physics route than a full equation-of-state and is a realistic Phase-2 option for us. |

### 5. NeSPReSO 2025 — PCA + neural network, Gulf of Mexico  `[ABSTRACT-ONLY]`
*Neural Synthetic Profiles from Remote Sensing and Observations (NeSPReSO)*, Ocean Modelling 196,
102550. [doi:10.1016/j.ocemod.2025.102550](https://www.sciencedirect.com/science/article/abs/pii/S1463500325000538)

| | |
|---|---|
| Region | Gulf of Mexico |
| Inputs | Time, location, satellite ADT, SST, SSS |
| Target | T and S profiles |
| Model | **PCA on Argo profiles → neural net predicts the principal components** (dimensionality reduction first) |
| Uncertainty | Not stated in the abstract; RMSE and bias reported |
| Validation | Held-out Argo **plus independent glider data** |
| Baselines beaten | GEM, Multiple Linear Regression, ISOP |
| **Overlap with us** | Different architecture family. Two things worth stealing: **(a)** benchmarking against *classical* baselines (GEM/MLR/ISOP), which is stronger than beating climatology alone — our LightGBM baseline serves the same purpose; **(b)** validating on a genuinely independent instrument type. |

---

## What this literature means for our positioning  `[INFERRED from the rows above]`

1. **Surface→subsurface DL reconstruction is an established field**, not a novel idea. Papers span
   2021–2026 across the Pacific, South China Sea, Gulf of Mexico and globally. Any claim that we
   invented this would be checkable in one search by a judge.
2. **We are behind the state of the art on model sophistication.** TS-Cast is uncertainty-aware,
   physics-constrained, daily, 1/8°. Our Aug-30 MVP is a per-column MLP at 0.25°, monthly-capable,
   11 depths to 500 m. That is a deliberate, documented MVP choice (`DECISIONS.md` D-002), not a
   claim of superiority.
3. **Where the gap actually is:** none of these abstracts mentions the **North Indian Ocean**, and
   none mentions an **observation-priority / where-to-measure-next decision layer**. That is our
   defensible ground — see `NOVELTY_MATRIX.md`. Note the caution: "not mentioned in the abstract"
   is **not** "not done in the paper", and NIO reconstruction papers may exist that this search did
   not surface.
4. **Their limits are our limits.** TS-Cast reports degradation at high frequency and depth from
   surface-data constraints; Meng is monthly-only. We should expect and report the same shape of
   degradation rather than presenting flat skill.

## Gaps in this review  `[UNKNOWN]`
- No search specifically for **North Indian Ocean / Bay of Bengal / Arabian Sea** subsurface
  reconstruction papers. Doing that is the single highest-value literature task remaining, because
  our whole regional-novelty claim rests on it.
- Wang 2021 and Chen 2022 from the TEAM_PLAN list were **not located** by these searches; the
  citations may be ambiguous. Whoever has the PDFs should supply the DOIs.
- No methods section has been read for any paper here.

---

## Barrier layer & temperature inversion — Bay of Bengal  (added 2026-09-14, Unit B, branch `phase2-bob-inversion`)

**Provenance of this section.** Every row was located on 2026-09-14 through bot-friendly metadata
APIs (Crossref `api.crossref.org/works/<DOI>`, Semantic Scholar `api.semanticscholar.org`) and one
Springer landing page. Publisher full-text pages (Wiley/AGU, Elsevier, AMS) and even HAL / NIO-DRS
returned bot-wall errors to the fetcher, and we did not try to get around them. Tags:
`[ABSTRACT-VERIFIED]` = the abstract text itself was returned by the API/page and is paraphrased from it;
`[CITATION-VERIFIED]` = title/authors/venue/DOI confirmed by Crossref, abstract not available;
`[SEARCH-SNIPPET-ONLY]` = seen only as a search-result title. **No methods section has been read.**
The PDFs that are free to read (AGU > 24 months old; HAL) should be saved by a human into
`all research papers/barrier_layer/` and the rows upgraded to `[READ]`.

### Definitions we rely on
| # | Paper | Tag | What we take from it |
|---|---|---|---|
| B1 | de Boyer Montégut, Madec, Fischer, Lazar, Iudicone (2004), *Mixed layer depth over the global ocean: An examination of profile data and a profile-based climatology*, JGR 109, C12003. doi:10.1029/2004JC002378. Green OA: hal.science/hal-00266983 | `[ABSTRACT-VERIFIED]` (Semantic Scholar) | Criterion = threshold from the 10 m value, **ΔT = 0.2 °C or Δσθ = 0.03 kg m⁻³**; also "a new global seasonal estimation of barrier layer thickness"; notes density-compensated (isopycnal but not mixed) layers. Exactly what `src/phase2/physics/layers.py` implements. |
| B2 | Sprintall & Tomczak (1992), *Evidence of the barrier layer in the surface layer of the tropics*, JGR 97, 7305–7316. doi:10.1029/92JC00407 | `[CITATION-VERIFIED]` | The paper that named the barrier layer (BLT = ILD − MLD). Cited for existence only. |
| B3 | de Boyer Montégut, Mignot, Lazar, Cravatte (2007), *Control of salinity on the mixed layer depth in the world ocean: 1. General description*, JGR 112, C06011. doi:10.1029/2006JC003953 | `[CITATION-VERIFIED]` (abstract elided by publisher) | Global barrier-layer / compensated-layer climatology. Cited for existence only. |

### The Bay of Bengal inversion itself
| # | Paper | Tag | What we take from it |
|---|---|---|---|
| B4 | Thadathil, Gopalakrishna, Muraleedharan, Reddy, Araligidad, Shenoy (2002), *Surface layer temperature inversion in the Bay of Bengal*, Deep-Sea Res. I 49, 1801–1818. doi:10.1016/S0967-0637(02)00044-4 | `[CITATION-VERIFIED]` (no abstract via API) | The reference hydrographic study. **Its numeric inversion threshold is [UNKNOWN] to us** — not read. Do not quote one. |
| B5 | Thadathil, Muraleedharan, Rao, Somayajulu, Reddy, Revichandran (2007), *Observed seasonal variability of barrier layer in the Bay of Bengal*, JGR 112. doi:10.1029/2006JC003651 | `[ABSTRACT-VERIFIED]` (Crossref) | BLT ~40 m first appears in the NE coastal Bay in June and spreads west; east-coast formation governed by the East India Coastal Current; **maximum ~60 m in February**; annual peaks Nov–Dec, secondary Feb–Mar and Aug–Sep. → sanity numbers for our truth-side BLT maps. |
| B6 | Thadathil, Suresh, Gautham, Prasanna Kumar, Lengaigne, Rao, Neetu, Hegde (2016), *Surface layer temperature inversion in the Bay of Bengal: Main characteristics and related mechanisms*, JGR Oceans 121, 5682–5696. doi:10.1002/2016JC011674. Bronze OA at Wiley `pdfdirect` | `[ABSTRACT-VERIFIED]` (Crossref) | Definition in words: a warm layer sandwiched between surface and subsurface colder waters, frequently with barrier layers. RAMA buoys 2006–2014 at four sites along 90 °E. Forms after the summer monsoon, fully developed in **winter**. **~80 % frequency and ~0.7 °C amplitude in the northern Bay**, lower southward; intraseasonal variation 0.44 °C > interannual 0.26 °C; **net surface heat loss dominates formation**, episodic cold advection in 2012–13; winter entrainment/diffusion warm the surface layer. → the anchor for E-INV-00's expected truth-side numbers. |
| B7 | Nagura, Terao, Hashizume (2015), *The Role of Temperature Inversions in the Generation of Seasonal and Interannual SST Variability in the Far Northern Bay of Bengal*, J. Climate 28(9). doi:10.1175/JCLI-D-14-00553.1. Bronze OA PDF at AMS | `[CITATION-VERIFIED]` | Cited for existence: inversions matter for SST itself in the far northern Bay. |
| B8 | Girishkumar, Ravichandran, McPhaden, Rao (2011), *Intraseasonal variability in barrier layer thickness in the south central Bay of Bengal*, JGR 116, C03009. doi:10.1029/2010JC006657 | `[CITATION-VERIFIED]` | RAMA-based BLT variability, south-central Bay. The plan draft said "2013" — **corrected to 2011 by Crossref**. |
| B9 | Pramanik, Parekh, Gnanaseelan, Chowdary, Pai (2025), *Unrepresented subsurface temperature inversion in the northern Bay of Bengal and associated forcing mechanisms*, Climate Dynamics. doi:10.1007/s00382-025-07870-x | `[ABSTRACT-VERIFIED]` (Springer page) | ORAS5 1958–2023. Winter inversions show the largest interannual variability; strong-amplitude years ↔ strong stratification, shallow MLD, thick barrier layer; heat budget: **surface cooling via net heat loss + subsurface warming via penetrative shortwave**; entrainment cools the inversion base. ⚠ The title's "Unrepresented" is **not** explained in the abstract — do not cite this paper as evidence that models fail to represent the inversion. |
| B10 | Jia, Gong, Zhu, Qi, Zhou, Yao, Gong, Wang (2025), *A dual-attention embedded CNN model for estimating mixed layer depths in the Bay of Bengal*, J. Oceanology and Limnology. doi:10.1007/s00343-024-4122-9 | `[CITATION-VERIFIED]` (abstract elided; reference list cites satellite inputs and barrier-layer work) | Nearest ML neighbour: a CNN that estimates **MLD** in the Bay. Target is MLD, not the temperature profile and not inversions — from the title/reference list only. |
| B11 | *Observations of barrier layer formation in the Bay of Bengal during summer monsoon* (Vinayachandran et al., GRL 2002) | `[SEARCH-SNIPPET-ONLY]` | Seen as a ResearchGate title only; DOI not verified. Not to be cited until checked. |
| B12 | *Spatial variability of the winter thermal inversion in the northern Bay of Bengal* (Regional Studies in Marine Science, 2022, Elsevier pii S2352485522001311) | `[SEARCH-SNIPPET-ONLY]` | Title only; a guessed Crossref DOI returned 404. Not to be cited until checked. |
| B13 | *Spatiotemporal variation and mechanisms of temperature inversion in the Bay of Bengal and the eastern equatorial Indian Ocean* (Acta Oceanologica Sinica 2021). doi:10.1007/s13131-021-1873-4 | `[SEARCH-SNIPPET-ONLY]` | Springer page needed a cookie hand-off; not read. |
