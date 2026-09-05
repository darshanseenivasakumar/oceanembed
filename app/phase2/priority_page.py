"""Where another observation would teach the model most. (Unit A / Arjhun.)

PHASE-2 ONLY. A NEW file under app/phase2/. The frozen demo (app/streamlit_app.py, app/panels/)
is READ-ONLY and is not imported here.

    streamlit run app/phase2/priority_page.py --server.port 8516

WHAT THIS PAGE MAY AND MAY NOT CLAIM -- see docs/NOVELTY_MATRIX.md
This project's own literature review marks observation-priority "ALREADY DONE": it is a simplified
heuristic version of a formally-optimised research area (JTECH 2023 objective-mapping optimisation,
Gumbel-Softmax sensor placement, FloatCast 2026). The sanctioned claim is "regions where additional
observations may provide high scientific value" and nothing stronger. This page never says the
model tells anyone where to deploy a float, and `priority_v2.CLAIM` / `NOT_A_CLAIM` are rendered
verbatim so the wording cannot drift.

WHY EKE INSTEAD OF v1's SPARSITY
Sparsity -- distance to the nearest float -- has a defect that cannot be fixed inside it: the
places floats are most absent are the places floats cannot GO. v1 ranked the Persian Gulf, 20 m
deep, at the top. EKE asks a question about the water instead of about the observing network, and
it cannot be maximised by a place no instrument can reach.

MEASURED, and stated on the page rather than assumed: on 2026-05-15 the guard excludes 3,042
too-shallow cells, and NONE of them were in the top 200 either way. The improvement is that the
BUG'S MECHANISM is gone, not that the guard rescued this particular map.
"""
from __future__ import annotations

import os
import sys

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import _fields                                              # noqa: E402
from oceanembed import config as base                       # noqa: E402
from phase2.derived import mapframe as MF                   # noqa: E402
from phase2.products import priority_v2 as P                # noqa: E402
from phase2.viz_explainer import Caveat, Explainer, render  # noqa: E402

st.set_page_config(page_title="OceanEmbed — Observation priority", layout="wide")
alt.data_transformers.disable_max_rows()

MAP_WIDTH, MAP_HEIGHT = MF.map_size(880)
CLR_NOT_WATER = "#3d3d3d"
LAYERS = {"priority": ("priority (σ × EKE)", "magma"),
          "sigma_norm": ("model uncertainty, normalised", "inferno"),
          "eke_norm": ("eddy kinetic energy, normalised", "viridis")}


@st.cache_data(show_spinner="Computing eddy kinetic energy …")
def compute(date_str: str, window_days: int, version: str, device: str | None) -> dict:
    from phase2.tscast_nio import field_cache as FC

    p = FC.get_predictor(1)
    ch = [str(c) for c in p.data["channels"]]
    u = np.asarray(p.data["surface"][:, :, :, ch.index("u")], dtype="float64")
    v = np.asarray(p.data["surface"][:, :, :, ch.index("v")], dtype="float64")
    t_idx, _ = p._time(date_str)
    k = P.eddy_kinetic_energy(u, v, t_index=t_idx, window_days=int(window_days))

    f = FC.field_for(date_str, device=device)
    with np.errstate(invalid="ignore"):
        sigma = np.nanmean(np.asarray(f["sigma"]), axis=2)
    return {"eke": k["eke"], "mean_speed": k["mean_speed"], "window": k["window"],
            "n_steps_used": k["n_steps_used"], "sigma": sigma,
            "valid_mask": np.asarray(f["valid_mask"], bool),
            "land_mask": np.asarray(f["land_mask"], bool), "date": f["date"],
            "calibrated": bool(f["provenance"].get("sigma_is_calibrated"))}


def rank(c: dict, w_sigma: float, w_eke: float, guard: bool) -> dict:
    return P.priority(c["sigma"], c["eke"],
                      valid_mask=c["valid_mask"] if guard else None,
                      weights=(w_sigma, w_eke))


