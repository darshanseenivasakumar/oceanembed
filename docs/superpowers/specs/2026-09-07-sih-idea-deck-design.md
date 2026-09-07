# SIH idea-submission deck — design

**Date** 2026-09-07 · **Owner** Arjhun · **Status** approved, building

## Goal

Produce `OceanEmbed_SIH26066_IDEA.pptx` — the **official SIH idea-submission format** deck for
SIH26066, written in the structure and visual language of a winning SIH deck the user supplied as
reference screenshots (team "Tech Pioneers", RockVision AI).

This is a **second, separate artifact**. `OceanEmbed_SIH26066.pptx` (12 slides, custom pitch deck)
is untouched — the two serve different stages: submission format vs. live pitch.

## Non-goals

- Restyling or replacing the existing 12-slide deck.
- Any claim not already measured and recorded in this repo.
- Reproducing the official SIH logo (see Placeholders).

## The reference structure, per slide

Every slide carries the same chrome, copied from the reference:

| element | treatment |
|---|---|
| slide size | 13.33 x 7.5 in (16:9), matching the existing deck |
| border | thin black rectangle outline, inset 0.12 in |
| top-left | violet oval outline, team name on two lines |
| top-centre | project/section title, bold serif (Times New Roman), ~40 pt, black |
| top-right | official SIH logo — **placeholder box**, see below |
| section head | `❖ <Name>`, dark blue, bold, underlined, ~24 pt |
| bullets | `➤` marker + **bold lead-in label:** + regular explanatory sentence |
| right ~40% | a diagram |

### Slide 1 — Proposed Solution
7 `➤` bullets (platform / satellite-only input / model / uncertainty / validation / derived
products / observation priority) + `arch.png` system architecture on the right.

### Slide 2 — Technical Approach
`❖ Technology Stack` — 6 bold-label category lines (Core, Ocean Data, AI/ML, Frontend, API &
Export, Reproducibility) + `chips.png` brand-coloured tech chip grid on the right + `flow.png`
methodology strip across the bottom.

The reference deck omits the methodology flow chart; the official rubric asks for it. Added
deliberately.

### Slide 3 — Feasibility and Viability
Two columns. Left: Feasibility (1-3), Viability (4-5), Challenges (6-9), Use Cases (10-12), one
continuous numbering as in the reference. Right: Deployment Potential (1-4), Solutions (5-7), and
`facts.png` — the green rounded supporting-facts card.

### Slide 4 — Impact and Benefits
Left: `tree.png` benefits tree (Social / Scientific / Economic / Environmental) above
`❖ Potential impact on the target audience:` with 5 audience bullets. Right:
`❖ Benefits of the solution` under the same four headings.

### Slide 5 — Research and References
Not in the supplied screenshots; required by the template. Papers with DOIs, CMEMS product IDs,
Argo, and the problem statement.

## Number ledger — the only figures any slide may quote

Every one is read from `artifacts/frozen_manifest.json` at build time and asserted, so a re-freeze
that moves a number breaks the build instead of shipping a stale slide.

| figure | value | source |
|---|---|---|
| RMSE vs independent Argo | 0.9006 °C | `overall_rmse` |
| skill vs climatology | +0.2400 (24%) | `overall_skill_rmse_ratio` |
| bias | +0.1066 °C | `overall_bias` |
| correlation | 0.8809 | `overall_correlation` |
| comparisons | 12,736 | `overall_n` |
| Argo profiles | 962 | `argo_profiles` |
| depths | 15 (0-1000 m) | `n_depths` |
| input window | 11 days | `T_SEQ` |
| input channels | 7 | `channels` |

Figures held in the script as constants, sourced from named files rather than the manifest:

| figure | value | source |
|---|---|---|
| model size | 549k parameters | existing deck slide 5 |
| training days | 388, gap-free | `PHASE2_STATUS.md` row 16 |
| grid | 0.25°, 100 x 240 cells | `docs/MASTER_SPEC.md` |
| beats climatology at | 14 of 15 depths | existing deck slides 7-8 |
| thermocline error | 1.1-1.2 °C at 50-150 m | existing deck slide 8 |
| selection-leak cost | +0.0824 °C, 3 seeds | manifest `selection_leak` |
| peak TCHP / D26 | 173 kJ/cm², 105 m | `docs/HANDOFF.md` 2026-09-03 |
| tests passing | 530 | `docs/HANDOFF.md` freeze block |
| feature modules | 15 | `app/ui/features/__init__.py` |
| training time | ~9 min, single GPU | existing deck slide 5 |

## Honesty constraints

1. **Literature is `[ABSTRACT-ONLY]`.** `docs/LITERATURE_MATRIX.md` states nobody on the team has
   read those methods sections. Slide 5 cites the five papers for **existence and general approach
   only**; no numerical comparison against their results appears anywhere in the deck.
2. **No fabricated economics.** The reference deck quotes "$2-5 million annually" and "70-90%
   reduction". We have measured no such figure and invent no equivalent. Economic benefit is stated
   qualitatively, plus the two costs we did measure (~9 min GPU training; zero data-licence cost).
3. **Challenges are the real documented ones** — thermocline error, uncertainty not calibrated, the
   epoch-selection leak, INCOIS unreachable — not softened placeholders.
4. **Two external facts** ("most densely populated cyclone basin", "ocean holds the dominant share
   of excess planetary heat") are general-knowledge context, not repo measurements. Flagged to the
   user to attach a citation if the jury is strict.

## Placeholders the user must fill

| what | why | where |
|---|---|---|
| **SIH official logo** | copyrighted mark, asset not in repo, will not be redrawn | dashed grey box, top-right of every slide |
| **Team name** | not recorded anywhere in the repo | `TEAM_NAME` constant, top of the build script |

The reference deck says **2025**; SIH26066 is the **2026** cycle. The pasted logo settles it.

## Build and QA

- `scripts/deck/build_idea_slides.py` — single script, no arguments. Renders 5 matplotlib PNGs to
  `artifacts/deck/`, then assembles the deck with python-pptx.
- Toolchain: system Python (python-pptx 1.0.2, matplotlib 3.10.8, pillow). The project venv has
  neither python-pptx nor matplotlib.
- **No Office renderer on this machine**, so QA is programmatic: re-open the built file, assert
  slide count, every text frame, and every image placement; plus visual inspection of the five
  PNGs, which are ordinary images.
- `tests/phase2/test_idea_deck_claims.py` — new, additive. Guards the new deck the way
  `test_presentation_claims.py` guards the old one: headline must match the frozen manifest, and
  the retracted pre-embargo numbers and the GLORYS comparator's metrics must not appear.
  `test_presentation_claims.py` is left untouched.
