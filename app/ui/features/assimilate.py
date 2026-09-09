"""When a float surfaces, correct the state — not the pixel.

OWNER: Unit A (Arjhun). NOT a page.

Pure artifact renderer. `scripts/phase2/run_latent_assimilation.py` owns the experiment.

WHAT IS BEING CLAIMED
Every paper in this specialisation treats Argo as the scoring rubric and never feeds it back. Here
the network stays frozen and the 128-number latent is optimised until the decoder reproduces an
observed profile; the correction then propagates to other cells by similarity in LATENT space
rather than by distance on the map.

THE CONTROL IS WHY IT CAN BE BELIEVED
The model runs +0.1003 degC warm (unmasked_v1, the protocol this artifact was scored under;
+0.1066 under seafloor_masked_v1), so ANY correction fitted to a real float tends to cool the
prediction, and cooling improves the score everywhere. A panel showing only "error fell at similar
cells" would be reporting a global bias correction as assimilation. So the identical correction is
applied to the least-similar decile and to random recipients, and those two are on screen beside
the headline at the same size.
"""
from __future__ import annotations

import json
import os

import altair as alt
import pandas as pd
import streamlit as st

from oceanembed import config as base

from app.ui import theme, ux

ART = "latent_assimilation.json"
POPS = [("similar", "latent-similar"), ("shuffled", "random recipients"),
        ("dissimilar", "least-similar decile")]


@st.cache_data(show_spinner=False)
def _result() -> dict:
    p = base.art(ART)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _sweep(by_lambda) -> pd.DataFrame:
    rows = []
    for r in by_lambda.values():
        for key, label in POPS + [("similar_far", "similar, ≥500 km away")]:
            g = r["populations"].get(key, {}).get("gain")
            if g is None:
                continue
            rows.append({"lambda": r["lambda"], "population": label, "gain": g,
                         "fit": r["in_sample_reduction"]})
    return pd.DataFrame(rows)