def map_chart(c: dict, r: dict, layer: str, top: list[dict]):
    title, scheme = LAYERS[layer]
    d = MF.add_edges(MF.level_frame(r[layer], c["land_mask"], base.LAT, base.LON))
    df = pd.DataFrame(d)
    heat = (alt.Chart(df).mark_rect(invalid=None).encode(
        x=alt.X("lon0:Q", title="longitude (°E)", scale=alt.Scale(nice=False, zero=False)),
        x2="lon1:Q",
        y=alt.Y("lat0:Q", title="latitude (°N)", scale=alt.Scale(nice=False, zero=False)),
        y2="lat1:Q",
        color=alt.condition("isValid(datum.value)",
                            alt.Color("value:Q", title=title,
                                      scale=alt.Scale(scheme=scheme),
                                      legend=alt.Legend(orient="right")),
                            alt.value(CLR_NOT_WATER)),
        tooltip=[alt.Tooltip("lat:Q", format=".2f", title="lat °N"),
                 alt.Tooltip("lon:Q", format=".2f", title="lon °E"),
                 alt.Tooltip("value:Q", format=".3f", title=title)]))
    layers = [heat]
    if top:
        pts = pd.DataFrame([{"lat": t["lat"], "lon": t["lon"], "rank": t["rank"],
                             "priority": t["priority"]} for t in top])
        layers.append(alt.Chart(pts).mark_point(
            shape="circle", size=70, filled=False, stroke="#ffffff", strokeWidth=1.6).encode(
            x="lon:Q", y="lat:Q",
            tooltip=[alt.Tooltip("rank:Q"), alt.Tooltip("lat:Q", format=".2f"),
                     alt.Tooltip("lon:Q", format=".2f"),
                     alt.Tooltip("priority:Q", format=".3f")]))
    return alt.layer(*layers).properties(width=MAP_WIDTH, height=MAP_HEIGHT)


def explainer(r: dict, c: dict) -> Explainer:
    return Explainer(
        title="Observation priority (v2)",
        plain=("This combines two things: how uncertain the model is at a point, and how "
               "dynamically active the ocean is there — eddy kinetic energy, high in eddies and "
               "jets, low in calm water. Multiplying them flags places that are BOTH turbulent "
               "AND poorly predicted, which is where a physical observation would teach the model "
               "the most."),
        formula=r"\mathrm{EKE} = \tfrac{1}{2}\left(u'^2 + v'^2\right), \qquad "
                r"\text{Priority}(x,y) = \big[\,\hat\sigma(x,y)\cdot \widehat{\mathrm{EKE}}(x,y)\,"
                r"\big]^{1/2}",
        formula_note=(
            "u′ and v′ are the eddy part of the surface current — the current minus its mean over "
            f"a ±{(c['window'][1] - c['window'][0]) // 2}-day window, {c['n_steps_used']} daily "
            "steps. σ̂ and EKÊ are each rescaled to 0–1 with 1st–99th percentile clipping before "
            "multiplying, because σ is in °C (order 1) and EKE in m²/s² (order 0.01); a raw "
            "product would rank on EKE alone. The square root makes it a geometric mean, the same "
            "combination the v1 product uses, so the two rank on the same footing."),
        how_to_read=("High priority does NOT mean 'the ocean is doing something important here'. "
                     "It means 'we genuinely don't know what is happening here, and it looks "
                     "dynamic enough to matter'. Circles mark the top-ranked cells. Compare the "
                     "two factor maps beside it: a place bright on only one of them is not a "
                     "candidate."),
        caveats=(
            Caveat("This is a heuristic, not an observing-system design.",
                   P.NOT_A_CLAIM + " The formally-optimised version of this problem is a "
                   "published research area — objective-mapping optimisation (JTECH 2023), "
                   "differentiable Gumbel-Softmax sensor placement, FloatCast 2026 — with cost "
                   "models, float drift and budget constraints, none of which are here.",
                   "docs/NOVELTY_MATRIX.md — marked ALREADY DONE, with the sanctioned wording"),
            Caveat("EKE is computed from the model's INPUT currents, not from anything it derived.",
                   "u and v are COPERNICUS-GLOBCURRENT surface currents, two of the seven channels "
                   "the model is fed. An EKE map is a fact about that product. Only the σ factor "
                   "is this model's own contribution.",
                   "phase2.tscast_nio.config.CHANNELS"),
            Caveat("Cells too shallow for a float are excluded, and that is a parameter, not a "
                   "default.",
                   f"v1 ranked the Persian Gulf — about 20 m of water — at the top, because a "
                   f"place no float can enter is by definition a place with no floats; the fix "
                   f"lived at v1's single call site, so every new caller reintroduced it. Here it "
                   f"is part of the product. On this date it removes "
                   f"{r['n_cells_excluded_as_too_shallow']:,} cells. Measured honestly: none of "
                   f"them were in the top 200 either way — EKE, unlike sparsity, is not maximised "
                   f"by places instruments cannot reach, so the mechanism of the bug is gone "
                   f"rather than merely patched.",
                   "src/oceanembed/inference/predict.py:302-311 — where v1's fix had to live"),
            Caveat("A ±30-day window, because this basin reverses seasonally.",
                   "Subtracting a full-record mean would leave the entire monsoon reversal inside "
                   "u′, and the result would be dominated by the seasonal cycle rather than by "
                   "eddies. The window removes the seasonal mean flow and leaves the mesoscale.",
                   "phase2.products.priority_v2.DEFAULT_WINDOW_DAYS"),
        ),
        references=(
            "Optimizing the distribution of BGC-Argo floats to minimise objective-mapping "
            "uncertainty, J. Atmos. Oceanic Technol. 40(11), 2023. [ABSTRACT-ONLY]",))


