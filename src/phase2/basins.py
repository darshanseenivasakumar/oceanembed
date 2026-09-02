"""The canonical Arabian Sea / Bay of Bengal definition. One place, so two units cannot quote
two different figures for the same thing.

WHY THIS FILE EXISTS
--------------------
It was asked for. `docs/phase2/AGENT_SYNC.md` records the barrier-layer comparison coming out as
"BoB 9.5 vs Arabian 7.1 m" on one machine and "8.3 vs 4.6 m" on the other, and the diagnosis was
not a bug:

    "The gaps are box definitions, not disagreement. I used BoB 15-22N/85-95E and Arabian
     10-22N/60-72E ... Worth pinning the boxes in config/ if either number is going on a slide --
     otherwise we will quote two different figures for the same thing."

Those were small open-ocean SAMPLING boxes, chosen to sit clear of coasts for a physics check.
They are the right tool for that job and the wrong tool for this one: reporting model skill by
basin needs a PARTITION of the domain, not two islands in it. So this module defines full-basin
masks, and deliberately does not reuse the sampling boxes.

THE BOUNDARIES, AND WHY EACH ONE
--------------------------------
The two basins are separated by the Indian subcontinent north of about 8 N, so for most of the
domain the LAND MASK does the separating and no arbitrary line is involved. A meridian is only
needed south of India, where the two waters actually connect.

  Arabian Sea      ocean, lon <= 78.0 E, minus the Persian Gulf
      78 E sits just east of Kanyakumari (77.5 E), India's southern tip, so north of ~8 N this
      line is inside land anyway and does no work. South of India it follows the conventional
      limit of the Laccadive Sea.

  Bay of Bengal    ocean, 80.0 E <= lon <= 100.0 E
      80 E sits just west of Sri Lanka's west coast (79.7 E). The eastern limit at 100 E excludes
      the Malacca Strait and the Gulf of Thailand, which drain to the PACIFIC and are not part of
      this basin -- 439 ocean cells that a naive "everything east" rule would silently include.
      The Andaman Sea (92-100 E) IS included: it is Indian-Ocean-side, monsoon-driven, and the
      standard phrasing in this literature is "Bay of Bengal and Andaman Sea". Stated because it
      is a real choice, not an oversight.

  Unassigned       everything else, 887 ocean cells in total: the 78-80 E strip south of Sri
      Lanka (129, genuinely ambiguous water), the Persian Gulf (319), and east of 100 E (439).
      Measured on the real land mask, not estimated.

WHY THE PERSIAN GULF IS EXCLUDED RATHER THAN CALLED "ARABIAN SEA"
      It is a shallow hypersaline marginal sea. `src/phase2/cube/ocean_cube.py` records 26.00 N
      52.50 E holding water only to 30 m. Folding it into Arabian Sea skill would mix cells that
      have no deep water into depth-resolved statistics, and the deep levels would silently be
      averaging over a different population than the shallow ones.

NOTHING IS FORCED INTO A BASIN. A cell or a float that does not clearly belong is labelled
`unassigned` and reported as such. Per-basin numbers that do not sum to the overall count are
honest; a partition that hides its own leftovers is not.
"""
from __future__ import annotations

import numpy as np

from oceanembed import config

__all__ = ["ARABIAN_SEA", "BAY_OF_BENGAL", "UNASSIGNED", "NAMES", "BOUNDS",
           "grid_masks", "classify_points", "summary"]

ARABIAN_SEA = "arabian_sea"
BAY_OF_BENGAL = "bay_of_bengal"
UNASSIGNED = "unassigned"
NAMES = (ARABIAN_SEA, BAY_OF_BENGAL)

#: Meridian limits. See the module docstring for why each was chosen.
_AS_LON_MAX = 78.0
_BOB_LON_MIN = 80.0
_BOB_LON_MAX = 100.0

#: Persian Gulf, excluded from the Arabian Sea. The eastern limit is the Strait of Hormuz.
#: 56.5 E rather than a rounder 57.0: at 57.0 the box reaches past Hormuz into the GULF OF OMAN,
#: which is deep Arabian Sea water and belongs in the Arabian Sea. Real data caught this -- four
#: Argo profiles at 25.2 N / 56.9 E came back `unassigned` on the first run. At 56.5 E the box
#: still excludes the Persian Gulf proper (319 ocean cells) and strands no float.
_PG_LAT_MIN = 23.5
_PG_LON_MAX = 56.5