def render(ctx) -> None:
    r = _result()
    if not r:
        st.error("`artifacts/latent_assimilation.json` is not on this machine, so there is "
                 "nothing to show. This panel never invents a gain.")
        st.code("PYTHONPATH=src .venv/Scripts/python.exe "
                "scripts/phase2/run_latent_assimilation.py")
        return
    if (r.get("control") or {}).get("agrees") is not True:
        st.error("The control does not reproduce the checkpoint's recorded RMSE; nothing below "
                 "would describe the shipped model.")
        return

    head = r["headline"]
    best = r["by_lambda"][str(head["lambda"])]
    pops = best["populations"]
    far = pops.get("similar_far", {})
    near = pops.get("similar_near", {})

    # ---------------------------------------------------------------- 01
    ux.instrument("Freeze the network. Ask which 128-number latent would have produced the profile "
                  "a real float measured. Then push that correction to water in a similar state.")

    ux.tiles([
        ("GAIN AT SIMILAR STATES", f"{head['gain_similar']:+.4f}", "°C",
         f"MAE {head['mae_before']:.4f} → {head['mae_similar']:.4f}"),
        ("RANDOM RECIPIENTS", f"{pops['shuffled']['gain']:+.4f}", "°C",
         "the same correction, unrelated states"),
        ("LEAST-SIMILAR DECILE", f"{pops['dissimilar']['gain']:+.4f}", "°C",
         "actively worse, as it should be"),
        ("STILL POSITIVE AT ≥500 km", f"{far.get('gain', float('nan')):+.4f}", "°C",
         f"over {far.get('n_comparisons', 0):,} comparisons"),
    ])

    if head.get("supported"):
        st.success(
            f"**The gain is specific to latent-similar water, not a global bias correction.** "
            f"Similar states improve by {head['gain_similar']:+.4f} °C while random recipients "
            f"move {pops['shuffled']['gain']:+.4f} and the least-similar decile "
            f"{pops['dissimilar']['gain']:+.4f}. If this were the model's warm bias being "
            f"cancelled, all three would improve together.", icon=":material/check_circle:")

    left, right = st.columns([1.2, 1.0], gap="large")
    with left:
        st.markdown("**The correction's effect, against how hard it was fitted**")
        df = _sweep(r["by_lambda"])
        ch = alt.Chart(df).mark_line(point=True, strokeWidth=2).encode(
            x=alt.X("lambda:Q", scale=alt.Scale(type="log", reverse=True),
                    title="ridge weight λ  (right → left: the latent is allowed to move further)"),
            y=alt.Y("gain:Q", title="error reduction at the recipients (°C)"),
            color=alt.Color("population:N", title=None,
                            scale=alt.Scale(range=[theme.CYAN, theme.AZURE,
                                                   theme.CORAL, theme.AMBER])),
            tooltip=["population", alt.Tooltip("lambda:Q", format=".3f"),
                     alt.Tooltip("gain:Q", format="+.4f", title="gain °C")],
        ).properties(height=330)
        zero = alt.Chart(pd.DataFrame({"y": [0.0]})).mark_rule(
            color=theme.INK_FAINT, strokeDash=[4, 3]).encode(y="y:Q")
        st.altair_chart(ch + zero, use_container_width=True)
        st.caption(
            f"Selected at **λ = {head['lambda']}** — the largest gain at similar states among the "
            f"λ values where **neither control improved**. Selecting on the margin instead would "
            f"have chosen λ=0.001, where similar states gain only +0.0033 °C but the controls are "
            f"driven 0.24 °C worse: a rule that rewards wrecking its own control will always "
            f"report success.")

    with right:
        st.markdown("**Does it travel by water mass, or just by distance?**")
        d2 = pd.DataFrame([
            {"group": "similar, <200 km", "gain": near.get("gain", 0.0),
             "n": near.get("n_comparisons", 0)},
            {"group": "similar, ≥500 km", "gain": far.get("gain", 0.0),
             "n": far.get("n_comparisons", 0)},
            {"group": "random", "gain": pops["shuffled"]["gain"],
             "n": pops["shuffled"]["n_comparisons"]},
        ])
        bar = alt.Chart(d2).mark_bar().encode(
            y=alt.Y("group:N", title=None, sort=None),
            x=alt.X("gain:Q", title="error reduction (°C)"),
            color=alt.condition(alt.datum.gain > 0, alt.value(theme.MINT), alt.value(theme.CORAL)),
            tooltip=[alt.Tooltip("gain:Q", format="+.4f"), alt.Tooltip("n:Q", format=",")],
        ).properties(height=200)
        st.altair_chart(bar, use_container_width=True)
        st.markdown(
            f"The correction **is** still positive at 500 km and beyond "
            f"(**{far.get('gain', 0):+.4f} °C** over {far.get('n_comparisons', 0):,} "
            f"comparisons), which is the claim: it follows the water mass, not the map. But most "
            f"of the benefit is local — **{near.get('gain', 0):+.4f} °C** under 200 km — so the "
            f"honest statement is that it generalises by state *and* is strongest nearby.")

    # ---------------------------------------------------------------- 02
    ux.maths(
        r"h^{*} = \operatorname*{arg\,min}_{h}\;"
        r"\big\lVert \operatorname{dec}(h) - y_{\mathrm{obs}} \big\rVert^{2}_{\mathcal{M}}"
        r"\;+\;\lambda\lVert h - h_0 \rVert^{2}"
        r"\qquad h_j \leftarrow h_j + w_{ij}\,(h^{*}-h_0),\;\;"
        r"w_{ij} = \frac{\cos(h_i,h_j)-\tau}{1-\tau}",
        [("h₀", "the encoder's own latent for the float's cell", "128-vector", "frozen encoder"),
         ("dec", "the shipped decoder head, weights frozen throughout", "—",
          "TSCastNIO.simple_head"),
         ("y_obs", "the float's measured profile, z-scored as the model was trained", "—",
          "held-out Argo, never used in training"),
         ("M", "the mask of levels the float actually reached", "—",
          "a level it never sampled contributes nothing"),
         ("λ", f"ridge anchoring h* to h₀ — selected at {head['lambda']}", "—",
          "swept, with the whole sweep in the artifact"),
         ("τ", f"cosine similarity above which a cell is treated as the same water mass — "
               f"{r['tau']}", "—", "a stated parameter")],
        "No gradient ever reaches a weight — a test asserts every parameter is bit-identical "
        "before and after a fit. This is inference-time assimilation on a frozen network, not "
        "fine-tuning, and the distinction is the whole claim.")

    # ---------------------------------------------------------------- 03
    ux.inference(
        what=(f"A real float's profile being fed back into the model's internal state, and what "
              f"that correction does at **other** floats — never at the donor's own profile, "
              f"which would measure the optimiser rather than the method."),
        conclude=(f"A frozen model can be improved by an observation at inference time, and the "
                  f"improvement follows similarity of ocean state rather than distance on the "
                  f"map. It is modest — **{head['gain_similar']:+.4f} °C** on a "
                  f"{head['mae_before']:.4f} °C mean absolute error, about "
                  f"{100*head['gain_similar']/head['mae_before']:.1f}% — and it needs no "
                  f"retraining, which is what makes it operationally interesting."),
        limits=[
            ("Recipients are other Argo cells, not the whole basin. The gain is measured only "
             "where an independent float exists to score it; propagating to all 24,000 cells is "
             "what an operational system would do and is not what was measured.",
             r["caveat"]),
            (f"Most of the benefit is local. Under 200 km the gain is "
             f"{near.get('gain', 0):+.4f} °C against {far.get('gain', 0):+.4f} °C beyond 500 km, "
             f"so 'travels by water mass' is true and is not the larger half of the effect.",
             "similar_near vs similar_far, both in the artifact"),
            ("Pushing the latent further out of distribution destroys the long-range effect "
             "while the local one survives — at λ ≤ 0.003 the far gain goes negative. The "
             "correction becomes a local patch.",
             "the λ sweep: far gain +0.0065 at λ=0.03, −0.0061 at λ=0.001"),
            ("It is a single-observation correction with no time evolution, no error covariance "
             "and no cycling. Operational data assimilation has all three; this has none of "
             "them.",
             "no forecast step exists in this project"),
        ])
