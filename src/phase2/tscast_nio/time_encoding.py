"""Day-of-year as an input the encoder can see. Owner: Unit B (Darshan), for the L1 leg of E-INV-00.

WHY THIS EXISTS
The shipped model receives no season signal at all. The decoder is `simple`, so the month index and
the 12-month climatology stack only feed the FiLM branch that is not used (D-013). What the encoder
sees is 11 days of seven surface fields plus three lat/lon channels -- nothing says "it is January".
A winter inversion under the Bay of Bengal's fresh lid is a seasonal object (Thadathil et al. 2016:
forms after the summer monsoon, fully developed in winter), so the cheapest physically motivated
lever is to let the model know the time of year.

HOW
Two constant channels, sin and cos of the angle 2*pi * (day_of_year - 1) / days_in_year, appended
to the geo channels exactly the way `dataset.geo_encoding` supplies lat/lon (Sinha & Abernathey
eq. 1). Using the calendar length of THAT year (365 or 366) rather than 365.25 makes the encoding
exactly continuous across Dec 31 -> Jan 1: the angle steps by one day, never by a fraction.

This module is numpy-only and torch-free so tests and the sampler can use it without the model.
"""
from __future__ import annotations

import numpy as np

#: How many input channels this encoding adds (sin, cos).
N_CHANNELS = 2


def doy_encoding(times) -> np.ndarray:
    """[sin, cos] of the day-of-year angle. One date -> shape (2,); N dates -> (N, 2). float32.

    `times` may be anything numpy can read as datetime64[D]: an ISO string, a datetime64, or an
    array of either.
    """
    t = np.asarray(times, dtype="datetime64[D]")
    scalar = t.ndim == 0
    t = np.atleast_1d(t)
    year_start = t.astype("datetime64[Y]").astype("datetime64[D]")
    next_year = (t.astype("datetime64[Y]") + 1).astype("datetime64[D]")
    doy0 = (t - year_start).astype("int64")                      # 0-based day of year
    n_days = (next_year - year_start).astype("int64")            # 365 or 366
    angle = 2.0 * np.pi * doy0.astype("float64") / n_days.astype("float64")
    out = np.stack([np.sin(angle), np.cos(angle)], axis=-1).astype("float32")
    return out[0] if scalar else out