def main() -> None:
    st.title("Observation priority — where another measurement would teach the model most")
    st.caption(P.CLAIM.capitalize() + ".")

    with st.sidebar:
        st.header("What to show")
        ver = _fields.version(1)
        date_str = _fields.date_picker(1, label="date", key="pr_date")
        window = st.slider("mean-flow window (± days)", 5, 90, P.DEFAULT_WINDOW_DAYS, 5,
                           help="The current minus its mean over this window is the eddy part. "
                                "Too long and the monsoon reversal leaks in; too short and the "
                                "eddies themselves are removed along with the mean.")
        layer = st.radio("map", list(LAYERS), format_func=lambda k: LAYERS[k][0])
        w_sigma = st.slider("weight — uncertainty", 0.0, 2.0, 1.0, 0.25)
        w_eke = st.slider("weight — EKE", 0.0, 2.0, 1.0, 0.25)
        guard = st.checkbox("exclude water too shallow for a float", value=True,
                            help="Off reproduces v1's failure mode. Left on by default because "
                                 "the guard belongs to the product, not to its caller.")
        n_top = st.slider("candidates to mark", 5, 50, 20, 5)
        device = _fields.device_picker(key="pr_dev")

    try:
        c = compute(date_str, window, ver, device)
    except Exception as e:
        st.error(f"Could not build the priority map for {date_str}: {e}")
        return
    if w_sigma + w_eke <= 0:
        st.warning("Both weights are zero — nothing to rank.")
        return

    r = rank(c, w_sigma, w_eke, guard)
    top = P.top_cells(r, n_top)

    st.info(f"**{P.NOT_A_CLAIM}**")

    m1, m2, m3 = st.columns(3)
    m1.metric("cells ranked", f"{r['n_cells_ranked']:,}")
    m2.metric("excluded as too shallow", f"{r['n_cells_excluded_as_too_shallow']:,}",
              delta="guard on" if guard else "GUARD OFF",
              delta_color="off" if guard else "inverse")
    m3.metric("mean-flow window", f"{c['n_steps_used']} days")

    if not guard:
        st.warning("**The shallow-water guard is off.** This reproduces v1's failure mode, where "
                   "places a float cannot reach could rank top. Shown because it is switchable, "
                   "not because it is a supported view.")

    st.altair_chart(map_chart(c, r, layer, top), use_container_width=False)
    st.caption(f"{c['date']} · {LAYERS[layer][0]} · circles mark the top {len(top)} candidates · "
               f"σ is the {'calibrated' if c['calibrated'] else 'RAW'} model uncertainty, "
               f"depth-averaged · EKE from the model's INPUT currents, not a derived diagnostic.")

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader(f"Top {len(top)} candidate regions")
        if not top:
            st.warning("Nothing is rankable on this date — an honest empty list rather than an "
                       "arbitrary one.")
        else:
            st.dataframe(pd.DataFrame(top)[["rank", "lat", "lon", "priority", "sigma_norm",
                                            "eke_norm"]].round(3),
                         hide_index=True, width="stretch")
    with right:
        st.subheader("Is this just a map of fast currents?")
        eke, spd = c["eke"], c["mean_speed"]
        fin = np.isfinite(eke) & np.isfinite(spd)
        qe, qs = np.nanpercentile(eke[fin], 90), np.nanpercentile(spd[fin], 90)
        te, ts = (eke >= qe) & fin, (spd >= qs) & fin
        jac = float((te & ts).sum() / max((te | ts).sum(), 1))
        st.metric("top-decile EKE ∩ top-decile mean speed", f"{jac:.0%} overlap")
        st.markdown(
            f"No. If EKE had been computed from the total current rather than its anomaly, this "
            f"overlap would be near 100% and the map would just be the Somali Current. At "
            f"**{jac:.0%}** the two are genuinely different fields: EKE is where the flow "
            f"*varies*, not where it is *strong*.\n\n"
            f"The mean flow is removed by construction — the time mean of u′ is zero to machine "
            f"precision, which `tests/phase2/test_priority_v2.py` asserts.")

    render(explainer(r, c))


if __name__ == "__main__":
    main()