#: The same limits as machine-readable numbers, for the output record. `summary()` renders them
#: as prose for a human report; a record needs the values themselves, or a reader a year from now
#: cannot tell which partition a per-basin number was computed over. Both are built from the
#: constants above, so they cannot drift apart.
BOUNDS = {
    ARABIAN_SEA: {
        "rule": "ocean west of the meridian, minus the Persian Gulf",
        "lon_max": _AS_LON_MAX,
        "excludes_persian_gulf": {"lat_min": _PG_LAT_MIN, "lon_max": _PG_LON_MAX},
    },
    BAY_OF_BENGAL: {
        "rule": "ocean between the meridians; includes the Andaman Sea, excludes Malacca "
                "and the Gulf of Thailand",
        "lon_min": _BOB_LON_MIN,
        "lon_max": _BOB_LON_MAX,
    },
    UNASSIGNED: {
        "rule": "ocean belonging clearly to neither: the 78-80 E strip south of Sri Lanka, "
                "the Persian Gulf, and east of 100 E. Nothing is forced into a basin.",
    },
}


def _grids() -> tuple[np.ndarray, np.ndarray]:
    lat = np.asarray(config.LAT, dtype="float64")[:, None]
    lon = np.asarray(config.LON, dtype="float64")[None, :]
    return lat, lon


def _persian_gulf(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    return (lat >= _PG_LAT_MIN) & (lon <= _PG_LON_MAX)


def grid_masks(land_mask: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """Boolean masks on the frozen (N_LAT, N_LON) grid.

    `land_mask` is True over LAND (verified against 21 N 78 E = central India). Pass one to avoid
    re-reading the artifact; otherwise it is loaded from `artifacts/land_mask.npy`.

    The three masks are mutually exclusive and together cover every OCEAN cell exactly once.
    Both properties are asserted in `tests/phase2/test_basins.py` rather than assumed here.
    """
    if land_mask is None:
        land_mask = np.load(config.art("land_mask.npy"))
    land_mask = np.asarray(land_mask, dtype=bool)
    if land_mask.shape != (config.N_LAT, config.N_LON):
        raise ValueError(f"land_mask is {land_mask.shape}, expected "
                         f"{(config.N_LAT, config.N_LON)} -- wrong grid, refusing to guess")

    ocean = ~land_mask
    lat, lon = _grids()

    arabian = ocean & (lon <= _AS_LON_MAX) & ~_persian_gulf(lat, lon)
    bengal = ocean & (lon >= _BOB_LON_MIN) & (lon <= _BOB_LON_MAX)
    unassigned = ocean & ~arabian & ~bengal
    return {ARABIAN_SEA: arabian, BAY_OF_BENGAL: bengal, UNASSIGNED: unassigned}


def classify_points(lat, lon) -> np.ndarray:
    """Label observation points (Argo floats, say) by basin.

    Deliberately does NOT consult the land mask. A float reports from water by definition, but at
    0.25 deg a coastal profile can land in a cell the mask calls land; dropping real observations
    because of coastline resolution would bias the very coastal regions the Bay of Bengal story
    depends on. Only longitude decides, exactly as it does for the grid.

    Returns an array of `arabian_sea` / `bay_of_bengal` / `unassigned`, one per input point.
    """
    lat = np.asarray(lat, dtype="float64").ravel()
    lon = np.asarray(lon, dtype="float64").ravel()
    if lat.shape != lon.shape:
        raise ValueError(f"lat/lon length mismatch: {lat.shape} vs {lon.shape}")

    out = np.full(lat.shape, UNASSIGNED, dtype=object)
    in_pg = (lat >= _PG_LAT_MIN) & (lon <= _PG_LON_MAX)
    out[(lon <= _AS_LON_MAX) & ~in_pg] = ARABIAN_SEA
    out[(lon >= _BOB_LON_MIN) & (lon <= _BOB_LON_MAX)] = BAY_OF_BENGAL
    return out.astype(str)


def summary(land_mask: np.ndarray | None = None) -> dict:
    """Cell counts per basin, so a report can state how much ocean each number rests on."""
    m = grid_masks(land_mask)
    counts = {k: int(v.sum()) for k, v in m.items()}
    counts["ocean_total"] = sum(counts.values())
    counts["bounds"] = {
        ARABIAN_SEA: f"ocean, lon <= {_AS_LON_MAX} E, excluding the Persian Gulf "
                     f"(lat >= {_PG_LAT_MIN} N and lon <= {_PG_LON_MAX} E)",
        BAY_OF_BENGAL: f"ocean, {_BOB_LON_MIN} E <= lon <= {_BOB_LON_MAX} E "
                       f"(includes the Andaman Sea, excludes Malacca/Gulf of Thailand)",
        UNASSIGNED: "ocean that belongs clearly to neither: the 78-80 E strip south of Sri "
                    "Lanka, the Persian Gulf, and east of 100 E",
    }
    return counts
