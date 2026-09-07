"""Build every jury note. Run from JURY_NOTES/_build with the project venv."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

SLUGS = {
    1: "Feature_01_Phase1_App",
    2: "Feature_02_Collocation",
    3: "Feature_03_Validation_Lab",
    4: "Feature_04_Cube_3D",
    5: "Feature_05_Physics",
    6: "Feature_06_Events",
    7: "Feature_07_TSCast_v2",
    8: "Feature_08_Argo_Overlay",
    9: "Feature_09_Cyclone_Heat",
    10: "Feature_10_Transect",
    11: "Feature_11_Export_API",
    12: "Feature_12_Click_Map",
    13: "Feature_13_Uncertainty",
    14: "Feature_14_Acoustics",
    15: "Feature_15_Cloud_Dropout",
    16: "Feature_16_Priority_v2",
    17: "Feature_17_Cyclone_Case_Study",
}


def main() -> int:
    from common import feature_note
    import features_01_06, features_07_12, features_13_17

    written = []

    # 00 -- the demo walkthrough: what to click, in what order, and what to say
    try:
        import note_00_demo
        written.append(note_00_demo.build_note(
            os.path.join(OUT, "00_Demo_Walkthrough.pdf")))
    except ImportError:
        pass

    # 01 -- the problem statement note
    try:
        import note_01_problem
        written.append(note_01_problem.build_note(
            os.path.join(OUT, "01_Problem_Statement_and_Solution.pdf")))
    except ImportError:
        pass

    specs = features_01_06.SPECS + features_07_12.SPECS + features_13_17.SPECS
    assert len(specs) == 17, f"expected 17 feature specs, got {len(specs)}"
    assert [s["n"] for s in specs] == list(range(1, 18)), "feature numbers out of order"

    for spec in specs:
        n = spec["n"]
        path = os.path.join(OUT, f"{n + 1:02d}_{SLUGS[n]}.pdf")
        written.append(feature_note(path, spec))

    # 19 -- the closing note
    try:
        import note_19_conclusion
        written.append(note_19_conclusion.build_note(
            os.path.join(OUT, "19_Conclusion_Limitations_Viva.pdf")))
    except ImportError:
        pass

    import pymupdf
    total = 0
    for p in written:
        with pymupdf.open(p) as d:
            total += d.page_count
            print(f"  {d.page_count:>2} pp   {os.path.basename(p)}")
    print(f"\n{len(written)} PDFs, {total} pages total -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
